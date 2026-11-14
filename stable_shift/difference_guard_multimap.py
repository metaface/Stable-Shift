"""Multi-map edit-object detection for exact-pixel compositing.

Purpose: distinguish *large coherent new visual content* from diffuse per-pixel
color drift and regenerated texture. Does NOT try to preserve unspecified fine
texture improvements. Cannot know intent (e.g., recoloring the whole scene).
"""
from __future__ import annotations
from dataclasses import dataclass
import cv2
import numpy as np
from PIL import Image

@dataclass
class MultiMapSettings:
    threshold: float = 23.0          # manual sensitivity control (higher = stricter)
    work_limit: int = 1024          # max working dimension (mask upsampled)
    min_area_percent: float = .00005
    max_area_percent: float = .30
    trim_radius: int = 0
    feather: float = 1.75


def smoothstep(a,b,x):
    t=np.clip((x-a)/max(b-a,1e-6),0,1)
    return t*t*(3-2*t)


def _lab(im):
    return cv2.cvtColor(im.astype(np.float32)/255.,cv2.COLOR_RGB2LAB)


def _rgb(im):
    return cv2.cvtColor(im.astype(np.float32),cv2.COLOR_LAB2RGB)


def multi_map_mask(reference: Image.Image, edited: Image.Image,
                   sensitivity: float=23.,work_limit:int=1024,
                   feather_pixels:float=2., diagnostics:bool=False):
    """Return float32 keep-edited mask on working resolution + diagnostics.
    Reference and edited images must have the same composition/alignment.
    """
    size=edited.size
    sc=min(1.,float(work_limit)/max(size))
    w=max(32,round(size[0]*sc));h=max(32,round(size[1]*sc))
    ref=np.asarray(reference.convert('RGB').resize((w,h),Image.Resampling.LANCZOS))
    edt=np.asarray(edited.convert('RGB').resize((w,h),Image.Resampling.LANCZOS))
    a=_lab(ref);b=_lab(edt)
    # First remove broad color / lighting cast statistically so it doesn't
    # count as a new object. Work with channels separately for robustness.
    dif=a-b
    center=np.median(dif.reshape(-1,3),axis=0)
    resid=dif-center
    rmag=np.linalg.norm(resid,axis=2)
    # Re-estimate the cast on the stable half of pixels, iterating to exclude
    # meaningful additions / large objects from the color baseline.
    for _ in range(2):
        stable=rmag < np.percentile(rmag,55)
        if np.count_nonzero(stable)>100:
            center=np.median(dif[stable],axis=0)
        resid=dif-center
        rmag=np.linalg.norm(resid,axis=2)
    corrected_lab=b+center.reshape(1,1,3)
    # Color anomalies on 2 scales: new objects should persist under
    # smoothing; noisy dots often disappear at 4-8px scale.
    cr=np.linalg.norm(cv2.GaussianBlur(a,(0,0),1.35)-cv2.GaussianBlur(corrected_lab,(0,0),1.35),axis=2)
    cr_low=np.linalg.norm(cv2.GaussianBlur(a,(0,0),4.0)-cv2.GaussianBlur(corrected_lab,(0,0),4.0),axis=2)
    # CIELAB chroma: avoids generic blue/gray brightness differences looking
    # like independent new objects.
    cd=np.linalg.norm(cv2.GaussianBlur(a[:,:,1:3],(0,0),1.5)-cv2.GaussianBlur(corrected_lab[:,:,1:3],(0,0),1.5),axis=2)
    # Hue and saturation difference, weighted by chroma to avoid neutral hue.
    al=a.astype('float32'); bl=corrected_lab.astype('float32')
    ca=np.linalg.norm(al[:,:,1:3],axis=2);cb=np.linalg.norm(bl[:,:,1:3],axis=2)
    dot=(al[:,:,1]*bl[:,:,1]+al[:,:,2]*bl[:,:,2])/(ca*cb+1e-5)
    hd=np.sqrt(np.maximum(0,1-np.clip(dot,-1,1))) * np.minimum(ca,cb)
    sd=np.abs(ca-cb)
    # Stable outlines: new objects often have strong edge features not present
    # in the source. 2-pixel tolerance absorbs small shifts.
    g0=cv2.cvtColor(ref,cv2.COLOR_RGB2GRAY)
    g1=cv2.cvtColor(edt,cv2.COLOR_RGB2GRAY)
    e0=cv2.Canny(g0,70,140);e1=cv2.Canny(g1,70,140)
    kern=cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(5,5))
    new_edge=np.float32((e1>0)&(cv2.dilate(e0,kern)==0))
    old_edge=np.float32((e0>0)&(cv2.dilate(e1,kern)==0))
    edge=cv2.GaussianBlur(cv2.dilate(np.uint8(255*(new_edge+old_edge>0)),cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(7,7))),(0,0),2.0)/255.
    # Visual evidence votes. Color & low-frequency difference strongly
    # contribute; edge novelty boosts boundaries, but cannot independently
    # turn random linework into a protected region.
    t=float(sensitivity)
    color=smoothstep(max(3,t*.55), t*1.3,cr)
    low=smoothstep(max(2,t*.40),t*1.15,cr_low)
    chroma=smoothstep(max(3,t*.30),t*.90,cd)
    hue=smoothstep(max(2,t*.22),t*.90,hd)
    saturation=smoothstep(max(2,t*.25),t*.85,sd)
    structure=smoothstep(.15,.65,edge)
    # Strong coherent differences are accepted, but single-map noisy
    # differences only get moderate confidence. Pairwise agreements can
    # accumulate sufficient confidence, especially for white-on-blue edits.
    agreement=(.30*color+.30*low+.15*chroma+.08*hue+.07*saturation+.10*structure)
    agreement+=.10*np.minimum(color,low)
    # Color/structure gating suppresses texture-only deterioration.
    seed=((color>.60)&(low>.55)) | ((color>.75)&(structure>.30)) | ((low>.70)&(chroma>.50)) | ((low>.75)&(structure>.5))
    seed=np.uint8(seed)*255
    # Merge short gaps in new-object interiors, then fill actual contours.
    close_r=max(2,round(min(h,w)/180))
    ckernel=cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(2*close_r+1,2*close_r+1))
    seed=cv2.morphologyEx(seed,cv2.MORPH_CLOSE,ckernel)
    n,lab,stats,_=cv2.connectedComponentsWithStats(seed,8)
    out=np.zeros((h,w),np.uint8)
    minarea=max(30,int(w*h*.00005))
    maxarea=int(w*h*.30)
    for i in range(1,n):
        area=stats[i,cv2.CC_STAT_AREA]
        if area<minarea or area>maxarea: continue
        component=np.uint8(lab==i)*255
        # A moderately strong region can have low-saturation gaps inside an
        # accessory; outline fill avoids cutting the weave/hair/flower petals.
        cc,_=cv2.findContours(component,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(out,cc,-1,255,thickness=cv2.FILLED)
    # Second reconstruction pass: allow contiguous pixels with sufficient
    # multi-map agreement to connect to existing seeds (hysteresis).
    for _ in range(2):
        k=cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(7,7))
        expanded=cv2.dilate(out,k)
        connected=(expanded>0)&(agreement>.38)&(low>.16)
        out[connected]=255
    # Fill holes again. Gradients between newly added objects and background
    # are retained within a narrow perimeter of the detected objects.
    close_r=max(3,round(min(h,w)/190))
    out=cv2.morphologyEx(out,cv2.MORPH_CLOSE,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(2*close_r+1,2*close_r+1)))
    contours,_=cv2.findContours(out,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    out=np.zeros_like(out)
    for c in contours:
        if cv2.contourArea(c) >= minarea:
            cv2.drawContours(out,[c],-1,255,-1)
    # Small dilation to retain the entire new edge/shadow, very limited
    # feathering to avoid colored rectangles around edited objects.
    out=cv2.dilate(out,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(5,5)))
    ff=max(.2,float(feather_pixels)*sc)
    soft=cv2.GaussianBlur(out.astype(np.float32)/255,(0,0),ff)
    result={'color':color,'low_frequency':low,'chroma':chroma,'hue':hue,'saturation':saturation,
            'edge_novelty':edge,'agreement':np.clip(agreement,0,1),'strong_seeds':seed.astype(np.float32)/255,
            'mask':soft,'offset_lab':center}
    return np.clip(soft,0,1),result if diagnostics else {}
