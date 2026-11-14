"""Difference Guard: reference-aware, non-generative color restoration.

Backend deliberately has no GUI or Forge dependencies so it can later be reused
inside a Forge Neo always-visible script, post-process hook, or standalone tool.

The reference is the cleaner image, the edited image is the one whose intentional
new content must remain. No VLM or diffusion is invoked.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np
from PIL import Image


@dataclass
class Settings:
    mode: str = "local"  # local, global, composite, composite_precise
    chroma_strength: float = 0.70  # 0..1
    brightness_strength: float = 0.45  # 0..1
    blur_percent: float = 2.5  # local shading scale relative to short side
    max_lab_change: float = 28.0  # cap per LAB channel (LAB L is 0..100)
    difference_threshold: float = 23.0  # DeltaE76 at work resolution
    auto_protect: bool = True
    protect_strength: float = 1.0  # 0..1
    feather_pixels: float = 6.0  # at source resolution; transition for masks
    work_limit: int = 1280

    def validated(self) -> "Settings":
        from dataclasses import replace
        mode = self.mode.lower()
        if mode not in ("local", "global", "composite", "composite_precise"):
            raise ValueError("Unknown mode. Choose local, global, composite, or composite_precise.")
        return replace(self,
            mode=mode,
            chroma_strength=float(np.clip(self.chroma_strength, 0, 1)),
            brightness_strength=float(np.clip(self.brightness_strength, 0, 1)),
            blur_percent=float(np.clip(self.blur_percent, 0.2, 12)),
            max_lab_change=float(np.clip(self.max_lab_change, 0, 90)),
            difference_threshold=float(np.clip(self.difference_threshold, 3, 90)),
            protect_strength=float(np.clip(self.protect_strength, 0, 1)),
            feather_pixels=float(np.clip(self.feather_pixels, 0, 100)),
            work_limit=int(np.clip(self.work_limit, 256, 2048)),
        )


def _resize_rgb(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    rgb = image.convert('RGB')
    if rgb.size != size:
        rgb = rgb.resize(size, Image.Resampling.LANCZOS)
    return rgb


def _to_lab(rgb: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(rgb.astype(np.float32) / 255.0, cv2.COLOR_RGB2LAB)


def _from_lab(lab: np.ndarray) -> np.ndarray:
    rgb = cv2.cvtColor(lab.astype(np.float32), cv2.COLOR_LAB2RGB)
    return (np.clip(rgb, 0, 1) * 255.0 + 0.5).astype(np.uint8)


def _softstep(edge0: float, edge1: float, x: np.ndarray) -> np.ndarray:
    t = np.clip((x - edge0) / max(edge1 - edge0, 1e-5), 0.0, 1.0)
    return t*t*(3.0-2.0*t)


def _coarse_inputs(reference: Image.Image, edited: Image.Image, limit: int):
    w,h=edited.size
    scale=min(1.0,limit/max(w,h))
    sw=max(16,round(w*scale)); sh=max(16,round(h*scale))
    target=(sw,sh)
    ref=np.asarray(_resize_rgb(reference, target), dtype=np.uint8)
    edt=np.asarray(_resize_rgb(edited, target), dtype=np.uint8)
    return ref,edt


def _detect_changes(ref: np.ndarray, edt: np.ndarray, lab_ref: np.ndarray,
                    lab_edt: np.ndarray, threshold: float) -> tuple[np.ndarray,np.ndarray,np.ndarray]:
    """Estimate edited regions conservatively. Not a semantic edit detector.

    Returns soft edited mask, DeltaE map, structural novelty map.
    """
    h,w=ref.shape[:2]
    de=np.linalg.norm(lab_ref-lab_edt,axis=2)
    # New object colors usually differ far more than gentle repeated-pass drift.
    vivid=_softstep(threshold, threshold+18.0,cv2.GaussianBlur(de,(0,0),1.2))

    # Structural novelty: edges in either frame that have no corresponding edge
    # nearby in the other. Robust to small edge shifts and global color casts.
    g0=cv2.cvtColor(ref,cv2.COLOR_RGB2GRAY)
    g1=cv2.cvtColor(edt,cv2.COLOR_RGB2GRAY)
    e0=cv2.Canny(g0,60,140)
    e1=cv2.Canny(g1,60,140)
    r=max(2,round(min(h,w)/180))
    k=cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(2*r+1,2*r+1))
    n0=(e0>0)&(cv2.dilate(e1,k)==0)
    n1=(e1>0)&(cv2.dilate(e0,k)==0)
    novelty=(n0|n1).astype(np.uint8)*255
    n=cv2.GaussianBlur(cv2.dilate(novelty,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(7,7))),(0,0),2.0)/255.0
    # Tiny regions changed only by noise shouldn't become protected objects.
    # Base protection mainly on genuine substantial color change. Edge novelty
    # slightly boosts boundaries, but by itself must not turn into a cutout.
    changed=np.maximum(vivid, _softstep(threshold*0.55, threshold+8.0,de)*n*0.8)
    # Smooth transitions; only for the mask, never blur the actual image texture.
    changed=cv2.GaussianBlur(changed.astype(np.float32),(0,0),max(1.0,min(h,w)*0.004))
    # For substantial newly added objects (e.g. woven hats), the texture can
    # create holes in a pixelwise color-difference mask. Fill enclosed holes
    # within large coherent candidate regions so denoising does not erase the
    # interiors of the objects. Keep each object's *actual outline*, never a
    # rectangular bounding box. Tiny speckle candidates are intentionally not
    # expanded into protected regions.
    binary=np.uint8(changed>0.42)*255
    radius=max(2,round(min(h,w)/150))
    kernel=cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(radius*2+1,radius*2+1))
    closed=cv2.morphologyEx(binary,cv2.MORPH_CLOSE,kernel)
    count,labels,stats,_=cv2.connectedComponentsWithStats(closed,8)
    min_area=max(80,round(h*w*.00008))
    substantial=np.zeros((h,w),np.uint8)
    for i in range(1,count):
        if min_area<=stats[i,cv2.CC_STAT_AREA]<=h*w*.16:
            component=np.uint8(labels==i)*255
            contours,_=cv2.findContours(component,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
            cv2.drawContours(substantial,contours,-1,255,thickness=cv2.FILLED)
    substantial=cv2.dilate(substantial,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(7,7)))
    substantial=cv2.GaussianBlur(substantial.astype(np.float32)/255,(0,0),1.3)
    changed=np.maximum(changed,substantial)
    return np.clip(changed,0,1),de,n.astype(np.float32)


def _prepare_mask(mask: Optional[Image.Image],size:tuple[int,int],worksize:tuple[int,int]):
    if mask is None:
        return np.zeros((worksize[1],worksize[0]),np.float32)
    arr=np.asarray(mask.convert('L').resize(worksize,Image.Resampling.BILINEAR),np.float32)/255.0
    return np.clip(arr,0,1)


def _calc_fields(reference:Image.Image,edited:Image.Image,s:Settings,manual_mask:Optional[Image.Image]):
    re,ed=_coarse_inputs(reference,edited,s.work_limit)
    rlab,elab=_to_lab(re),_to_lab(ed)
    h,w=ed.shape[:2]
    detected,de,novelty=_detect_changes(re,ed,rlab,elab,s.difference_threshold)
    manual=_prepare_mask(manual_mask,edited.size,(w,h))
    combined=np.maximum(manual,detected*s.protect_strength if s.auto_protect else manual)
    # Force manually protected pixels to survive even at low auto strength.
    combined=np.maximum(manual,combined)
    sigma=max(0.4,s.feather_pixels*min(w/edited.width,h/edited.height))
    if sigma>0.5:
        combined=cv2.GaussianBlur(combined.astype(np.float32),(0,0),sigma)
    combined=np.clip(combined,0,1)
    if s.mode == 'global':
        # Robustly estimate a global shift even when lighting changes a lot.
        # An absolute DeltaE threshold incorrectly rejected all pixels in
        # strongly brightened/darkened versions. Instead estimate the shift
        # from correspondences, then filter on residual disagreement.
        eligible=combined<0.2
        if np.count_nonzero(eligible)<100:
            eligible=np.ones((h,w),dtype=bool)
        shifts=rlab-elab
        guess=np.median(shifts[eligible],axis=0).astype(np.float32)
        residual=np.linalg.norm(shifts-guess[None,None,:],axis=2)
        cutoff=max(8.0,float(np.percentile(residual[eligible],65)))
        weight=eligible&(residual <= cutoff)
        if np.count_nonzero(weight)<100:
            weight=eligible
        a=rlab[weight];b=elab[weight]
        offset=np.median(a-b,axis=0).astype(np.float32)
        gain=np.ones(3,np.float32)
        for c in range(3):
            range_cur=max(1.0,float(np.percentile(b[:,c],75)-np.percentile(b[:,c],25)))
            range_ref=max(1.0,float(np.percentile(a[:,c],75)-np.percentile(a[:,c],25)))
            gain[c]=np.clip(range_ref/range_cur,0.60,1.65)
        correction=np.broadcast_to(offset,(h,w,3)).copy()
        mid=np.median(b,axis=0)
        correction+=(elab-mid)*(gain-1.0)*0.90
    else:
        # Local low-frequency LAB field: direct restoration of local color and
        # lightness without replacing high-frequency details of the edited result.
        sigma=max(0.5,min(h,w)*s.blur_percent/100.0)
        rlow=cv2.GaussianBlur(rlab,(0,0),sigma)
        elow=cv2.GaussianBlur(elab,(0,0),sigma)
        correction=rlow-elow
    correction[:,:,0]*=s.brightness_strength
    correction[:,:,1:3]*=s.chroma_strength
    correction=np.clip(correction,-s.max_lab_change,s.max_lab_change)
    correction*= (1.0-combined[:,:,None])
    return correction,combined,de,novelty


def restore(reference:Image.Image, edited:Image.Image, settings:Settings|None=None,
            protected_mask:Image.Image|None=None, diagnostics:bool=True, denoise_settings=None):
    """Return (restored PIL image, diagnostics dict). Purely CPU / non-generative.

    protected_mask white=retain edited pixels, black=allow restoring. A mask is
    strongly recommended in composite mode; automatic inferred regions are not
    guaranteed to preserve new objects.
    """
    if reference is None or edited is None:
        raise ValueError('Both a clean reference and an edited image are required.')
    s=(settings or Settings()).validated()
    source_target=edited.convert('RGB')
    target=source_target
    w,h=target.size
    ref=_resize_rgb(reference,(w,h))
    # v0.6 new multiscale methods denoise the RAW edited image first,
    # then apply the palette correction once to the reconstructed result.
    # Legacy v0.5 methods retain their previous processing order for comparison.
    pre_denoise_diag={}
    already_denoised=False
    if (s.mode=='global' and denoise_settings is not None
            and denoise_settings.mode!='off'
            and denoise_settings.method in ('multiscale_nlm','multiscale_wavelet','pyramid_nlm','pyramid_wavelet')):
        from difference_guard_denoise import denoise
        target,pre_denoise_diag=denoise(source_target,ref,denoise_settings,protected_mask)
        already_denoised=True
    correction,keep,de,novelty=_calc_fields(ref,target,s,protected_mask)
    multi_maps={}
    if s.mode == 'composite_precise':
        # Composite ONLY the new visual objects. Everything else remains the
        # cleaner reference EXACTLY, including fine detail and clean colors.
        # No generic denoise/color transfer is run on the output.
        from .difference_guard_multimap import multi_map_mask
        if reference.size != target.size:
            raise ValueError('Precise composite needs same-sized, aligned images (no automatic geometry scaling).')
        if s.auto_protect:
            keep,multi_maps=multi_map_mask(ref,target, sensitivity=s.difference_threshold,
                work_limit=s.work_limit,feather_pixels=max(0.3,min(s.feather_pixels,5)),diagnostics=diagnostics)
            keep*=s.protect_strength
        else:
            keep=np.zeros_like(keep,dtype=np.float32)
        sh,sw=keep.shape
        manual=_prepare_mask(protected_mask,target.size,(sw,sh))
        # Manual painting ALWAYS wins over the automatic classifier.
        keep=np.maximum(keep,manual)
    sh,sw=keep.shape
    target_arr=np.asarray(target,dtype=np.uint8)
    output=np.empty_like(target_arr)

    if s.mode in ('composite', 'composite_precise'):
        # This is exact pixel preservation outside protected areas, *not* color
        # correction. It is best used with a manually painted mask.
        for y in range(0,h,256):
            yy=min(h,y+256)
            # Resize a single strip of the mask, avoiding huge full-frame buffers.
            # Global resize first for exact bilinear pixel mapping across strips.
            if y==0:
                mask_full=cv2.resize(keep,(w,h),interpolation=cv2.INTER_LINEAR)
                ref_arr=np.asarray(ref,dtype=np.uint8)
            m=mask_full[y:yy,:,None]
            output[y:yy]=np.clip(ref_arr[y:yy]*(1.0-m)+target_arr[y:yy]*m+0.5,0,255).astype(np.uint8)
    else:
        # Upsample only the three-channel correction field (not full RGB inputs)
        # and apply the LAB transformation in bounded strips to save RAM.
        cfull=cv2.resize(correction,(w,h),interpolation=cv2.INTER_LINEAR)
        for y in range(0,h,256):
            yy=min(h,y+256)
            lab=_to_lab(target_arr[y:yy])
            lab+=cfull[y:yy]
            lab[:,:,0]=np.clip(lab[:,:,0],0,100)
            lab[:,:,1:3]=np.clip(lab[:,:,1:3],-127,127)
            output[y:yy]=_from_lab(lab)
    final=Image.fromarray(output,'RGB')
    final.info.update(edited.info)

    diag=dict(pre_denoise_diag) if diagnostics else {}
    if diagnostics:
        # Resize preview outputs to a fixed bounded width for GUI and file export.
        dmax=960
        factor=min(1,dmax/max(sw,sh))
        dw=max(16,round(sw*factor)); dh=max(16,round(sh*factor))
        def heatmap(x,maxval):
            heat=np.uint8(np.clip(x/maxval,0,1)*255)
            heat=cv2.applyColorMap(heat,cv2.COLORMAP_TURBO)
            return Image.fromarray(cv2.cvtColor(heat,cv2.COLOR_BGR2RGB))
        # Additional independent color/tonal difference diagnostics.
        rc=cv2.cvtColor(_coarse_inputs(reference,target,s.work_limit)[0].astype(np.float32)/255,cv2.COLOR_RGB2HSV)
        ec=cv2.cvtColor(_coarse_inputs(reference,target,s.work_limit)[1].astype(np.float32)/255,cv2.COLOR_RGB2HSV)
        dh=np.abs(rc[:,:,0]-ec[:,:,0]); dh=np.minimum(dh,360-dh)
        hue=dh*np.minimum(rc[:,:,1],ec[:,:,1])  # hue unreliable in neutrals
        sat=np.abs(rc[:,:,1]-ec[:,:,1])*100
        diag['delta_e_heatmap']=heatmap(de,50)
        diag['hue_difference_heatmap']=heatmap(hue,30)
        diag['saturation_difference_heatmap']=heatmap(sat,35)
        diag['edge_novelty_heatmap']=heatmap(novelty,1)
        diag['protected_region_mask']=Image.fromarray(np.uint8(keep*255),'L')
        if s.mode=='composite_precise':
            for key,value in multi_maps.items():
                if isinstance(value,np.ndarray) and value.ndim==2:
                    diag['multi_map_'+key]=Image.fromarray(np.uint8(np.clip(value,0,1)*255),'L')
        diag['reference_resized']=ref.size!=reference.size
        diag['mean_delta_e']=round(float(np.mean(de)),2)
        diag['protected_share']=round(float(np.mean(keep))*100,1)
    if s.mode != 'composite_precise' and not already_denoised and denoise_settings is not None and denoise_settings.mode != 'off':
        from difference_guard_denoise import denoise
        # Pass the calculated auto + painted protection mask to *every* denoising
        # mode, not just the optional reference-detail stage.
        denoise_keep = Image.fromarray(np.uint8(np.clip(
            cv2.resize(keep,(w,h),interpolation=cv2.INTER_LINEAR)*255,0,255)), 'L')
        final, denoise_diag = denoise(final, ref, denoise_settings, denoise_keep)
        if diagnostics:
            diag.update(denoise_diag)
    # Absolute manual keep mask wins over RGB/LAB roundtrip errors and ALL
    # repair operations, including the optional reference-detail stage.
    if protected_mask is not None and (denoise_settings is None or getattr(denoise_settings,'protect_edits',True)):
        painted=np.asarray(protected_mask.convert('L').resize((w,h),Image.Resampling.NEAREST))
        fixed=(painted>=254)
        if np.any(fixed):
            arr=np.asarray(final,dtype=np.uint8).copy()
            arr[fixed]=np.asarray(source_target,dtype=np.uint8)[fixed]
            final=Image.fromarray(arr,'RGB')
            final.info.update(edited.info)
    return final,diag
