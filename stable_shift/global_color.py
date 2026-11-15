"""Robust global RGB correction, source tonal contrast, and LAB fallback.

Coarse paired samples estimate twelve global coefficients. No reference pixels,
spatial reference fields, or reference edges enter the new RGB transform.
The separate tonal stage restores supported source lightness contrast.
Unrelated compositions can make these correspondences meaningless; use held-out
tiles to reject poor fits rather than always accepting a flexible regression.
"""
from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image, ImageOps

from .frozen_palette import freeze_palette


METHODS = ('Classic', 'Robust global')


@dataclass(frozen=True)
class GlobalColor:
    matrix: np.ndarray
    source_pivot: np.ndarray
    reference_pivot: np.ndarray

    def apply(self, rgb):
        rgb = np.asarray(rgb)
        if rgb.dtype != np.uint8 or rgb.ndim != 3 or rgb.shape[2] != 3:
            raise ValueError('Color correction requires uint8 RGB pixels.')
        output = np.empty_like(rgb)
        matrix = self.matrix.astype(np.float32)
        for top in range(0, len(rgb), 128):
            block = rgb[top:top+128].astype(np.float32)/255
            converted = (block-self.source_pivot.astype(np.float32)) @ matrix
            converted += self.reference_pivot.astype(np.float32)
            output[top:top+128] = np.uint8(np.clip(converted*255+.5, 0, 255))
        return output


def _fit(x, y):
    weights = np.ones(len(x), np.float64)
    for _ in range(8):
        a = np.average(x, axis=0, weights=weights)
        b = np.average(y, axis=0, weights=weights)
        xx, yy = x-a, y-b
        covariance = (xx*weights[:, None]).T @ xx
        ridge = max(1e-7, np.trace(covariance)/3*.001)
        # A small identity prior keeps poorly observed channel mixtures stable.
        matrix = np.linalg.solve(covariance+np.eye(3)*ridge,
                                 (xx*weights[:, None]).T @ yy+np.eye(3)*ridge)
        error = np.linalg.norm(xx @ matrix+b-y, axis=1)
        scale = max(.003, float(np.percentile(error, 55)))
        weights = 1/(1+(error/scale)**2)
    return GlobalColor(matrix, a, b)


def _lab(rgb):
    return cv2.cvtColor(rgb.astype(np.float32)/255, cv2.COLOR_RGB2LAB)


def restore_shading_contrast(source_rgb, classic_rgb, global_rgb):
    """Retain coherent source-derived lightness contrast after the RGB fit.

    Classic can retain more of the local-cleanup baseline's tonal transitions
    than the native RGB mapping. Recover only its supported medium-scale L
    contrast, keeping the new mapping's broad lighting and a/b colors. Inputs
    are alternate renderings of the SAME cleaned image, never reference pixels.
    """
    arrays = [np.asarray(rgb) for rgb in (source_rgb, classic_rgb, global_rgb)]
    if any(rgb.dtype != np.uint8 or rgb.ndim != 3 or rgb.shape[2] != 3 for rgb in arrays):
        raise ValueError('Shading contrast requires uint8 RGB images.')
    if any(rgb.shape != arrays[0].shape for rgb in arrays[1:]):
        raise ValueError('Shading contrast images must have matching dimensions.')
    source_rgb, classic_rgb, global_rgb = arrays
    report = {'enabled': True, 'changed_pixels_percent': 0.,
              'mean_absolute_lightness_change': 0., 'maximum_absolute_lightness_change': 0.,
              'channel': 'CIELAB L only before RGB gamut conversion',
              'fine_sigma_pixels': 1.5, 'broad_sigma_pixels': 64.,
              'maximum_lightness_step': 4.,
              'note': 'Coherent medium-scale tonal contrast from the source-derived Classic rendering; no reference texture or geometry.'}
    if np.array_equal(source_rgb, global_rgb) or np.array_equal(classic_rgb, global_rgb):
        report['reason'] = 'Identity or no tonal difference; exact bypass.'
        return global_rgb.copy(), report

    def blur(value, sigma):
        return cv2.GaussianBlur(value, (0, 0), sigma, borderType=cv2.BORDER_REFLECT)

    def smooth(low, high, value):
        t = np.clip((value-low)/(high-low), 0, 1)
        return t*t*(3-2*t)

    classic_l = _lab(classic_rgb)[:, :, 0].copy()
    new_lab = _lab(global_rgb)
    source_l = _lab(source_rgb)[:, :, 0].copy()
    delta = classic_l-new_lab[:, :, 0]
    # Suppress fine grain, retain local shading transitions, and remove broad
    # exposure/cast differences instead of reverting to Classic brightness.
    band = blur(delta, 1.5)-blur(delta, 64)
    guide = blur(source_l, 2.5)
    gx = cv2.Scharr(guide, cv2.CV_32F, 1, 0)
    gy = cv2.Scharr(guide, cv2.CV_32F, 0, 1)
    xx, yy, xy = blur(gx*gx, 5), blur(gy*gy, 5), blur(gx*gy, 5)
    coherence = np.sqrt((xx-yy)**2+4*xy*xy)/(xx+yy+1e-6)
    classic_detail = classic_l-blur(classic_l, 64)
    covariance = blur(classic_detail*band, 5)
    energy = blur(classic_detail*classic_detail, 5)
    # Positive covariance selects contrast lost by the RGB rendering. Quiet or
    # directionless variations do not authorize turning old grain back up.
    permission = smooth(.02, .15, covariance/(energy+1e-5))*smooth(.30, .75, coherence)
    permission *= smooth(.15, .60, np.sqrt(energy))
    correction = np.clip(band*1.5, -4, 4)*permission
    # Sub-step L changes can otherwise create unrelated one-level RGB changes
    # from the color-space round trip, despite having no useful tonal effect.
    use = np.abs(correction) >= .05
    if not np.any(use):
        report['reason'] = 'No supported tonal contrast deficit; exact bypass.'
        return global_rgb.copy(), report
    new_lab[:, :, 0] = np.clip(new_lab[:, :, 0]+correction, 0, 100)
    corrected = np.uint8(np.clip(cv2.cvtColor(new_lab, cv2.COLOR_LAB2RGB)*255+.5, 0, 255))
    corrected[~use] = global_rgb[~use]
    report.update(changed_pixels_percent=float(100*np.mean(np.any(corrected != global_rgb, axis=2))),
                  mean_absolute_lightness_change=float(np.mean(np.abs(correction[use]))),
                  maximum_absolute_lightness_change=float(np.max(np.abs(correction[use]))),
                  reason='Restored supported tonal contrast while retaining the global color fit.')
    return corrected, report


def apply_global_palette(reference, baseline_rgb, cleaned_rgb, classic_rgb):
    """Return the previous RGB rendering, shading-aware rendering, and report."""
    transform, report = fit_global_color(reference, baseline_rgb)
    if report['selected_method'] != 'Robust global':
        report['shading_contrast'] = {'enabled': False, 'reason': 'Classic fallback retained exactly.'}
        return classic_rgb, classic_rgb, report
    previous = transform.apply(cleaned_rgb)
    corrected, shading = restore_shading_contrast(cleaned_rgb, classic_rgb, previous)
    report['shading_contrast'] = shading
    report['validation_note'] = 'Held-out fit metrics describe the global RGB transform before source tonal-contrast restoration.'
    return previous, corrected, report


def fit_global_color(reference, baseline_rgb):
    """Return a reusable transform plus a JSON-safe selection report.

The baseline is the same pre-broad image used by Classic in a normal run.
Training excludes high-gradient mixtures; validation uses separate 8px tiles.
Both methods are scored on those same held-out colors, never cleanup strength.
"""
    baseline_rgb = np.asarray(baseline_rgb)
    classic = freeze_palette(reference, baseline_rgb)
    report = {'requested_method': 'Robust global', 'selected_method': 'Classic',
              'fit_note': 'Global coefficients only; held-out color agreement is not a perceptual quality score.'}

    def fallback(reason):
        report['reason'] = reason
        return classic, report

    target_image = Image.fromarray(baseline_rgb)
    ref = reference.convert('RGB')
    if ref.size == target_image.size and np.array_equal(np.asarray(ref), baseline_rgb):
        report.update(selected_method='Robust global', reason='Identical reference and baseline; identity transform.')
        return GlobalColor(np.eye(3), np.zeros(3), np.zeros(3)), report
    small = np.asarray(ImageOps.contain(target_image, (384, 384), Image.Resampling.LANCZOS))
    if min(small.shape[:2]) < 16:
        return fallback('Too few pixels for independent fit and validation tiles.')
    target = np.asarray(ref.resize((small.shape[1], small.shape[0]), Image.Resampling.LANCZOS))

    def gradient(rgb):
        smooth = cv2.GaussianBlur(rgb.astype(np.float32), (0, 0), .7)
        gx = cv2.Sobel(smooth, cv2.CV_32F, 1, 0)
        gy = cv2.Sobel(smooth, cv2.CV_32F, 0, 1)
        return np.sqrt(np.sum(gx*gx+gy*gy, axis=2))

    source_grad, ref_grad = gradient(small), gradient(target)
    eligible = ((source_grad <= np.percentile(source_grad, 65)) &
                (ref_grad <= np.percentile(ref_grad, 65)))
    yy, xx = np.indices(small.shape[:2])
    held_out = ((xx//8+yy//8) % 4) == 0
    training, validation = eligible & ~held_out, eligible & held_out
    report.update(training_samples=int(training.sum()), validation_samples=int(validation.sum()))
    if training.sum() < 256 or validation.sum() < 64:
        return fallback('Too few eligible colors for a reliable fit.')
    x = small[training].astype(np.float64)/255
    y = target[training].astype(np.float64)/255
    color_spread = np.linalg.eigvalsh(np.cov(x, rowvar=False))
    if color_spread[0] < 1e-6:
        return fallback('Insufficient independent channel variation; retaining Classic.')
    model = _fit(x, y)
    singular = np.linalg.svd(model.matrix, compute_uv=False)
    report.update(matrix=model.matrix.tolist(), source_pivot=model.source_pivot.tolist(),
                  reference_pivot=model.reference_pivot.tolist(), singular_values=singular.tolist())
    if (np.linalg.det(model.matrix) <= 0 or singular[-1] < .25 or
            singular[0] > 4 or singular[0]/singular[-1] > 8):
        return fallback('Fit would collapse, invert, or excessively amplify color channels.')
    # Resize the exact Classic baseline output so the comparator includes its
    # inherited interpolated-field behavior rather than a different small fit.
    classic_small = np.asarray(Image.fromarray(classic.apply(baseline_rgb)).resize(
        (small.shape[1], small.shape[0]), Image.Resampling.LANCZOS))
    target_lab = _lab(target)[validation]
    def errors(rgb):
        error = np.linalg.norm(_lab(rgb)[validation]-target_lab, axis=1)
        return float(np.median(error)), float(np.percentile(error, 80))
    old_median, old_q80 = errors(classic_small)
    new_median, new_q80 = errors(model.apply(small))
    constant = np.empty_like(small)
    constant[:] = np.uint8(np.clip(np.median(y, axis=0)*255+.5, 0, 255))
    constant_median, _ = errors(constant)
    report.update(classic_validation_median_delta_e=old_median,
                  classic_validation_q80_delta_e=old_q80,
                  global_validation_median_delta_e=new_median,
                  global_validation_q80_delta_e=new_q80,
                  constant_validation_median_delta_e=constant_median)
    if new_median > 8 or new_q80 > 16 or new_median > .5*constant_median:
        return fallback('Paired colors do not support a reliable global mapping; retaining Classic.')
    if new_median >= old_median*.98 or new_q80 > old_q80*1.02:
        return fallback('Held-out colors do not improve sufficiently over Classic.')
    report.update(selected_method='Robust global', reason='Bounded global fit improves held-out color agreement.')
    return model, report
