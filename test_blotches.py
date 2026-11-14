from dataclasses import replace

import cv2
import numpy as np
from PIL import Image
import pytest

from engine import Options, restore_quality, _palette
from frozen_palette import freeze_palette
from surface_normalization import normalize_surfaces


def patch_data(amplitude=2.):
    h, w = 160, 220
    y, x = np.mgrid[:h, :w]
    lab = np.full((h, w, 3), [45, -2, -18], np.float32)
    lab[:, :, 0] += 3*x/w+2*(y/h)**2
    rng = np.random.default_rng(3)
    blotches = cv2.GaussianBlur(rng.normal(0, 1, (h, w)).astype(np.float32), (0, 0), 5)
    blotches /= max(.01, float(blotches.std()))
    dirty = lab.copy()
    dirty[:, :, 0] += blotches*amplitude
    dirty[:, :, 1] += blotches*(amplitude*.7)
    dirty[:, :, 2] -= blotches*(amplitude*.35)
    def rgb(a):
        return np.uint8(np.clip(cv2.cvtColor(a, cv2.COLOR_LAB2RGB)*255+.5, 0, 255))
    return rgb(lab), rgb(dirty)


def test_broad_blotches_removed_while_smooth_shading_remains():
    clean, dirty = patch_data()
    out, maps, report = normalize_surfaces(dirty, 70, 12, 100)
    before = np.mean((dirty.astype(float)-clean)**2)
    after = np.mean((out.astype(float)-clean)**2)
    assert after < before*.4, (before, after)
    assert report['changed_pixels_percent'] > 70
    assert report['mean_rgb_change'] > 1
    assert 'blotch_automatic_amount' in maps


def test_clean_surface_is_exact_and_repeat_processing_does_not_flatten_it():
    clean, _ = patch_data(0)
    current = clean.copy()
    for _ in range(5):
        current, _, report = normalize_surfaces(current, 100, 12, 100)
    assert np.array_equal(current, clean)
    assert report['changed_pixels_percent'] == 0


def test_auto_response_is_lower_for_mild_than_severe_variation():
    clean, mild = patch_data(.1)
    _, severe = patch_data(2)
    _, _, mild_report = normalize_surfaces(mild, 70, 12, 100)
    _, _, severe_report = normalize_surfaces(severe, 70, 12, 100)
    assert severe_report['mean_automatic_amount_percent'] > mild_report['mean_automatic_amount_percent']+20
    assert mild_report['changed_pixels_percent'] < 1


def test_fine_grain_is_not_treated_as_broad_color_contamination():
    rng = np.random.default_rng(4)
    rgb = np.full((180, 180, 3), [80, 110, 140], np.uint8)
    rgb = np.uint8(np.clip(rgb.astype(float)+rng.normal(0, 2, rgb.shape), 0, 255))
    out, _, report = normalize_surfaces(rgb, 70, 12, 100)
    assert report['mean_rgb_change'] < .2


def test_original_core_and_separate_surfaces_remain_exact():
    clean, dirty = patch_data()
    dirty[:, 109] = [10, 15, 20]
    dirty[:, 110:] = np.uint8(np.clip(dirty[:, 110:].astype(float)-25, 0, 255))
    core = np.zeros(dirty.shape[:2], bool)
    core[:, 108:111] = True
    out, maps, _ = normalize_surfaces(dirty, 100, 30, 100, core)
    assert np.array_equal(out[core], dirty[core])
    assert np.all(maps['blotch_boundaries'][core] == 1)
    assert np.mean(out[:, 115:]) < np.mean(out[:, :104])-10


def test_off_bypasses_exactly():
    _, dirty = patch_data()
    out, maps, report = normalize_surfaces(dirty, 0)
    assert np.array_equal(out, dirty)
    assert not maps and report['changed_pixels_percent'] == 0


@pytest.mark.parametrize('shape', [(1, 1), (3, 5), (1, 200)])
def test_small_or_narrow_regions_are_safe(shape):
    rgb = np.full((*shape, 3), [80, 110, 140], np.uint8)
    out, _, _ = normalize_surfaces(rgb, 70)
    assert np.array_equal(out, rgb)


def test_frozen_palette_matches_original_v21_output():
    y, x = np.mgrid[:90, :160]
    base = np.uint8(np.stack((40+x, 60+y, 70+x//2+y//2), axis=-1))
    ref = Image.fromarray(np.uint8(np.clip(base.astype(float)*.7+25, 0, 255))).resize((80, 45))
    assert np.array_equal(freeze_palette(ref, base).apply(base), _palette(ref, base))


def test_engine_keeps_protected_rgb_and_signed_stage_accounting(monkeypatch):
    import engine
    from test_v21 import weak_cabin
    rgb = weak_cabin()
    y, x = np.mgrid[:rgb.shape[0], :rgb.shape[1]]
    noisy = rgb.copy()
    mask = (y > 72) & (x > 35) & (np.min(rgb, axis=2) > 40)
    noisy[mask] = np.uint8(np.clip(noisy[mask].astype(float)+2*np.sin(x[mask]/3)[:, None], 0, 255))
    monkeypatch.setattr(engine, '_bm3d', lambda a, *args: cv2.GaussianBlur(a, (3, 3), .5))
    ref = Image.fromarray(np.uint8(np.clip(noisy.astype(float)*1.05+5, 0, 255)))
    opts = Options(method='CPU BM3D', cleanup=60, blotch_strength=70)
    result, maps = restore_quality(ref, Image.fromarray(noisy), opts)
    baseline, before_maps = restore_quality(ref, Image.fromarray(noisy), replace(opts, blotch_strength=0))
    core = maps['source_line_core'] > .5
    assert np.any(core)
    assert np.array_equal(np.asarray(result)[core], np.asarray(baseline)[core])
    assert np.array_equal(maps['local_cleanup_signed_rgb']+maps['blotch_signed_rgb'], maps['cleanup_signed_rgb'])
    total = maps['denoise_signed_rgb']+maps['cleanup_signed_rgb']+maps['palette_signed_rgb']
    assert np.array_equal(total, maps['total_signed_rgb'])


def test_reference_cannot_supply_structure_to_broad_stage():
    _, dirty = patch_data()
    edited = Image.fromarray(dirty)
    opts = Options(method='Region cleanup only', cleanup=0, blotch_strength=70, color_match=False)
    a, ma = restore_quality(Image.new('RGB', (12, 19), 'red'), edited, opts)
    b, mb = restore_quality(Image.new('RGB', (31, 17), 'blue'), edited, opts)
    assert np.array_equal(a, b)
    assert np.array_equal(ma['blotch_boundaries'], mb['blotch_boundaries'])


def test_blotch_comparison_runs_denoiser_once_and_holds_palette_fixed(tmp_path, monkeypatch):
    import engine
    from blotch_comparison import export_blotch_comparison
    from test_v21 import weak_cabin
    rgb = weak_cabin()
    calls = []
    def denoise(a, *args):
        calls.append(a.shape)
        return a.copy()
    monkeypatch.setattr(engine, '_bm3d', denoise)
    image = Image.fromarray(rgb)
    summary = export_blotch_comparison(image, image, Options(method='CPU BM3D', cleanup=0, blotch_strength=70), tmp_path)
    assert len(calls) == 1
    assert summary['shared_denoiser_ran_once'] is True
    assert summary['line_preservation_check']['source_protected_pixels'] > 0
    assert summary['line_preservation_check']['changed_before_palette'] == 0
    assert summary['line_preservation_check']['changed_after_palette'] == 0
    for name in ('00_v21_before_palette.png', '01_broad_before_palette.png', '02_v21_same_palette.png', '03_broad_same_palette.png'):
        assert Image.open(tmp_path/name).size == image.size
    assert len(list(tmp_path.glob('blotch_crop_*_100percent.png'))) == 3


def test_nonlinear_shadow_keeps_its_tonal_separation_at_maximum_range():
    # A curved, broad shadow is not a noisy flat surface. V2.3's regional fit
    # can flatten this even though its protected-pixel count remains perfect.
    y, x = np.mgrid[:180, :400]
    lab = np.full((*x.shape, 3), [45., -2., -18.], np.float32)
    lab[:, :, 0] += 12*np.tanh((x-180)/22)
    source = np.uint8(np.clip(cv2.cvtColor(lab, cv2.COLOR_LAB2RGB)*255+.5, 0, 255))
    output, _, _ = normalize_surfaces(source, 100, 40, 100)
    before, after = [cv2.cvtColor(z.astype(np.float32)/255, cv2.COLOR_RGB2LAB)[:, :, 0]
                     for z in (source, output)]
    contrast_before = before[:, 240:].mean()-before[:, :100].mean()
    contrast_after = after[:, 240:].mean()-after[:, :100].mean()
    assert contrast_after >= contrast_before*.98
    assert np.mean(np.abs(after-before)) < .6


def test_maximum_correction_cannot_introduce_local_channel_extrema():
    _, source = patch_data(5.)
    output, _, _ = normalize_surfaces(source, 100, 40, 100)
    assert not np.array_equal(output, source)
    kernel = np.ones((49, 49), np.uint8)
    lower = cv2.erode(source, kernel, borderType=cv2.BORDER_REFLECT)
    upper = cv2.dilate(source, kernel, borderType=cv2.BORDER_REFLECT)
    assert np.all(output >= lower) and np.all(output <= upper)


def test_weak_stroke_contrast_and_nearby_colors_survive_maximum_cleanup():
    # RGB equality on the stroke alone is insufficient. Its immediate surround
    # must remain stable too, or the unchanged stroke can fade/disappear.
    _, source = patch_data(3.)
    source[:, 109:111] = np.maximum(0, source[:, 109:111].astype(int)-8).astype(np.uint8)
    core = np.zeros(source.shape[:2], bool)
    core[:, 108:112] = True
    output, maps, _ = normalize_surfaces(source, 100, 40, 100, core)
    assert not np.array_equal(output, source)
    assert np.array_equal(output[core], source[core])
    near = cv2.dilate(core.astype(np.uint8), np.ones((7, 7), np.uint8)).astype(bool) & ~core
    assert np.max(np.abs(output.astype(int)-source.astype(int))[near]) <= 1
    assert maps['blotch_boundary_taper'][near].max() < .1


def test_loop_passes_do_not_accumulate_flattening_on_clean_nonlinear_shading():
    y, x = np.mgrid[:160, :220]
    lab = np.full((*x.shape, 3), [45., -2., -18.], np.float32)
    lab[:, :, 0] += 3*np.sin(x/70)+2*np.cos(y/90)
    source = np.uint8(np.clip(cv2.cvtColor(lab, cv2.COLOR_LAB2RGB)*255+.5, 0, 255))
    current = source.copy()
    for _ in range(5):
        current, _, _ = normalize_surfaces(current, 100, 40, 100)
    assert np.mean(np.abs(current.astype(float)-source.astype(float))) < .1


@pytest.mark.parametrize('with_mask', [False, True])
def test_saved_pair_replay_states_its_mask_and_does_not_rerun_generation(tmp_path, with_mask):
    import json
    from validate_blotch_pair import replay
    _, dirty = patch_data()
    dirty[:, 90:93] = 10
    core = np.zeros(dirty.shape[:2], bool)
    core[:, 89:94] = True
    previous, _, _ = normalize_surfaces(dirty, 100, 40, 100, core)
    Image.fromarray(dirty).save(tmp_path/'00_v21_before_palette.png')
    Image.fromarray(previous).save(tmp_path/'01_broad_before_palette.png')
    Image.fromarray(core.astype(np.uint8)*255).save(tmp_path/'shared_source_line_core.png')
    (tmp_path/'blotch_settings_and_timings.json').write_text(json.dumps({'options': {
        'blotch_strength': 100, 'cleanup_range': 40, 'cleanup_luma': 100}}))
    report = replay(tmp_path, tmp_path/'replay', tmp_path/'shared_source_line_core.png' if with_mask else None)
    assert report['frozen_pixels_changed'] == 0
    assert report['candidate_local_channel_envelope_violations'] == 0
    assert ('Supplied original' in report['mask_note']) == with_mask
    assert (tmp_path/'replay/04_local_before_palette.png').exists()
