from dataclasses import replace
import json
from zipfile import ZipFile

import cv2
import numpy as np
from PIL import Image
import pytest

from stable_shift.engine import Options
from stable_shift.reconstruction import reconstruct


def layers(rgb):
    h, w = rgb.shape[:2]
    return [cv2.resize(rgb, ((w+d-1)//d, (h+d-1)//d), interpolation=cv2.INTER_AREA) for d in (2, 4)]


def gradient():
    h, w = 192, 256
    y, x = np.mgrid[:h, :w]
    lab = np.full((h, w, 3), [60., 5., -10.], np.float32)
    lab[:, :, 1] += 8*x/(w-1)
    return np.uint8(np.clip(cv2.cvtColor(lab, cv2.COLOR_LAB2RGB)*255+.5, 0, 255))


def test_supported_color_gradient_is_a_smooth_model_not_native_texture():
    clean = gradient()
    half, quarter = layers(clean)
    noisy = np.uint8(np.clip(clean.astype(float)+np.random.default_rng(9).normal(0, 3, clean.shape), 0, 255))
    outputs, maps, report = reconstruct(noisy, half, quarter)
    assert report['gradient_regions'] > 0
    assert maps['reconstruction_gradient_regions'].mean() > .5
    solid_error = np.mean((outputs['hard'].astype(float)-clean)**2)
    gradient_error = np.mean((outputs['gradients'].astype(float)-clean)**2)
    assert gradient_error < solid_error*.5, (solid_error, gradient_error)
    assert gradient_error < np.mean((noisy.astype(float)-clean)**2)*.2
    # Every solid paint region has precisely one RGB value.
    for group in np.unique(maps['reconstruction_regions']):
        if group:
            assert len(np.unique(outputs['hard'][maps['reconstruction_regions'] == group], axis=0)) == 1


def test_bright_texture_permission_vetoes_gradient_exception():
    rgb = gradient()
    outputs, maps, report = reconstruct(rgb, *layers(rgb), texture_permission=np.ones(rgb.shape[:2], np.float32))
    assert report['gradient_regions'] == 0
    assert not np.any(maps['reconstruction_gradient_regions'])
    assert np.array_equal(outputs['hard'], outputs['gradients'])


def test_all_modes_retain_colored_ink_stitches_and_clean_their_interiors():
    clean = np.full((193, 257, 3), [85, 120, 165], np.uint8)
    rng = np.random.default_rng(11)
    full = np.uint8(np.clip(clean.astype(float)+rng.normal(0, 6, clean.shape), 0, 255))
    core = np.zeros(clean.shape[:2], bool)
    core[:, 40] = True
    for y in (20, 35, 50):
        core[y, 80:90] = True
    full[core] = [25, 36, 61]
    outputs, _, _ = reconstruct(full, *layers(clean), core)
    free = ~cv2.dilate(core.astype(np.uint8), np.ones((9, 9), np.uint8)).astype(bool)
    before = np.mean((full[free].astype(float)-clean[free])**2)
    for output in outputs.values():
        assert output.shape == full.shape
        assert np.array_equal(output[core], full[core])
        assert np.mean((output[free].astype(float)-clean[free])**2) < before*.05
        assert np.all(output[26, 82:88] > 70)  # Paint remains in the stitch gap.


def test_uninked_shading_step_survives_reconstruction():
    rgb = np.full((160, 240, 3), [95, 115, 140], np.uint8)
    rgb[:, 120:] += 12
    outputs, _, _ = reconstruct(rgb, *layers(rgb))
    original = cv2.cvtColor(rgb.astype(np.float32)/255, cv2.COLOR_RGB2LAB)[:, :, 0]
    before = original[:, 125:140].mean()-original[:, 100:115].mean()
    for output in outputs.values():
        lightness = cv2.cvtColor(output.astype(np.float32)/255, cv2.COLOR_RGB2LAB)[:, :, 0]
        after = lightness[:, 125:140].mean()-lightness[:, 100:115].mean()
        assert after > before*.9


def test_guided_color_enlargement_cannot_invent_paint_outside_coarse_range():
    from stable_shift.reconstruction import _up
    coarse = np.zeros((8, 8, 3), np.float32)
    coarse[:, :, 0] = np.arange(8)[None]*6+20
    coarse[:, :, 1] = 8
    coarse[:, :, 2] = -12
    guide = np.zeros((64, 64, 3), np.float32)
    guide[:, :, 0] = np.random.default_rng(44).uniform(10, 90, (64, 64))
    up = _up(coarse, guide)
    assert up[:, :, 0].min() >= 20 and up[:, :, 0].max() <= 62
    assert np.allclose(up[:, :, 1], 8)
    assert np.allclose(up[:, :, 2], -12)


def test_unrelated_fine_noise_does_not_create_a_supported_gradient():
    rng = np.random.default_rng(5)
    half = np.uint8(np.clip(np.full((96, 128, 3), [110, 135, 160])+rng.normal(0, .5, (96, 128, 3)), 0, 255))
    quarter = np.uint8(np.clip(np.full((48, 64, 3), [110, 135, 160])+rng.normal(0, .5, (48, 64, 3)), 0, 255))
    full = np.full((192, 256, 3), [110, 135, 160], np.uint8)
    _, _, report = reconstruct(full, half, quarter)
    assert report['gradient_regions'] == 0


def test_native_sparkle_halo_is_not_copied_back_into_clean_coarse_paint():
    clean = np.full((192, 256, 3), [230, 235, 240], np.uint8)
    y, x = np.mgrid[:192, :256]
    halo = np.exp(-((x-110)**2+(y-90)**2)/(2*8**2))
    full = np.uint8(np.clip(clean.astype(float)+halo[:, :, None]*[-18, -10, 0], 0, 255))
    core = np.zeros(clean.shape[:2], bool)
    core[88:93, 109:112] = True
    core[89:92, 108:113] = True
    full[core] = 255
    outputs, _, _ = reconstruct(full, *layers(clean), core)
    for output in outputs.values():
        assert np.array_equal(output[core], full[core])
        assert np.abs(output[~core].astype(float)-clean[~core]).max() <= 1


def test_gradual_halo_surviving_coarse_layers_is_not_a_new_solid_paint_region():
    clean = np.full((192, 256, 3), [230, 235, 240], np.uint8)
    y, x = np.mgrid[:192, :256]
    halo = np.exp(-((x-110)**2+(y-90)**2)/(2*14**2))
    full = np.uint8(np.clip(clean.astype(float)+halo[:, :, None]*[-16, -10, 0], 0, 255))
    core = np.zeros(clean.shape[:2], bool)
    core[88:93, 109:112] = True
    full[core] = 255
    outputs, _, report = reconstruct(full, *layers(full), core)
    for name in ('hard', 'gradients'):
        assert np.abs(outputs[name][~core].astype(float)-clean[~core]).max() <= 1
    assert report['gradient_regions'] == 0


@pytest.mark.parametrize('shape', [(1, 1), (1, 25), (3, 5)])
def test_small_images_and_all_protected_images_are_safe(shape):
    full = np.full((*shape, 3), [110, 135, 160], np.uint8)
    output, _, _ = reconstruct(full, *layers(full), np.ones(shape, bool))
    for value in output.values():
        assert np.array_equal(value, full)


@pytest.mark.parametrize('automatic', [False, True])
def test_comparison_uses_independent_layers_and_shared_colors_with_finishing_off(tmp_path, monkeypatch, automatic):
    from stable_shift import engine
    from stable_shift import reconstruction_comparison as comparison
    from tests.test_finishing import colors, shifted
    calls = []
    backend_calls = []
    run = comparison.restore_quality
    def restored(reference, image, options, **kwargs):
        calls.append((image.size, options))
        return run(reference, image, options, **kwargs)
    def backend(rgb, noise, chroma):
        backend_calls.append(rgb.shape)
        return cv2.GaussianBlur(rgb, (3, 3), .5)
    monkeypatch.setattr(comparison, 'restore_quality', restored)
    monkeypatch.setattr(engine, '_bm3d', backend)
    source = Image.fromarray(colors())
    reference = Image.fromarray(shifted(colors()))
    options = Options(method='CPU BM3D', color_match=True, auto_strength=automatic,
                      color_method='Classic', cleanup=60, blotch_strength=70,
                      antialias_strength=100, stroke_strength=100)
    summary = comparison.export_reconstruction_comparison(reference, source, options, tmp_path)
    assert [size for size, _ in calls] == [source.size, ((source.width+3)//4, (source.height+3)//4),
                                                       ((source.width+1)//2, (source.height+1)//2)]
    assert len(backend_calls) <= 3
    if not automatic:
        assert len(backend_calls) == 3
    for _, opt in calls:
        assert opt.color_match is False and opt.antialias_strength == 0 and opt.stroke_strength == 0
    for _, opt in calls[1:]:
        assert opt.blotch_strength == 0 and opt.source_guard is False
    assert summary['normal_run_unchanged'] is True
    for check in summary['checks'].values():
        assert check['protected_pixels_changed_before_color'] == 0
        assert check['protected_pixels_changed_after_shared_color'] == 0
    with ZipFile(tmp_path/summary['share_zip']) as archive:
        assert {'01_accepted.png', '02_pyramid.png', '03_hard_colors.png', '04_hard_with_gradients.png',
                'edited_source.png', 'color_reference.png'} <= set(archive.namelist())
        saved = json.loads(archive.read('reconstruction_settings_and_timings.json'))
        assert saved['requested_options']['stroke_strength'] == 100
    if summary['color_correction']['selected_method'] == 'Robust global':
        expected, _ = run(reference, source, replace(options, color_method='Robust global', antialias_strength=0, stroke_strength=0))
        assert np.array_equal(np.asarray(expected), np.asarray(Image.open(tmp_path/'01_accepted.png')))


def test_comparison_does_not_apply_spatial_reference_field_when_global_fit_is_rejected(tmp_path):
    from stable_shift.reconstruction_comparison import export_reconstruction_comparison
    source = Image.new('RGB', (80, 72), (100, 125, 150))
    reference = np.full((72, 80, 3), [240, 20, 90], np.uint8)
    reference[::4] = 0
    summary = export_reconstruction_comparison(Image.fromarray(reference), source,
        Options(method='Region cleanup only', color_match=True), tmp_path)
    assert summary['color_correction']['selected_method'] == 'Off'
    for name in ('01_accepted.png', '02_pyramid.png', '03_hard_colors.png', '04_hard_with_gradients.png'):
        output = np.asarray(Image.open(tmp_path/name))
        assert np.abs(output.astype(float)-np.asarray(source)).max() <= 1
