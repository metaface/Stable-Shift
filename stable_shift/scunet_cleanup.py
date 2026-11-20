"""One SCUNet pass, then cached edge-aware surface-color cleanup.

No classical denoiser, source copy-back, region fill or stroke fitter participates.
Both cleanup endpoints start from the same uncolored model output. One uniform
color transform is then frozen across every view, including cleanup-off.
"""
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from time import perf_counter

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageOps

from .live_lines import LinePreview, image_signature
from .reconstruction_comparison import _shared_color
from .scunet import denoise
from .scunet_comparison import save_bundle


def _validate_rgb(rgb):
    if (not isinstance(rgb, np.ndarray) or rgb.dtype != np.uint8 or rgb.ndim != 3
            or rgb.shape[2] != 3 or min(rgb.shape[:2]) < 1):
        raise ValueError('SCUNet cleanup requires a nonempty uint8 RGB image.')


def cleanup_candidates(rgb, progress=None):
    """Average similar neighboring model colors; keep the two passes independent.

    OpenCV's recursive domain-transform filter limits averaging across color
    differences without a binary protection map. Brightness is included because
    the remaining broad patches are not exclusively chroma noise. No original
    edited pixels or reference pixels can enter the result here.
    """
    _validate_rgb(rgb)
    endpoints, reports = [], []
    flat = bool(np.all(rgb == rgb[0, 0]))
    for strength, spatial, color_range in ((100, 100, .05), (200, 120, .10)):
        if progress:
            progress(f'SCUNet color cleanup: preparing {strength}% endpoint')
        started = perf_counter()
        result = rgb.copy() if flat else cv2.edgePreservingFilter(
            np.ascontiguousarray(rgb), flags=1, sigma_s=spatial, sigma_r=color_range)
        endpoints.append(result)
        reports.append({'strength': strength, 'spatial_sigma_pixels': spatial,
            'color_range': color_range, 'seconds': perf_counter()-started,
            'mean_rgb_change': float(np.abs(result.astype(np.int16)-rgb).mean())})
    return *endpoints, {'method': 'Recursive domain-transform color averaging',
        'endpoints': reports, 'input': 'Uncolored full-strength SCUNet output',
        'channels': 'RGB, including brightness', 'source_copyback': False,
        'binary_protection': False, 'region_fill': False, 'stroke_fitting': False,
        'note': 'Contrast limits averaging; this is not semantic detection of noise. Strong cleanup can soften faint marks, gradients and texture.'}


class ScunetCleanupPreview(LinePreview):
    """Use the existing reversible RGB blend cache, with cleanup-specific reports."""
    def __init__(self, base, regular, strong, model_rgb, report):
        support = np.any((base != regular) | (base != strong), axis=2)
        super().__init__(base, regular, strong, support, report)
        self.model_rgb = np.array(model_rgb, dtype=np.uint8, copy=True)
        self.model_rgb.flags.writeable = False

    def render(self, strength):
        image, report = super().render(strength)
        blend = report.pop('line_preservation')
        blend['meaning'] = ('0 = SCUNet only; 100 = color cleanup; '
                            '200 = stronger color cleanup. All views use the same frozen global colors.')
        report['scunet_cleanup'] = blend
        return image, report

    def diagnostics(self, image, report):
        signed = np.asarray(image).astype(np.int16)-self.base.astype(np.int16)
        return {'scunet_cleanup_signed_rgb': signed,
                'scunet_cleanup_change': np.mean(np.abs(signed), axis=2)/16,
                'report': deepcopy(report)}


def prepare_scunet_cleanup(reference, edited, options, progress=None, *, cached=None):
    """Prepare the model and two color fields once; the slider only blends RGB.

    A previous SCUNet-cleanup preparation may supply the raw model output only
    when its edited-image pixel signature matches. Cleanup and colors are still
    recomputed, so changed settings never become mislabeled cached pixels.
    """
    started = perf_counter()
    source = np.asarray(edited.convert('RGB')).copy()
    signatures = {'edited': image_signature(edited), 'reference': image_signature(reference)}
    reused = (isinstance(cached, ScunetCleanupPreview)
              and cached.report.get('input_signatures', {}).get('edited') == signatures['edited'])
    if reused:
        model_rgb, model_report = cached.model_rgb, deepcopy(cached.report['scunet'])
        if progress:
            progress('SCUNet color cleanup: reusing matching raw model output')
    else:
        model_rgb, model_report = denoise(source, progress)
    _validate_rgb(model_rgb)
    if model_rgb.shape != source.shape:
        raise ValueError('SCUNet cleanup needs a native-size model output.')
    regular, strong, cleanup = cleanup_candidates(model_rgb, progress)
    if progress:
        progress('SCUNet color cleanup: freezing one global color correction for all strengths')
    transform, color = _shared_color(reference, model_rgb, options)
    apply = lambda rgb: rgb.copy() if transform is None else transform.apply(rgb)
    base, regular, strong = (apply(rgb) for rgb in (model_rgb, regular, strong))
    report = {'version': '2.21', 'preview_kind': 'scunet_cleanup',
        'backend': 'SCUNet with optional color cleanup',
        'input_signatures': signatures, 'requested_options': asdict(options),
        'scunet': model_report, 'model_output_reused': reused,
        'color_cleanup_preparation': cleanup, 'color_correction': color,
        'same_color_transform': True, 'normal_processing_unchanged': True,
        'bypassed_controls': ['Denoiser selection', 'Automatic strength', 'Luminance/color denoise',
            'Local/broad cleanup', 'Source/edge guards', 'Pyramid', 'Line reconstruction', 'Strokes', 'AA'],
        'note': 'Full SCUNet output plus one independent color-averaging pass. The reference supplies only a uniform RGB transform fitted to SCUNet alone. No reference detail or original source texture is copied back.'}
    preview = ScunetCleanupPreview(base, regular, strong, model_rgb, report)
    preview.report['preparation_seconds'] = perf_counter()-started
    return preview


def save_scunet_cleanup_test(preview, strength, directory, source, reference=None):
    """Export the displayed cached strength and model-only control without reruns."""
    if image_signature(source) != preview.report['input_signatures']['edited']:
        raise ValueError('The source image does not match this SCUNet preparation.')
    if reference is not None and image_signature(reference) != preview.report['input_signatures']['reference']:
        raise ValueError('The reference image does not match this SCUNet preparation.')
    selected, report = preview.render(strength)
    strength = report['scunet_cleanup']['strength']
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    views = [('00_scunet_only.png', 'SCUNet only / 0%', preview.render(0)[0]),
             ('01_cleanup_100.png', 'Color cleanup / 100%', preview.render(100)[0]),
             ('02_cleanup_200.png', 'Stronger cleanup / 200%', preview.render(200)[0]),
             ('03_selected.png', f'Selected / {strength:g}%', selected)]
    for name, _, image in views:
        image.save(directory/name)
    Image.fromarray(preview.model_rgb).save(directory/'scunet_before_color.png')
    source.save(directory/'edited_source.png')
    required = ['00_scunet_only.png', '03_selected.png', 'edited_source.png']
    if reference is not None:
        reference.save(directory/'color_reference.png')
        required.append('color_reference.png')
    sheet = Image.new('RGB', (1600, 435), '#202124')
    for column, (_, title, image) in enumerate(views):
        thumb = ImageOps.contain(image, (390, 390), Image.Resampling.LANCZOS)
        sheet.paste(thumb, (column*400+(400-thumb.width)//2, 35))
        ImageDraw.Draw(sheet).text((column*400+6, 9), title, fill='white')
    sheet.save(directory/'scunet_cleanup_comparison.jpg', quality=95)
    crops = []
    for index, (fx, fy) in enumerate(((.35, .27), (.46, .46), (.60, .58), (.73, .20), (.08, .54)), 1):
        size = min(320, source.width, source.height)
        left = max(0, min(source.width-size, round(source.width*fx-size/2)))
        top = max(0, min(source.height-size, round(source.height*fy-size/2)))
        panel = Image.new('RGB', (size*len(views), size+28), '#202124')
        for column, (_, title, image) in enumerate(views):
            panel.paste(image.crop((left, top, left+size, top+size)), (column*size, 28))
            ImageDraw.Draw(panel).text((column*size+3, 7), title, fill='white')
        name = f'crop_{index}_x{left}_y{top}.png'
        panel.save(directory/name)
        crops.append(name)
    optional = ['01_cleanup_100.png', '02_cleanup_200.png', 'scunet_before_color.png',
                'scunet_cleanup_comparison.jpg']+crops
    save_bundle(directory, report, [], required=required, optional=optional,
        report_name='scunet_cleanup_settings.json', archive_name='share_scunet_cleanup.zip')
    return directory/report['share_zip'] if report['share_zip'] else None
