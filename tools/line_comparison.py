"""V2.4 versus faint-line continuity with one shared backend and palette field."""
from dataclasses import asdict, replace
import json
from pathlib import Path
from time import perf_counter
from zipfile import ZipFile, ZIP_DEFLATED

import numpy as np
from PIL import Image, ImageDraw, ImageOps

from stable_shift.engine import array, structure_maps, _denoise_candidate, restore_quality
from stable_shift.frozen_palette import freeze_palette
from stable_shift.stage_maps import save_diagnostics


def export_line_comparison(clean, edited, options, directory, progress=None):
    options = replace(options, auto_strength=False)
    if not options.source_guard:
        raise ValueError('Enable Trace source lines before comparing faint-line continuity.')
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    started = perf_counter()
    source = array(edited)
    if progress:
        progress('Shared denoiser: '+options.method+' (runs once)')
    evidence = structure_maps(edited, None, options.shade_threshold)
    denoise_start = perf_counter()
    candidate = _denoise_candidate(source, options, evidence)
    denoise_seconds = perf_counter()-denoise_start
    outputs, diagnostics = [], []
    for enabled in (False, True):
        label = 'Faint-line continuity' if enabled else 'V2.4 line protection'
        def phase(message):
            if progress:
                progress(label+': '+message)
        result, maps = restore_quality(clean, edited,
            replace(options, faint_continuity=enabled, color_match=False),
            diagnostics=True, progress=phase, denoised_candidate=candidate)
        outputs.append(array(result))
        diagnostics.append(maps)
    baseline, continued = outputs
    before_maps, after_maps = diagnostics
    core_before = before_maps['source_line_core'] > .5
    core_after = after_maps['source_line_core'] > .5
    added = core_after & ~core_before
    # V2.4 fits its palette from the local-cleanup result before the blotch
    # stage. Recover that exact input from the saved signed stage difference.
    local_baseline = np.uint8(baseline.astype(np.int16)-before_maps.get('blotch_signed_rgb', 0))
    palette_start = perf_counter()
    if options.color_match:
        palette = freeze_palette(clean, local_baseline)
        baseline_final, continued_final = [palette.apply(rgb) for rgb in outputs]
    else:
        baseline_final, continued_final = outputs
    palette_seconds = perf_counter()-palette_start
    for enabled, before, final, maps in zip((False, True), outputs,
            (baseline_final, continued_final), diagnostics):
        signed = final.astype(np.int16)-before.astype(np.int16)
        maps['palette_signed_rgb'] = signed
        maps['palette_change'] = np.mean(np.abs(signed.astype(np.float32)), axis=2)/16
        maps['total_signed_rgb'] += signed
        maps['total_change'] = np.mean(np.abs(maps['total_signed_rgb'].astype(np.float32)), axis=2)/16
        maps['difference'] = maps['total_change']*(16/70)
        maps['report'].update({
            'options': asdict(replace(options, faint_continuity=enabled)),
            'color_match': options.color_match,
            'palette_note': 'Line comparison uses one frozen V2.4 baseline palette field for both variants.',
            'palette_timing_note': 'Palette applied after both variants; time recorded as paired_palette_seconds in the comparison report.',
        })
    check = {
        'v24_protected_pixels': int(core_before.sum()),
        'updated_protected_pixels': int(core_after.sum()),
        'additional_protected_pixels': int(added.sum()),
        'v24_core_pixels_removed': int(np.count_nonzero(core_before & ~core_after)),
        'v24_core_changed_before_palette': int(np.count_nonzero(np.any(continued[core_before] != baseline[core_before], axis=1))),
        'v24_core_changed_after_palette': int(np.count_nonzero(np.any(continued_final[core_before] != baseline_final[core_before], axis=1))),
        'new_core_differs_from_source_before_palette': int(np.count_nonzero(np.any(continued[core_after] != source[core_after], axis=1))),
        'note': 'Exact source retention is not proof that every real line was detected or visibly restored.',
    }
    summary = {
        'version': '2.8', 'options': asdict(options),
        'comparison': 'V2.4 tracing versus source-supported faint-segment continuation',
        'shared_denoiser_ran_once': True, 'shared_denoise_seconds': denoise_seconds,
        'shared_denoise_note': 'Variant denoise_seconds measure guard/copy-back only; backend time is recorded once above.',
        'palette': 'Same frozen V2.4 baseline field for both variants' if options.color_match else 'Off for both',
        'paired_palette_seconds': palette_seconds,
        'baseline': before_maps['report'], 'continued': after_maps['report'],
        'line_preservation_check': check,
        'processing_seconds': perf_counter()-started,
        'reference_size': list(clean.size), 'edited_size': list(edited.size),
    }
    views = [
        ('00_v24_before_palette.png', 'V2.4 before palette', baseline),
        ('01_faint_lines_before_palette.png', 'Faint lines before palette', continued),
        ('02_v24_same_palette.png', 'V2.4 same palette', baseline_final),
        ('03_faint_lines_same_palette.png', 'Faint lines same palette', continued_final),
    ]
    if progress:
        progress('Exporting line comparison, source masks and compact share ZIP')
    for name, _, rgb in views:
        Image.fromarray(rgb).save(directory/name)
    edited.convert('RGB').save(directory/'edited_source.png')
    save_diagnostics(before_maps, directory, prefix='v24_')
    save_diagnostics(after_maps, directory, prefix='v25_')
    sheet = Image.new('RGB', (2000, 525), '#202124')
    for i, (_, title, rgb) in enumerate(views):
        thumbnail = ImageOps.contain(Image.fromarray(rgb), (480, 480), Image.Resampling.LANCZOS)
        sheet.paste(thumbnail, (500*i+(500-thumbnail.width)//2, 35))
        ImageDraw.Draw(sheet).text((500*i+8, 10), title, fill='white')
    sheet.save(directory/'line_comparison.jpg', quality=95)
    for number, (fx, fy) in enumerate(((.40, .24), (.60, .58), (.80, .16)), 1):
        size = min(256, edited.width, edited.height)
        left = max(0, min(edited.width-size, round(edited.width*fx-size/2)))
        top = max(0, min(edited.height-size, round(edited.height*fy-size/2)))
        crop = Image.new('RGB', ((size+10)*4, size+35), '#202124')
        for i, (_, title, rgb) in enumerate(views):
            crop.paste(Image.fromarray(rgb).crop((left, top, left+size, top+size)), (i*(size+10), 30))
            ImageDraw.Draw(crop).text((i*(size+10)+2, 8), title, fill='white')
        crop.save(directory/f'line_crop_{number}_x{left}_y{top}_100percent.png')
    names = [name for name, _, _ in views]+['edited_source.png',
        'v24_source_line_core.png', 'v24_source_line_trace.png',
        'v25_source_line_core.png', 'v25_source_line_trace.png',
        'v25_source_line_rescued.png', 'v25_source_line_added_core.png']
    # Keep headroom below the tool's 32-MiB transfer limit. PNGs are already
    # compressed, so use their actual byte counts instead of guessing a ratio.
    fits = sum((directory/name).stat().st_size for name in names)+100_000 < 30*1024*1024
    summary['share_zip'] = 'share_line_test.zip' if fits else None
    summary['share_note'] = ('Includes full outputs, original edited RGB, masks and settings; excludes large NPZ maps.'
        if fits else 'Full-resolution files exceed the compact share budget; outputs are retained individually.')
    report_name = 'line_settings_and_timings.json'
    (directory/report_name).write_text(json.dumps(summary, indent=2), encoding='utf-8')
    if fits:
        with ZipFile(directory/summary['share_zip'], 'w', compression=ZIP_DEFLATED) as archive:
            for name in names+[report_name]:
                archive.write(directory/name, arcname=name)
    return summary
