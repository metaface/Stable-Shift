"""Full-strength SCUNet alone versus the accepted live-pyramid processing."""
from dataclasses import asdict
import json
from pathlib import Path
from time import perf_counter
from zipfile import ZipFile, ZIP_DEFLATED

import numpy as np
from PIL import Image, ImageDraw, ImageOps

from .global_color import GlobalColor
from .live_lines import prepare_line_preview, validate_strength, image_signature
from .scunet import denoise

SHARE_LIMIT = 30*1024*1024


def save_bundle(directory, report, crops):
    """Prioritize compared results and inputs; keep extras in the full folder."""
    directory = Path(directory)
    required = ['01_current_pipeline.png', '02_scunet_only.png', 'edited_source.png', 'color_reference.png']
    optional = ['scunet_before_color.png', '03_input_same_colors.png', 'scunet_comparison.jpg']+list(crops)
    # Include the actual metadata size, with headroom for filenames, ZIP headers
    # and worst-case recompression of already compressed PNGs.
    base = {key: value for key, value in report.items() if not key.startswith('share_') and key != 'omitted_optional_files'}
    budget = SHARE_LIMIT-len(json.dumps(base, indent=2).encode('utf-8'))-200_000
    used = sum((directory/name).stat().st_size for name in required)
    share = required.copy()
    omitted = []
    for name in optional:
        length = (directory/name).stat().st_size
        if used+length <= budget:
            share.append(name)
            used += length
        else:
            omitted.append(name)
    share_zip = 'share_scunet_test.zip' if sum((directory/name).stat().st_size for name in required) <= budget else None
    report.update(share_zip=share_zip, share_files=share if share_zip else [], omitted_optional_files=omitted,
                  share_required_files=required)
    report_name = 'scunet_settings_and_timings.json'
    (directory/report_name).write_text(json.dumps(report, indent=2), encoding='utf-8')
    archive_path = directory/'share_scunet_test.zip'
    if share_zip:
        with ZipFile(archive_path, 'w', compression=ZIP_DEFLATED) as archive:
            for name in share+[report_name]:
                archive.write(directory/name, name)
        if archive_path.stat().st_size > SHARE_LIMIT:
            archive_path.unlink()
            report.update(share_zip=None, share_files=[])
            (directory/report_name).write_text(json.dumps(report, indent=2), encoding='utf-8')
    else:
        archive_path.unlink(missing_ok=True)
    return report


def color_transform(report):
    """Reuse the accepted view's coefficients rather than refitting SCUNet."""
    if report['selected_method'] == 'Off':
        return None
    if report['selected_method'] != 'Robust global':
        raise ValueError('SCUNet comparison needs the live preview\'s uniform RGB correction.')
    if 'matrix' not in report:
        if report.get('reason') != 'Identical reference and baseline; identity transform.':
            raise ValueError('The accepted preview has no reusable RGB coefficients.')
        return GlobalColor(np.eye(3), np.zeros(3), np.zeros(3))
    return GlobalColor(*(np.asarray(report[key], np.float64)
                         for key in ('matrix', 'source_pivot', 'reference_pivot')))


def export_scunet_comparison(reference, edited, options, directory, progress=None,
                             *, line_strength=100, current_preview=None):
    strength = validate_strength(line_strength)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    started = perf_counter()
    reused = current_preview is not None
    if reused:
        if current_preview.report['requested_options'] != asdict(options):
            raise ValueError('The cached current pipeline has different preparation settings.')
        signatures = {'edited': image_signature(edited), 'reference': image_signature(reference)}
        if current_preview.report.get('input_signatures') != signatures:
            raise ValueError('The cached current pipeline belongs to different input images.')
    # Run the model first so a missing optional runtime does not waste a full
    # classical preparation. No masks or strength ceilings enter this call.
    source = np.asarray(edited.convert('RGB')).copy()
    model_rgb, model_report = denoise(source, progress)
    if current_preview is None:
        current_preview = prepare_line_preview(reference, edited, options, progress)
    current, current_report = current_preview.render(strength)
    color = current_report['color_correction']
    transform = color_transform(color)
    apply = lambda pixels: pixels.copy() if transform is None else transform.apply(pixels)
    scunet_rgb, source_colored = apply(model_rgb), apply(source)
    views = [
        ('01_current_pipeline.png', f'Current pyramid / lines {strength:g}%', np.asarray(current)),
        ('02_scunet_only.png', 'SCUNet only / same colors', scunet_rgb),
        ('03_input_same_colors.png', 'Input / same colors', source_colored),
    ]
    for name, _, pixels in views:
        Image.fromarray(pixels).save(directory/name)
    Image.fromarray(model_rgb).save(directory/'scunet_before_color.png')
    edited.save(directory/'edited_source.png')
    reference.save(directory/'color_reference.png')
    sheet = Image.new('RGB', (1500, 535), '#202124')
    for column, (_, title, pixels) in enumerate(views):
        thumb = ImageOps.contain(Image.fromarray(pixels), (480, 480), Image.Resampling.LANCZOS)
        sheet.paste(thumb, (column*500+(500-thumb.width)//2, 38))
        ImageDraw.Draw(sheet).text((column*500+8, 10), title, fill='white')
    sheet.save(directory/'scunet_comparison.jpg', quality=95)
    crops = []
    for index, (fx, fy) in enumerate(((.35, .27), (.46, .46), (.60, .58), (.73, .20), (.08, .54)), 1):
        size = min(320, edited.width, edited.height)
        left = max(0, min(edited.width-size, round(edited.width*fx-size/2)))
        top = max(0, min(edited.height-size, round(edited.height*fy-size/2)))
        crop = Image.new('RGB', (size*3, size+28), '#202124')
        for column, (_, title, pixels) in enumerate(views):
            crop.paste(Image.fromarray(pixels).crop((left, top, left+size, top+size)), (column*size, 28))
            ImageDraw.Draw(crop).text((column*size+3, 7), title, fill='white')
        name = f'crop_{index}_x{left}_y{top}.png'
        crop.save(directory/name)
        crops.append(name)
    report = {'version': '2.20', 'requested_options': asdict(options),
              'scunet': model_report, 'current_pipeline': current_report,
              'current_preparation_reused': reused, 'current_line_strength': strength,
              'color_correction': color, 'same_color_transform': True,
              'scunet_only': {'model_strength_percent': 100, 'automatic_limits': False,
                  'source_copyback': False, 'local_cleanup': False, 'broad_cleanup': False,
                  'pyramid': False, 'stroke_fitting': False, 'antialias': False,
                  'after_model': 'Only the current pipeline\'s uniform color transform, when enabled; uncolored model output is also exported.'},
              'normal_processing_unchanged': True,
              'processing_seconds': perf_counter()-started}
    return save_bundle(directory, report, crops)
