"""Stage-separated, signed diagnostics with explicit units and legends."""
from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageOps


def stage_diagnostics(original, denoised, cleaned, final):
    pairs = {'denoise': (original, denoised), 'cleanup': (denoised, cleaned),
             'palette': (cleaned, final), 'total': (original, final)}
    maps = {}
    for name, (before, after) in pairs.items():
        signed = after.astype(np.int16)-before.astype(np.int16)
        maps[name+'_signed_rgb'] = signed
        # All four stage heatmaps use the SAME fixed scale, not per-map maxima.
        maps[name+'_change'] = np.mean(np.abs(signed.astype(np.float32)), axis=2)/16
    # Retain the old key, but explicitly label its total-change semantics.
    maps['difference'] = maps['total_change']*(16/70)
    return maps


def _signed_preview(signed):
    h, w = signed.shape[:2]
    preview_w, preview_h = min(512, w), min(512, h)
    tile_w = preview_w+10
    sheet = Image.new('RGB', (tile_w*3, preview_h+56), '#202124')
    draw = ImageDraw.Draw(sheet)
    for c, name in enumerate(('R', 'G', 'B')):
        level = np.clip(signed[:, :, c].astype(np.float32)/16, -1, 1)
        color = np.full((*level.shape, 3), 128, np.float32)
        negative = np.array([40, 110, 240], np.float32)
        positive = np.array([245, 140, 25], np.float32)
        target = np.where((level >= 0)[:, :, None], positive, negative)
        color += np.abs(level)[:, :, None]*(target-color)
        im = ImageOps.contain(Image.fromarray(color.astype(np.uint8)), (preview_w, preview_h), Image.Resampling.NEAREST)
        sheet.paste(im, (c*tile_w, 45))
        draw.text((c*tile_w+4, 27), name+' change (after - before)', fill='white')
    draw.text((5, 7), 'Blue: negative | Gray: zero | Orange: positive | saturation: +/-16 RGB levels', fill='white')
    return sheet


def save_diagnostics(maps, directory, prefix=''):
    """Export exact data plus readable pictures; never encode signs as magnitudes."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    exact = {}
    binary = {'source_line_candidates', 'source_line_seeds', 'source_line_trace',
              'source_line_core', 'v2_boundaries'}
    count = 0
    for name, field in maps.items():
        if not isinstance(field, np.ndarray):
            continue
        exact[name] = field
        if field.ndim == 3 and name.endswith('_signed_rgb'):
            _signed_preview(field).save(directory/(prefix+name+'_preview.png'))
            count += 1
        elif field.ndim == 2:
            if name in binary:
                picture = Image.fromarray(np.uint8(field > .5)*255)
            else:
                scale = field/18 if name == 'distance' else field/255 if name == 'guide' else field
                picture = Image.fromarray(cv2.cvtColor(cv2.applyColorMap(
                    np.uint8(np.clip(scale, 0, 1)*255), cv2.COLORMAP_TURBO), cv2.COLOR_BGR2RGB))
            picture.save(directory/(prefix+name+'.png'))
            count += 1
    # Exact native-resolution values, including signed RGB differences, are
    # separate from downscaled, clipped, colored human-readable previews.
    np.savez_compressed(directory/(prefix+'diagnostics_raw.npz'), **exact)
    guide = Image.new('RGB', (700, 140), '#202124')
    gradient = np.tile(np.arange(256, dtype=np.uint8), (22, 1))
    bar = Image.fromarray(cv2.cvtColor(cv2.applyColorMap(gradient, cv2.COLORMAP_TURBO), cv2.COLOR_BGR2RGB))
    guide.paste(bar.resize((660, 22)), (20, 35))
    draw = ImageDraw.Draw(guide)
    draw.text((20, 8), 'Stage change maps: mean absolute RGB change (same fixed scale for every stage)', fill='white')
    draw.text((20, 63), '0                   4                   8                   12                   16+ /255', fill='white')
    draw.text((20, 90), 'Binary protection maps: black = unprotected; white = protected.', fill='white')
    draw.text((20, 113), 'Colors visualize numbers. They do not identify the hue or type of noise.', fill='white')
    guide.save(directory/(prefix+'MAP_LEGEND.png'))
    note = '''# Diagnostic map meanings — V2.1

- source_line_confidence: original hard/soft evidence before denoising; 0–1.
- source_line_seeds / candidates / trace: detected strong seeds, supported weak candidates and linked lines. Black/white, not a color probability.
- source_line_core: actual original-pixel protection at the denoiser handoff, and the SAME mask passed into cleanup barriers. White pixels retain original RGB before final palette correction.
- hard / soft / guard: legacy BM3D/NLM evidence and blending. They are not the V2.1 source-line core. In legacy Boundary constrained, guard summarizes requested edge weights, not a separate copy-back operation.
- v2_boundaries: actual combined cleanup exclusions from carried source lines AND locally detected cleanup boundaries. White = excluded. The source core can be present even if the denoised image's local gradient has disappeared.
- denoise_change: original edited input → denoiser + guards handoff.
- cleanup_change: that handoff → V2 surface cleanup, BEFORE reference color correction.
- palette_change: cleaned image → final reference color correction ONLY.
- total_change: original edited input → final output. This is NOT a detected-noise map.
- difference: compatibility alias for total change, scaled to 70 RGB levels instead of 16. Prefer the separate stage maps.
- *_signed_rgb: native-resolution int16 RGB differences, AFTER minus BEFORE, in diagnostics_raw.npz. All signs and values are retained. Their previews use blue for negative, gray for zero, orange for positive, saturating at +/-16 levels, and may be resized.
- *_change: raw normalized mean absolute RGB change, divided by 16. Display saturates at 16; the NPZ retains larger values.
- v2_changed: compatibility cleanup-only magnitude, divided by 12.
- v2_medium_difference / fine_difference: computed scale-difference magnitudes, normalized by the configured LAB similarity range. They are not noise classifications.
- v2_fine_weight / sample_support: reconstruction weights and available sample support; 0–1.
- distance: legacy distance to hard boundaries; its preview saturates at 18 pixels.

Only the edited image supplies structure. Palette changes can still recolor protected line pixels; protection is exact BEFORE palette correction.
'''
    (directory/(prefix+'MAP_LEGEND.md')).write_text(note, encoding='utf-8')
    if 'report' in maps:
        (directory/(prefix+'diagnostics_report.json')).write_text(json.dumps(maps['report'], indent=2), encoding='utf-8')
    return count
