"""Behavioral checks for cleanup on already denoised SCUNet pixels."""
from dataclasses import replace
import json
from zipfile import ZipFile

import cv2
import numpy as np
from PIL import Image
import pytest

from stable_shift import scunet_cleanup as cleanup
from stable_shift.engine import Options
from stable_shift.global_color import GlobalColor


def scene():
    h, w = 256, 320
    truth = np.full((h, w, 3), (95, 130, 165), np.uint8)
    truth[:, 160:] = (62, 83, 105)
    # Colored ink, a real shade step, stitch gaps, and a filled feature.
    truth[:, 62:65] = (20, 35, 50)
    for y in range(12, 230, 16):
        truth[y:y+9, 112:114] = (30, 45, 60)
    cv2.ellipse(truth, (245, 180), (27, 18), 0, 0, 360, (18, 24, 30), -1)
    y, x = np.mgrid[:h, :w]
    patches = np.sin(x/13)*np.cos(y/15)
    source = np.uint8(np.clip(truth.astype(float)+patches[..., None]*[5, 3, 6]+.5, 0, 255))
    return source, truth


def test_default_visibly_reduces_broad_patches_without_losing_shade_or_ink():
    source, truth = scene()
    regular, strong, _ = cleanup.cleanup_candidates(source)
    for out, reduction in ((regular, .45), (strong, .25)):
        original = source[30:210, 75:100].astype(float)-truth[30:210, 75:100]
        residual = out[30:210, 75:100].astype(float)-truth[30:210, 75:100]
        assert residual.std() < original.std()*reduction
        # Location/contrast of the hard shade boundary, not a protection-map test.
        before = source[30:130, 150:160].mean()-source[30:130, 160:170].mean()
        after = out[30:130, 150:160].mean()-out[30:130, 160:170].mean()
        assert after > before*.90
        original_ink = np.where(source[100].mean(axis=1) < 60)[0]
        actual_ink = np.where(out[100].mean(axis=1) < 60)[0]
        np.testing.assert_array_equal(actual_ink, original_ink)
        # No forced black ink or black overshoot around a filled nose-like shape.
        assert out.min() >= source.min()
        np.testing.assert_array_equal(out[160:205, 210:280].mean(axis=2) < 45,
                                      source[160:205, 210:280].mean(axis=2) < 45)
        for y in range(12, 220, 16):
            assert out[y+4, 112:114].mean() < 60
            assert out[y+12, 111:115].mean() > 110


def test_bright_smoke_retains_boundary_without_a_new_dark_outline():
    source = np.full((170, 160, 3), 60, np.uint8)
    points = np.int32([[80+22*np.sin(y/19), y] for y in range(15, 155)])
    cv2.polylines(source, [points], False, (105, 105, 105), 20, cv2.LINE_AA)
    regular, strong, _ = cleanup.cleanup_candidates(source)
    for out in (regular, strong):
        assert out.min() >= 60 and out.max() <= 105
        assert np.mean((source[..., 0] >= 83) != (out[..., 0] >= 83)) < .005


def test_smooth_color_gradient_keeps_its_direction_and_span():
    ramp = np.linspace(0, 1, 320)[None, :, None]
    source = np.uint8(np.broadcast_to([80, 110, 150]+ramp*[80, 50, -30], (80, 320, 3)))
    for out in cleanup.cleanup_candidates(source)[:2]:
        left, right = out[:, 15:30].mean(axis=(0, 1)), out[:, -30:-15].mean(axis=(0, 1))
        assert right[0]-left[0] > 55 and right[2]-left[2] < -18
        assert np.diff(out[40, :, 0].astype(int)).min() >= -1


@pytest.mark.parametrize('shape', [(1, 1, 3), (1, 23, 3), (25, 1, 3), (25, 31, 3)])
def test_small_and_flat_images_remain_native_and_exact(shape):
    source = np.full(shape, (16, 89, 233), np.uint8)
    regular, strong, _ = cleanup.cleanup_candidates(source)
    np.testing.assert_array_equal(regular, source)
    np.testing.assert_array_equal(strong, source)


@pytest.mark.parametrize('source', [np.zeros((0, 2, 3), np.uint8), np.zeros((2, 2, 4), np.uint8),
                                    np.zeros((2, 2, 3), float), np.zeros((2, 2), np.uint8)])
def test_invalid_rgb_is_rejected(source):
    with pytest.raises(ValueError, match='uint8 RGB'):
        cleanup.cleanup_candidates(source)


def prepared(monkeypatch, options=None):
    source = Image.fromarray(scene()[0])
    raw = scene()[0]
    calls = []
    def model(rgb, progress):
        calls.append(rgb.copy())
        return raw.copy(), {'device_name': 'Test stub', 'seconds': .1}
    monkeypatch.setattr(cleanup, 'denoise', model)
    options = options or Options(color_match=False, method='CPU BM3D', auto_strength=True,
        noise=0, color_noise=0, cleanup=0, blotch_strength=0, stroke_strength=100, antialias_strength=100)
    return cleanup.prepare_scunet_cleanup(source, source, options), source, options, calls


def test_model_only_zero_and_live_strength_are_reversible_without_the_old_stack(monkeypatch):
    def forbidden(*a, **k):
        pytest.fail('SCUNet cleanup must not invoke classical processing')
    for module, name in [('engine', 'restore_quality'), ('reconstruction', 'pyramid_field'),
                          ('line_reconstruction', 'reconstruct_lines')]:
        monkeypatch.setattr(f'stable_shift.{module}.{name}', forbidden)
    preview, source, _, calls = prepared(monkeypatch)
    assert len(calls) == 1
    np.testing.assert_array_equal(preview.render(0)[0], source)
    monkeypatch.setattr(cleanup, 'cleanup_candidates', forbidden)
    monkeypatch.setattr(cleanup, 'denoise', forbidden)
    monkeypatch.setattr(cleanup, 'fit_scunet_color', forbidden)
    first = np.array(preview.render(73)[0])
    for strength in (25, 100, 200, 0, 73):
        image, report = preview.render(strength)
        assert report['scunet_cleanup']['strength'] == strength
        assert not report['scunet_cleanup']['upstream_reprocessed']
        assert 'line_preservation' not in report
        if strength:
            assert np.mean(np.abs(np.array(image).astype(float)-np.array(source))) > .1
    np.testing.assert_array_equal(preview.render(73)[0], first)
    np.testing.assert_array_equal(preview.render(0)[0], source)
    with pytest.raises(ValueError):
        preview.model_rgb[0, 0] = 0
    _, report = preview.render(100)
    report['scunet']['device_name'] = 'changed'
    assert preview.report['scunet']['device_name'] == 'Test stub'


def test_one_frozen_uniform_transform_applies_to_model_and_both_cleanup_endpoints(monkeypatch):
    raw = scene()[0]
    image = Image.fromarray(raw)
    monkeypatch.setattr(cleanup, 'denoise', lambda *a: (raw.copy(), {'device_name': 'Test stub'}))
    transform = GlobalColor(np.diag([.8, .9, .7]), np.zeros(3), np.full(3, .03))
    fits = []
    def fit(reference, model_rgb, **kwargs):
        fits.append(model_rgb.copy())
        return transform, {'selected_method': 'Robust global'}
    monkeypatch.setattr(cleanup, 'fit_scunet_color', fit)
    regular, strong, _ = cleanup.cleanup_candidates(raw)
    preview = cleanup.prepare_scunet_cleanup(image, image, Options())
    assert len(fits) == 1
    np.testing.assert_array_equal(fits[0], raw)
    for strength, pixels in ((0, raw), (100, regular), (200, strong)):
        np.testing.assert_array_equal(preview.render(strength)[0], transform.apply(pixels))


def test_matching_raw_model_cache_is_reused_but_different_source_is_not(monkeypatch):
    preview, source, options, calls = prepared(monkeypatch)
    updated = replace(options, noise=70, stroke_strength=0)
    other_ref = Image.new('RGB', (81, 73), 'red')
    again = cleanup.prepare_scunet_cleanup(other_ref, source, updated, cached=preview)
    assert len(calls) == 1 and again.report['model_output_reused']
    assert again.report['requested_options']['noise'] == 70
    assert again.report['input_signatures']['reference'] != preview.report['input_signatures']['reference']
    other_source = source.copy()
    other_source.putpixel((0, 0), (0, 0, 0))
    rebuilt = cleanup.prepare_scunet_cleanup(other_ref, other_source, updated, cached=preview)
    assert len(calls) == 2 and not rebuilt.report['model_output_reused']


def test_export_exact_selected_control_inputs_signed_maps_and_actual_strength(tmp_path, monkeypatch):
    preview, source, _, _ = prepared(monkeypatch)
    archive = cleanup.save_scunet_cleanup_test(preview, 135, tmp_path, source, source)
    assert archive.is_file()
    selected, report = preview.render(135)
    np.testing.assert_array_equal(Image.open(tmp_path/'03_selected.png'), selected)
    np.testing.assert_array_equal(Image.open(tmp_path/'00_scunet_only.png'), source)
    saved = json.loads((tmp_path/'scunet_cleanup_settings.json').read_text())
    assert saved['scunet_cleanup']['strength'] == 135
    assert saved['same_color_transform']
    with ZipFile(archive) as z:
        assert set(saved['share_required_files']) <= set(z.namelist())
    maps = preview.diagnostics(selected, report)
    np.testing.assert_array_equal(maps['scunet_cleanup_signed_rgb'],
        np.array(selected).astype(np.int16)-preview.base.astype(np.int16))
    with pytest.raises(ValueError, match='does not match'):
        cleanup.save_scunet_cleanup_test(preview, 100, tmp_path/'stale', Image.new('RGB', source.size, 'red'))
