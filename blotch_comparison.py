"""Compare broad correction on ONE shared V2.1 denoise/local-cleanup base."""
from dataclasses import asdict, replace
from pathlib import Path
from time import perf_counter
import json
import math

import cv2
import numpy as np
from PIL import Image, ImageOps, ImageDraw

from engine import restore_quality
from frozen_palette import freeze_palette
from surface_normalization import normalize_surfaces
from stage_maps import save_diagnostics


def export_blotch_comparison(clean, edited, options, directory, progress=None):
    options = replace(options, auto_strength=False)
    if not math.isfinite(options.blotch_strength) or not 0 < options.blotch_strength <= 100:
        raise ValueError('Set Broad correction maximum above 0 and at most 100 before comparing.')
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    if progress:
        progress('Shared V2.1 denoise/local cleanup (runs once)')
    shared, maps = restore_quality(clean, edited, replace(options, blotch_strength=0, color_match=False),
                                  diagnostics=True, progress=progress)
    baseline = np.asarray(shared)
    core = maps.get('source_line_core', np.zeros(baseline.shape[:2])) > .5
    broad, broad_maps, report = normalize_surfaces(baseline, options.blotch_strength,
        options.cleanup_range, options.cleanup_luma, core, True, progress)
    shared.save(directory/'00_v21_before_palette.png')
    Image.fromarray(broad).save(directory/'01_broad_before_palette.png')
    started = perf_counter()
    if options.color_match:
        if progress:
            progress('Applying one frozen V2.1 palette field to both outputs')
        palette = freeze_palette(clean, baseline)
        base_final, broad_final = palette.apply(baseline), palette.apply(broad)
    else:
        base_final, broad_final = baseline, broad
    palette_seconds = perf_counter()-started
    Image.fromarray(base_final).save(directory/'02_v21_same_palette.png')
    Image.fromarray(broad_final).save(directory/'03_broad_same_palette.png')
    # The only differences on guarded source pixels should be zero, even AFTER
    # color correction, because the exact same frozen field is used for both.
    before_changed = int(np.count_nonzero(np.any(broad[core] != baseline[core], axis=1)))
    after_changed = int(np.count_nonzero(np.any(broad_final[core] != base_final[core], axis=1)))
    nearby = cv2.dilate(core.astype(np.uint8), np.ones((7, 7), np.uint8)).astype(bool) & ~core
    nearby_change = np.abs(broad.astype(np.int16)-baseline.astype(np.int16))[nearby]
    summary = {
        'version': '2.8', 'options': asdict(options), 'shared_processing': maps['report'],
        'broad_correction': report, 'shared_denoiser_ran_once': True,
        'palette': 'Same frozen V2.1 field for both variants' if options.color_match else 'Off for both variants',
        'paired_palette_seconds': palette_seconds,
        'line_preservation_check': {'source_protected_pixels': int(core.sum()),
            'changed_before_palette': before_changed, 'changed_after_palette': after_changed,
            'near_guard_mean_rgb_change': float(nearby_change.mean()) if nearby_change.size else 0.,
            'near_guard_max_rgb_change': int(nearby_change.max()) if nearby_change.size else 0,
            'note': 'Nearby change measures contrast risk; exact core RGB alone does not prove visible line preservation.'},
        'reference_size': list(clean.size), 'edited_size': list(edited.size),
    }
    save_diagnostics(maps, directory, prefix='shared_')
    broad_maps['report'] = summary
    save_diagnostics(broad_maps, directory, prefix='broad_')
    views = [('V2.1 before palette', shared), ('Broad before palette', Image.fromarray(broad)),
             ('V2.1 same palette', Image.fromarray(base_final)), ('Broad same palette', Image.fromarray(broad_final))]
    sheet = Image.new('RGB', (500*len(views), 525), '#202124')
    for i, (name, im) in enumerate(views):
        thumb = ImageOps.contain(im, (480, 480), Image.Resampling.LANCZOS)
        sheet.paste(thumb, (500*i+(500-thumb.width)//2, 35))
        ImageDraw.Draw(sheet).text((500*i+10, 10), name, fill='white')
    sheet.save(directory/'blotch_comparison.jpg', quality=95)
    for i, (fx, fy) in enumerate(((.40, .24), (.60, .58), (.80, .24)), 1):
        size = min(256, edited.width, edited.height)
        left = max(0, min(edited.width-size, round(edited.width*fx-size/2)))
        top = max(0, min(edited.height-size, round(edited.height*fy-size/2)))
        crop = Image.new('RGB', ((size+10)*4, size+35), '#202124')
        for col, (name, im) in enumerate(views):
            crop.paste(im.crop((left, top, left+size, top+size)), (col*(size+10), 30))
            ImageDraw.Draw(crop).text((col*(size+10)+3, 8), name, fill='white')
        crop.save(directory/f'blotch_crop_{i}_x{left}_y{top}_100percent.png')
    (directory/'blotch_settings_and_timings.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    return summary
