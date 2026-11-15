"""Isolated reconstruction experiment; the accepted normal Run is unchanged."""
from dataclasses import asdict, replace
import json
from pathlib import Path
from time import perf_counter
from zipfile import ZipFile, ZIP_DEFLATED

import numpy as np
from PIL import Image, ImageDraw, ImageOps

from .engine import array, restore_quality
from .global_color import fit_global_color
from .reconstruction import reconstruct


def export_reconstruction_comparison(reference, edited, options, directory, progress=None):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    started = perf_counter()
    fixed = replace(options, color_match=False, antialias_strength=0, stroke_strength=0)
    if progress:
        progress('Reconstruction comparison: accepted full-resolution cleanup')
    accepted, maps = restore_quality(reference, edited, fixed, diagnostics=True, progress=progress)
    accepted_rgb = array(accepted)
    local = np.uint8(accepted_rgb.astype(np.int16)-maps.get('blotch_signed_rgb', 0))
    core = maps.get('source_line_core', np.zeros(local.shape[:2])) > .5
    layers = {}
    scale_reports = {}
    for divisor, name in ((4, 'quarter'), (2, 'half')):
        if progress:
            progress(f'Reconstruction comparison: independently cleaning {name} resolution')
        size = (max(1, (edited.width+divisor-1)//divisor), max(1, (edited.height+divisor-1)//divisor))
        source = edited.resize(size, Image.Resampling.BOX)
        # The coarse layers contain paint information, not exact native ink.
        # Their source grids are independent reductions of the edited input.
        scale_options = replace(fixed, blotch_strength=0, source_guard=False,
                                cleanup_radius=max(2, round(options.cleanup_radius/divisor)))
        result, scale_maps = restore_quality(source, source, scale_options, diagnostics=False, progress=progress)
        layers[name] = array(result)
        scale_reports[name] = scale_maps['report']
        result.save(directory/f'{name}_independently_cleaned.png')
    if progress:
        progress('Reconstruction comparison: pyramid, solid regions and smooth gradients')
    candidates, evidence, report = reconstruct(local, layers['half'], layers['quarter'], core,
        maps.get('auto_bright_neutral_permission'))
    before_color = {'accepted': accepted_rgb, **candidates}
    color_report = {'selected_method': 'Off', 'reason': 'Reference correction disabled.'}
    transform = None
    if options.color_match:
        fitted, color_report = fit_global_color(reference, local)
        if color_report['selected_method'] == 'Robust global':
            transform = fitted
        else:
            # A spatial Classic field would turn a genuinely solid fill into
            # variable color and invalidate this experiment. Use source colors
            # for every view when no uniform transform is accepted.
            color_report = dict(color_report, selected_method='Off',
                reason='No reliable global RGB fit; all comparison views retain source colors. '+color_report['reason'])
    views = []
    checks = {}
    colored_local = local if transform is None else transform.apply(local)
    for key, name, title in (
        ('accepted', '01_accepted.png', 'Accepted V2.12 cleanup'),
        ('pyramid', '02_pyramid.png', 'Quarter -> half -> full'),
        ('hard', '03_hard_colors.png', 'Solid paint regions'),
        ('gradients', '04_hard_with_gradients.png', 'Solid + supported gradients')):
        raw = before_color[key]
        output = raw.copy() if transform is None else transform.apply(raw)
        Image.fromarray(output).save(directory/name)
        Image.fromarray(raw).save(directory/f'{key}_before_color.png')
        checks[key] = {
            'protected_pixels_changed_before_color': int(np.count_nonzero(np.any(raw[core] != local[core], axis=1))),
            'protected_pixels_changed_after_shared_color': int(np.count_nonzero(np.any(output[core] != colored_local[core], axis=1))),
            'changed_from_accepted_percent': float(100*np.mean(np.any(raw != accepted_rgb, axis=2)))}
        views.append((name, title, output))
    edited.save(directory/'edited_source.png')
    reference.save(directory/'color_reference.png')
    Image.fromarray(np.uint8(core)*255).save(directory/'source_protection.png')
    Image.fromarray(np.uint8(evidence['reconstruction_gradient_regions'])*255).save(directory/'supported_gradient_regions.png')
    np.savez_compressed(directory/'reconstruction_evidence.npz', **evidence)
    sheet = Image.new('RGB', (2000, 535), '#202124')
    for column, (_, title, rgb) in enumerate(views):
        thumb = ImageOps.contain(Image.fromarray(rgb), (480, 480), Image.Resampling.LANCZOS)
        sheet.paste(thumb, (500*column+(500-thumb.width)//2, 38))
        ImageDraw.Draw(sheet).text((500*column+8, 10), title, fill='white')
    sheet.save(directory/'reconstruction_comparison.jpg', quality=95)
    crop_names = []
    for index, (fx, fy) in enumerate(((.40, .24), (.60, .58), (.08, .54), (.75, .30), (.67, .69), (.81, .47), (.44, .40), (.73, .20)), 1):
        size = min(256, edited.width, edited.height)
        left = max(0, min(edited.width-size, round(edited.width*fx-size/2)))
        top = max(0, min(edited.height-size, round(edited.height*fy-size/2)))
        crop = Image.new('RGB', ((size+10)*4, size+35), '#202124')
        for column, (_, title, rgb) in enumerate(views):
            crop.paste(Image.fromarray(rgb).crop((left, top, left+size, top+size)), (column*(size+10), 30))
            ImageDraw.Draw(crop).text((column*(size+10)+2, 8), title, fill='white')
        name = f'reconstruction_crop_{index}_x{left}_y{top}_100percent.png'
        crop.save(directory/name)
        crop_names.append(name)
    required = [v[0] for v in views]+['edited_source.png', 'color_reference.png', 'source_protection.png']
    optional = ['supported_gradient_regions.png', 'quarter_independently_cleaned.png', 'half_independently_cleaned.png']+crop_names
    limit = 30*1024*1024-200_000
    used = sum((directory/name).stat().st_size for name in required)
    share = required.copy()
    omitted = []
    for name in optional:
        length = (directory/name).stat().st_size
        if used+length <= limit:
            share.append(name)
            used += length
        else:
            omitted.append(name)
    share_zip = 'share_reconstruction_test.zip' if sum((directory/name).stat().st_size for name in required) <= limit else None
    summary = {'version': '2.13', 'requested_options': asdict(options),
        'accepted_run': maps['report'], 'independent_scale_runs': scale_reports,
        'reconstruction': report, 'color_correction': color_report, 'checks': checks,
        'comparison': 'Accepted full-resolution cleanup versus full-strength reconstruction candidates. Independent quarter/half edited inputs; one shared global RGB transform, or source colors if no fit. Strokes and AA off.',
        'normal_run_unchanged': True, 'processing_seconds': perf_counter()-started,
        'share_zip': share_zip, 'share_files': share if share_zip else [], 'omitted_optional_files': omitted}
    report_name = 'reconstruction_settings_and_timings.json'
    (directory/report_name).write_text(json.dumps(summary, indent=2), encoding='utf-8')
    if share_zip:
        with ZipFile(directory/share_zip, 'w', compression=ZIP_DEFLATED) as archive:
            for name in share+[report_name]:
                archive.write(directory/name, arcname=name)
    return summary
