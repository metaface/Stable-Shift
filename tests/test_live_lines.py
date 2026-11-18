import json
import numpy as np
import pytest
from PIL import Image
from stable_shift.line_borders import LUMA
from stable_shift.line_reconstruction import reconstruct_lines
from stable_shift.live_lines import LinePreview, result_view, save_line_test, validate_strength


PAINT = np.array([155, 175, 195])
INK = np.array([40, 60, 80])


def scene():
    h, w = 120, 110
    source = np.full((h, w, 3), PAINT, np.uint8)
    rng = np.random.default_rng(10)
    for y in range(h):
        x = 50+rng.integers(-1, 2)
        source[y, x-1:x+2] = INK
        if y % 7 == 0:
            source[y, x-1:x+2] += np.array([12, 25, 8], np.uint8)
    core = np.zeros(source.shape[:2], bool)
    core[:, 44:58] = True
    return source.copy(), source, core


def metrics(image):
    alpha = np.clip(np.mean((PAINT-image)/(PAINT-INK), axis=2), 0, 1)
    mass = alpha.sum(axis=1)
    center = (alpha*np.arange(image.shape[1])).sum(axis=1)/np.maximum(1e-5, mass)
    return float(np.mean(mass[12:-12])), float(np.std(center[12:-12]))


def test_reconstruction_smooths_geometry_without_widening_and_uses_existing_color():
    base, source, core = scene()
    regular, strong, support, report = reconstruct_lines(base, core)
    original_width, original_jitter = metrics(base)
    for image in (regular, strong):
        width, jitter = metrics(image)
        assert jitter < original_jitter*.55  # actual center geometry, not only darker pixels
        assert original_width*.85 < width < original_width*1.10
        assert np.any(image.astype(int) > base.astype(int))  # remove old protrusions
        assert np.any(image.astype(int) < base.astype(int))  # fill the smoothed path
        assert np.all(image.min(axis=(0, 1)) >= INK-1)  # colored ink, no forced black
        np.testing.assert_array_equal(image[~support], base[~support])
    assert report['supersampling'] == 4


def test_stitch_gaps_and_nearby_parallel_lines_do_not_join():
    source = np.full((96, 100, 3), PAINT, np.uint8)
    for y in (8, 30, 52, 74):
        source[y:y+10, 40:42] = INK
        source[y:y+10, 47:49] = INK
    core = np.zeros(source.shape[:2], bool)
    core[:, 37:52] = True
    regular, strong, _, _ = reconstruct_lines(source, core)
    for image in (regular, strong):
        for y in (22, 44, 66):
            np.testing.assert_array_equal(image[y, 38:51], source[y, 38:51])
        for y in (13, 35, 57, 79):
            assert image[y, 40:42].mean() < 130
            assert image[y, 47:49].mean() < 130
            np.testing.assert_array_equal(image[y, 44], PAINT)


def test_shade_step_smoke_edge_and_isolated_dot_are_not_rebuilt_as_lines():
    source = np.full((80, 112, 3), 100, np.uint8)
    source[:, :56] = 160
    source[30, 80] = 25
    regular, strong, _, _ = reconstruct_lines(source, np.ones(source.shape[:2], bool))
    np.testing.assert_array_equal(regular, source)
    np.testing.assert_array_equal(strong, source)


@pytest.mark.parametrize('width', [1, 2, 3])
@pytest.mark.parametrize('gap', [2, 3])
def test_tiny_stitch_gaps_remain_open_at_both_powers(width, gap):
    image = np.full((100, 90, 3), PAINT, np.uint8)
    for y in range(7, 90, 6+gap):
        image[y:y+6, 44:44+width] = INK
    core = np.zeros(image.shape[:2], bool)
    core[:, 40:53] = True
    regular, strong, _, _ = reconstruct_lines(image, core)
    for output in (regular, strong):
        for y in range(7, 80, 6+gap):
            assert output[y+3, 44:44+width].mean() < 110
            np.testing.assert_array_equal(output[y+6+gap//2, 44:44+width], image[y+6+gap//2, 44:44+width])


@pytest.mark.parametrize('shape', ['circle', 'smoke', 'wave'])
def test_curved_bright_smoke_does_not_acquire_new_darker_ink(shape):
    import cv2
    image = np.full((170, 160, 3), 75, np.uint8)
    if shape == 'circle':
        cv2.circle(image, (80, 85), 50, (125, 125, 125), -1)
    else:
        amplitude, period, width = (22, 19, 19) if shape == 'smoke' else (35, 14, 11)
        points = np.int32([[80+amplitude*np.sin(y/period), y] for y in range(15, 155)])
        cv2.polylines(image, [points], False, (125, 125, 125), width, cv2.LINE_AA)
    regular, strong, _, _ = reconstruct_lines(image, np.ones(image.shape[:2], bool))
    for output in (regular, strong):
        assert output.min() >= 75
        assert output.max() <= 126
        if shape != 'wave':
            np.testing.assert_array_equal(output, image)


def preview():
    base, source, core = scene()
    regular, strong, support, report = reconstruct_lines(base, core)
    return LinePreview(base, regular, strong, support,
        {'requested_options': {'noise': 70}, 'line_reconstruction': report})


def test_cached_render_is_visible_below_100_non_cumulative_and_reversible(monkeypatch):
    p = preview()
    def forbidden(*args, **kwargs):
        pytest.fail('Slider called preparation/analysis')
    monkeypatch.setattr('stable_shift.live_lines.reconstruct_lines', forbidden)
    monkeypatch.setattr('stable_shift.engine.restore_quality', forbidden)
    monkeypatch.setattr('stable_shift.reconstruction.pyramid_field', forbidden)
    monkeypatch.setattr('stable_shift.global_color.fit_global_color', forbidden)
    base, _ = p.render(0)
    np.testing.assert_array_equal(base, p.base)
    for strength in (25, 50, 100, 150, 200):
        image, report = p.render(strength)
        assert np.count_nonzero(np.any(np.asarray(image) != p.base, axis=2)) > 50
        assert report['line_preservation']['strength'] == strength
        assert report['line_preservation']['upstream_reprocessed'] is False
    first = np.asarray(p.render(73)[0]).copy()
    p.render(200)
    np.testing.assert_array_equal(p.render(73)[0], first)
    np.testing.assert_array_equal(p.render(0)[0], base)
    with pytest.raises(ValueError):
        p.base[0, 0] = 1
    _, report = p.render(25)
    report['requested_options']['noise'] = 0
    assert p.report['requested_options']['noise'] == 70


@pytest.mark.parametrize('strength', [-1, 201, float('nan'), float('inf')])
def test_invalid_strength(strength):
    with pytest.raises(ValueError):
        validate_strength(strength)


def test_native_view_and_zoom_crop_are_exact():
    data = np.arange(120*160*3, dtype=np.uint8).reshape(120, 160, 3)
    image = Image.fromarray(data)
    view, box = result_view(image, (40, 30), '100%', (.5, .5))
    assert box == (60, 45, 100, 75)
    np.testing.assert_array_equal(view, data[45:75, 60:100])
    view, box = result_view(image, (40, 30), '200%', (0, 1))
    assert box == (0, 105, 20, 120)
    np.testing.assert_array_equal(np.asarray(view)[::2, ::2], data[105:, :20])


def test_export_saves_full_images_actual_setting_and_exact_signed_maps(tmp_path):
    p = preview()
    source = Image.fromarray(scene()[1])
    archive = save_line_test(p, 125, tmp_path, source)
    assert archive.exists()
    selected = Image.open(tmp_path/'02_selected.png')
    assert selected.size == source.size
    report = json.loads((tmp_path/'live_line_settings.json').read_text())
    assert report['line_preservation']['strength'] == 125
    maps = p.diagnostics(selected, report)
    np.testing.assert_array_equal(maps['line_preservation_signed_rgb'],
        np.asarray(selected).astype(np.int16)-p.base.astype(np.int16))


def test_preparation_runs_three_scales_and_slider_never_repeats_them(monkeypatch):
    from dataclasses import asdict
    from stable_shift import reconstruction_comparison as comparison
    from stable_shift.engine import Options
    from stable_shift.live_lines import prepare_line_preview
    source = Image.fromarray(scene()[1])
    calls = []
    def restore(ref, image, options, **kwargs):
        calls.append((image.size, asdict(options)))
        return image.copy(), {'source_line_core': scene()[2], 'report': {'options': asdict(options)}}
    monkeypatch.setattr(comparison, 'restore_quality', restore)
    opts = Options(color_match=False, antialias_strength=50, stroke_strength=100)
    p = prepare_line_preview(source, source, opts)
    assert [size for size, _ in calls] == [(110, 120), (28, 30), (55, 60)]
    assert all(o['antialias_strength'] == o['stroke_strength'] == 0 for _, o in calls)
    for value in (0, 100, 200, 80, 100):
        p.render(value)
    assert len(calls) == 3
    assert p.report['requested_options']['antialias_strength'] == 50
    assert p.report['normal_run_unchanged']


def test_preparation_gates_native_copyback_and_reuses_the_traced_paths(monkeypatch, tmp_path):
    from dataclasses import asdict
    from stable_shift import reconstruction_comparison as comparison
    from stable_shift import reconstruction, line_borders, live_lines
    from stable_shift.engine import Options
    from stable_shift.global_color import GlobalColor
    raw = np.full((100, 140, 3), PAINT, np.uint8)
    raw[10:90, 50:53] = INK
    raw[40, 59] = [30, 40, 50]
    clean_pyramid = raw.copy()
    clean_pyramid[40, 59] = PAINT
    core = np.ones(raw.shape[:2], bool)
    options = Options(color_match=True)
    def layers(*args, **kwargs):
        return tmp_path, 0, raw.copy(), {'source_line_core': core, 'report': {'options': asdict(options)}}, raw.copy(), core, {'half': raw.copy(), 'quarter': raw.copy()}, {}
    monkeypatch.setattr(comparison, '_prepare_layers', layers)
    monkeypatch.setattr(reconstruction, 'pyramid_field', lambda *args, **kwargs: (reconstruction._lab(clean_pyramid), reconstruction._lab(clean_pyramid), None))
    monkeypatch.setattr(line_borders, 'clean_line_borders', lambda previous, *args, **kwargs: (previous.copy(), {}, {}))
    transform = GlobalColor(np.eye(3)*.9, np.zeros(3), np.full(3, .02))
    monkeypatch.setattr(comparison, '_shared_color', lambda *args: (transform, {'selected_method': 'Robust global'}))
    calls = []
    trace = live_lines.trace_stroke_paths
    def traced(*args, **kwargs):
        calls.append(True)
        return trace(*args, **kwargs)
    monkeypatch.setattr(live_lines, 'trace_stroke_paths', traced)
    image = Image.fromarray(raw)
    state = live_lines.prepare_line_preview(image, image, options)
    assert len(calls) == 1
    np.testing.assert_array_equal(state.original_base, transform.apply(raw))
    np.testing.assert_array_equal(np.asarray(state.render(0)[0])[40, 59], transform.apply(clean_pyramid)[40, 59])
    assert state.report['line_reconstruction']['trace_validation']['accepted_paths'] > 0
    for strength in (0, 100, 200, 20, 100):
        state.render(strength)
    assert len(calls) == 1


def test_dirty_baseline_export_and_signed_stage_sum(tmp_path):
    base, _, core = scene()
    dirty = base.copy()
    dirty[50, 56] = 30
    state = LinePreview(base, base, base, core, {'version': '2.18'}, original_base=dirty)
    archive = save_line_test(state, 0, tmp_path, Image.fromarray(dirty))
    assert archive.exists()
    np.testing.assert_array_equal(Image.open(tmp_path/'00_original_preservation_base.png'), dirty)
    np.testing.assert_array_equal(Image.open(tmp_path/'01_reconstruction_off.png'), base)
    result, report = state.render(100)
    maps = state.diagnostics(result, report)
    np.testing.assert_array_equal(maps['source_preservation_signed_rgb']+maps['line_preservation_signed_rgb'],
        np.asarray(result).astype(np.int16)-dirty.astype(np.int16))
    with pytest.raises(ValueError):
        state.original_base[0, 0] = 0
