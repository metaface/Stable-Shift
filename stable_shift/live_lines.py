"""Prepare once, then render line-preservation strength from fixed RGB endpoints.

The zero endpoint is exactly the V2.14 pyramid/border result. Recovery uses
two-sided darker profiles in the edited image, never reference geometry or the
old wide source copy-back. Slider rendering does no image analysis or cleanup.
"""
from copy import deepcopy
from dataclasses import asdict
import math
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from zipfile import ZipFile, ZIP_DEFLATED
import json

import cv2
import numpy as np
from PIL import Image

from .line_borders import LUMA, sample


def validate_strength(value):
    value = float(value)
    if not math.isfinite(value) or not 0 <= value <= 200:
        raise ValueError('Line preservation must be between 0 and 200%.')
    return value


def recovery_endpoints(base, source, source_core):
    """Recover measured dark strokes, with extra observed coverage above 100.

    100 restores source RGB only where a supported stroke is darker than the
    clean base. 200 can increase coverage toward a nearby observed ink sample.
    One-sided shade steps and lighter paint fringes do not qualify. This is
    profile measurement, not semantic line recognition or gap drawing.
    """
    if (base.dtype != np.uint8 or source.dtype != np.uint8 or base.shape != source.shape
            or base.ndim != 3 or base.shape[2] != 3 or min(base.shape[:2]) < 1):
        raise ValueError('Live line inputs must be matching nonempty uint8 RGB arrays.')
    core = np.asarray(source_core, dtype=bool)
    if core.shape != base.shape[:2]:
        raise ValueError('Line support must match the image.')
    src = source.astype(np.float32)
    guide = cv2.GaussianBlur(src, (0, 0), .8)
    gx, gy = cv2.Scharr(guide, -1, 1, 0), cv2.Scharr(guide, -1, 0, 1)
    xx = cv2.GaussianBlur(np.sum(gx*gx, axis=2), (0, 0), 1.35)
    yy = cv2.GaussianBlur(np.sum(gy*gy, axis=2), (0, 0), 1.35)
    xy = cv2.GaussianBlur(np.sum(gx*gy, axis=2), (0, 0), 1.35)
    angle = .5*np.arctan2(2*xy, xx-yy)
    nx, ny = np.cos(angle), np.sin(angle)
    coherence = np.sqrt((xx-yy)**2+4*xy*xy)/(xx+yy+1e-5)
    h, w = core.shape
    profiles = np.zeros(core.shape, bool)
    ink = source.copy()
    for top in range(0, h, 96):
        bottom = min(h, top+96)
        cy, cx = np.mgrid[top:bottom, :w].astype(np.float32)
        ux, uy = nx[top:bottom], ny[top:bottom]
        center = src[top:bottom]
        for radius in (2.5, 4., 6.):
            a = sample(src, cx+radius*ux, cy+radius*uy)-center
            b = sample(src, cx-radius*ux, cy-radius*uy)-center
            profiles[top:bottom] |= ((a@LUMA > .75) & (b@LUMA > .75)
                & (np.sum(a*b, axis=2) > 0))
        # Actual RGB samples from the stroke's narrow normal profile, not black.
        darkest = center.copy()
        for offset in (-2., -1., 1., 2.):
            neighbor = sample(src, cx+offset*ux, cy+offset*uy)
            use = neighbor@LUMA < darkest@LUMA
            darkest[use] = neighbor[use]
        ink[top:bottom] = np.uint8(np.clip(darkest+.5, 0, 255))
    profiles &= core & (coherence > .2)
    # Require short directional support, without linking separate stitch dashes.
    supported = np.zeros_like(profiles)
    orientation = np.floor((angle % np.pi)/(np.pi/4)+.5).astype(np.uint8) % 4
    for sector, kernel in enumerate((np.ones((5, 1), np.float32),
            np.fliplr(np.eye(5, dtype=np.float32)), np.ones((1, 5), np.float32),
            np.eye(5, dtype=np.float32))):
        count = cv2.filter2D(profiles.astype(np.float32), -1, kernel,
                             borderType=cv2.BORDER_CONSTANT)
        supported |= profiles & (orientation == sector) & (count >= 3)
    native = base.copy()
    use = supported & (src@LUMA < base.astype(np.float32)@LUMA-.25)
    native[use] = source[use]
    strong = native.copy()
    # The darkest sample is an ink bound: increase darkness from source toward
    # that sample, rather than extrapolating beyond its observed RGB color.
    candidate = ink.astype(np.float32)
    use_strong = supported & (candidate@LUMA < native.astype(np.float32)@LUMA-.25)
    strong[use_strong] = np.uint8(candidate)[use_strong]
    return native, strong, supported


class LinePreview:
    """Immutable post-color endpoints; sparse blends make strength reversible."""
    def __init__(self, base, native, strong, support, report):
        self.base = np.array(base, dtype=np.uint8, copy=True)
        native = np.asarray(native)
        strong = np.asarray(strong)
        if native.shape != self.base.shape or strong.shape != self.base.shape:
            raise ValueError('Line preview endpoints must have matching dimensions.')
        # A global color transform can reverse small contrasts. Filter after it
        # too, so the preview always increases dark-ink preservation.
        native = native.copy()
        native[native.astype(np.float32)@LUMA >= self.base.astype(np.float32)@LUMA] = self.base[
            native.astype(np.float32)@LUMA >= self.base.astype(np.float32)@LUMA]
        strong = strong.copy()
        strong[strong.astype(np.float32)@LUMA >= native.astype(np.float32)@LUMA] = native[
            strong.astype(np.float32)@LUMA >= native.astype(np.float32)@LUMA]
        self.indices = np.flatnonzero(np.any((native != self.base) | (strong != self.base), axis=2))
        self.values = tuple(a.reshape(-1, 3)[self.indices].copy()
                            for a in (self.base, native, strong))
        self.support = np.array(support, dtype=bool, copy=True)
        self.report = deepcopy(report)
        for a in (self.base, self.indices, self.support, *self.values):
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
            'meaning': '0 = V2.14 clean borders; 100 = darker supported source ink; 200 = stronger observed ink coverage.',
            'upstream_reprocessed': False}
        return Image.fromarray(rgb), report

    def diagnostics(self, image, report):
        signed = np.asarray(image).astype(np.int16)-self.base.astype(np.int16)
        return {'line_support': self.support.astype(np.float32),
                'line_preservation_signed_rgb': signed,
                'line_preservation_change': np.mean(np.abs(signed), axis=2)/16,
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
        progress('Live line preview: caching source ink and fixed color correction')
    support = maps.get('source_line_core')
    if support is None or not options.source_guard:
        from .engine import structure_maps
        from .line_protection import trace_source_lines
        support = trace_source_lines(np.asarray(edited), structure_maps(edited),
                                     continue_faint=True)['source_line_core']
    native, strong, support = recovery_endpoints(base, np.asarray(edited), support > .5)
    transform, color = comparison._shared_color(reference, local, options)
    if transform is not None:
        base, native, strong = (transform.apply(a) for a in (base, native, strong))
    report = {'version': '2.15', 'backend': 'Live pyramid line preservation',
        'requested_options': asdict(options), 'accepted_run': maps['report'],
        'independent_scale_runs': reports, 'line_border_cleanup': borders,
        'color_correction': color, 'preparation_seconds': perf_counter()-start,
        'normal_run_unchanged': True,
        'note': 'Cached source profiles and fixed RGB color transform. Strokes/AA off. Other settings require Prepare again.'}
    return LinePreview(base, native, strong, support, report)


def save_line_test(preview, strength, directory, source, reference=None):
    """Save full endpoints/current view from cache, never rerun the backend."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    selected, report = preview.render(strength)
    selected.save(directory/'02_selected.png')
    preview.render(0)[0].save(directory/'01_v214_baseline.png')
    preview.render(200)[0].save(directory/'03_preservation_200.png')
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
