"""Run: python test_engine.py (NLM and boundary-constrained; BM3D optional)."""
from dataclasses import replace
import numpy as np
import cv2
from PIL import Image
from engine import Options, restore_quality, preserve_edits, structure_maps


def synthetic(w=256,h=256,noise=17):
    y,x=np.mgrid[:h,:w]
    base=np.zeros((h,w,3),dtype=np.uint8)
    base[:,:w//2]=[220,224,231]
    base[:,w//2:]=[45,61,78]
    # Draw fine details and a subtly shaded form.
    cv2.rectangle(base,(w//5,h//4),(w//3,3*h//4),(100,148,176),2)
    cv2.line(base,(w//2+25,h//4),(w-10,3*h//4),(200,180,155),2)
    rng=np.random.default_rng(4)
    dirty=np.uint8(np.clip(base.astype(float)+rng.normal(0,noise,base.shape),0,255))
    return Image.fromarray(base),Image.fromarray(dirty)


def test_restoration():
    clean,edited=synthetic()
    for method in ['NLM','Boundary constrained']:
        for match in [False,True]:
            out,m=restore_quality(clean,edited,Options(method=method,color_match=match,noise=66,color_noise=70))
            assert out.size==edited.size
            assert np.isfinite(np.asarray(out)).all()
            assert all(n in m for n in ('hard','soft','guard','distance'))
    # Downscaled clean reference -> larger edited result (initial upscale flow)
    small=clean.resize((128,128),Image.Resampling.LANCZOS)
    for method in ['NLM','Boundary constrained']:
        out,_=restore_quality(small,edited,Options(method=method,noise=60,color_noise=55))
        assert out.size==edited.size, method
    # Non-registered, different sized reference still supports palette-only approximation.
    strange=Image.fromarray(np.full((60,90,3),[210,190,175],np.uint8))
    out,_=restore_quality(strange,edited,Options(method='Boundary constrained'))
    assert out.size==edited.size
    try:
        preserve_edits(small,edited,Options())
    except ValueError as exc:
        assert 'same dimensions' in str(exc)
    else:
        raise AssertionError('Exact compositing must reject different geometry.')
    print('PASS: restore sizes, palette, nonregistered reference, exact-composite restrictions')


def test_boundary_constraint():
    clean,dirty=synthetic(w=256,h=180,noise=20)
    opt=Options(method='Boundary constrained',noise=85,color_noise=90,hard_guard=100,soft_guard=100,color_match=False)
    out,m=restore_quality(clean,dirty,opt)
    a=np.asarray(dirty,dtype=np.float32)
    b=np.asarray(out,dtype=np.float32)
    original=np.asarray(clean,dtype=np.float32)
    # Noise reduction in interiors.
    mask=np.zeros(a.shape[:2],bool);mask[20:150,20:75]=True
    before=np.mean((a[mask]-original[mask])**2)
    after=np.mean((b[mask]-original[mask])**2)
    assert after<before*.86, (before,after)
    # A true white/dark boundary should retain a strong jump.
    before_step=abs(float(a[50:110,126,0].mean()-a[50:110,130,0].mean()))
    after_step=abs(float(b[50:110,126,0].mean()-b[50:110,130,0].mean()))
    assert after_step >=before_step*.94,(before_step,after_step)
    print('PASS: boundary constrained filtering reduces noise without washing out sharp step')


def test_output_from_real_image():
    from pathlib import Path
    p=Path('/mnt/data/00000-2652902711(1).png')
    if not p.exists():
        import pytest
        pytest.skip('Historical real-image fixture is not available in this environment.')
    original=Image.open(p).convert('RGB').resize((640,640),Image.Resampling.LANCZOS)
    small=original.resize((320,320),Image.Resampling.LANCZOS)
    # Real illustration; reference is half the edited resolution.
    for meth in ('NLM','Boundary constrained'):
        out,_=restore_quality(small,original,Options(method=meth,noise=55,color_noise=60),diagnostics=False)
        assert out.size==(640,640)
    print('PASS: real illustration 2x image dimension compatibility')

if __name__=='__main__':
    test_restoration();test_boundary_constraint();test_output_from_real_image()
