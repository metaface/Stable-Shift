from dataclasses import replace
import json
from zipfile import ZipFile

import cv2
import numpy as np
from PIL import Image
import pytest

from stable_shift.engine import Options, restore_quality
from stable_shift.stroke_cleanup import clean_strokes, refinish_strokes
from stable_shift.antialias import refinish_antialias


def strokes():
    base = np.full((128, 192, 3), [62, 95, 140], np.uint8)
    for x in range(12, 180, 10):
        base[36:39, x:x+5] = [65, 35, 47]  # colored ink, real blue gaps
    base[80:83, 12:180] = [38, 50, 80]
    damaged = base.copy()
    for x in range(15, 180, 7):
        damaged[80:83, x:x+1] = [58, 87, 112]
    core = np.zeros(base.shape[:2], bool)
    core[32:43, 8:184] = True
    core[76:87, 8:184] = True
    return base, damaged, core


def test_full_strength_repaints_grid_cuts_with_observed_colored_ink_and_retains_dash_gaps():
    desired, damaged, core = strokes()
    result, maps, report = clean_strokes(damaged, 100, core)
    region = (slice(80, 83), slice(24, 168))
    before = np.abs(damaged[region].astype(float)-desired[region]).mean()
    after = np.abs(result[region].astype(float)-desired[region]).mean()
    assert after < before*.25, (before, after)
    assert np.array_equal(result[37, 14], [65, 35, 47])
    for x in range(12, 170, 10):
        assert np.array_equal(result[37, x+5:x+10], damaged[37, x+5:x+10])
    assert np.array_equal(result[~core], damaged[~core])
    assert np.any(result[core] != damaged[core])  # carried map authorizes repair
    assert report['maximum_rgb_change'] >= 20
    assert report['mean_rgb_change_on_candidates'] > 1
    assert np.min(result) >= np.min(damaged)  # no fixed black paint introduced
    assert not np.any(maps['stroke_support'][~core])


def test_power_is_exact_blend_of_full_candidate_and_zero_is_exact_bypass():
    _, damaged, core = strokes()
    full, _, _ = clean_strokes(damaged, 100, core)
    middle, _, _ = clean_strokes(damaged, 60, core)
    expected = np.uint8(np.clip(damaged.astype(np.float32)+(full.astype(np.float32)-damaged)*.6+.5, 0, 255))
    assert np.array_equal(middle, expected)
    off, maps, report = clean_strokes(damaged, 0, core)
    assert np.array_equal(off, damaged) and maps == {}
    assert report['changed_pixels_percent'] == 0


def test_curved_colored_stroke_improves_without_replacing_it_with_black():
    clean = np.full((160, 224, 3), [165, 175, 190], np.uint8)
    x = np.arange(15, 209)
    points = np.stack((x, np.rint(80+18*np.sin(x/35)).astype(int)), axis=1).astype(np.int32)
    cv2.polylines(clean, [points], False, (83, 49, 68), 2, cv2.LINE_AA)
    core = cv2.dilate(np.uint8(np.any(clean != [165, 175, 190], axis=2)), np.ones((3, 3), np.uint8)) > 0
    ink = np.min(clean, axis=2) < 100
    damaged = clean.copy()
    grid = (np.indices(clean.shape[:2])[1] % 7 == 0) & ink
    damaged[grid] = np.uint8(np.clip(damaged[grid].astype(int)+[18, 27, 12], 0, 255))
    result, _, _ = clean_strokes(damaged, 100, core)
    assert np.abs(result[ink].astype(float)-clean[ink]).mean() < np.abs(damaged[ink].astype(float)-clean[ink]).mean()*.75
    assert np.min(result) >= 49
    assert np.array_equal(result[~core], damaged[~core])


def test_broad_smoke_or_shading_step_does_not_become_a_dark_outline():
    rgb = np.full((96, 144, 3), [70, 80, 90], np.uint8)
    rgb[:, 72:] = [105, 112, 120]
    result, maps, report = clean_strokes(rgb, 100, np.ones(rgb.shape[:2], bool))
    assert np.array_equal(result, rgb)
    assert not np.any(maps['stroke_support'])
    assert report['changed_pixels_percent'] == 0


def test_white_texture_next_to_sharp_outline_does_not_borrow_black_ink():
    rgb = np.full((100, 140, 3), [245, 243, 239], np.uint8)
    points = np.array([[15, 85], [35, 45], [55, 65], [75, 20], [110, 60]], np.int32)
    cv2.polylines(rgb, [points], False, (15, 20, 25), 2, cv2.LINE_AA)
    bright = np.min(rgb, axis=2) > 225
    grain = np.random.default_rng(24).integers(-4, 5, (int(bright.sum()), 3))
    rgb[bright] = np.uint8(np.clip(rgb[bright].astype(int)+grain, 0, 255))
    result, _, _ = clean_strokes(rgb, 100, np.ones(rgb.shape[:2], bool))
    assert np.min(result[bright]) > 190


@pytest.mark.parametrize('value', [-1, 101, float('nan'), float('inf')])
def test_invalid_stroke_strength_fails_before_backend(value, monkeypatch):
    from stable_shift import engine
    monkeypatch.setattr(engine, '_bm3d', lambda *a: pytest.fail('Backend ran for invalid finishing settings.'))
    image = Image.new('RGB', (32, 32), 'blue')
    with pytest.raises(ValueError, match='Stroke cleanup strength'):
        restore_quality(image, image, Options(stroke_strength=value))


def test_quick_stroke_and_aa_previews_are_not_cumulative_and_signed_stages_add_up():
    _, damaged, _ = strokes()
    image = Image.fromarray(damaged)
    opts = Options(method='Region cleanup only', color_match=False, stroke_strength=100, antialias_strength=35)
    result, maps = restore_quality(image, image, opts)
    post_color = np.uint8(np.asarray(result).astype(np.int16)-maps['stroke_signed_rgb']-maps['antialias_signed_rgb'])
    sixty, updated = refinish_strokes(post_color, maps, 60, 35)
    repeated, again = refinish_strokes(post_color, updated, 60, 35)
    assert np.array_equal(sixty, repeated)
    restored, disabled = refinish_strokes(post_color, again, 0, 0)
    assert np.array_equal(restored, post_color)
    assert updated['report']['options']['stroke_strength'] == 60
    assert maps['report']['options']['stroke_strength'] == 100
    assert not np.any(disabled['stroke_signed_rgb'])
    pre_aa = np.uint8(sixty.astype(np.int16)-updated['antialias_signed_rgb'])
    aa_only, aa_maps = refinish_antialias(pre_aa, updated, 70)
    assert aa_maps['report']['options']['stroke_strength'] == 60
    for run in (maps, updated, again, disabled, aa_maps):
        assert np.array_equal(sum(run[name+'_signed_rgb'] for name in ('denoise', 'cleanup', 'palette', 'stroke', 'antialias')),
                              run['total_signed_rgb'])
    assert np.array_equal(aa_only.astype(np.int16)-damaged.astype(np.int16), aa_maps['total_signed_rgb'])


def test_comparison_uses_one_backend_fixed_colors_full_strengths_and_aa_off(tmp_path, monkeypatch):
    from stable_shift import engine
    from stable_shift.stroke_comparison import export_stroke_comparison
    _, damaged, _ = strokes()
    image = Image.fromarray(damaged)
    reference = Image.fromarray(np.uint8(damaged*.9+8))
    calls = []
    def backend(rgb, *args):
        calls.append(args)
        return rgb.copy()
    monkeypatch.setattr(engine, '_bm3d', backend)
    opts = Options(method='CPU BM3D', color_method='Robust global', stroke_strength=15, antialias_strength=100)
    report = export_stroke_comparison(reference, image, opts, tmp_path)
    assert len(calls) == 1
    assert report['upstream_run']['options']['stroke_strength'] == 0
    assert report['upstream_run']['options']['antialias_strength'] == 0
    for strength, name in ((0, '00_strokes_off.png'), (60, '01_strokes_60.png'), (100, '02_strokes_100.png')):
        actual, _ = restore_quality(reference, image, replace(opts, stroke_strength=strength, antialias_strength=0))
        assert np.array_equal(np.asarray(actual), np.asarray(Image.open(tmp_path/name)))
    with ZipFile(tmp_path/'share_stroke_test.zip') as archive:
        assert {'color_reference.png', 'edited_source.png', '00_strokes_off.png', '02_strokes_100.png'} <= set(archive.namelist())
        saved = json.loads(archive.read('stroke_settings_and_timings.json'))
        assert saved['candidate']['strength'] == 100
        assert saved['requested_options']['stroke_strength'] == 15
