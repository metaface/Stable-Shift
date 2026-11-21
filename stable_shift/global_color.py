"""Robust global RGB correction, with the accepted LAB matcher as fallback.

Coarse paired samples estimate twelve global coefficients. No reference pixels,
spatial correction fields, or reference edges enter the new transform's output.
Unrelated compositions can make these correspondences meaningless; use held-out
tiles to reject poor fits rather than always accepting a flexible regression.
"""
from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image, ImageOps

METHODS = ('Robust global', 'Classic')


@dataclass
class ClassicColor:
    correction: np.ndarray

    def apply(self, rgb):
        if rgb.shape != self.correction.shape:
            raise ValueError('Classic correction and target dimensions must match.')
        output = np.empty_like(rgb)
        for top in range(0, len(rgb), 256):
            lab = _lab(rgb[top:top+256])+self.correction[top:top+256]
            lab[..., 0] = np.clip(lab[..., 0], 0, 100)
            lab[..., 1:] = np.clip(lab[..., 1:], -127, 127)
            value = cv2.cvtColor(lab.astype(np.float32), cv2.COLOR_LAB2RGB)
            output[top:top+256] = np.uint8(np.clip(value, 0, 1)*255+.5)
        return output


def freeze_palette(reference, baseline_rgb):
    """The accepted Classic LAB fit, extracted from the removed Edit engine."""
    image = Image.fromarray(baseline_rgb)
    reference = reference.convert('RGB')
    if reference.size != image.size:
        reference = reference.resize(image.size, Image.Resampling.LANCZOS)
    factor = min(1., 1280/max(image.size))
    size = tuple(max(16, round(v*factor)) for v in image.size)
    ref = _lab(np.asarray(reference.resize(size, Image.Resampling.LANCZOS)))
    source = _lab(np.asarray(image.resize(size, Image.Resampling.LANCZOS)))
    shifts = ref-source
    guess = np.median(shifts.reshape(-1, 3), axis=0).astype(np.float32)
    residual = np.linalg.norm(shifts-guess, axis=2)
    weight = residual <= max(8., float(np.percentile(residual, 65)))
    if weight.sum() < 100:
        weight[:] = True
    a, b = ref[weight], source[weight]
    offset = np.median(a-b, axis=0).astype(np.float32)
    gain = np.ones(3, np.float32)
    for channel in range(3):
        current = max(1., float(np.percentile(b[:, channel], 75)-np.percentile(b[:, channel], 25)))
        target = max(1., float(np.percentile(a[:, channel], 75)-np.percentile(a[:, channel], 25)))
        gain[channel] = np.clip(target/current, .60, 1.65)
    correction = np.broadcast_to(offset, source.shape).copy()
    correction += (source-np.median(b, axis=0))*(gain-1)*.90
    correction = np.clip(correction, -90, 90)
    return ClassicColor(cv2.resize(correction, image.size, interpolation=cv2.INTER_LINEAR))


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
    determinant = float(np.linalg.det(model.matrix))
    exposure = float(np.cbrt(determinant)) if determinant > 0 else 0.
    normalized = singular/max(exposure, 1e-12)
    report.update(exposure_scale=exposure,
                  exposure_normalized_singular_values=normalized.tolist())
    # Judge color mixing relative to the fitted overall exposure. Uniform
    # darkening/brightening must not itself be classified as color collapse.
    if (not np.isfinite(model.matrix).all() or determinant <= 0 or exposure < 1e-6 or
            normalized[-1] < .25 or normalized[0] > 4 or singular[0]/singular[-1] > 8):
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
    constant_median, constant_q80 = errors(constant)
    # Corresponding pixels can still differ after an edit/generation. Judge
    # the candidate against the actual alternatives on these held-out colors,
    # rather than requiring it to explain half the error of a flat-color guess.
    score = lambda median, q80: .65*median+.35*q80
    classic_score = score(old_median, old_q80)
    global_score = score(new_median, new_q80)
    constant_score = score(constant_median, constant_q80)
    tie_margin = max(.15, .02*classic_score)
    tail_margin = max(2., .20*old_q80)
    report.update(classic_validation_median_delta_e=old_median,
                  classic_validation_q80_delta_e=old_q80,
                  global_validation_median_delta_e=new_median,
                  global_validation_q80_delta_e=new_q80,
                  constant_validation_median_delta_e=constant_median,
                  constant_validation_q80_delta_e=constant_q80,
                  classic_validation_score=classic_score, global_validation_score=global_score,
                  constant_validation_score=constant_score,
                  classic_tie_margin=tie_margin, classic_tail_margin=tail_margin,
                  selection_policy='Prefer a stable uniform fit when comparable to Classic; reject flat-color predictions and materially worse held-out errors.')
    if global_score >= constant_score-max(.05, .01*constant_score):
        return fallback('The global fit does not meaningfully beat a flat-color prediction; retaining Classic.')
    if global_score > classic_score+tie_margin or new_q80 > old_q80+tail_margin:
        return fallback('Held-out global color errors are materially worse than Classic; retaining Classic.')
    report.update(selected_method='Robust global',
                  reason='Stable global fit beats a flat-color prediction and matches or improves Classic on held-out colors.')
    return model, report



def fit_reference_color(reference, baseline_rgb, *, method='Robust global', enabled=True):
    if method not in METHODS:
        raise ValueError('Unknown color method: '+str(method))
    if not enabled or reference is None:
        return None, {'requested_method': method, 'selected_method': 'Off',
                      'reason': 'No active color reference.'}
    if method == 'Classic':
        return freeze_palette(reference, baseline_rgb), {'requested_method': method,
            'selected_method': method, 'reason': 'Classic LAB correction selected.'}
    transform, report = fit_global_color(reference, baseline_rgb)
    if report['selected_method'] == 'Classic':
        report = dict(report, fallback_from=method, fallback_reason=report['reason'])
    return transform, report


def color_method_label(report):
    """Identify an applied fallback without relabeling the requested setting."""
    applied = report.get('selected_method', 'Off')
    requested = report.get('requested_method', applied)
    if applied != 'Off' and applied != requested:
        return f'{requested} -> {applied} (fallback)'
    return applied
