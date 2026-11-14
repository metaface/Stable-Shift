from dataclasses import replace
import sys
import numpy as np
from PIL import Image
from stable_shift.engine import Options,restore_quality,_lab
from tests.test_engine import synthetic


def test_reference_does_not_guide_structure():
    clean,edited=synthetic(96,96)
    unrelated=Image.new('RGB',(33,47),'red')
    opts=Options(method='Boundary constrained',color_match=False,cleanup=65)
    a,ma=restore_quality(clean,edited,opts)
    b,mb=restore_quality(unrelated,edited,opts)
    assert np.array_equal(a,b)
    assert np.array_equal(ma['hard'],mb['hard'])


def test_chroma_cleanup():
    y,x=np.mgrid[:96,:96]
    rgb=np.full((96,96,3),160,np.uint8)
    rgb[:,:,0]=160+np.round(5*np.sin(x/3)).astype(np.int16)
    edited=Image.fromarray(rgb)
    options=Options(method='Color only',color_match=False)
    plain,_=restore_quality(edited,edited,options)
    out,m=restore_quality(edited,edited,replace(options,cleanup=100))
    assert np.array_equal(plain,edited)
    assert np.mean(np.abs(_lab(np.asarray(out))[:,:,0]-_lab(rgb)[:,:,0]))<.5
    assert np.std(_lab(np.asarray(out))[:,:,1])<np.std(_lab(rgb)[:,:,1])
    assert all(m['report'][k]>=0 for k in m['report'] if k.endswith('_seconds'))


def test_cpu_bm3d():
    clean,dirty=synthetic(64,64,noise=12)
    out,m=restore_quality(clean,dirty,Options(method='CPU BM3D',color_match=False,hard_guard=0,soft_guard=0,noise=55,color_noise=55))
    target=np.asarray(clean,dtype=float)
    assert np.mean((np.asarray(out,dtype=float)-target)**2)<np.mean((np.asarray(dirty,dtype=float)-target)**2)
    assert m['report']['backend']=='CPU BM3D'


def test_gpu_failure_is_explicit():
    clean,dirty=synthetic(32,32)
    # Deterministically simulate an unavailable GPU dependency.
    from unittest.mock import patch
    with patch.dict(sys.modules,{'cupy':None}):
        try:restore_quality(clean,dirty,Options(method='GPU BM3D'))
        except RuntimeError as exc:assert 'No CPU fallback' in str(exc)
        else:raise AssertionError('GPU failure must be explicit')
