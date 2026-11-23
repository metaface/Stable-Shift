"""Optional, deterministic color changes in linear RGB; no model inference."""
from dataclasses import dataclass
import math

import numpy as np
from PIL import Image, ImageOps


def loop_count(value, maximum=10000):
    number = float(value)
    if not math.isfinite(number) or number != int(number) or not 0 <= number <= maximum:
        raise ValueError(f'Color-change count must be a whole number from 0 to {maximum}.')
    return int(number)


def to_linear(image):
    rgb = np.asarray(image.convert('RGB'), dtype=np.float32)/255
    return np.where(rgb <= .04045, rgb/12.92, ((rgb+.055)/1.055)**2.4)


def from_linear(rgb):
    rgb = np.clip(rgb, 0, 1)
    encoded = np.where(rgb <= .0031308, 12.92*rgb, 1.055*rgb**(1/2.4)-.055)
    return Image.fromarray(np.uint8(np.clip(encoded*255+.5, 0, 255)))


@dataclass(frozen=True)
class ColorShift:
    enabled: bool = False
    exposure: float = 0.
    red: float = 0.
    blue: float = 0.
    saturation: float = 0.

    def validate(self):
        for name, limit in (('exposure', .5), ('red', .25), ('blue', .25), ('saturation', 25.)):
            value = float(getattr(self, name))
            if not math.isfinite(value) or not -limit <= value <= limit:
                raise ValueError(f'Per-loop {name} must be between {-limit:g} and {limit:g}.')
        return self

    @property
    def active(self):
        return self.enabled and any(float(value) != 0 for value in
                                   (self.exposure, self.red, self.blue, self.saturation))

    def advance(self, linear):
        """One step, retaining float precision between reference/preview steps."""
        self.validate()
        if not self.active:
            return linear.copy()
        exposure, red, blue = float(self.exposure), float(self.red), float(self.blue)
        # Opponent balances span all chromatic directions. Their log-gain mean
        # is zero; exposure provides the independent overall brightness control.
        gains = np.exp2(np.array([exposure+red-blue/2, exposure-(red+blue)/2,
                                  exposure+blue-red/2], dtype=np.float32))
        saturation = np.float32(1+float(self.saturation)/100)
        luminance = np.sum(linear*np.array([.2126, .7152, .0722], np.float32), axis=2, keepdims=True)
        return np.clip((luminance+(linear-luminance)*saturation)*gains, 0, 1)

    def apply(self, image, count=1):
        self.validate()
        count = loop_count(count)
        if not self.active or count == 0:
            return image.copy()
        pixels = to_linear(image)
        for _ in range(count):
            pixels = self.advance(pixels)
        return from_linear(pixels)


def preview(image, count=10, *, exposure=0., red=0., blue=0., saturation=0.):
    """Original / first / midpoint / final previews, capped for responsive UI."""
    if image is None:
        raise ValueError('Load an img2img image, upload a color reference, or choose a preview image.')
    count = loop_count(count, 100)
    shift = ColorShift(True, exposure, red, blue, saturation).validate()
    source = ImageOps.exif_transpose(image).convert('RGB')
    source.thumbnail((768, 768), Image.Resampling.LANCZOS)
    selected = {0, min(1, count), count//2, count}
    images = [(source.copy(), 'Original')]
    pixels = to_linear(source)
    for step in range(1, count+1):
        pixels = shift.advance(pixels)
        if step in selected:
            images.append((from_linear(pixels) if shift.active else source.copy(),
                           f'After {step} '+('loop' if step == 1 else 'loops')))
    return images
