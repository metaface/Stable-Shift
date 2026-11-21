"""Focused checks for the retained restoration path."""
from dataclasses import replace
import importlib.util
import json
from pathlib import Path
from zipfile import ZipFile
import numpy as np
from PIL import Image
import pytest

from stable_shift import pipeline
from stable_shift.pipeline import Options, prepare
from stable_shift.automatic import analyze_noise, analyze_surfaces
from stable_shift.global_color import fit_global_color, fit_reference_color
from stable_shift.export import save_result, save_test


def scene():
    colors = np.random.default_rng(19).integers(30, 205, (10, 12, 3), dtype=np.uint8)
    return np.repeat(np.repeat(colors, 16, axis=0), 16, axis=1)


@pytest.mark.parametrize('gain,low,high', [(.1, 30, 220), (6., 4, 38)])
def test_robust_accepts_exposure_without_loosening_relative_color_checks(gain, low, high):
    source = np.repeat(np.repeat(np.random.default_rng(18).integers(low, high, (10, 12, 3), dtype=np.uint8), 20, axis=0), 20, axis=1)
    target = np.uint8(np.clip(source.astype(float)*gain+.5, 0, 255))
    model, report = fit_global_color(Image.fromarray(target), source)
    assert report['selected_method'] == 'Robust global', report
    assert np.abs(model.apply(source).astype(float)-target).mean() < 1
    np.testing.assert_allclose(report['exposure_normalized_singular_values'], [1,1,1], atol=.08)


def test_unrelated_colors_still_fall_back_explicitly_and_off_is_available():
    source = scene()
    ref = Image.fromarray(np.roll(source, (55, 71), (0, 1)))
    _, report = fit_reference_color(ref, source)
    assert report['selected_method'] == 'Classic' and report['fallback_reason']
    model, report = fit_reference_color(ref, source, enabled=False)
    assert model is None and report['selected_method'] == 'Off'


def test_analysis_distinguishes_quiet_noisy_and_smooth_surfaces():
    quiet = np.full((128,160,3), 150, np.uint8)
    noisy = np.uint8(np.clip(quiet.astype(float)+np.random.default_rng(9).normal(0,3,quiet.shape)+.5,0,255))
    assert analyze_noise(quiet)['denoise'] == 0
    assert analyze_noise(noisy)['denoise'] == 100
    assert analyze_surfaces(quiet)['deblotch'] == 0
    ramp = np.uint8(np.broadcast_to(np.linspace(70,180,160)[None,:,None], quiet.shape))
    assert analyze_surfaces(ramp)['deblotch'] < 25


def test_quiet_auto_skips_optional_runtime_and_preserves_exact_pixels(monkeypatch):
    monkeypatch.setattr(pipeline, 'denoise', lambda *a, **k: pytest.fail('Quiet input should not load a model'))
    image = Image.new('RGB',(81,67),(120,140,160))
    state = prepare(None, image)
    result, report = state.render()
    np.testing.assert_array_equal(result,image)
    assert report['applied'] == {'automatic': True,'denoise':0,'deblotch':0,'color':0,'color_method':'Off'}
    assert state.cache is None


def test_live_overrides_are_reversible_and_reruns_reuse_only_matching_models(monkeypatch):
    source=scene(); calls=[]
    def model(rgb,progress):
        calls.append(True)
        return np.uint8(np.clip(rgb.astype(int)+2,0,255)), {'device_name':'Test stub'}
    monkeypatch.setattr(pipeline,'denoise',model)
    options=Options(automatic=False,reference=False)
    state=prepare(None,Image.fromarray(source),options)
    first=np.array(state.render(73,0)[0]);state.render(200,0)
    np.testing.assert_array_equal(state.render(73,0)[0],first)
    ref=Image.fromarray(source)
    another=prepare(ref,Image.fromarray(source),replace(options,denoise=50,reference=True,color_method='Classic'),cached=state.cache)
    assert len(calls)==1 and another.report['model_reused']
    source[0,0]=0
    prepare(None,Image.fromarray(source),options,cached=state.cache)
    assert len(calls)==2


def test_saved_pixels_report_and_bundle_use_applied_settings(tmp_path,monkeypatch):
    source=Image.fromarray(scene())
    monkeypatch.setattr(pipeline,'denoise',lambda rgb,progress:(rgb.copy(),{'device_name':'Test stub'}))
    state=prepare(None,source,Options(automatic=False))
    image,report=state.render(135,90,automatic=False)
    # No reference: the effective color dose is zero even if a manual slider is nonzero.
    assert report['applied']['color']==0
    path=tmp_path/'selected.png';save_result(image,report,path)
    np.testing.assert_array_equal(Image.open(path),image)
    assert json.loads(path.with_suffix('.settings.json').read_text())['applied']['deblotch']==135
    archive=save_test(state,image,report,source,None,tmp_path/'test')
    with ZipFile(archive) as z:
        assert {'edited_source.png','result.png','settings.json'} <= set(z.namelist())
    with pytest.raises(ValueError):
        save_test(state,image,report,Image.new('RGB',source.size),None,tmp_path/'wrong')


def test_removed_modules_are_not_runtime_dependencies():
    for name in ('engine','line_protection','reconstruction','antialias','difference_guard_core'):
        assert importlib.util.find_spec('stable_shift.'+name) is None
