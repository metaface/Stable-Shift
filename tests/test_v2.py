from dataclasses import replace
from pathlib import Path
import tkinter as tk

import cv2
import numpy as np
from PIL import Image
import pytest

from stable_shift.engine import Options, restore_quality
from stable_shift.image_inputs import drop_path, load_image
from stable_shift.region_cleanup import RegionOptions, surface_cleanup


def test_surface_cleanup_changes_small_variation_and_reduces_error():
    rng = np.random.default_rng(11)
    clean = np.full((96, 120, 3), [75, 110, 145], np.uint8)
    dirty = np.uint8(np.clip(clean.astype(float) + rng.normal(0, 4, clean.shape), 0, 255))
    unchanged, _, _ = surface_cleanup(dirty, RegionOptions(strength=0))
    result, maps, report = surface_cleanup(dirty, RegionOptions(100, 14, 100, 16))
    assert np.array_equal(unchanged, dirty)
    before = np.mean((dirty.astype(float) - clean) ** 2)
    after = np.mean((result.astype(float) - clean) ** 2)
    assert after < before * .55, (before, after)
    assert report['changed_pixels_percent'] > 70
    assert report['mean_rgb_change'] > 1
    assert 'v2_boundaries' in maps and 'v2_changed' in maps


def test_no_sampling_through_one_pixel_window_frame():
    # Surface colors are close enough to match, but a one-pixel frame separates
    # them. Endpoints alone would permit averaging; path constraints must stop it.
    rgb = np.full((80, 96, 3), [80, 110, 140], np.uint8)
    rgb[:, 48:] = [90, 120, 150]
    rgb[:, 47] = [12, 14, 16]
    result, maps, _ = surface_cleanup(rgb, RegionOptions(100, 30, 100, 24))
    assert np.array_equal(result[:, 47], rgb[:, 47])
    assert np.max(np.abs(result[:, :46].astype(int) - rgb[:, :46])) <= 1
    assert np.max(np.abs(result[:, 49:].astype(int) - rgb[:, 49:])) <= 1
    assert np.all(maps['v2_boundaries'][:, 47] == 1)


def test_diagonal_stitch_and_cel_shading_survive():
    rgb = np.full((96, 96, 3), [80, 120, 160], np.uint8)
    rgb[48:] = [45, 75, 110]
    cv2.line(rgb, (12, 12), (80, 35), (15, 25, 40), 1)
    result, _, _ = surface_cleanup(rgb, RegionOptions(100, 12, 100, 24))
    stitch = np.all(rgb == (15, 25, 40), axis=2)
    assert np.array_equal(result[stitch], rgb[stitch])
    assert np.array_equal(result[47:49], rgb[47:49])


def test_large_neighborhood_cleans_broad_variation_more_than_fine():
    y, x = np.mgrid[:100, :120]
    lab = np.empty((100, 120, 3), np.float32)
    lab[:] = [45, -2, -18]
    lab[:, :, 1] += 3 * np.sin(x / 5) * np.sin(y / 6)
    rgb = np.uint8(np.clip(cv2.cvtColor(lab, cv2.COLOR_LAB2RGB) * 255 + .5, 0, 255))
    fine, _, _ = surface_cleanup(rgb, RegionOptions(100, 14, 100, 2))
    broad, _, _ = surface_cleanup(rgb, RegionOptions(100, 14, 100, 24))
    def chroma_std(im):
        return np.std(cv2.cvtColor(im.astype(np.float32) / 255, cv2.COLOR_RGB2LAB)[8:-8, 8:-8, 1])
    assert chroma_std(broad) < chroma_std(fine) * .8


def test_color_reference_has_no_structural_effect():
    rng = np.random.default_rng(12)
    edited = Image.fromarray(np.uint8(rng.integers(70, 100, (48, 64, 3))))
    first = Image.new('RGB', (17, 21), 'red')
    second = Image.new('RGB', (99, 12), 'blue')
    opts = Options(method='Region cleanup only', color_match=False, cleanup=75)
    a, ma = restore_quality(first, edited, opts)
    b, mb = restore_quality(second, edited, opts)
    assert np.array_equal(a, b)
    assert np.array_equal(ma['v2_boundaries'], mb['v2_boundaries'])
    assert a.size == edited.size


def test_zero_luminance_preserves_lab_brightness():
    rng = np.random.default_rng(2)
    rgb = np.full((80, 80, 3), [80, 115, 150], np.uint8)
    rgb = np.uint8(np.clip(rgb.astype(float) + rng.normal(0, 3, rgb.shape), 0, 255))
    result, _, _ = surface_cleanup(rgb, RegionOptions(100, 14, 0, 16))
    before = cv2.cvtColor(rgb.astype(np.float32) / 255, cv2.COLOR_RGB2LAB)[:, :, 0]
    after = cv2.cvtColor(result.astype(np.float32) / 255, cv2.COLOR_RGB2LAB)[:, :, 0]
    assert np.mean(np.abs(before - after)) < .2


@pytest.mark.parametrize('shape', [(1, 1), (1, 17), (17, 1), (3, 5)])
def test_tiny_images(shape):
    rgb = np.full((*shape, 3), [80, 120, 160], np.uint8)
    result, _, _ = surface_cleanup(rgb, RegionOptions())
    assert result.shape == rgb.shape
    assert np.max(np.abs(result.astype(int) - rgb)) <= 1


@pytest.mark.parametrize('options', [RegionOptions(float('nan')), RegionOptions(radius=0), RegionOptions(color_range=100)])
def test_invalid_options(options):
    with pytest.raises(ValueError):
        surface_cleanup(np.zeros((8, 8, 3), np.uint8), options)


def test_drop_paths_with_spaces_unicode_and_braces(tmp_path):
    tcl = tk.Tcl()
    path = tmp_path / 'denim {test} café image.png'
    Image.new('RGB', (9, 7), 'blue').save(path)
    payload = tcl.call('list', str(path))
    assert drop_path(tcl, payload) == path
    assert load_image(drop_path(tcl, payload)).size == (9, 7)
    assert drop_path(tcl, path.as_uri()) == path
    with pytest.raises(ValueError):
        drop_path(tcl, tcl.call('list', str(path), str(path)))
    with pytest.raises(ValueError):
        load_image(tmp_path)


def test_compare_exports_exact_settings_and_native_crops(tmp_path):
    import json
    from stable_shift.comparison import export_comparison
    rng = np.random.default_rng(1)
    edited = Image.fromarray(np.uint8(rng.integers(60, 90, (48, 64, 3))))
    reference = edited.resize((16, 12))
    options = Options(method='Region cleanup only', cleanup=70, color_match=False)
    reports = export_comparison(reference, edited, options, tmp_path)
    assert len(reports) == 2
    assert reports[0]['options']['cleanup'] == 0
    assert reports[1]['options']['cleanup'] == 70
    assert Image.open(tmp_path / '02_surface_only.png').size == edited.size
    assert len(list(tmp_path.glob('crop_*_100percent.png'))) == 3
    assert len(list(tmp_path.glob('*v2_boundaries.png'))) == 1
    metadata = json.loads((tmp_path / 'settings_and_timings.json').read_text())
    assert metadata['reference_size'] == [16, 12]
    assert metadata['edited_size'] == [64, 48]
    assert all(r['total_seconds'] >= r['cleanup_seconds'] for r in reports)
