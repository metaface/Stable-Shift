"""Regressions for weak source lines and misleading combined difference maps."""
from dataclasses import replace

import cv2
import numpy as np
from PIL import Image

from stable_shift.engine import Options, restore_quality, structure_maps
from stable_shift.line_protection import trace_source_lines
from stable_shift.region_cleanup import RegionOptions, surface_cleanup
from stable_shift.stage_maps import save_diagnostics, stage_diagnostics


def weak_cabin():
    rgb = np.full((192, 192, 3), [75, 90, 110], np.uint8)
    rgb[:70, :70] = [240, 240, 235]  # strong foreground can dominate legacy scaling
    for y in (100, 130, 160):
        cv2.line(rgb, (30, y), (180, y), (67, 82, 102), 1)
    cv2.line(rgb, (30, 90), (30, 180), (25, 30, 40), 1)
    return rgb


def test_faint_long_lines_survive_even_without_hard_seeds():
    rgb = np.full((80, 140, 3), [75, 90, 110], np.uint8)
    rgb[40, 15:125] = [67, 82, 102]
    soft = np.zeros(rgb.shape[:2], np.float32)
    soft[38:43, 14:126] = .12
    maps = {'hard': np.zeros_like(soft), 'soft': soft}
    lines = trace_source_lines(rgb, maps)
    assert not np.any(lines['source_line_seeds'])
    assert lines['source_line_core'][40, 20:120].mean() > .95


def test_noise_only_does_not_become_a_protected_surface():
    rng = np.random.default_rng(1)
    base = np.full((192, 192, 3), [75, 90, 110], np.uint8)
    rgb = np.uint8(np.clip(base.astype(float)+rng.normal(0, 3, base.shape), 0, 255))
    lines = trace_source_lines(rgb, structure_maps(Image.fromarray(rgb)))
    assert lines['source_line_core'].mean() < .10


def test_same_source_mask_survives_denoiser_handoff_and_cleanup(monkeypatch):
    from stable_shift import engine
    rgb = weak_cabin()
    # Model a denoiser that loses the weak line. This isolates guard wiring from
    # the quality of any one denoiser implementation.
    monkeypatch.setattr(engine, '_bm3d', lambda im, *args: cv2.GaussianBlur(im, (5, 5), 1.2))
    edited = Image.fromarray(rgb)
    reference = Image.new('RGB', (32, 17), 'red')
    options = Options(method='CPU BM3D', color_match=False, hard_guard=0, soft_guard=0,
                      cleanup=100, cleanup_luma=100, cleanup_range=30, source_guard=True)
    out, maps = restore_quality(reference, edited, options)
    core = maps['source_line_core'] > .5
    assert core[100, 50:175].mean() > .95
    assert np.array_equal(np.asarray(out)[core], rgb[core])
    assert np.all(maps['v2_boundaries'][core] == 1)
    assert not np.any(maps['cleanup_signed_rgb'][core])
    old, old_maps = restore_quality(reference, edited, replace(options, source_guard=False))
    assert 'source_line_core' not in old_maps
    before = np.mean(np.abs(np.asarray(old)[100, 50:175].astype(float)-rgb[100, 50:175]))
    after = np.mean(np.abs(np.asarray(out)[100, 50:175].astype(float)-rgb[100, 50:175]))
    assert before > 1 and after < before*.1


def test_carried_mask_blocks_paths_when_local_boundary_is_missing():
    rgb = np.full((80, 96, 3), [80, 110, 140], np.uint8)
    rgb[:, 48:] = [90, 120, 150]  # within the allowed range, not a detected barrier
    protected = np.zeros(rgb.shape[:2], bool)
    protected[:, 47] = True
    opts = RegionOptions(100, 30, 100, 24)
    unprotected, _, _ = surface_cleanup(rgb, opts)
    carried, maps, _ = surface_cleanup(rgb, opts, protected=protected)
    assert np.any(unprotected[:, 46] != rgb[:, 46])
    assert np.max(np.abs(carried[:, :46].astype(int)-rgb[:, :46])) <= 1
    assert np.array_equal(carried[protected], rgb[protected])
    assert np.all(maps['v2_boundaries'][protected] == 1)


def test_signed_stage_differences_telescope_and_keep_zero_stages():
    original = np.full((8, 9, 3), [80, 100, 120], np.uint8)
    denoised = original.copy()
    denoised[1, 2] = [75, 103, 121]
    cleaned = denoised.copy()
    cleaned[2, 3] = [84, 95, 117]
    final = np.uint8(cleaned+np.array([4, 2, 1], np.uint8))
    maps = stage_diagnostics(original, denoised, cleaned, final)
    assert np.any(maps['denoise_signed_rgb'] < 0)
    assert np.any(maps['denoise_signed_rgb'] > 0)
    assert np.array_equal(maps['denoise_signed_rgb']+maps['cleanup_signed_rgb']+maps['palette_signed_rgb'], maps['total_signed_rgb'])
    empty = stage_diagnostics(original, denoised, denoised, final)
    assert not np.any(empty['cleanup_change'])
    assert np.any(empty['palette_change'])


def test_palette_only_difference_cannot_be_mistaken_for_cleanup():
    rgb = weak_cabin()
    edited = Image.fromarray(rgb)
    reference = Image.fromarray(np.uint8(np.clip(rgb.astype(float)*1.1+10, 0, 255)))
    out, maps = restore_quality(reference, edited, Options(method='Color only', cleanup=0, color_match=True))
    assert not np.any(maps['denoise_signed_rgb'])
    assert not np.any(maps['cleanup_signed_rgb'])
    assert np.any(maps['palette_signed_rgb'])
    assert np.array_equal(maps['total_signed_rgb'], maps['palette_signed_rgb'])


def test_exports_keep_exact_signs_and_binary_protection(tmp_path):
    original = np.full((8, 9, 3), 90, np.uint8)
    changed = original.copy()
    changed[2, 3] = [80, 100, 90]
    maps = stage_diagnostics(original, original, changed, changed)
    core = np.zeros((8, 9), np.float32)
    core[4, :] = 1
    maps['source_line_core'] = core
    save_diagnostics(maps, tmp_path)
    with np.load(tmp_path/'diagnostics_raw.npz') as raw:
        assert raw['cleanup_signed_rgb'].dtype == np.int16
        assert tuple(raw['cleanup_signed_rgb'][2, 3]) == (-10, 10, 0)
    binary = Image.open(tmp_path/'source_line_core.png')
    assert binary.mode == 'L'
    assert binary.getpixel((3, 4)) == 255
    assert binary.getpixel((3, 3)) == 0
    assert (tmp_path/'MAP_LEGEND.png').exists()
    assert 'NOT a detected-noise map' in (tmp_path/'MAP_LEGEND.md').read_text()


def test_comparison_isolates_source_protection_from_surface_cleanup():
    from stable_shift.comparison import comparison_plan
    runs = comparison_plan(Options(method='GPU BM3D', cleanup=60, source_guard=True))
    assert len(runs) == 4
    assert [(opts.source_guard, opts.cleanup) for _, opts in runs[:3]] == [(False, 0), (True, 0), (True, 60)]
    assert runs[-1][1].method == 'Region cleanup only'
