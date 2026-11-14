from dataclasses import replace
import json
from zipfile import ZipFile

import cv2
import numpy as np
from PIL import Image
import pytest

from stable_shift.engine import Options, restore_quality
from stable_shift.line_protection import trace_source_lines, _continue_faint_segments
from tools.line_comparison import export_line_comparison


def faint_stroke(blank_gap=False, tail=False):
    rgb = np.full((100, 180, 3), [75, 90, 110], np.uint8)
    rgb[50, 15:165] = [67, 82, 102]
    soft = np.zeros(rgb.shape[:2], np.float32)
    soft[48:53, 14:166] = .12
    soft[48:53, 85:95] = .04
    if blank_gap:
        rgb[50, 85:95] = [75, 90, 110]
    if tail:
        soft[48:53, 150:166] = .04
    return rgb, {'hard': np.zeros_like(soft), 'soft': soft}


def test_faint_supported_gap_is_retained_without_removing_existing_protection():
    rgb, evidence = faint_stroke()
    previous = trace_source_lines(rgb, evidence, continue_faint=False)
    updated = trace_source_lines(rgb, evidence)
    old = previous['source_line_core'] > .5
    new = updated['source_line_core'] > .5
    assert old[50, 86:94].mean() == 0
    assert new[50, 86:94].mean() == 1
    assert np.all(new[old])
    assert np.count_nonzero(updated['source_line_rescued']) > 0
    assert np.all(updated['source_line_rescued'][old] == 0)


def test_missing_stroke_pixels_are_not_invented_and_single_ended_tails_do_not_grow():
    rgb, evidence = faint_stroke(blank_gap=True, tail=True)
    updated = trace_source_lines(rgb, evidence)
    assert not np.any(updated['source_line_rescued'][48:53, 88:92])
    assert not np.any(updated['source_line_core'][50, 89:91])
    assert not np.any(updated['source_line_rescued'][:, 155:])


def test_opposite_gradient_polarities_cannot_support_a_bridge():
    shape = (35, 45)
    anchors = np.zeros(shape, bool)
    anchors[17, 15] = anchors[17, 27] = True
    candidates = np.zeros(shape, bool)
    candidates[17, 16:27] = True
    orientation = np.full(shape, 4, np.uint8)
    gx = np.zeros((*shape, 3), np.float32)
    gy = np.zeros_like(gx)
    gy[:, :, 0] = 1
    gy[:, 27:, 0] = -1
    assert not np.any(_continue_faint_segments(anchors, candidates, orientation, gx, gy))


def test_broken_slanted_stroke_is_not_limited_to_horizontal_or_diagonal_lines():
    shape = (80, 100)
    anchors = np.zeros(shape, bool)
    candidates = np.zeros(shape, bool)
    for x in range(20, 80):
        y = round(25+(x-20)*.5)
        if 44 <= x <= 52:
            candidates[y, x] = True
        else:
            anchors[y, x] = True
    orientation = np.full(shape, 5, np.uint8)
    gx = np.ones((*shape, 3), np.float32)
    gy = np.ones_like(gx)*-2
    rescued = _continue_faint_segments(anchors, candidates, orientation, gx, gy)
    assert rescued[candidates].mean() > .8


def test_noisy_flat_image_does_not_gain_a_large_new_protected_area():
    from stable_shift.engine import structure_maps
    rng = np.random.default_rng(1)
    rgb = np.uint8(np.clip(np.full((192, 192, 3), [75, 90, 110])+rng.normal(0, 3, (192, 192, 3)), 0, 255))
    evidence = structure_maps(Image.fromarray(rgb))
    old = trace_source_lines(rgb, evidence, continue_faint=False)['source_line_core'] > .5
    new = trace_source_lines(rgb, evidence)['source_line_core'] > .5
    assert np.mean(new & ~old) < .01


def test_comparison_reuses_backend_recovers_source_stroke_and_keeps_palette_fixed(tmp_path, monkeypatch):
    from stable_shift import engine
    rgb, evidence = faint_stroke()
    monkeypatch.setattr(engine, 'structure_maps', lambda *args: {k: v.copy() for k, v in evidence.items()})
    calls = []
    def backend(source, *args):
        result = cv2.GaussianBlur(source, (5, 5), 1.2)
        calls.append((result, result.copy()))
        return result
    monkeypatch.setattr(engine, '_bm3d', backend)
    source = Image.fromarray(rgb)
    reference = Image.fromarray(np.uint8(np.clip(rgb.astype(float)*.8+20, 0, 255)))
    opts = Options(method='CPU BM3D', noise=100, color_noise=100, hard_guard=0, soft_guard=0,
        cleanup=100, cleanup_luma=100, cleanup_range=40, blotch_strength=100)
    report = export_line_comparison(reference, source, opts, tmp_path)
    assert len(calls) == 1 and np.array_equal(*calls[0])
    previous = np.array(Image.open(tmp_path/'00_v24_before_palette.png'))
    updated = np.array(Image.open(tmp_path/'01_faint_lines_before_palette.png'))
    assert np.mean(np.abs(previous[50, 86:94].astype(int)-rgb[50, 86:94])) > 2
    assert np.array_equal(updated[50, 86:94], rgb[50, 86:94])
    check = report['line_preservation_check']
    assert check['additional_protected_pixels'] > 0
    assert check['v24_core_pixels_removed'] == 0
    assert check['v24_core_changed_before_palette'] == check['v24_core_changed_after_palette'] == 0
    assert check['new_core_differs_from_source_before_palette'] == 0
    with ZipFile(tmp_path/report['share_zip']) as archive:
        names = archive.namelist()
        assert 'edited_source.png' in names
        assert '03_faint_lines_same_palette.png' in names
        assert not any(name.endswith('.npz') for name in names)
        saved = json.loads(archive.read('line_settings_and_timings.json'))
        assert saved['baseline']['options']['faint_continuity'] is False
        assert saved['continued']['options']['faint_continuity'] is True
    with np.load(tmp_path/'v25_diagnostics_raw.npz') as maps:
        assert np.array_equal(maps['denoise_signed_rgb']+maps['cleanup_signed_rgb']+maps['palette_signed_rgb'], maps['total_signed_rgb'])


def test_shared_result_is_not_mutated_by_source_copyback_and_rejects_wrong_shape():
    rgb, _ = faint_stroke()
    candidate = np.full_like(rgb, 115)
    original = candidate.copy()
    opts = Options(method='Region cleanup only', color_match=False, cleanup=0, blotch_strength=0)
    restore_quality(Image.fromarray(rgb), Image.fromarray(rgb), opts, denoised_candidate=candidate)
    assert np.array_equal(candidate, original)
    with pytest.raises(ValueError, match='Shared denoiser result'):
        restore_quality(Image.fromarray(rgb), Image.fromarray(rgb), opts, denoised_candidate=candidate[:50])
    with pytest.raises(ValueError, match='Unknown method'):
        restore_quality(Image.fromarray(rgb), Image.fromarray(rgb), replace(opts, method='unknown'), denoised_candidate=candidate)
