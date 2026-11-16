import json
import numpy as np
import pytest
from PIL import Image

from stable_shift.live_lines import (LinePreview, LUMA, recovery_endpoints,
    result_view, save_line_test, validate_strength)


def scene():
    source = np.full((80, 112, 3), (130, 155, 180), np.uint8)
    source[:, 48:50] = (36, 60, 85)  # colored ink, not black
    source[:, 47] = source[:, 50] = (95, 120, 145)
    core = np.zeros(source.shape[:2], bool)
    core[:, 45:53] = True
    base = np.full_like(source, (130, 155, 180))
    base[:, 48:50] = (68, 90, 112)  # a faded stroke after reconstruction
    return base, source, core


def test_live_recovers_actual_colored_ink_and_leaves_lighter_fringe():
    base, source, core = scene()
    source[:, 46] = (155, 185, 200)
    native, strong, support = recovery_endpoints(base, source, core)
    assert support[30, 48]
    np.testing.assert_array_equal(native[30, 48], source[30, 48])
    np.testing.assert_array_equal(native[:, 46], base[:, 46])
    np.testing.assert_array_equal(strong[:, 46], base[:, 46])
    assert np.all(strong[30, 47] >= (36, 60, 85))
    assert np.any(strong != native)
    np.testing.assert_array_equal(native[~core], base[~core])
    np.testing.assert_array_equal(strong[~core], base[~core])


def test_no_recovery_on_shading_step_or_isolated_noise_dot():
    source = np.full((80, 112, 3), 160, np.uint8)
    source[:, :56] = 80
    source[30, 80] = 25
    base = np.full_like(source, 180)
    native, strong, _ = recovery_endpoints(base, source, np.ones(source.shape[:2], bool))
    np.testing.assert_array_equal(native, base)
    np.testing.assert_array_equal(strong, base)


def preview():
    base, source, core = scene()
    native, strong, support = recovery_endpoints(base, source, core)
    return LinePreview(base, native, strong, support, {'requested_options': {'noise': 70}})


def test_cached_render_is_non_cumulative_reversible_and_monotonic(monkeypatch):
    p = preview()
    def forbidden(*args, **kwargs):
        pytest.fail('Slider called preparation/analysis')
    monkeypatch.setattr('stable_shift.live_lines.recovery_endpoints', forbidden)
    monkeypatch.setattr('stable_shift.engine.restore_quality', forbidden)
    monkeypatch.setattr('stable_shift.reconstruction.pyramid_field', forbidden)
    monkeypatch.setattr('stable_shift.global_color.fit_global_color', forbidden)
    base, _ = p.render(0)
    np.testing.assert_array_equal(base, p.base)
    previous = np.asarray(base).astype(float)@LUMA
    for strength in (25, 50, 100, 150, 200):
        image, report = p.render(strength)
        light = np.asarray(image).astype(float)@LUMA
        assert np.all(light <= previous+1)
        previous = light
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
    assert [size for size, _ in calls] == [(112, 80), (28, 20), (56, 40)]
    assert all(o['antialias_strength'] == o['stroke_strength'] == 0 for _, o in calls)
    for value in (0, 100, 200, 80, 100):
        p.render(value)
    assert len(calls) == 3
    assert p.report['requested_options']['antialias_strength'] == 50
    assert p.report['normal_run_unchanged']
