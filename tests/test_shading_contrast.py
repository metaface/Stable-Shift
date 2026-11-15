import cv2
import numpy as np
import pytest

from stable_shift.global_color import restore_shading_contrast


def rgb(lab):
    return np.uint8(np.clip(cv2.cvtColor(lab.astype(np.float32), cv2.COLOR_LAB2RGB)*255+.5, 0, 255))


def lab(rgb):
    return cv2.cvtColor(rgb.astype(np.float32)/255, cv2.COLOR_RGB2LAB)


@pytest.mark.parametrize('width', [5, 24, 40])
def test_coherent_shadow_contrast_returns_without_reverting_new_colors(width):
    yy, xx = np.indices((96, 288))
    transition = np.tanh((xx-144)/width)
    source = np.empty((96, 288, 3), np.float32)
    source[:, :, 0] = 40+4*transition
    source[:, :, 1:] = [5, 22]
    classic = source.copy()
    classic[:, :, 0] = 42+6*transition
    classic[:, :, 1:] = [9, 17]
    global_lab = source.copy()
    global_lab[:, :, 0] = 42+3*transition
    global_lab[:, :, 1:] = [-4, 9]
    new_rgb, old_rgb = rgb(global_lab), rgb(classic)
    result, report = restore_shading_contrast(rgb(source), old_rgb, new_rgb)
    def edge_contrast(image):
        value = lab(image)[:, :, 0]
        offset = max(7, width//2)
        return float(value[:, 144+offset-2:144+offset+3].mean()-value[:, 144-offset-2:144-offset+3].mean())
    before, after, wanted = [edge_contrast(im) for im in (new_rgb, result, old_rgb)]
    assert after > before*1.5, (before, after, wanted)
    assert abs(wanted-after) < abs(wanted-before)*.6
    # Brightness may change; the successful new a/b colors are retained.
    assert np.percentile(np.abs(lab(result)[:, :, 1:]-lab(new_rgb)[:, :, 1:]), 99) < .65
    assert report['changed_pixels_percent'] > 0
    # Overall exposure/cast should not be replaced with Classic brightness.
    assert np.max(np.abs(result[:, :10].astype(int)-new_rgb[:, :10].astype(int))) <= 1
    assert np.max(np.abs(result[:, -10:].astype(int)-new_rgb[:, -10:].astype(int))) <= 1
    assert abs(float(lab(result)[:, :, 0].mean()-lab(new_rgb)[:, :, 0].mean())) < .5


def test_identity_equal_renderings_and_flat_colors_have_exact_bypasses():
    rng = np.random.default_rng(44)
    source = rng.integers(40, 190, (64, 80, 3), dtype=np.uint8)
    other = np.uint8(np.clip(source.astype(float)*1.03+3, 0, 255))
    for a, b, c in ((source, other, source), (source, other, other)):
        result, report = restore_shading_contrast(a, b, c)
        assert np.array_equal(result, c)
        assert report['changed_pixels_percent'] == 0
    source[:] = [80, 100, 120]
    classic = np.full_like(source, [95, 112, 139])
    global_rgb = np.full_like(source, [91, 110, 135])
    result, _ = restore_shading_contrast(source, classic, global_rgb)
    assert np.array_equal(result, global_rgb)


def test_directionless_fine_grain_does_not_trigger_tonal_restoration():
    noise = np.random.default_rng(59).normal(0, 1, (128, 160, 1))
    source = np.uint8(np.clip(np.full((128, 160, 3), [90, 105, 125])+noise, 0, 255))
    classic = np.uint8(np.clip(np.full((128, 160, 3), [95, 110, 132])+noise*1.6, 0, 255))
    global_rgb = np.uint8(np.clip(np.full((128, 160, 3), [97, 112, 134])+noise, 0, 255))
    result, report = restore_shading_contrast(source, classic, global_rgb)
    before = lab(global_rgb)[:, :, 0]
    after = lab(result)[:, :, 0]
    highpass = lambda value: value-cv2.GaussianBlur(value, (0, 0), 1.5)
    assert np.std(highpass(after)) <= np.std(highpass(before))*1.01
    assert np.max(np.abs(result.astype(int)-global_rgb.astype(int))) <= 1


def test_tonal_restore_rejects_different_image_dimensions():
    source = np.full((20, 30, 3), 120, np.uint8)
    with pytest.raises(ValueError, match='matching dimensions'):
        restore_shading_contrast(source, source[:, :20], source)


def test_complete_color_stage_does_not_accumulate_small_loop_drift():
    from PIL import Image
    from stable_shift.engine import Options, correct_palette
    from tests.test_finishing import colors
    reference = colors()
    value = reference.copy()
    for _ in range(6):
        value = np.uint8(np.clip(value.astype(float)*[.99, .98, .985]+[1, 2, 1]+.5, 0, 255))
        value, _ = correct_palette(Image.fromarray(reference), value, value,
            Options(method='Color only', color_method='Robust global'))
    assert np.abs(value.astype(float)-reference).mean() < 1.5
