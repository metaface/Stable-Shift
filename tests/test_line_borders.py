from dataclasses import replace
import json
from zipfile import ZipFile

import cv2
import numpy as np
from PIL import Image
import pytest

from stable_shift.engine import Options
from stable_shift.line_borders import clean_line_borders


def seam(weak=False, gradient=False):
    h, w = 140, 220
    paint = np.full((h, w, 3), [70, 105, 155] if not weak else [102, 110, 125], np.uint8)
    if gradient:
        x = np.arange(w, dtype=float)[None, :, None]
        paint = np.uint8(paint.astype(float)+x*.12)
    source = paint.copy()
    ink = np.zeros((h, w), bool)
    ink[:, 99:101] = True
    source[ink] = [22, 35, 62] if not weak else [96, 104, 119]
    core = cv2.dilate(ink.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)
    return source, paint, ink, core


@pytest.mark.parametrize('weak', [False, True])
def test_cleans_a_noisy_light_fringe_inside_old_core_without_altering_colored_ink(weak):
    source, paint, ink, core = seam(weak)
    fringe = np.zeros(core.shape, bool)
    fringe[:, 97:99] = True
    fringe[:, 101:103] = True
    source[fringe] = np.uint8(np.clip(source[fringe].astype(float)+10+
        np.random.default_rng(10).normal(0, 1, source[fringe].shape), 0, 255))
    output, maps, report = clean_line_borders(source, source, paint, core)
    before = np.mean((source[fringe].astype(float)-paint[fringe])**2)
    after = np.mean((output[fringe].astype(float)-paint[fringe])**2)
    assert after < before*.15, (before, after)
    assert np.array_equal(output[ink], source[ink])
    assert report['ink_pixels_changed'] == 0
    assert report['old_core_pixels_changed'] > 100
    assert np.array_equal(maps['border_signed_rgb'], output.astype(np.int16)-source.astype(np.int16))
    assert np.array_equal(output[:, :85], source[:, :85])


def test_keeps_ink_antialiasing_on_opposite_paint_colors():
    source, paint, ink, core = seam()
    paint[:, :99] = [225, 230, 235]
    source[:] = paint
    source[ink] = [22, 35, 62]
    aa = np.zeros(core.shape, bool)
    aa[:, 98] = True
    aa[:, 101] = True
    source[aa] = np.uint8(paint[aa]*.5+np.array([22, 35, 62])*.5+.5)
    fringe = np.zeros(core.shape, bool)
    fringe[:, 97] = True
    fringe[:, 102] = True
    source[fringe] = np.uint8(np.minimum(255, source[fringe].astype(int)+10))
    output, _, _ = clean_line_borders(source, source, paint, core)
    assert np.array_equal(output[ink | aa], source[ink | aa])
    assert np.abs(output[fringe].astype(float)-paint[fringe]).max() <= 1


def test_clean_shading_continues_to_the_line_without_an_added_color_band():
    source, paint, ink, core = seam(gradient=True)
    output, _, _ = clean_line_borders(source, source, paint, core)
    assert np.array_equal(output[ink], source[ink])
    assert np.abs(output[~ink].astype(int)-source[~ink]).max() <= 1


def test_antialiased_edge_color_is_cleaned_without_changing_its_ink_coverage():
    source, paint, ink, core = seam()
    aa = np.zeros(core.shape, bool)
    aa[:, 98] = True
    aa[:, 101] = True
    expected = source.copy()
    expected[aa] = np.uint8(paint[aa]*.5+np.array([22, 35, 62])*.5+.5)
    source[aa] = np.uint8(expected[aa]+[8, -4, 2])
    output, _, _ = clean_line_borders(source, source, paint, core)
    before = np.mean((source[aa].astype(float)-expected[aa])**2)
    after = np.mean((output[aa].astype(float)-expected[aa])**2)
    assert after < before*.2, (before, after)
    assert np.array_equal(output[ink], source[ink])


def test_curved_colored_strokes_and_blue_dash_gaps_do_not_get_repainted():
    paint = np.full((180, 260, 3), [75, 115, 165], np.uint8)
    source = paint.copy()
    ink = np.zeros(paint.shape[:2], np.uint8)
    cv2.ellipse(ink, (120, 90), (65, 45), 20, 0, 260, 1, 2)
    for x in (25, 45, 65):
        ink[145:147, x:x+9] = 1
    source[ink > 0] = [28, 44, 72]
    core = cv2.dilate(ink, np.ones((5, 5), np.uint8)).astype(bool)
    fringe = core & (ink == 0)
    source[fringe] = np.minimum(255, source[fringe].astype(int)+8).astype(np.uint8)
    output, _, report = clean_line_borders(source, source, paint, core)
    assert np.array_equal(output[ink > 0], source[ink > 0])
    assert np.array_equal(output[145:147, 35:43], paint[145:147, 35:43])
    assert report['changed_pixels_percent'] > 1


def test_paint_sampling_stops_at_another_stroke_in_a_narrow_gap():
    paint = np.full((100, 160, 3), [60, 100, 150], np.uint8)
    paint[:, 62:69] = [150, 90, 80]
    paint[:, 69:] = [90, 140, 100]
    source = paint.copy()
    ink = np.zeros(paint.shape[:2], bool)
    ink[:, 61:63] = True
    ink[:, 68:70] = True
    source[ink] = [20, 25, 30]
    core = cv2.dilate(ink.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)
    output, _, _ = clean_line_borders(source, source, paint, core)
    assert np.array_equal(output[ink], source[ink])
    assert np.array_equal(output[:, 63:68], source[:, 63:68])


def test_shading_step_and_isolated_bright_details_are_not_dark_ink():
    source = np.full((100, 160, 3), [70, 95, 130], np.uint8)
    source[:, 80:] += 20
    source[35:38, 100:110] = 250
    output, _, report = clean_line_borders(source, source, source, np.ones(source.shape[:2], bool))
    assert np.array_equal(output, source)
    assert report['changed_pixels_percent'] == 0


@pytest.mark.parametrize('shape', [(1, 1), (1, 80), (3, 5)])
def test_tiny_images_without_supported_ink_bypass(shape):
    source = np.full((*shape, 3), [90, 115, 150], np.uint8)
    output, _, _ = clean_line_borders(source, source, source, np.ones(shape, bool))
    assert np.array_equal(output, source)


@pytest.mark.parametrize('strength', [-1, 101, float('nan')])
def test_invalid_strength_is_rejected(strength):
    source, paint, _, core = seam()
    with pytest.raises(ValueError, match='strength'):
        clean_line_borders(source, source, paint, core, strength=strength)


def test_zero_strength_is_exact():
    source, paint, _, core = seam()
    output, _, _ = clean_line_borders(source, source, paint, core, strength=0)
    assert np.array_equal(output, source)


def test_comparison_reuses_the_same_pyramid_layers_and_color_fit(tmp_path, monkeypatch):
    from stable_shift import engine, reconstruction_comparison as comparison
    from tests.test_finishing import colors, shifted
    calls = []
    actual = comparison.restore_quality
    def restored(reference, edited, options, **kwargs):
        calls.append((edited.size, options))
        return actual(reference, edited, options, **kwargs)
    monkeypatch.setattr(comparison, 'restore_quality', restored)
    monkeypatch.setattr(engine, '_bm3d', lambda rgb, *a: cv2.GaussianBlur(rgb, (3, 3), .5))
    source = Image.fromarray(colors())
    reference = Image.fromarray(shifted(colors()))
    opts = Options(method='CPU BM3D', auto_strength=False, cleanup=50, blotch_strength=70,
                   color_match=True, stroke_strength=100, antialias_strength=100)
    summary = comparison.export_line_border_comparison(reference, source, opts, tmp_path)
    assert len(calls) == 3
    assert all(not opt.color_match and opt.stroke_strength == 0 and opt.antialias_strength == 0 for _, opt in calls)
    assert summary['observed_ink_pixels_changed_after_shared_color'] == 0
    assert summary['normal_run_unchanged'] is True
    with ZipFile(tmp_path/summary['share_zip']) as archive:
        assert {'01_pyramid_v213.png', '02_clean_line_borders.png', 'edited_source.png',
                'color_reference.png', 'line_border_settings_and_timings.json'} <= set(archive.namelist())
    saved = json.loads((tmp_path/'line_border_settings_and_timings.json').read_text())
    assert saved['requested_options']['stroke_strength'] == 100
    assert saved['line_border_cleanup']['strength'] == 100
