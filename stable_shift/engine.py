"""Stable Shift v2.11 — non-generative image restoration.

The reference supplies palette information only in Restore Quality. Structural analysis and optional V2 surface cleanup use the edited/denoised image. No Forge hooks.
"""
from __future__ import annotations
from dataclasses import dataclass
import os
os.environ.setdefault("OMP_NUM_THREADS","4")
import numpy as np
import cv2
from PIL import Image

@dataclass
class Options:
    method: str='CPU BM3D'  # Explicit CPU/GPU BM3D, V2 surface-only, or legacy methods
    blotch_strength: float=0.0
    source_guard: bool=True
    faint_continuity: bool=False
    auto_strength: bool=False
    cleanup: float=0.0
    cleanup_range: float=12.0
    cleanup_luma: float=60.0
    cleanup_radius: int=16
    noise: float=55.0
    color_noise: float=55.0
    hard_guard: float=95.0
    soft_guard: float=60.0
    shade_threshold: float=35.0 # sensitivity to tonal transitions
    color_match: bool=True
    color_method: str='Classic'
    antialias_strength: float=0.0
    stroke_strength: float=0.0
    # keep user changes in Preserve Edit as well
    edit_sensitivity: float=23.0


def array(img:Image.Image)->np.ndarray:
    return np.asarray(img.convert('RGB'),np.uint8)

def _lab(rgb):
    return cv2.cvtColor(rgb.astype(np.float32)/255.0,cv2.COLOR_RGB2LAB)

def _smooth(a,b,x):
    t=np.clip((x-a)/max(b-a,1e-5),0,1)
    return t*t*(3-2*t)

def _gradient(lab,sigma):
    if sigma:
        lab=cv2.GaussianBlur(lab,(0,0),sigma,borderType=cv2.BORDER_REFLECT)
    mags=[]
    for c,scale in ((0,1.),(1,1.10),(2,1.10)):
        gx=cv2.Scharr(lab[:,:,c],cv2.CV_32F,1,0)
        gy=cv2.Scharr(lab[:,:,c],cv2.CV_32F,0,1)
        mags.append(cv2.magnitude(gx,gy)*scale)
    return np.maximum.reduce(mags)

def structure_maps(edited:Image.Image, reference:Image.Image|None=None,
                   shade_threshold:float=35.0)->dict[str,np.ndarray]:
    """Strong contours and soft shading boundaries as *separate* maps.

    All edge guides are inferred locally from the edited image and scaled reference.
    Hard boundary confidence restricts direct smoothing within diffusion.
    """
    im=array(edited); ref=None if reference is None else array(reference)
    h,w=im.shape[:2]
    if ref is not None and ref.shape!=im.shape:raise ValueError('Internal error: the reference was not aligned to the edited dimensions.')
    x=_lab(im)
    g0=_gradient(x,0.65)
    g1=_gradient(x,1.55)
    g2=_gradient(x,3.00)
    # Robust within-image scaling: Scharr operates on LAB, whose raw magnitude
    # depends heavily on scale and image content. Fixed cutoffs would mark
    # practically EVERY pixel in a textured image as an edge.
    threshold=float(np.clip(shade_threshold,0,100))
    def grad_weight(m, lowpct, highpct, floor=2.):
        sample=m[::4,::4]
        lo=max(floor,float(np.percentile(sample,lowpct)))
        hi=max(lo+floor,float(np.percentile(sample,highpct)))
        return _smooth(lo,hi,m)
    hard=np.maximum(grad_weight(g0,87,99.4),grad_weight(g1,88,99.0)*.91)
    sp=68-threshold*.14  # more shading sensitivity: more low-contrast lines
    soft=np.maximum(grad_weight(g1,sp,95),grad_weight(g2,sp-5,93))
    if ref is not None:
        r=_lab(ref)
        r0=_gradient(r,0.65);r1=_gradient(r,1.55);r2=_gradient(r,3.0)
        near=cv2.dilate(grad_weight(r0,87,99.4),np.ones((5,5),np.uint8))
        # Corroborating references reinforce boundaries but shouldn't turn
        # every slight brushstroke into a hard anti-denoising constraint.
        hard=np.maximum(hard,np.minimum(near,hard*.87+.10))
        soft=np.maximum(soft,np.minimum(grad_weight(r1,sp,95),soft*.87+.08))
        soft=np.maximum(soft,np.minimum(grad_weight(r2,sp-5,93),soft*.87+.06))
    # Do not make tiny isolated grain a hard boundary. Preserve coherent lines.
    e=np.uint8(hard>.50)*255
    n,lab,stats,_=cv2.connectedComponentsWithStats(e,8)
    small=(stats[:,cv2.CC_STAT_AREA]<4)
    small[0]=False
    hard[small[lab]]*=.15
    hard=np.clip(hard,0,1).astype(np.float32)
    soft=np.clip(np.maximum(soft,hard),0,1).astype(np.float32)
    # Distance to hard boundary is useful when tuning flat-region smoothing.
    boundary=np.uint8(hard>.55)
    distance=cv2.distanceTransform(1-boundary,cv2.DIST_L2,3)
    return {'hard':hard,'soft':soft,'distance':distance.astype(np.float32),
            'guide':np.uint8(np.clip(soft*.55+hard*.45,0,1)*255)}


def _nlm(rgb, noise, color_noise):
    # Reference OpenCV patch-based NLM; make settings reasonable for 2K drawings.
    h=max(0.1,1.0+float(noise)*.18); hc=max(.1,1.0+float(color_noise)*.20)
    src=cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR)
    return cv2.cvtColor(cv2.fastNlMeansDenoisingColored(src,None,h,hc,7,21),cv2.COLOR_BGR2RGB)


def _boundary_constrained_diffusion(rgb, clean, maps, noise, color_noise, hard_guard, soft_guard):
    """Discrete anisotropic diffusion with hard/soft line barriers INSIDE its flux.

    Unlike the BM3D/NLM paths, no unconditional full-image denoiser runs first.
    Each exchange of pixel values is weighted by original/ref color boundaries and
    by coherent line/shading confidence; there is no final edge-blend rescue step.
    This is experimental, not a drop-in reimplementation of BM3D or NLM.
    """
    # LAB is useful here so that chroma smoothing can be stronger than luminance.
    source = _lab(rgb).astype(np.float32)
    x = source.copy()
    guide = cv2.GaussianBlur(source, (0, 0), 1.2, borderType=cv2.BORDER_REFLECT)
    if clean is not None:
        ref_guide = cv2.GaussianBlur(_lab(clean), (0, 0), 1.0, borderType=cv2.BORDER_REFLECT)
        # Reference and edited are often differently colored globally; gradient
        # magnitudes are the relevant evidence, not the absolute color offset.
    else:
        ref_guide = None
    hard = maps['hard']
    soft = maps['soft']
    hg = float(np.clip(hard_guard / 100, 0, 1))
    sg = float(np.clip(soft_guard / 100, 0, 1))
    def barriers(axis):
        if axis == 1:
            delta = guide[:, 1:, :] - guide[:, :-1, :]
            ha = np.maximum(hard[:, 1:], hard[:, :-1])
            sa = np.maximum(soft[:, 1:], soft[:, :-1])
            if ref_guide is not None:
                delta_ref = ref_guide[:, 1:, :] - ref_guide[:, :-1, :]
        else:
            delta = guide[1:, :, :] - guide[:-1, :, :]
            ha = np.maximum(hard[1:, :], hard[:-1, :])
            sa = np.maximum(soft[1:, :], soft[:-1, :])
            if ref_guide is not None:
                delta_ref = ref_guide[1:, :, :] - ref_guide[:-1, :, :]
        # Chroma and luminance differences both count as a boundary.
        mag = np.sqrt(delta[..., 0] ** 2 + 0.65*(delta[..., 1]**2 + delta[..., 2]**2))
        if ref_guide is not None:
            refmag = np.sqrt(delta_ref[..., 0] ** 2 + 0.65*(delta_ref[..., 1]**2 + delta_ref[..., 2]**2))
            mag = np.maximum(mag, refmag * 0.75)
        # Reject transfers across edges BEFORE averaging anything.
        w = np.exp(-np.square(mag / 6.5)).astype(np.float32)
        w *= 1.0 - hg * ha
        w *= 1.0 - sg * 0.78 * sa
        # Very confident hard outlines are impermeable at full protection.
        if hg >= .999:
            w[ha > .88] = 0
        return np.clip(w, 0, 1)
    wh=barriers(1)
    wv=barriers(0)
    iterations=round(5+22*max(float(noise),float(color_noise))/100.)
    strength=np.float32([.225*noise/100.,.225*color_noise/100.,.225*color_noise/100.])
    # Flux is bounded by the 4-neighbor stability constraint, so repeated steps
    # converge to region-wise averages without ordinary Gaussian cross-edge bleed.
    for _ in range(iterations):
        update=np.zeros_like(x)
        fh=(x[:,1:]-x[:,:-1])*wh[:,:,None]
        fv=(x[1:]-x[:-1])*wv[:,:,None]
        update[:,:-1]+=fh
        update[:,1:]-=fh
        update[:-1]+=fv
        update[1:]-=fv
        x += update*strength
    out = cv2.cvtColor(x,cv2.COLOR_LAB2RGB)
    return np.uint8(np.clip(out*255+.5,0,255))


def _bm3d(rgb, noise, color_noise):
    try:from bm3d import bm3d
    except ImportError as e:raise RuntimeError('Optional BM3D is not installed. In the app virtual environment run: pip install bm3d. Note that its published license is non-commercial.') from e
    # BM3D normally assumes additive (approximately stationary) Gaussian noise.
    # Keeping it a separate candidate rather than pretending diffusion noise is Gaussian.
    lab=_lab(rgb)
    l=lab[:,:,0]/100.
    ab=(lab[:,:,1:3]+128.)/255.
    sigma_l=.005+noise/100.*.075
    sigma_c=.005+color_noise/100.*.085
    channels=[bm3d(l,sigma_psd=sigma_l)]
    for c in range(2):channels.append(bm3d(ab[:,:,c],sigma_psd=sigma_c))
    back=np.stack((channels[0]*100,channels[1]*255-128,channels[2]*255-128),axis=-1).astype(np.float32)
    return np.uint8(np.clip(cv2.cvtColor(back,cv2.COLOR_LAB2RGB)*255+0.5,0,255))


def _palette(clean, restored):
    # Reuse v0.8's tested LAB global matcher; no denoising or edit mode here.
    from .difference_guard_core import Settings, restore
    im,_=restore(clean,Image.fromarray(restored),Settings(mode='global',chroma_strength=1,
        brightness_strength=1,max_lab_change=90,auto_protect=False),diagnostics=False)
    return array(im)


def correct_palette(clean, local_rgb, rgb, opts):
    """Finish one fixed cleanup result; Classic retains its exact V2.8 path."""
    report={'requested_method':opts.color_method,'selected_method':'Off'}
    if not opts.color_match:
        return rgb,report
    if opts.blotch_strength>0:
        from .frozen_palette import freeze_palette
        classic_rgb=freeze_palette(clean,local_rgb).apply(rgb)
    else:
        classic_rgb=_palette(clean,rgb)
    if opts.color_method=='Robust global':
        from .global_color import apply_global_palette
        _,corrected,report=apply_global_palette(clean,local_rgb,rgb,classic_rgb)
        return corrected,report
    report['selected_method']='Classic'
    return classic_rgb,report


def _denoise_candidate(raw, opts, maps):
    """Unchanged backend result, before legacy blending and source copy-back."""
    if opts.method=='NLM':
        candidate=_nlm(raw,opts.noise,opts.color_noise)
    elif opts.method=='Boundary constrained':
        candidate=_boundary_constrained_diffusion(raw,None,maps,
            opts.noise,opts.color_noise,opts.hard_guard,opts.soft_guard)
    elif opts.method in ('CPU BM3D','BM3D (optional)'):
        candidate=_bm3d(raw,opts.noise,opts.color_noise)
    elif opts.method=='GPU BM3D':
        candidate=_gpu_bm3d(raw,opts.noise,opts.color_noise)
    elif opts.method in ('Color only','Region cleanup only'):
        candidate=raw.copy()
    else:
        raise ValueError(f'Unknown method {opts.method}')
    return candidate


def _restore_quality_base(clean:Image.Image, edited:Image.Image, opts:Options, diagnostics=True, maps=None, source_core=None, denoised_candidate=None):
    raw=array(edited)
    # Reference geometry never guides restoration. Palette matching alone uses
    # the clean image; output dimensions always follow the edited image.
    if maps is None:maps=structure_maps(edited,None,opts.shade_threshold)
    if denoised_candidate is None:
        candidate=_denoise_candidate(raw,opts,maps)
    else:
        if opts.method not in ('NLM','Boundary constrained','CPU BM3D','BM3D (optional)',
                                'GPU BM3D','Color only','Region cleanup only'):
            raise ValueError(f'Unknown method {opts.method}')
        candidate=np.asarray(denoised_candidate)
        if candidate.shape!=raw.shape or candidate.dtype!=np.uint8:
            raise ValueError('Shared denoiser result must match the edited RGB dimensions and uint8 type.')
        # Each comparison applies its own masks. Never let source copy-back in
        # one variant mutate the shared, unguarded backend result.
        candidate=candidate.copy()
    candidate_snapshot=candidate.copy() if diagnostics else None
    if opts.method in ('Boundary constrained','Color only','Region cleanup only'):
        # Internal barrier already controlled smoothing. Do NOT blend in source
        # pixels afterward, which would undo the user's requested behavior.
        result=candidate
        maps['guard']=np.maximum(maps['hard']*opts.hard_guard/100,
                                 maps['soft']*opts.soft_guard/100)
    else:
        # Legacy denoisers do not accept boundary masks internally; guard here
        # is a visibly documented fallback, NOT boundary-constrained inference.
        hard=maps['hard']*np.clip(opts.hard_guard/100,0,1)
        soft=maps['soft']*np.clip(opts.soft_guard/100,0,1)
        guard=np.maximum(hard,soft*.63)
        guard=np.clip(guard,0,1)
        guard[(maps['hard']>.94)&(opts.hard_guard>=99)]=1
        result=np.uint8(np.clip(candidate.astype(np.float32)*(1-guard[:,:,None])+
                  raw.astype(np.float32)*guard[:,:,None]+.5,0,255))
        maps['guard']=guard
    if source_core is not None:
        # BM3D itself has no custom-mask API. Preserve only traced source cores
        # at this handoff; downstream cleanup receives the SAME original mask.
        result[source_core] = raw[source_core]
    if diagnostics:
        maps['unprotected_denoise_signed_rgb']=candidate_snapshot.astype(np.int16)-raw.astype(np.int16)
        maps['unprotected_denoise_change']=np.mean(np.abs(maps['unprotected_denoise_signed_rgb'].astype(np.float32)),axis=2)/16
        maps['guard_signed_rgb']=result.astype(np.int16)-candidate_snapshot.astype(np.int16)
        maps['guard_change']=np.mean(np.abs(maps['guard_signed_rgb'].astype(np.float32)),axis=2)/16
    if opts.color_match:
        # The shared LAB color engine already supports differing source sizes.
        result=_palette(clean,result)
    if diagnostics:
        maps['difference']=np.mean(np.abs(result.astype(np.float32)-raw.astype(np.float32)),axis=2)/70
    return Image.fromarray(result,'RGB'),maps


def preserve_edits(clean:Image.Image,edited:Image.Image,opts:Options):
    """Legacy precise multi-map preservation, for maintaining an unbroken baseline."""
    if clean.size != edited.size:
        raise ValueError('Preserve Edits requires the reference and edited image to have the same dimensions and registration. Restore Quality supports different sizes.')
    from .difference_guard_core import Settings,restore
    out,maps=restore(clean,edited,Settings(mode='composite_precise',auto_protect=True,
        protect_strength=1.0,difference_threshold=opts.edit_sensitivity,
        feather_pixels=2,work_limit=1280),diagnostics=True)
    return out,maps


def heatmap(map_arr):
    arr=np.uint8(np.clip(map_arr,0,1)*255)
    return Image.fromarray(cv2.cvtColor(cv2.applyColorMap(arr,cv2.COLORMAP_TURBO),cv2.COLOR_BGR2RGB))


def _gpu_bm3d(rgb, noise, color_noise):
    try:
        import cupy as cp
        from bm3d_cupy import bm3d_gpu
        cp.cuda.runtime.getDeviceCount()
        lab=_lab(rgb)
        planes=[lab[:,:,0]/100.,(lab[:,:,1]+128.)/255.,(lab[:,:,2]+128.)/255.]
        sigmas=[.005+noise/100.*.075]+[.005+color_noise/100.*.085]*2
        restored=[]
        for plane,sigma in zip(planes,sigmas):
            value=bm3d_gpu(cp.asarray(plane,dtype=cp.float32),cp.asarray(sigma,dtype=cp.float32))
            restored.append(cp.asnumpy(value))
        cp.cuda.get_current_stream().synchronize()
        back=np.stack((restored[0]*100,restored[1]*255-128,restored[2]*255-128),axis=-1).astype(np.float32)
        return np.uint8(np.clip(cv2.cvtColor(back,cv2.COLOR_LAB2RGB)*255+.5,0,255))
    except Exception as exc:
        raise RuntimeError('GPU BM3D could not run. No CPU fallback was performed. Select CPU BM3D or inspect GPU installation/driver compatibility. Details: '+str(exc)) from exc


def restore_quality(clean, edited, opts, diagnostics=True, progress=None, *, denoised_candidate=None):
    from time import perf_counter
    from dataclasses import replace, asdict
    from .region_cleanup import surface_cleanup, RegionOptions
    from .line_protection import trace_source_lines
    from .stage_maps import stage_diagnostics
    from .surface_normalization import normalize_surfaces
    from .antialias import antialias,validate_strength
    from .stroke_cleanup import clean_strokes,validate_strength as validate_stroke
    from .global_color import METHODS
    import math
    if opts.color_method not in METHODS:
        raise ValueError('Unknown color method: '+str(opts.color_method))
    validate_strength(opts.antialias_strength)
    validate_stroke(opts.stroke_strength)
    if opts.auto_strength and denoised_candidate is not None:
        raise ValueError('Automatic strength requires a backend run at its estimated settings; a manual cached candidate cannot be reused.')
    if not math.isfinite(opts.blotch_strength) or not 0 <= opts.blotch_strength <= 100:
        raise ValueError('Broad correction maximum must be between 0 and 100.')
    start=perf_counter()
    region_options=RegionOptions(opts.cleanup, opts.cleanup_range, opts.cleanup_luma, opts.cleanup_radius).validated()
    if progress:progress('Original image: structure analysis and line tracing')
    original=array(edited)
    maps=structure_maps(edited,None,opts.shade_threshold)
    source_core=None
    if opts.source_guard:
        source_maps=trace_source_lines(original,maps,continue_faint=opts.faint_continuity)
        source_core=source_maps['source_line_core']>.5
        maps.update(source_maps)
    effective=opts
    auto_maps={}
    auto_report={'enabled':False}
    if opts.auto_strength:
        from .automatic_strength import estimate_strength,limit_cleanup
        if progress:progress('Automatic strength: measuring native and correlated multiscale scatter')
        effective,auto_maps,auto_report=estimate_strength(original,opts,source_core)
        maps.update(auto_maps)
    analyzed=perf_counter()
    if progress:
        progress('Fine denoising skipped: '+auto_report['backend_skip_reason']
                 if auto_report.get('backend_skipped') else 'Denoising: '+opts.method)
    candidate=original if auto_report.get('backend_skipped',False) else denoised_candidate
    out,maps=_restore_quality_base(clean,edited,replace(effective,color_match=False),diagnostics=diagnostics,
                                  maps=maps,source_core=source_core,denoised_candidate=candidate)
    if opts.auto_strength:
        handoff=array(out)
        limited=limit_cleanup(original,handoff,auto_maps['auto_denoise_luminance_strength'],
                              auto_maps['auto_denoise_chroma_strength'],source_core)
        if diagnostics:
            signed=limited.astype(np.int16)-handoff.astype(np.int16)
            maps['auto_denoise_limit_signed_rgb']=signed
            maps['auto_denoise_limit_change']=np.mean(np.abs(signed.astype(np.float32)),axis=2)/16
        auto_report['actual_denoise_mean_rgb_change']=float(np.mean(np.abs(limited.astype(np.float32)-original)))
        out=Image.fromarray(limited)
    denoised=perf_counter()
    denoised_rgb=array(out)
    if opts.auto_strength:region_options=RegionOptions(effective.cleanup, opts.cleanup_range, opts.cleanup_luma, opts.cleanup_radius).validated()
    rgb,region_maps,region_report=surface_cleanup(denoised_rgb,region_options,diagnostics,progress,
                                                protected=source_core)
    if opts.auto_strength:
        candidate_stats=region_report.copy()
        rgb=limit_cleanup(denoised_rgb,rgb,auto_maps['auto_luminance_strength'],auto_maps['auto_chroma_strength'],source_core)
        actual=rgb.astype(np.int16)-denoised_rgb.astype(np.int16)
        region_report.update({'candidate_mean_rgb_change':candidate_stats['mean_rgb_change'],
            'changed_pixels_percent':float(100*np.mean(np.any(actual!=0,axis=2))),
            'mean_rgb_change':float(np.mean(np.abs(actual.astype(np.float32)))),
            'automatic_limits_applied':True})
        if diagnostics:region_maps['v2_changed']=np.mean(np.abs(actual.astype(np.float32)),axis=2)/12
    maps.update(region_maps)
    local_rgb=rgb
    rgb,blotch_maps,blotch_report=normalize_surfaces(rgb,effective.blotch_strength,opts.cleanup_range,
        opts.cleanup_luma,source_core,diagnostics,progress)
    if opts.auto_strength:
        candidate_stats=blotch_report.copy()
        rgb=limit_cleanup(local_rgb,rgb,auto_maps['auto_luminance_strength'],auto_maps['auto_chroma_strength'],source_core)
        actual=rgb.astype(np.int16)-local_rgb.astype(np.int16)
        blotch_report.update({'candidate_mean_rgb_change':candidate_stats['mean_rgb_change'],
            'changed_pixels_percent':float(100*np.mean(np.any(actual!=0,axis=2))),
            'mean_rgb_change':float(np.mean(np.abs(actual.astype(np.float32)))),
            'automatic_limits_applied':True})
        if diagnostics:
            blotch_maps['blotch_signed_rgb']=actual
            blotch_maps['blotch_change']=np.mean(np.abs(actual.astype(np.float32)),axis=2)/16
    maps.update(blotch_maps)
    if diagnostics:
        local_signed=local_rgb.astype(np.int16)-denoised_rgb.astype(np.int16)
        maps['local_cleanup_signed_rgb']=local_signed
        maps['local_cleanup_change']=np.mean(np.abs(local_signed.astype(np.float32)),axis=2)/16
    cleaned=perf_counter()
    if progress:progress('Reference color correction' if opts.color_match else 'Finishing')
    cleanup_rgb=rgb
    rgb,color_report=correct_palette(clean,local_rgb,rgb,opts)
    colored=perf_counter()
    palette_rgb=rgb
    rgb,stroke_maps,stroke_report=clean_strokes(rgb,opts.stroke_strength,source_core,diagnostics,progress)
    maps.update(stroke_maps)
    stroked=perf_counter()
    stroke_rgb=rgb
    if progress and opts.antialias_strength>0:progress('Optional edge antialiasing')
    rgb=antialias(rgb,opts.antialias_strength)
    finished=perf_counter()
    if diagnostics:
        maps.update(stage_diagnostics(original,denoised_rgb,cleanup_rgb,rgb,colored=palette_rgb,stroked=stroke_rgb))
    diagnostics_finished=perf_counter()
    maps['report']={'version':'2.11','backend':opts.method,'resolution':list(edited.size),
        'source_analysis_seconds':analyzed-start,'denoise_seconds':denoised-analyzed,
        'cleanup_seconds':cleaned-denoised,'color_seconds':colored-cleaned,
        'stroke_seconds':stroked-colored,'antialias_seconds':finished-stroked,
        'diagnostics_seconds':diagnostics_finished-finished,'total_seconds':diagnostics_finished-start,
        'source_protected_pixels_percent':0. if source_core is None else float(100*np.mean(source_core)),
        'faint_continuity':opts.faint_continuity,
        'rescued_trace_pixels':int(np.count_nonzero(maps.get('source_line_rescued',np.zeros((0,0))))),
        'denoiser_reused':denoised_candidate is not None,
        'automatic_strength':auto_report,'effective_options':asdict(effective),
        'cleanup_strength':opts.cleanup,'color_match':opts.color_match,'options':asdict(opts),
        'region_cleanup':region_report,'broad_normalization':blotch_report,
        'color_correction':color_report,
        'stroke_cleanup':stroke_report,
        'palette_note':'Fitted to local-cleanup baseline; not refitted after broad correction. Classic retains the V2.8 path.',
        'antialias_note':'Optional final edge filtering; source-core RGB protection applies before color/strokes/AA.',
        'difference_note':'Total change includes palette correction; it is not a noise map.'}
    return Image.fromarray(rgb),maps
