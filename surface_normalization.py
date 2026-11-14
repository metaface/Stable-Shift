"""Local, bounded blotch correction within the existing V2.1 boundary graph.

This operates only on edited/denoised pixels. No reference image is accepted.
Regional trends only detrend the samples. They are never used as a replacement
surface: local residuals retain wider shading that a regional fit cannot model.
"""
from __future__ import annotations

import math
from time import perf_counter
from typing import Callable

import cv2
import numpy as np

from region_cleanup import boundary_graph


def _fit(groups, basis, colors, weights, count):
    """Grouped weighted quadratic least squares with mild curvature damping."""
    size = len(basis)
    matrix = np.empty((count, size, size), np.float64)
    rhs = np.empty((count, size, 3), np.float64)
    for i in range(size):
        wi = weights*basis[i]
        for j in range(i, size):
            value = np.bincount(groups, weights=wi*basis[j], minlength=count)
            matrix[:, i, j] = value
            matrix[:, j, i] = value
        for channel in range(3):
            rhs[:, i, channel] = np.bincount(groups, weights=wi*colors[:, channel], minlength=count)
    population = np.maximum(1., matrix[:, 0, 0])
    for i, ridge in enumerate((1e-10, 1e-6, 1e-6, 1e-4, 1e-4, 1e-4)):
        matrix[:, i, i] += population*ridge
    return np.linalg.solve(matrix, rhs)


def _predict(groups, basis, coefficients):
    result = np.zeros((len(groups), 3), np.float32)
    for i, column in enumerate(basis):
        result += column[:, None]*coefficients[groups, i, :].astype(np.float32)
    return result


def _local_residual(lab, labels, stats, ids, model, sigma=32.):
    """Smooth residuals inside each component; do not mix disjoint surfaces.

    The model removes coordinate bias near a region's border. Adding the local
    residual back retains non-quadratic shading instead of flattening an entire
    tree, fold or face to the regional polynomial. Mask-normalized convolution
    uses only native-resolution samples from that same connected component.
    """
    target = lab.copy()
    variance = np.zeros(lab.shape[:2], np.float32)
    for region in ids:
        left, top, width, height, _ = stats[region]
        roi = (slice(top, top+height), slice(left, left+width))
        mask = (labels[roi] == region).astype(np.float32)
        def blur(value):
            return cv2.GaussianBlur(value, (0, 0), sigma, borderType=cv2.BORDER_CONSTANT)
        support = np.maximum(1e-6, blur(mask))
        residual = lab[roi]-model[roi]
        mean = blur(residual*mask[..., None])/support[..., None]
        energy = blur(np.sum(residual*residual, axis=2)*mask)/support
        inside = mask > 0
        target[roi][inside] = (model[roi]+mean)[inside]
        variance[roi][inside] = np.maximum(0., energy-np.sum(mean*mean, axis=2))[inside]
    return target, variance


def normalize_surfaces(rgb, strength=70., color_range=12., luminance=60.,
                       protected=None, diagnostics=True,
                       progress: Callable[[str], None] | None = None):
    start = perf_counter()
    if not all(math.isfinite(float(v)) for v in (strength, color_range, luminance)):
        raise ValueError('Broad correction settings must be finite.')
    if not 0 <= strength <= 100 or not 0 <= luminance <= 100 or not 2 <= color_range <= 40:
        raise ValueError('Broad correction strength/brightness must be 0–100; color range 2–40.')
    rgb = np.asarray(rgb)
    if rgb.ndim != 3 or rgb.shape[2] != 3 or rgb.dtype != np.uint8:
        raise ValueError('Surface normalization expects H x W x 3 uint8 RGB.')
    summary = {'maximum_strength': float(strength), 'backend': 'CPU NumPy/OpenCV',
               'changed_pixels_percent': 0., 'mean_rgb_change': 0., 'modeled_regions': 0,
               'algorithm': 'local detrended residual; bounded correction; boundary taper',
               'note': 'Local variation estimate, not semantic noise recognition.'}
    if strength == 0:
        summary['seconds'] = perf_counter()-start
        return rgb.copy(), {}, summary
    lab = cv2.cvtColor(rgb.astype(np.float32)/255, cv2.COLOR_RGB2LAB)
    _, boundary = boundary_graph(lab, color_range, protected)
    free = np.uint8(boundary == 0)
    if progress:
        progress('Broad correction: identifying bounded surfaces')
    number, labels, stats, _ = cv2.connectedComponentsWithStats(free, connectivity=4)
    valid = stats[:, cv2.CC_STAT_AREA] >= 128
    valid[0] = False
    ids = np.flatnonzero(valid)
    if not len(ids):
        summary['seconds'] = perf_counter()-start
        return rgb.copy(), {'blotch_boundaries': boundary.astype(np.float32)} if diagnostics else {}, summary
    selected = np.flatnonzero(valid[labels].ravel())
    old_groups = labels.ravel()[selected]
    remap = np.zeros(number, np.int32)
    remap[ids] = np.arange(len(ids), dtype=np.int32)
    groups = remap[old_groups]
    yy, xx = np.divmod(selected, rgb.shape[1])
    boxes = stats[old_groups]
    x = ((xx-boxes[:, cv2.CC_STAT_LEFT])-(boxes[:, cv2.CC_STAT_WIDTH]-1)*.5)/np.maximum(1., (boxes[:, cv2.CC_STAT_WIDTH]-1)*.5)
    y = ((yy-boxes[:, cv2.CC_STAT_TOP])-(boxes[:, cv2.CC_STAT_HEIGHT]-1)*.5)/np.maximum(1., (boxes[:, cv2.CC_STAT_HEIGHT]-1)*.5)
    x, y = x.astype(np.float32), y.astype(np.float32)
    basis = [np.ones(len(selected), np.float32), x, y, x*x, x*y, y*y]
    colors = lab.reshape(-1, 3)[selected]
    weights = np.ones(len(selected), np.float32)
    for iteration in range(2):
        if progress:
            progress(f'Broad correction: robust surface fit {iteration+1}/2')
        coefficients = _fit(groups, basis, colors, weights, len(ids))
        model = _predict(groups, basis, coefficients)
        residual2 = np.sum((colors-model)**2, axis=1)
        weights = np.minimum(1., (color_range*.5)/np.maximum(1e-5, np.sqrt(residual2)))
    model_field = lab.copy()
    model_field.reshape(-1, 3)[selected] = model
    if progress:
        progress('Broad correction: retaining local shading and tapering boundaries')
    target, local_variance = _local_residual(lab, labels, stats, ids, model_field)
    local_model = target.reshape(-1, 3)[selected]
    residual2 = np.sum((colors-local_model)**2, axis=1)
    variance = local_variance.ravel()[selected]
    # High-frequency scatter estimates distinguish broad patches from residual
    # fine grain. Exclude boundary-adjacent samples from that noise estimate.
    interior = cv2.erode(free, np.ones((3, 3), np.uint8), borderType=cv2.BORDER_CONSTANT)
    highpass_kernel = np.array([[1,-2,1],[-2,4,-2],[1,-2,1]], np.float32)
    highpass = cv2.filter2D(lab, -1, highpass_kernel, borderType=cv2.BORDER_REFLECT)
    hf2 = np.sum(highpass.reshape(-1, 3)[selected]**2, axis=1)/36
    usable = interior.ravel()[selected].astype(np.float32)
    noise_population = np.bincount(groups, weights=usable, minlength=len(ids))
    fine_variance = np.bincount(groups, weights=hf2*usable, minlength=len(ids))/np.maximum(1, noise_population)
    broad_variance = np.maximum(0., variance-fine_variance[groups])
    activity = np.clip((np.sqrt(broad_variance)-.20)/.80, 0, 1)
    # A permissive similarity setting must not make a large, heterogeneous
    # surface almost certain to be noise (V2.3 did exactly that at range 40).
    trust_range = min(8., color_range)
    confidence = np.clip(1.-variance/trust_range**2, 0, 1)
    broad_fraction = broad_variance/np.maximum(.04, variance)
    local_trust = np.clip(1-residual2/trust_range**2, 0, 1)
    distance = cv2.distanceTransform(free, cv2.DIST_L2, 3)
    taper = np.clip((distance.ravel()[selected]-1.)/12., 0, 1)
    taper = taper*taper*(3.-2.*taper)
    amount = (strength/100)*confidence*activity*broad_fraction*local_trust*taper
    correction = (local_model-colors)*amount[:, None]
    correction[:, 0] *= luminance/100
    magnitude = np.linalg.norm(correction, axis=1)
    # Softly suppress sub-quantization changes, and bound any one-pass move.
    # This avoids the hard island cutoff and 15-LAB brightness jumps in V2.3.
    correction *= (np.maximum(0., magnitude-.05)/np.maximum(1e-6, magnitude))[:, None]
    magnitude = np.linalg.norm(correction, axis=1)
    correction *= np.minimum(1., 3./np.maximum(1e-6, magnitude))[:, None]
    significant = np.any(correction != 0, axis=1)
    result_lab = lab.copy()
    result_lab.reshape(-1, 3)[selected] += correction
    result = np.uint8(np.clip(cv2.cvtColor(result_lab, cv2.COLOR_LAB2RGB)*255+.5, 0, 255))
    # Detrending is not a license to extrapolate a new black dot or bright spot.
    # Every output channel stays inside the observed 49x49 source envelope.
    kernel = np.ones((49, 49), np.uint8)
    lower = cv2.erode(rgb, kernel, borderType=cv2.BORDER_REFLECT)
    upper = cv2.dilate(rgb, kernel, borderType=cv2.BORDER_REFLECT)
    result = np.minimum(upper, np.maximum(lower, result))
    eligible = np.zeros(rgb.shape[:2], bool)
    eligible.ravel()[selected[significant]] = True
    result[~eligible] = rgb[~eligible]
    signed = result.astype(np.int16)-rgb.astype(np.int16)
    summary.update({
        'changed_pixels_percent': float(100*np.mean(np.any(signed != 0, axis=2))),
        'mean_rgb_change': float(np.mean(np.abs(signed.astype(np.float32)))),
        'modeled_regions': int(len(ids)),
        'active_regions': int(np.count_nonzero(np.bincount(groups, weights=amount, minlength=len(ids)) > .01)),
        'mean_automatic_amount_percent': float(100*np.mean(amount)),
        'maximum_requested_lab_step': 3., 'local_residual_sigma_pixels': 32.,
        'boundary_taper_pixels': 12.,
        'seconds': perf_counter()-start,
    })
    maps = {}
    if diagnostics:
        fit_error = np.zeros(rgb.shape[:2], np.float32)
        fit_error.ravel()[selected] = np.sqrt(residual2)/color_range
        confidence_map = np.zeros(rgb.shape[:2], np.float32)
        confidence_map.ravel()[selected] = amount
        taper_map = np.zeros(rgb.shape[:2], np.float32)
        taper_map.ravel()[selected] = taper
        maps = {'blotch_boundaries': boundary.astype(np.float32),
                'blotch_automatic_amount': confidence_map, 'blotch_fit_error': fit_error,
                'blotch_boundary_taper': taper_map,
                'blotch_change': np.mean(np.abs(signed.astype(np.float32)), axis=2)/16,
                'blotch_signed_rgb': signed}
    return result, maps, summary
