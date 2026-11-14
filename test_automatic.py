from dataclasses import replace
import json
from zipfile import ZipFile

import cv2
import numpy as np
from PIL import Image
import pytest

from automatic_strength import estimate_strength, limit_cleanup
from engine import Options, restore_quality
from auto_comparison import export_auto_comparison


def to_rgb(lab):
    return np.uint8(np.clip(cv2.cvtColor(lab.astype(np.float32), cv2.COLOR_LAB2RGB)*255+.5, 0, 255))


def mottled(colored=True):
    rng = np.random.default_rng(31)
    y, x = np.mgrid[:128, :160]
    lab = np.full((*x.shape, 3), [48., -3., -16.], np.float32)
    lab[:, :, 0] += x/160*2+y/128
    noise = cv2.GaussianBlur(rng.normal(0, 1, x.shape).astype(np.float32), (0, 0), 4.)
    noise /= noise.std()
    dirty = lab.copy()
    dirty[:, :, 0] += noise*1.8
    if colored:
        dirty[:, :, 1] += noise*1.4
        dirty[:, :, 2] -= noise*1.4
    return to_rgb(lab), to_rgb(dirty)


def ceilings(**changes):
    return replace(Options(method='CPU BM3D', noise=100, color_noise=100,
        cleanup=100, cleanup_luma=100, cleanup_range=40, blotch_strength=100,
        auto_strength=True, color_match=False), **changes)


def test_colored_blotching_authorizes_more_luminance_cleanup_than_gray_structure():
    _, color = mottled(True)
    _, gray = mottled(False)
    _, cm, _ = estimate_strength(color, ceilings())
    _, gm, _ = estimate_strength(gray, ceilings())
    assert cm['auto_luminance_strength'].mean() > gm['auto_luminance_strength'].mean()+.15
    assert gm['auto_luminance_strength'].mean() < .03


def test_fine_noise_response_increases_and_never_exceeds_requested_ceilings():
    rng = np.random.default_rng(9)
    lab = np.full((96, 120, 3), [48., -3., -16.], np.float32)
    low = to_rgb(lab+rng.normal(0, .15, lab.shape).astype(np.float32))
    high = to_rgb(lab+rng.normal(0, 4, lab.shape).astype(np.float32))
    _, _, a = estimate_strength(low, ceilings())
    effective, _, b = estimate_strength(high, ceilings(noise=12, color_noise=7))
    assert b['fine_sigma_lab'][0] > a['fine_sigma_lab'][0]+2
    assert 0 < effective.noise <= 12 and 0 < effective.color_noise <= 7
    assert a['effective_noise'] == a['effective_color_noise'] == 0


def test_clean_shaded_input_remains_exact_over_repeated_automatic_passes(monkeypatch):
    import engine
    y, x = np.mgrid[:96, :120]
    lab = np.full((*x.shape, 3), [48., -3., -16.], np.float32)
    lab[:, :, 0] += x/120*3+y/96*2
    source = to_rgb(lab)
    def unexpected(*args):
        pytest.fail('Clean source should skip the fine denoiser.')
    monkeypatch.setattr(engine, '_bm3d', unexpected)
    current = Image.fromarray(source)
    for _ in range(3):
        current, maps = restore_quality(current, current, ceilings())
    assert np.array_equal(current, source)
    assert maps['report']['automatic_strength']['backend_skipped'] is True


def test_permission_fields_taper_beside_source_protection_and_stay_bounded():
    _, source = mottled()
    core = np.zeros(source.shape[:2], bool)
    core[:, 75:78] = True
    _, maps, _ = estimate_strength(source, ceilings(), core)
    for name in ('auto_luminance_strength', 'auto_chroma_strength'):
        field = maps[name]
        assert np.all(np.isfinite(field)) and field.min() >= 0 and field.max() <= 1
        assert not np.any(field[core])
        assert field[:, 74].max() < .01


def test_limiting_can_bypass_exactly_or_keep_luminance_and_protected_rgb():
    before = np.full((30, 40, 3), [80, 110, 140], np.uint8)
    candidate = np.full_like(before, [110, 115, 125])
    zero = np.zeros(before.shape[:2], np.float32)
    one = np.ones_like(zero)
    assert np.array_equal(limit_cleanup(before, candidate, zero, zero), before)
    assert np.array_equal(limit_cleanup(before, candidate, one, one), candidate)
    core = np.zeros_like(zero, bool);core[:, 20] = True
    output = limit_cleanup(before, candidate, zero, one, core)
    assert np.array_equal(output[core], before[core])
    original_l = cv2.cvtColor(before.astype(np.float32)/255, cv2.COLOR_RGB2LAB)[:, :, 0]
    output_l = cv2.cvtColor(output.astype(np.float32)/255, cv2.COLOR_RGB2LAB)[:, :, 0]
    assert np.abs(original_l-output_l).max() < .3


def test_backend_gets_effective_strengths_and_actual_stage_residuals_add_up(monkeypatch):
    import engine
    rng = np.random.default_rng(5)
    source = np.uint8(np.clip(np.full((96, 120, 3), [90, 110, 130])+rng.normal(0, 5, (96, 120, 3)), 0, 255))
    source[42:45, 10:110] = 20
    calls = []
    def backend(rgb, noise, color):
        calls.append((noise, color))
        return cv2.GaussianBlur(rgb, (3, 3), .6)
    monkeypatch.setattr(engine, '_bm3d', backend)
    out, maps = restore_quality(Image.fromarray(source), Image.fromarray(source), ceilings())
    report = maps['report']['automatic_strength']
    assert calls == [(report['effective_noise'], report['effective_color_noise'])]
    assert calls[0][0] < 100 and calls[0][1] < 100
    assert not np.array_equal(out, source)
    core = maps['source_line_core'] > .5
    assert np.array_equal(np.array(out)[core], source[core])
    assert np.array_equal(maps['unprotected_denoise_signed_rgb']+maps['guard_signed_rgb']+
        maps['auto_denoise_limit_signed_rgb'], maps['denoise_signed_rgb'])
    assert np.array_equal(maps['local_cleanup_signed_rgb']+maps['blotch_signed_rgb'], maps['cleanup_signed_rgb'])
    assert np.array_equal(maps['denoise_signed_rgb']+maps['cleanup_signed_rgb']+maps['palette_signed_rgb'], maps['total_signed_rgb'])


def test_reference_cannot_change_automatic_detection_or_structure():
    _, source = mottled()
    image = Image.fromarray(source)
    opts = ceilings(method='Region cleanup only')
    a, am = restore_quality(Image.new('RGB', (12, 19), 'red'), image, opts)
    b, bm = restore_quality(Image.new('RGB', (31, 17), 'blue'), image, opts)
    assert np.array_equal(a, b)
    for key in ('auto_luminance_strength', 'auto_chroma_strength', 'source_line_core'):
        assert np.array_equal(am[key], bm[key])


def test_automatic_reduces_known_colored_blotches_without_a_fine_backend():
    clean, source = mottled()
    out, _ = restore_quality(Image.fromarray(source), Image.fromarray(source), ceilings(method='Region cleanup only'))
    old_error = np.mean((source.astype(float)-clean)**2)
    new_error = np.mean((np.array(out).astype(float)-clean)**2)
    # The unchanged source tracer protects some smooth mottling too. Require
    # useful error reduction without claiming this conservative mode removes
    # most of a correlated pattern that is ambiguous with real shading.
    assert new_error < old_error*.95, (old_error, new_error)


def test_actual_cpu_automatic_denoising_reduces_known_random_noise():
    rng = np.random.default_rng(32)
    clean = np.full((48, 48, 3), [90, 110, 130], np.uint8)
    source = np.uint8(np.clip(clean.astype(float)+rng.normal(0, 6, clean.shape), 0, 255))
    out, _ = restore_quality(Image.fromarray(source), Image.fromarray(source), ceilings())
    assert np.mean((np.array(out).astype(float)-clean)**2) < np.mean((source.astype(float)-clean)**2)*.5


def mixed_correlated_source():
    """Known colored contamination beside legitimate gray low-contrast detail."""
    rng = np.random.default_rng(81)
    y, x = np.mgrid[:256, :384]
    clean = np.full((*x.shape, 3), [48., -3., -16.], np.float32)
    clean[:, 192:] = [48., 0., 0.]
    clean[:, 192:, 0] += np.sin(y[:, 192:]/19.)*1.5
    clean[55:200, 265:320, 0] += 3.
    noise = cv2.GaussianBlur(rng.normal(0, 1, x.shape).astype(np.float32), (0, 0), 4.)
    noise /= noise.std()
    dirty = clean.copy()
    dirty[:, :192, 0] += noise[:, :192]*1.8+np.sin(x[:, :192]*np.pi/4.)*.8
    dirty[:, :192, 1] += noise[:, :192]*1.4
    dirty[:, :192, 2] -= noise[:, :192]*1.4
    return to_rgb(clean), to_rgb(dirty)


def test_correlated_noise_can_trigger_backend_despite_small_native_scatter():
    _, source = mixed_correlated_source()
    effective, maps, report = estimate_strength(source, ceilings())
    assert report['fine_sigma_lab'][0] < .5
    assert max(report['fine_sigma_lab'][1:]) < 1.275
    assert not report['backend_skipped']
    assert effective.noise > 10
    assert report['correlated_equivalent_sigma_lab'][0] > 1
    gray = maps['auto_denoise_luminance_strength'][80:175, 250:350]
    assert gray.max() == 0


def test_backend_spatial_limits_retain_gray_detail_beside_colored_contamination(monkeypatch):
    import engine
    _, source = mixed_correlated_source()
    calls = []
    def deliberately_destructive_candidate(rgb, noise, color):
        calls.append((noise, color))
        return cv2.GaussianBlur(rgb, (0, 0), 15.)
    monkeypatch.setattr(engine, '_bm3d', deliberately_destructive_candidate)
    out, maps = restore_quality(Image.fromarray(source), Image.fromarray(source),
        ceilings(source_guard=False))
    gray = np.s_[80:175, 250:350]
    assert calls and calls[0][0] > 0
    assert np.array_equal(np.array(out)[gray], source[gray])
    assert np.any(maps['auto_denoise_limit_signed_rgb'][gray] != 0)


def test_actual_cpu_reduces_correlated_colored_noise_and_keeps_neighboring_gray_detail():
    clean, source = mixed_correlated_source()
    out, _ = restore_quality(Image.fromarray(source), Image.fromarray(source),
        ceilings(source_guard=False))
    color = np.s_[32:224, 24:160]
    gray = np.s_[80:175, 250:350]
    before = np.mean((source[color].astype(float)-clean[color])**2)
    after = np.mean((np.array(out)[color].astype(float)-clean[color])**2)
    assert after < before*.6, (before, after)
    assert np.array_equal(np.array(out)[gray], source[gray])


def test_comparison_runs_both_selected_strengths_and_freezes_palette(tmp_path, monkeypatch):
    import engine
    rng = np.random.default_rng(40)
    source = np.uint8(np.clip(np.full((64, 80, 3), [90, 110, 130])+rng.normal(0, 4, (64, 80, 3)), 0, 255))
    calls = []
    def backend(rgb, noise, color):
        calls.append((noise, color))
        return cv2.GaussianBlur(rgb, (3, 3), .5)
    monkeypatch.setattr(engine, '_bm3d', backend)
    image = Image.fromarray(source)
    ref = Image.fromarray(np.uint8(np.clip(source.astype(float)*.8+20, 0, 255)))
    report = export_auto_comparison(ref, image, ceilings(color_match=True), tmp_path)
    assert len(calls) == 2 and calls[0] == (100, 100)
    assert calls[1][0] < 100 and calls[1][1] < 100
    assert report['manual']['automatic_strength']['enabled'] is False
    assert report['automatic']['automatic_strength']['enabled'] is True
    assert report['source_protection_check']['identical_source_masks'] is True
    assert report['source_protection_check']['changed_after_palette'] == 0
    with ZipFile(tmp_path/report['share_zip']) as archive:
        names = archive.namelist()
        assert 'color_reference.png' in names and 'edited_source.png' in names
        assert '03_auto_same_palette.png' in names
        assert not any(name.endswith('.npz') for name in names)
        saved = json.loads(archive.read('auto_settings_and_timings.json'))
        assert saved['automatic']['effective_options']['color_match'] is True


def test_manual_cached_candidate_cannot_be_mislabeled_as_automatic():
    image = Image.new('RGB', (20, 20), (80, 100, 120))
    with pytest.raises(ValueError, match='cached candidate'):
        restore_quality(image, image, ceilings(), denoised_candidate=np.array(image))


@pytest.mark.parametrize('value', [-1, 101, float('nan')])
def test_invalid_denoiser_ceilings_are_rejected(value):
    image = np.full((20, 20, 3), 100, np.uint8)
    with pytest.raises(ValueError, match='ceilings'):
        estimate_strength(image, ceilings(noise=value))
