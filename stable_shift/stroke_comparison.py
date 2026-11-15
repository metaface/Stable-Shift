"""One fixed denoise/color result, stroke cleanup at 0/60/100, AA off."""
from dataclasses import asdict, replace
import json
from pathlib import Path
from time import perf_counter
from zipfile import ZipFile, ZIP_DEFLATED

import numpy as np
from PIL import Image, ImageDraw, ImageOps

from .engine import array, heatmap, restore_quality
from .stroke_cleanup import clean_strokes


def export_stroke_comparison(reference, edited, options, directory, progress=None):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    run_options = replace(options, stroke_strength=0, antialias_strength=0)
    result, maps = restore_quality(reference, edited, run_options, diagnostics=True, progress=progress)
    base = array(result)
    started = perf_counter()
    candidate, detail, candidate_report = clean_strokes(base, 100, maps.get('source_line_core'), True, progress)
    stroke_seconds = perf_counter()-started
    views, runs = [], []
    for strength, name in ((0, '00_strokes_off.png'), (60, '01_strokes_60.png'), (100, '02_strokes_100.png')):
        rgb = np.uint8(np.clip(base.astype(np.float32)+
            (candidate.astype(np.float32)-base)*(strength/100)+.5, 0, 255))
        signed = rgb.astype(np.int16)-base.astype(np.int16)
        views.append((name, f'Strokes {strength} / AA off', rgb))
        runs.append({'strength': strength, 'antialias_strength': 0,
                     'changed_pixels_percent': float(100*np.mean(np.any(signed != 0, axis=2))),
                     'mean_rgb_change': float(np.abs(signed).mean()),
                     'maximum_rgb_change': int(np.abs(signed).max())})
        Image.fromarray(rgb).save(directory/name)
    edited.convert('RGB').save(directory/'edited_source.png')
    reference.convert('RGB').save(directory/'color_reference.png')
    core = maps.get('source_line_core', np.zeros(base.shape[:2])) > .5
    Image.fromarray(np.uint8(core)*255).save(directory/'source_line_core.png')
    Image.fromarray(np.uint8(detail['stroke_support'] > .5)*255).save(directory/'stroke_support.png')
    heatmap(np.mean(np.abs(candidate.astype(np.float32)-base), axis=2)/16).save(directory/'stroke_change_100.png')
    sheet = Image.new('RGB', (1500, 535), '#202124')
    for i, (_, title, rgb) in enumerate(views):
        thumbnail = ImageOps.contain(Image.fromarray(rgb), (480, 480), Image.Resampling.LANCZOS)
        sheet.paste(thumbnail, (500*i+(500-thumbnail.width)//2, 38))
        ImageDraw.Draw(sheet).text((500*i+8, 10), title, fill='white')
    sheet.save(directory/'stroke_comparison.jpg', quality=95)
    crops = []
    for number, (fx, fy) in enumerate(((.40, .24), (.60, .58), (.76, .25)), 1):
        size = min(256, edited.width, edited.height)
        left = max(0, min(edited.width-size, round(edited.width*fx-size/2)))
        top = max(0, min(edited.height-size, round(edited.height*fy-size/2)))
        crop = Image.new('RGB', ((size+10)*3, size+35), '#202124')
        for i, (_, title, rgb) in enumerate(views):
            crop.paste(Image.fromarray(rgb).crop((left, top, left+size, top+size)), (i*(size+10), 30))
            ImageDraw.Draw(crop).text((i*(size+10)+2, 8), title, fill='white')
        name = f'stroke_crop_{number}_x{left}_y{top}_100percent.png'
        crop.save(directory/name)
        crops.append(name)
    names = [name for name, _, _ in views]+['edited_source.png', 'color_reference.png',
        'source_line_core.png', 'stroke_support.png', 'stroke_change_100.png']+crops
    summary = {'version': '2.10', 'requested_options': asdict(options),
               'upstream_run': maps['report'], 'candidate': candidate_report, 'runs': runs,
               'stroke_candidate_seconds': stroke_seconds,
               'comparison': 'One fixed denoise/cleanup/color result; full stroke candidate blended at 0, 60 and 100. AA off throughout.',
               'color_note': 'The selected color method is fitted once upstream; no color refit between strengths.',
               'timing_note': 'Upstream processing and one full stroke candidate are timed separately; exports excluded.',
               'share_zip': 'share_stroke_test.zip', 'share_files': names}
    if sum((directory/name).stat().st_size for name in names) > 30*1024*1024-100_000:
        summary.update(share_zip=None, share_files=[])
    report_name = 'stroke_settings_and_timings.json'
    (directory/report_name).write_text(json.dumps(summary, indent=2), encoding='utf-8')
    if summary['share_zip']:
        with ZipFile(directory/summary['share_zip'], 'w', compression=ZIP_DEFLATED) as archive:
            for name in names+[report_name]:
                archive.write(directory/name, arcname=name)
    return summary
