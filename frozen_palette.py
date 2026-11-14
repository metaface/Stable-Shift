"""Freeze the existing V2.1 palette field for controlled cleanup comparisons.

No V2.2 palette application change or new palette estimator is included here.
"""
from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image

from difference_guard_core import Settings, _resize_rgb, _calc_fields, _to_lab, _from_lab


@dataclass
class FrozenPalette:
    correction: np.ndarray

    def apply(self, rgb):
        rgb = np.asarray(rgb)
        if rgb.shape != self.correction.shape:
            raise ValueError('Frozen palette and target dimensions must match.')
        output = np.empty_like(rgb)
        for top in range(0, rgb.shape[0], 256):
            end = min(rgb.shape[0], top+256)
            lab = _to_lab(rgb[top:end])
            lab += self.correction[top:end]
            lab[:, :, 0] = np.clip(lab[:, :, 0], 0, 100)
            lab[:, :, 1:] = np.clip(lab[:, :, 1:], -127, 127)
            output[top:end] = _from_lab(lab)
        return output


def freeze_palette(reference, baseline_rgb):
    target = Image.fromarray(baseline_rgb)
    ref = _resize_rgb(reference, target.size)
    options = Settings(mode='global', chroma_strength=1, brightness_strength=1,
                       max_lab_change=90, auto_protect=False).validated()
    correction, _, _, _ = _calc_fields(ref, target, options, None)
    field = cv2.resize(correction, target.size, interpolation=cv2.INTER_LINEAR)
    return FrozenPalette(field)
