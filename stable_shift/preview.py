"""Fixed native endpoints for reversible, inexpensive manual previews."""
from copy import deepcopy
from hashlib import sha256
import math
from time import perf_counter
import numpy as np
from PIL import Image, ImageOps


def image_signature(image):
    rgb = image.convert('RGB')
    h = sha256(str(rgb.size).encode())
    h.update(np.asarray(rgb).tobytes())
    return h.hexdigest()


def strength(value, maximum=100):
    value = float(value)
    if not math.isfinite(value) or not 0 <= value <= maximum:
        raise ValueError(f'Strength must be between 0 and {maximum}%.')
    return value


def blend(a, b, percent):
    if percent == 0:
        return a.copy()
    if percent == 100:
        return b.copy()
    t = np.float32(percent/100)
    return np.uint8(np.clip(a.astype(np.float32)*(1-t)+b.astype(np.float32)*t+.5, 0, 255))


class Preview:
    def __init__(self, endpoints, colored, report, cache=None):
        self.endpoints = tuple(np.array(a, copy=True) for a in endpoints)
        self.colored = tuple(np.array(a, copy=True) for a in colored)
        self.report = deepcopy(report)
        self.cache = cache
        for a in self.endpoints+self.colored:
            a.flags.writeable = False

    def render(self, deblotch=None, color=None, *, automatic=None):
        started = perf_counter()
        defaults = self.report['prepared_strengths']
        b = strength(defaults['deblotch'] if deblotch is None else deblotch, 200)
        c = strength(defaults['color'] if color is None else color)
        if self.report['color_correction']['selected_method'] == 'Off':
            c = 0.
        lo, hi, amount = (0, 1, b) if b <= 100 else (1, 2, b-100)
        if c == 0:
            pixels = blend(self.endpoints[lo], self.endpoints[hi], amount)
        elif c == 100:
            pixels = blend(self.colored[lo], self.colored[hi], amount)
        else:
            raw = blend(self.endpoints[lo], self.endpoints[hi], amount)
            colored = blend(self.colored[lo], self.colored[hi], amount)
            pixels = blend(raw, colored, c)
        report = deepcopy(self.report)
        report['applied'] = {'automatic': report['options']['automatic'] if automatic is None else bool(automatic),
            'denoise': defaults['denoise'], 'deblotch': b, 'color': c,
            'color_method': report['color_correction']['selected_method'] if c else 'Off'}
        report['render_seconds'] = perf_counter()-started
        return Image.fromarray(pixels), report


def result_view(image, size, zoom='Fit', center=(.5, .5)):
    width, height = max(1, size[0]), max(1, size[1])
    if zoom == 'Fit':
        return ImageOps.contain(image, (width, height), Image.Resampling.LANCZOS), (0, 0, *image.size)
    scale = float(zoom.removesuffix('%'))/100
    cw, ch = min(image.width, max(1, round(width/scale))), min(image.height, max(1, round(height/scale)))
    left = max(0, min(image.width-cw, round(center[0]*image.width-cw/2)))
    top = max(0, min(image.height-ch, round(center[1]*image.height-ch/2)))
    box = left, top, left+cw, top+ch
    return image.crop(box).resize((max(1, round(cw*scale)), max(1, round(ch*scale))), Image.Resampling.NEAREST), box
