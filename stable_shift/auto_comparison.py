"""Manual ceilings versus automatic strengths with one frozen palette field."""
from dataclasses import asdict, replace
import json
from pathlib import Path
from time import perf_counter
from zipfile import ZipFile, ZIP_DEFLATED

import numpy as np
from PIL import Image, ImageDraw, ImageOps

from .engine import array, restore_quality
from .frozen_palette import freeze_palette
from .stage_maps import save_diagnostics


def export_auto_comparison(clean, edited, options, directory, progress=None):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    started = perf_counter()
    source = array(edited)
    outputs, diagnostics = [], []
    for automatic in (False, True):
        label = 'Automatic' if automatic else 'Manual ceilings'
        def phase(message):
            if progress:
                progress(label+': '+message)
        result, maps = restore_quality(clean, edited,
            replace(options, auto_strength=automatic, color_match=False),
            diagnostics=True, progress=phase)
        outputs.append(array(result))
        diagnostics.append(maps)
    manual, automatic = outputs
    manual_maps, auto_maps = diagnostics
    manual_local = np.uint8(manual.astype(np.int16)-manual_maps.get('blotch_signed_rgb', 0))
    palette_started = perf_counter()
    if options.color_match:
        palette = freeze_palette(clean, manual_local)
        manual_final, auto_final = [palette.apply(rgb) for rgb in outputs]
    else:
        manual_final, auto_final = outputs
    palette_seconds = perf_counter()-palette_started
    for enabled, before, final, maps in zip((False, True), outputs,
            (manual_final, auto_final), diagnostics):
        signed = final.astype(np.int16)-before.astype(np.int16)
        maps['palette_signed_rgb'] = signed
        maps['palette_change'] = np.mean(np.abs(signed.astype(np.float32)), axis=2)/16
        maps['total_signed_rgb'] += signed
        maps['total_change'] = np.mean(np.abs(maps['total_signed_rgb'].astype(np.float32)), axis=2)/16
        maps['difference'] = maps['total_change']*(16/70)
        maps['report'].update({
            'options': asdict(replace(options, auto_strength=enabled)),
            'color_match': options.color_match,
            'palette_note': 'Automatic comparison uses the same manual-baseline V2.4 palette field for both variants.',
            'palette_timing_note': 'Applied after both variants; recorded once as paired_palette_seconds.',
        })
        maps['report']['effective_options']['color_match'] = options.color_match
    manual_core = manual_maps.get('source_line_core', np.zeros(source.shape[:2])) > .5
    auto_core = auto_maps.get('source_line_core', np.zeros(source.shape[:2])) > .5
    common = manual_core & auto_core
    summary = {
        'version': '2.8', 'options': asdict(options),
        'comparison': 'Same source, manual ceilings versus multiscale automatic candidate strengths and spatial limits',
        'manual': manual_maps['report'], 'automatic': auto_maps['report'],
        'denoiser_note': 'Different candidate strengths require separate backend runs. Automatic skips only when native and eligible coarse cues do not justify denoising.',
        'palette': 'Same frozen manual-baseline field for both' if options.color_match else 'Off for both',
        'paired_palette_seconds': palette_seconds,
        'processing_seconds': perf_counter()-started,
        'source_protection_check': {
            'identical_source_masks': bool(np.array_equal(manual_core, auto_core)),
            'common_protected_pixels': int(common.sum()),
            'changed_before_palette': int(np.count_nonzero(np.any(automatic[common] != manual[common], axis=1))),
            'changed_after_palette': int(np.count_nonzero(np.any(auto_final[common] != manual_final[common], axis=1))),
        },
        'reference_size': list(clean.size), 'edited_size': list(edited.size),
    }
    views = [
        ('00_manual_before_palette.png', 'Manual before colors', manual),
        ('01_auto_before_palette.png', 'Automatic before colors', automatic),
        ('02_manual_same_palette.png', 'Manual same colors', manual_final),
        ('03_auto_same_palette.png', 'Automatic same colors', auto_final),
    ]
    if progress:
        progress('Exporting manual/automatic comparison and compact share ZIP')
    for name, _, rgb in views:
        Image.fromarray(rgb).save(directory/name)
    edited.convert('RGB').save(directory/'edited_source.png')
    clean.convert('RGB').save(directory/'color_reference.png')
    Image.fromarray(common.astype(np.uint8)*255).save(directory/'source_protection.png')
    for prefix, maps in (('manual_', manual_maps), ('auto_', auto_maps)):
        save_diagnostics(maps, directory, prefix=prefix)
        candidate = np.uint8(source.astype(np.int16)+maps['unprotected_denoise_signed_rgb'])
        Image.fromarray(candidate).save(directory/(prefix+'raw_denoiser.png'))
    controlled = np.uint8(source.astype(np.int16)+auto_maps['denoise_signed_rgb'])
    Image.fromarray(controlled).save(directory/'auto_controlled_denoiser.png')
    sheet = Image.new('RGB', (2000, 525), '#202124')
    for i, (_, title, rgb) in enumerate(views):
        thumbnail = ImageOps.contain(Image.fromarray(rgb), (480, 480), Image.Resampling.LANCZOS)
        sheet.paste(thumbnail, (500*i+(500-thumbnail.width)//2, 35))
        ImageDraw.Draw(sheet).text((500*i+8, 10), title, fill='white')
    sheet.save(directory/'auto_comparison.jpg', quality=95)
    for number, (fx, fy) in enumerate(((.40, .24), (.60, .58), (.76, .25)), 1):
        size = min(256, edited.width, edited.height)
        left = max(0, min(edited.width-size, round(edited.width*fx-size/2)))
        top = max(0, min(edited.height-size, round(edited.height*fy-size/2)))
        crop = Image.new('RGB', ((size+10)*4, size+35), '#202124')
        for i, (_, title, rgb) in enumerate(views):
            crop.paste(Image.fromarray(rgb).crop((left, top, left+size, top+size)), (i*(size+10), 30))
            ImageDraw.Draw(crop).text((i*(size+10)+2, 8), title, fill='white')
        crop.save(directory/f'auto_crop_{number}_x{left}_y{top}_100percent.png')
    names = [name for name, _, _ in views]+['edited_source.png', 'source_protection.png']
    optional = ['color_reference.png', 'auto_raw_denoiser.png', 'auto_controlled_denoiser.png',
        'auto_auto_bright_neutral_permission.png', 'auto_auto_luminance_strength.png',
        'auto_auto_chroma_strength.png', 'manual_raw_denoiser.png']
    size = sum((directory/name).stat().st_size for name in names)+100_000
    omitted = []
    if size < 30*1024*1024:
        for name in optional:
            if size+(directory/name).stat().st_size < 30*1024*1024:
                names.append(name)
                size += (directory/name).stat().st_size
            else:
                omitted.append(name)
        summary['share_zip'] = 'share_auto_test.zip'
    else:
        summary['share_zip'] = None
        omitted = optional
    summary['share_files'] = names if summary['share_zip'] else []
    summary['share_optional_omitted'] = omitted
    summary['share_note'] = 'Large NPZ maps are excluded. Full-resolution inputs and outputs are included when the 30-MiB budget permits.'
    report_name = 'auto_settings_and_timings.json'
    (directory/report_name).write_text(json.dumps(summary, indent=2), encoding='utf-8')
    if summary['share_zip']:
        with ZipFile(directory/summary['share_zip'], 'w', compression=ZIP_DEFLATED) as archive:
            for name in names+[report_name]:
                archive.write(directory/name, arcname=name)
    return summary
