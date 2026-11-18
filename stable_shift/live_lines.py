"""Prepare once, then render line-preservation strength from fixed RGB endpoints.

The zero endpoint restores source pixels only where traces justify them.
The old wide-copy baseline is retained for comparison. Recovery uses
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
from .stroke_paths import trace_stroke_paths


def validate_strength(value):
    value = float(value)
    if not math.isfinite(value) or not 0 <= value <= 200:
        raise ValueError('Line reconstruction must be between 0 and 200%.')
    return value


class LinePreview:
    """Immutable post-color endpoints; sparse blends make strength reversible."""
    def __init__(self, base, native, strong, support, report, original_base=None, path_maps=None):
        self.base = np.array(base, dtype=np.uint8, copy=True)
        native = np.asarray(native)
        strong = np.asarray(strong)
        if native.shape != self.base.shape or strong.shape != self.base.shape:
            raise ValueError('Line preview endpoints must have matching dimensions.')
        self.indices = np.flatnonzero(np.any((native != self.base) | (strong != self.base), axis=2))
        self.values = tuple(a.reshape(-1, 3)[self.indices].copy()
                            for a in (self.base, native, strong))
        self.support = np.array(support, dtype=bool, copy=True)
        self.original_base = self.base.copy() if original_base is None else np.array(original_base, dtype=np.uint8, copy=True)
        if self.original_base.shape != self.base.shape:
            raise ValueError('The original baseline must match the preview dimensions.')
        self.path_maps = {key: np.array(value, copy=True) for key, value in (path_maps or {}).items()}
        self.report = deepcopy(report)
        for a in (self.base, self.original_base, self.indices, self.support, *self.values, *self.path_maps.values()):
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
            'meaning': '0 = traced source preservation only; 100 = smooth traced strokes; 200 = stronger same-path smoothing.',
            'upstream_reprocessed': False}
        return Image.fromarray(rgb), report

    def diagnostics(self, image, report):
        signed = np.asarray(image).astype(np.int16)-self.base.astype(np.int16)
        preservation = self.base.astype(np.int16)-self.original_base.astype(np.int16)
        return {'line_support': self.support.astype(np.float32), **self.path_maps,
                'line_preservation_signed_rgb': signed,
                'line_preservation_change': np.mean(np.abs(signed), axis=2)/16,
                'source_preservation_signed_rgb': preservation,
                'source_preservation_change': np.mean(np.abs(preservation), axis=2)/16,
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
    pyramid_rgb = _rgb(pyramid)
    previous = pyramid_rgb.copy()
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
    paths = trace_stroke_paths(base, source_support)
    original_base = base.copy()
    # Restore only justified ink/short marks/filled objects from the old native
    # handoff. All other pixels in its wide guard stay on the clean pyramid.
    replace = core & ~paths['copy_back']
    base[replace] = pyramid_rgb[replace]
    native, strong, support, reconstruction = reconstruct_lines(base, source_support, paths=paths)
    transform, color = comparison._shared_color(reference, local, options)
    if transform is not None:
        base, native, strong, original_base = (transform.apply(a) for a in (base, native, strong, original_base))
    report = {'version': '2.18', 'backend': 'Live pyramid traced-stroke reconstruction',
        'requested_options': asdict(options), 'accepted_run': maps['report'],
        'independent_scale_runs': reports, 'line_border_cleanup': borders, 'line_reconstruction': reconstruction,
        'color_correction': color, 'preparation_seconds': perf_counter()-start,
        'source_preservation': {'pixels_returned_to_pyramid': int(replace.sum()),
            'changed_rgb_pixels': int(np.any(base != original_base, axis=2).sum()),
            'trace_validation': paths['report']},
        'normal_run_unchanged': True,
        'note': 'Cached reconstructed stroke profiles and fixed RGB color transform. Strokes/AA off. Other settings require Prepare again.'}
    path_maps = {'stroke_path_ids': paths['path_ids'], 'stroke_paths_accepted': paths['accepted'],
        'stroke_filled_exclusion': paths['filled'], 'stroke_short_unfitted': paths['short'],
        'stroke_source_copyback': paths['copy_back'], 'stroke_filled_fit_guard': paths['filled_fit_guard']}
    preview = LinePreview(base, native, strong, support, report, original_base, path_maps)
    preview.report['preparation_seconds'] = perf_counter()-start
    return preview


def save_line_test(preview, strength, directory, source, reference=None):
    """Save full endpoints/current view from cache, never rerun the backend."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    selected, report = preview.render(strength)
    selected.save(directory/'02_selected.png')
    Image.fromarray(preview.original_base).save(directory/'00_original_preservation_base.png')
    preview.render(0)[0].save(directory/'01_reconstruction_off.png')
    preview.render(200)[0].save(directory/'03_reconstruction_200.png')
    source.save(directory/'edited_source.png')
    if reference is not None:
        reference.save(directory/'color_reference.png')
    for key in ('stroke_paths_accepted', 'stroke_filled_exclusion', 'stroke_source_copyback'):
        if key in preview.path_maps:
            Image.fromarray(np.uint8(preview.path_maps[key] > 0)*255).save(directory/(key+'.png'))
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
