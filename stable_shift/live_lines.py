"""Prepare once, then render line-preservation strength from fixed RGB endpoints.

The zero endpoint is the pyramid/border result with surface speckles cleaned.
The original pre-cleanup base is retained for comparison. Recovery uses
fitted stroke centers/widths and signed coverage changes, never reference
geometry or a wide source copy-back. Slider rendering does no image analysis or cleanup.
"""
from copy import deepcopy
from dataclasses import asdict
import math
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from zipfile import ZipFile, ZIP_DEFLATED
import json

import numpy as np
from PIL import Image

from .line_reconstruction import reconstruct_lines


def validate_strength(value):
    value = float(value)
    if not math.isfinite(value) or not 0 <= value <= 200:
        raise ValueError('Line reconstruction must be between 0 and 200%.')
    return value


class LinePreview:
    """Immutable post-color endpoints; sparse blends make strength reversible."""
    def __init__(self, base, native, strong, support, report, before_speckles=None):
        self.base = np.array(base, dtype=np.uint8, copy=True)
        native = np.asarray(native)
        strong = np.asarray(strong)
        if native.shape != self.base.shape or strong.shape != self.base.shape:
            raise ValueError('Line preview endpoints must have matching dimensions.')
        self.indices = np.flatnonzero(np.any((native != self.base) | (strong != self.base), axis=2))
        self.values = tuple(a.reshape(-1, 3)[self.indices].copy()
                            for a in (self.base, native, strong))
        self.support = np.array(support, dtype=bool, copy=True)
        self.before_speckles = self.base.copy() if before_speckles is None else np.array(before_speckles, dtype=np.uint8, copy=True)
        if self.before_speckles.shape != self.base.shape:
            raise ValueError('The pre-speckle baseline must match the preview dimensions.')
        self.report = deepcopy(report)
        for a in (self.base, self.before_speckles, self.indices, self.support, *self.values):
            a.flags.writeable = False

    def render(self, strength):
        strength = validate_strength(strength)
        start = perf_counter()
        a, b = (0, 1) if strength <= 100 else (1, 2)
        amount = strength/100 if strength <= 100 else (strength-100)/100
        rgb = self.base.copy()
        values = self.values[a].astype(np.float32)*(1-amount)+self.values[b]*amount
        values = np.uint8(np.clip(values+.5, 0, 255))
        rgb.reshape(-1, 3)[self.indices] = values
        report = deepcopy(self.report)
        report['line_preservation'] = {
            'strength': strength, 'range': [0, 200],
            'changed_pixels_percent': float(100*np.count_nonzero(
                np.any(values != self.values[0], axis=1))/self.support.size),
            'render_seconds': perf_counter()-start,
            'meaning': '0 = reconstruction off with surface-speckle cleanup; 100 = smooth fitted strokes; 200 = stronger geometry smoothing.',
            'upstream_reprocessed': False}
        return Image.fromarray(rgb), report

    def diagnostics(self, image, report):
        signed = np.asarray(image).astype(np.int16)-self.base.astype(np.int16)
        speckles = self.base.astype(np.int16)-self.before_speckles.astype(np.int16)
        return {'line_support': self.support.astype(np.float32),
                'line_preservation_signed_rgb': signed,
                'line_preservation_change': np.mean(np.abs(signed), axis=2)/16,
                'surface_speckle_signed_rgb': speckles,
                'surface_speckle_change': np.mean(np.abs(speckles), axis=2)/16,
                'report': deepcopy(report)}


def prepare_line_preview(reference, edited, options, progress=None):
    """One native/quarter/half preparation; temporary images are removed."""
    from . import reconstruction_comparison as comparison
    from .reconstruction import _lab, _rgb, pyramid_field
    from .line_borders import clean_line_borders
    start = perf_counter()
    with TemporaryDirectory(prefix='stable_shift_live_') as directory:
        _, _, _, maps, local, core, layers, reports = comparison._prepare_layers(
            reference, edited, options, directory, progress, 'Live line preview')
    if progress:
        progress('Live line preview: rebuilding pyramid and cleaning line borders')
    pyramid, paint, _ = pyramid_field(_lab(local), _lab(layers['half']),
                                     _lab(layers['quarter']), capture_paint=True)
    previous = _rgb(pyramid)
    previous[core] = local[core]
    base, _, borders = clean_line_borders(previous, local, _rgb(paint), core, diagnostics=False)
    if progress:
        progress('Live line preview: fitting smooth stroke profiles and fixed color correction')
    support = maps.get('source_line_core')
    if support is None or not options.source_guard:
        from .engine import structure_maps
        from .line_protection import trace_source_lines
        support = trace_source_lines(np.asarray(edited), structure_maps(edited),
                                     continue_faint=True)['source_line_core']
    source_support = support > .5
    native, strong, support, reconstruction = reconstruct_lines(base, source_support)
    transform, color = comparison._shared_color(reference, local, options)
    if transform is not None:
        base, native, strong = (transform.apply(a) for a in (base, native, strong))
    # Clean each fixed endpoint in its final RGB colors. This directly limits
    # the repair to lightening paint outliers, and leaves accepted fitting intact.
    from .surface_speckles import clean_surface_speckles
    before_speckles = base.copy()
    endpoint_reports = {}
    views = []
    for name, pixels in (('zero', base), ('regular', native), ('strong', strong)):
        cleaned, _, endpoint_reports[name] = clean_surface_speckles(pixels, source_support)
        views.append(cleaned)
    base, native, strong = views
    report = {'version': '2.17', 'backend': 'Live pyramid line reconstruction',
        'requested_options': asdict(options), 'accepted_run': maps['report'],
        'independent_scale_runs': reports, 'line_border_cleanup': borders, 'line_reconstruction': reconstruction,
        'color_correction': color, 'preparation_seconds': perf_counter()-start,
        'surface_speckles': endpoint_reports,
        'normal_run_unchanged': True,
        'note': 'Cached reconstructed stroke profiles and fixed RGB color transform. Strokes/AA off. Other settings require Prepare again.'}
    preview = LinePreview(base, native, strong, support, report, before_speckles)
    preview.report['preparation_seconds'] = perf_counter()-start
    return preview


def save_line_test(preview, strength, directory, source, reference=None):
    """Save full endpoints/current view from cache, never rerun the backend."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    selected, report = preview.render(strength)
    selected.save(directory/'02_selected.png')
    Image.fromarray(preview.before_speckles).save(directory/'00_before_speckle_cleanup.png')
    preview.render(0)[0].save(directory/'01_reconstruction_off.png')
    preview.render(200)[0].save(directory/'03_reconstruction_200.png')
    source.save(directory/'edited_source.png')
    if reference is not None:
        reference.save(directory/'color_reference.png')
    (directory/'live_line_settings.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    files = sorted(directory.glob('*.png'))+[directory/'live_line_settings.json']
    archive = directory/'share_live_line_test.zip'
    if sum(p.stat().st_size for p in files) > 30*1024*1024-200_000:
        return None
    with ZipFile(archive, 'w', compression=ZIP_DEFLATED) as z:
        for path in files:
            z.write(path, path.name)
    return archive


def result_view(image, size, zoom='Fit', center=(.5, .5)):
    """Crop at native coordinates before scaling; save always uses full image."""
    width, height = max(1, size[0]), max(1, size[1])
    if zoom == 'Fit':
        from PIL import ImageOps
        return ImageOps.contain(image, (width, height), Image.Resampling.LANCZOS), (0, 0, *image.size)
    scale = float(zoom.removesuffix('%'))/100
    cw, ch = min(image.width, max(1, round(width/scale))), min(image.height, max(1, round(height/scale)))
    left = max(0, min(image.width-cw, round(center[0]*image.width-cw/2)))
    top = max(0, min(image.height-ch, round(center[1]*image.height-ch/2)))
    box = (left, top, left+cw, top+ch)
    crop = image.crop(box)
    return crop.resize((max(1, round(cw*scale)), max(1, round(ch*scale))),
                       Image.Resampling.NEAREST), box
