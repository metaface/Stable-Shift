"""Compare color methods after a single, fixed cleanup run, with AA off."""
from dataclasses import asdict, replace
import json
from pathlib import Path
from time import perf_counter
from zipfile import ZipFile, ZIP_DEFLATED

import numpy as np
from PIL import Image, ImageDraw, ImageOps

from .engine import array, correct_palette, restore_quality
from .global_color import apply_global_palette


def export_color_comparison(reference, edited, options, directory, progress=None):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    started = perf_counter()
    run_options = replace(options, color_match=False, antialias_strength=0, stroke_strength=0)
    result, maps = restore_quality(reference, edited, run_options, diagnostics=True, progress=progress)
    cleaned = array(result)
    # Exact local baseline, before the broad stage, as in normal Run.
    local = np.uint8(cleaned.astype(np.int16)-maps.get('blotch_signed_rgb', 0))
    views = [('00_before_color.png', 'Before color / AA off', cleaned)]
    if progress:
        progress('Comparing Classic, previous RGB colors and restored shading contrast')
    before = perf_counter()
    classic, classic_report = correct_palette(reference, local, cleaned,
        replace(options, color_match=True, color_method='Classic', antialias_strength=0, stroke_strength=0))
    classic_seconds = perf_counter()-before
    before = perf_counter()
    previous, corrected, report = apply_global_palette(reference, local, cleaned, classic)
    global_seconds = perf_counter()-before
    reports = {'Classic': dict(classic_report, seconds=classic_seconds),
               'Robust global': dict(report, seconds=global_seconds),
               'Robust global (V2.9)': {'selected_method': report['selected_method'],
                   'note': 'Same fitted global RGB transform, without shading-contrast restoration.'}}
    views.extend([('01_classic.png', 'Classic / finishing off', classic),
                  ('02_robust_previous.png', 'Previous RGB / finishing off', previous),
                  ('03_robust_global.png', 'Restored shading / finishing off', corrected)])
    for name, _, rgb in views:
        Image.fromarray(rgb).save(directory/name)
    edited.save(directory/'edited_source.png')
    reference.save(directory/'color_reference.png')
    core = maps.get('source_line_core', np.zeros(cleaned.shape[:2])) > .5
    Image.fromarray(np.uint8(core)*255).save(directory/'source_protection.png')
    sheet = Image.new('RGB', (500*len(views), 535), '#202124')
    for i, (_, title, rgb) in enumerate(views):
        thumb = ImageOps.contain(Image.fromarray(rgb), (480, 480), Image.Resampling.LANCZOS)
        sheet.paste(thumb, (500*i+(500-thumb.width)//2, 38))
        ImageDraw.Draw(sheet).text((500*i+8, 10), title, fill='white')
    sheet.save(directory/'color_comparison.jpg', quality=95)
    for i, (fx, fy) in enumerate(((.40, .24), (.60, .58), (.76, .25), (.08, .54)), 1):
        size = min(256, edited.width, edited.height)
        left = max(0, min(edited.width-size, round(edited.width*fx-size/2)))
        top = max(0, min(edited.height-size, round(edited.height*fy-size/2)))
        sheet = Image.new('RGB', ((size+10)*len(views), size+35), '#202124')
        for column, (_, title, rgb) in enumerate(views):
            sheet.paste(Image.fromarray(rgb).crop((left, top, left+size, top+size)), (column*(size+10), 30))
            ImageDraw.Draw(sheet).text((column*(size+10)+2, 8), title, fill='white')
        sheet.save(directory/f'color_crop_{i}_x{left}_y{top}_100percent.png')
    names = [name for name, _, _ in views]+['edited_source.png', 'color_reference.png', 'source_protection.png']
    summary = {'version': '2.11', 'requested_options': asdict(options),
               'cleanup_run': maps['report'], 'methods': reports,
               'comparison': 'One unchanged cleanup result; Classic, previous global RGB and the same RGB fit with source shading contrast restored. Reference correction on; stroke cleanup and AA off throughout.',
               'processing_seconds': perf_counter()-started,
               'timing_note': 'Cleanup and each color fit have separate timings; processing_seconds also includes image exports.',
               'share_files': names, 'share_zip': 'share_color_test.zip'}
    if sum((directory/name).stat().st_size for name in names) > 30*1024*1024-100_000:
        summary.update(share_files=[], share_zip=None)
    report_name = 'color_settings_and_timings.json'
    (directory/report_name).write_text(json.dumps(summary, indent=2), encoding='utf-8')
    if summary['share_zip']:
        with ZipFile(directory/summary['share_zip'], 'w', compression=ZIP_DEFLATED) as archive:
            for name in names+[report_name]:
                archive.write(directory/name, arcname=name)
    return summary
