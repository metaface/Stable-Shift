from dataclasses import replace
import json
from zipfile import ZipFile

import cv2
import numpy as np
from PIL import Image
import pytest

from stable_shift.antialias import antialias, refinish_antialias
from stable_shift.engine import Options, correct_palette, restore_quality
from stable_shift.global_color import GlobalColor, fit_global_color


def colors():
    rng = np.random.default_rng(193)
    # Flat independent colors with connected drawn contours, not white noise.
    patches = rng.integers(40, 190, (12, 14, 3), dtype=np.uint8)
    rgb = np.repeat(np.repeat(patches, 12, axis=0), 12, axis=1)
    cv2.line(rgb, (10, 8), (130, 130), (15, 18, 23), 1)
    return rgb


def shifted(rgb):
    matrix = np.array([[1.08, -.02, .08], [.03, 1.13, .01], [-.04, .01, .91]])
    return np.uint8(np.clip(rgb.astype(float) @ matrix+[-9, 6, 15]+.5, 0, 255))


def test_global_recovers_channel_mixing_without_importing_reference_detail():
    rgb = colors()
    target = shifted(rgb)
    # A new object is present only in the reference. It must not be pasted in.
    target[15:47, 75:120] = [245, 25, 70]
    model, report = fit_global_color(Image.fromarray(target), rgb)
    assert report['selected_method'] == 'Robust global', report
    result = model.apply(rgb)
    expected = shifted(rgb)
    assert np.mean(np.abs(result.astype(float)-expected)) < 1
    # Global mapping: identical RGB always yields identical RGB at other sites.
    row = np.full((1, 9, 3), rgb[20, 80], np.uint8)
    assert np.all(model.apply(row) == result[20, 80])
    assert report['global_validation_median_delta_e'] < report['classic_validation_median_delta_e']*.75


def test_reference_grid_cannot_become_an_output_spatial_pattern():
    rgb = colors()
    target = shifted(rgb)
    grid = np.indices(rgb.shape[:2]).sum(axis=0) % 8 == 0
    target[grid] = np.uint8(np.clip(target[grid].astype(int)+4, 0, 255))
    model, report = fit_global_color(Image.fromarray(target), rgb)
    assert isinstance(model, GlobalColor), report
    result = model.apply(rgb)
    # Two equal-color source pixels can straddle a reference grid line.
    assert np.array_equal(rgb[70, 50], rgb[70, 51])
    assert np.array_equal(result[70, 50], result[70, 51])


def test_identical_reference_is_exact_and_degenerate_or_unrelated_fits_fall_back():
    rgb = colors()
    model, report = fit_global_color(Image.fromarray(rgb), rgb)
    assert report['selected_method'] == 'Robust global'
    assert np.array_equal(model.apply(rgb), rgb)
    for ref in (Image.new('RGB', (40, 30), 'red'), Image.fromarray(np.roll(rgb, (49, 71), (0, 1)))):
        model, report = fit_global_color(ref, rgb)
        assert report['selected_method'] == 'Classic', report
    flat = np.full((80, 90, 3), [80, 100, 120], np.uint8)
    model, report = fit_global_color(Image.new('RGB', (40, 30), 'orange'), flat)
    assert report['selected_method'] == 'Classic'
    assert model.apply(flat).shape == flat.shape


def test_small_repeated_color_drift_does_not_accumulate():
    reference = colors()
    value = reference.copy()
    for _ in range(6):
        value = np.uint8(np.clip(value.astype(float)*[.99, .98, .985]+[1, 2, 1]+.5, 0, 255))
        model, _ = fit_global_color(Image.fromarray(reference), value)
        value = model.apply(value)
    assert np.mean(np.abs(value.astype(float)-reference)) < 1.5


def test_antialias_reduces_diagonal_stair_steps_and_leaves_flat_pixels_exact():
    yy, xx = np.indices((96, 128))
    rgb = np.repeat(np.where(xx > .43*yy+20.3, 220, 30).astype(np.uint8)[..., None], 3, axis=2)
    truth = np.zeros(rgb.shape[:2], np.float64)
    for oy in (np.arange(16)+.5)/16-.5:
        for ox in (np.arange(16)+.5)/16-.5:
            truth += np.where(xx+ox > .43*(yy+oy)+20.3, 220, 30)/256
    output = antialias(rgb, 35)
    assert np.mean(np.abs(output[..., 0]-truth)) < np.mean(np.abs(rgb[..., 0]-truth))*.9
    assert np.array_equal(output[:, 95:], rgb[:, 95:])
    assert np.array_equal(antialias(rgb, 0), rgb)
    assert np.min(output) >= 30 and np.max(output) <= 220
    # Straight vertical lines and isolated tiny stitches retain their centers.
    lines = np.full((64, 64, 3), 210, np.uint8)
    lines[:, 20:22] = 25
    for y in (12, 26, 40):
        lines[y, 40:48] = 25
    smoothed = antialias(lines, 35)
    assert np.all(smoothed[:, 20:22] < 60)
    assert np.all(smoothed[[12, 26, 40], 43] < 60)


@pytest.mark.parametrize('value', [-1, 101, float('nan'), float('inf')])
def test_invalid_finishing_is_rejected_before_denoising(value, monkeypatch):
    from stable_shift import engine
    monkeypatch.setattr(engine, '_bm3d', lambda *a: pytest.fail('Invalid settings must fail before BM3D.'))
    image = Image.fromarray(colors())
    with pytest.raises(ValueError, match='Antialias strength'):
        restore_quality(image, image, Options(antialias_strength=value))


def test_aa_preview_is_not_cumulative_and_preserves_upstream_settings_and_maps():
    rgb = colors()
    options = Options(method='Region cleanup only', auto_strength=True, cleanup=90,
                      color_match=False, antialias_strength=35)
    image, maps = restore_quality(Image.fromarray(rgb), Image.fromarray(rgb), options)
    pre = np.uint8(np.asarray(image).astype(np.int16)-maps['antialias_signed_rgb'])
    new, updated = refinish_antialias(pre, maps, 65)
    again, repeated = refinish_antialias(pre, updated, 65)
    off, disabled = refinish_antialias(pre, repeated, 0)
    assert np.array_equal(new, again)
    assert np.array_equal(off, pre)
    assert disabled['report']['options']['cleanup'] == 90
    assert maps['report']['options']['antialias_strength'] == 35
    assert updated['report']['options']['antialias_strength'] == 65
    for key in ('denoise_signed_rgb', 'cleanup_signed_rgb', 'palette_signed_rgb', 'source_line_core'):
        assert np.array_equal(maps[key], updated[key])
    assert np.array_equal(sum(updated[name+'_signed_rgb'] for name in ('denoise', 'cleanup', 'palette', 'antialias')),
                          updated['total_signed_rgb'])
    assert np.array_equal(new.astype(np.int16)-rgb.astype(np.int16), updated['total_signed_rgb'])


@pytest.mark.parametrize('automatic', [False, True])
def test_color_comparison_uses_one_backend_and_matches_normal_run_colors(tmp_path, monkeypatch, automatic):
    from stable_shift import engine
    from stable_shift.color_comparison import export_color_comparison
    rgb = colors()
    if automatic:
        grain = np.random.default_rng(12).normal(0, 3, rgb.shape)
        rgb = np.uint8(np.clip(rgb.astype(float)+grain, 0, 255))
    reference, image = Image.fromarray(shifted(rgb)), Image.fromarray(rgb)
    calls = []
    def backend(raw, *args):
        calls.append(args)
        return cv2.GaussianBlur(raw, (3, 3), .5)
    monkeypatch.setattr(engine, '_bm3d', backend)
    options = Options(method='CPU BM3D', cleanup=60, blotch_strength=70,
                      color_method='Robust global', antialias_strength=100, auto_strength=automatic)
    summary = export_color_comparison(reference, image, options, tmp_path)
    assert len(calls) == 1
    assert summary['cleanup_run']['options']['antialias_strength'] == 0
    assert summary['cleanup_run']['options']['color_match'] is False
    for method, name in (('Classic', '01_classic.png'), ('Robust global', '02_robust_global.png')):
        normal, _ = restore_quality(reference, image, replace(options, color_method=method, antialias_strength=0))
        assert np.array_equal(np.asarray(normal), np.asarray(Image.open(tmp_path/name)))
    with ZipFile(tmp_path/'share_color_test.zip') as archive:
        assert {'edited_source.png', 'color_reference.png', '01_classic.png', '02_robust_global.png'} <= set(archive.namelist())
        saved = json.loads(archive.read('color_settings_and_timings.json'))
        assert saved['requested_options']['antialias_strength'] == 100
