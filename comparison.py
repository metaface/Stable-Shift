"""Comparable V2 runs and native-resolution crop exports."""
from dataclasses import asdict, replace
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps, ImageDraw

from engine import restore_quality
from stage_maps import save_diagnostics


def comparison_plan(options):
    if options.cleanup <= 0:
        raise ValueError('Set Surface cleanup above 0 before comparing cleanup variants.')
    if options.method in ('Region cleanup only', 'Color only'):
        return [
            ('01_color_only', replace(options, method='Color only', cleanup=0, source_guard=False)),
            ('02_surface_only', replace(options, method='Region cleanup only')),
        ]
    runs = [('01_denoiser_only', replace(options, cleanup=0, source_guard=False))]
    if options.source_guard:
        runs.append(('02_denoiser_source_lines', replace(options, cleanup=0)))
    runs += [('03_denoiser_plus_surface', options),
             ('04_surface_only', replace(options, method='Region cleanup only'))]
    return runs



def export_comparison(clean, edited, options, directory, progress=None):
    options = replace(options, auto_strength=False)
    plan = comparison_plan(options)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    outputs = [('Edited input', edited)]
    reports = []
    edited.save(directory / '00_edited_input.png')
    for name, opts in plan:
        def update(stage):
            if progress:
                progress(name + ': ' + stage)
        out, maps = restore_quality(clean, edited, replace(opts, blotch_strength=0), diagnostics=True, progress=update)
        out.save(directory / (name + '.png'))
        report = maps['report']
        reports.append({'name': name, **report})
        (directory / (name + '.json')).write_text(json.dumps(report, indent=2), encoding='utf-8')
        outputs.append((name, out))
        save_diagnostics(maps, directory, prefix=name+'_')
    tiles = []
    for name, im in [('Color reference', clean)] + outputs:
        thumb = ImageOps.contain(im, (480, 480), Image.Resampling.LANCZOS)
        tile = Image.new('RGB', (500, 525), '#202124')
        tile.paste(thumb, ((500 - thumb.width) // 2, 35))
        ImageDraw.Draw(tile).text((10, 10), name, fill='white')
        tiles.append(tile)
    sheet = Image.new('RGB', (500 * len(tiles), 525), '#202124')
    for i, tile in enumerate(tiles):
        sheet.paste(tile, (500 * i, 0))
    sheet.save(directory / 'comparison.jpg', quality=95)
    # Native-resolution crops use identical edited-image coordinates, never the
    # differently shaped reference. No crop is enlarged or reduced.
    for i, (fx, fy) in enumerate(((.40, .24), (.60, .58), (.80, .24)), 1):
        size = min(256, edited.width, edited.height)
        left = max(0, min(edited.width - size, round(edited.width * fx - size / 2)))
        top = max(0, min(edited.height - size, round(edited.height * fy - size / 2)))
        tile = Image.new('RGB', ((size + 10) * len(outputs), size + 35), '#202124')
        for j, (name, im) in enumerate(outputs):
            tile.paste(im.crop((left, top, left + size, top + size)), (j * (size + 10), 30))
            ImageDraw.Draw(tile).text((j * (size + 10) + 3, 8), name, fill='white')
        tile.save(directory / f'crop_{i}_x{left}_y{top}_100percent.png')
    (directory / 'settings_and_timings.json').write_text(json.dumps({
        'version': '2.7', 'options': asdict(options),
        'reference_size': list(clean.size), 'edited_size': list(edited.size),
        'runs': reports,
    }, indent=2), encoding='utf-8')
    return reports
