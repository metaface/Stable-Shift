"""Conservative source-only strength estimation and spatial cleanup limits.

Fine scatter sets the existing denoiser strength. Correlated color variation
authorizes extra surface cleanup. Coherent structure and line neighborhoods
reduce that permission. These are heuristics, not probabilities of noise.
"""
from dataclasses import replace
import math
from time import perf_counter

import cv2
import numpy as np


def _ramp(low, high, values):
    t = np.clip((values-low)/(high-low), 0., 1.)
    return t*t*(3.-2.*t)


def _coherence(gx, gy):
    if gx.ndim == 3:
        xx, yy, xy = (np.sum(v, axis=2) for v in (gx*gx, gy*gy, gx*gy))
    else:
        xx, yy, xy = gx*gx, gy*gy, gx*gy
    xx, yy, xy = (cv2.GaussianBlur(v, (0, 0), 5., borderType=cv2.BORDER_REFLECT)
                  for v in (xx, yy, xy))
    return np.clip(np.sqrt((xx-yy)**2+4*xy*xy)/(xx+yy+1e-8), 0, 1)


def estimate_strength(rgb, requested, protected=None):
    started = perf_counter()
    rgb = np.asarray(rgb)
    if rgb.ndim != 3 or rgb.shape[2] != 3 or rgb.dtype != np.uint8 or min(rgb.shape[:2]) < 1:
        raise ValueError('Automatic strength expects a nonempty uint8 RGB image.')
    if any(not math.isfinite(float(v)) or not 0 <= v <= 100
           for v in (requested.noise, requested.color_noise)):
        raise ValueError('Denoiser strength ceilings must be finite and between 0 and 100.')
    if protected is None:
        protected = np.zeros(rgb.shape[:2], bool)
    protected = np.asarray(protected, dtype=bool)
    if protected.shape != rgb.shape[:2]:
        raise ValueError('Automatic strength and source protection dimensions must match.')
    lab = cv2.cvtColor(rgb.astype(np.float32)/255, cv2.COLOR_RGB2LAB)
    kernel = np.array([[1, -2, 1], [-2, 4, -2], [1, -2, 1]], np.float32)
    highpass = cv2.filter2D(lab, -1, kernel, borderType=cv2.BORDER_REFLECT)
    sigma = np.median(np.abs(highpass[::2, ::2]), axis=(0, 1))/(6*.67449)
    # Invert the existing BM3D slider-to-sigma mapping; retain its minimum
    # sigma and exact manual adapter. Legacy backends use these bounded slider
    # values too; their strength scales are not equivalent Gaussian sigmas.
    target_l = float(sigma[0])*1.15
    target_c = float(np.max(sigma[1:]))*1.15
    noise = min(float(requested.noise), max(0., min(100., (target_l-.5)/7.5*100)))
    color_noise = min(float(requested.color_noise), max(0., min(100., (target_c-1.275)/21.675*100)))
    effective = replace(requested, noise=noise, color_noise=color_noise)

    medium = cv2.GaussianBlur(lab, (0, 0), 2., borderType=cv2.BORDER_REFLECT)
    broad = cv2.GaussianBlur(lab, (0, 0), 6., borderType=cv2.BORDER_REFLECT)
    band = medium-broad
    rms = np.sqrt(np.maximum(0., cv2.GaussianBlur(band*band, (0, 0), 5., borderType=cv2.BORDER_REFLECT)))
    color_variation = np.sqrt(np.sum(rms[:, :, 1:]**2, axis=2))
    luma_activity = _ramp(.20, .55, rms[:, :, 0])
    color_activity = _ramp(.15, .50, color_variation)
    colored_luma_permission = _ramp(.30, .55, color_variation)
    gx = cv2.Sobel(medium, cv2.CV_32F, 1, 0)
    gy = cv2.Sobel(medium, cv2.CV_32F, 0, 1)
    luma_coherence = _coherence(gx[:, :, 0], gy[:, :, 0])
    color_coherence = _coherence(gx[:, :, 1:], gy[:, :, 1:])
    luma_flatness = np.clip((.90-luma_coherence)/.50, 0, 1)
    color_flatness = np.clip((.95-color_coherence)/.60, 0, 1)
    distance = cv2.distanceTransform((~protected).astype(np.uint8), cv2.DIST_L2, 3)
    taper = _ramp(1., 12., distance)
    # Luminance variation alone can be smoke, shading or surface texture.
    # Require accompanying colored contamination before smoothing it broadly.
    luma_amount = .90*luma_activity*colored_luma_permission*luma_flatness*taper
    color_amount = color_activity*color_flatness*taper
    luma_amount[protected] = color_amount[protected] = 0
    if not np.any(luma_amount) and not np.any(color_amount):
        effective = replace(effective, cleanup=0., blotch_strength=0.)
    # The manual BM3D adapters have a nonzero sigma even at slider zero.
    # Do not apply that minimum to a source with less measured fine scatter.
    if requested.method in ('Color only', 'Region cleanup only'):
        skip_reason = 'The selected method has no fine denoising stage.'
    elif noise == 0 and color_noise == 0:
        skip_reason = 'Fine scatter is below the backend minimum, or both fine-strength ceilings are zero.'
    else:
        skip_reason = None
    skip_backend = skip_reason is not None
    bm3d_method = requested.method in ('CPU BM3D', 'GPU BM3D', 'BM3D (optional)')
    report = {
        'enabled': True, 'fine_sigma_lab': sigma.astype(float).tolist(),
        'requested_noise_ceiling': float(requested.noise),
        'requested_color_noise_ceiling': float(requested.color_noise),
        'effective_noise': noise, 'effective_color_noise': color_noise,
        'backend_sigma_lab': [.5+noise*.075, 1.275+color_noise*.21675, 1.275+color_noise*.21675]
            if bm3d_method and not skip_backend else None,
        'backend_sigma_note': 'LAB sigma applies to BM3D only; null when skipped or using a legacy method.',
        'backend_skipped': skip_backend,
        'backend_skip_reason': skip_reason,
        'mean_luminance_surface_permission_percent': float(100*luma_amount.mean()),
        'mean_chroma_surface_permission_percent': float(100*color_amount.mean()),
        'note': 'Source-only variation/structure heuristics. Permission is not semantic certainty; gray-only blotches may remain.',
        'seconds': perf_counter()-started,
    }
    maps = {
        'auto_luminance_strength': luma_amount.astype(np.float32),
        'auto_chroma_strength': color_amount.astype(np.float32),
        'auto_color_variation': np.clip(color_variation/2., 0, 1),
        'auto_luminance_coherence': luma_coherence.astype(np.float32),
    }
    return effective, maps, report


def limit_cleanup(before, candidate, luma_amount, color_amount, protected=None):
    """Limit an existing stage's LAB correction, keeping zero-weight RGB exact."""
    if before.shape != candidate.shape:
        raise ValueError('Cleanup candidate and input dimensions must match.')
    if before.ndim != 3 or before.shape[2] != 3 or before.dtype != np.uint8 or candidate.dtype != np.uint8:
        raise ValueError('Automatic cleanup limiting expects uint8 RGB images.')
    shape = before.shape[:2]
    luma_amount = np.asarray(luma_amount, dtype=np.float32)
    color_amount = np.asarray(color_amount, dtype=np.float32)
    if np.shape(luma_amount) != shape or np.shape(color_amount) != shape:
        raise ValueError('Automatic strength fields must match the cleanup image.')
    if any(not np.all(np.isfinite(v)) or np.any(v < 0) or np.any(v > 1) for v in (luma_amount, color_amount)):
        raise ValueError('Automatic strength fields must be finite and between 0 and 1.')
    if protected is not None and np.shape(protected) != shape:
        raise ValueError('Automatic protection dimensions must match the cleanup image.')
    if not np.any(luma_amount) and not np.any(color_amount):
        return before.copy()
    if np.all(luma_amount == 1) and np.all(color_amount == 1) and protected is None:
        return candidate.copy()
    old = cv2.cvtColor(before.astype(np.float32)/255, cv2.COLOR_RGB2LAB)
    new = cv2.cvtColor(candidate.astype(np.float32)/255, cv2.COLOR_RGB2LAB)
    delta = new-old
    delta[:, :, 0] *= luma_amount
    delta[:, :, 1:] *= color_amount[:, :, None]
    length = np.linalg.norm(delta, axis=2)
    delta *= np.maximum(0., 1.-.05/np.maximum(1e-8, length))[:, :, None]
    active = np.any(delta != 0, axis=2)
    if protected is not None:
        active &= ~np.asarray(protected, dtype=bool)
    output = np.uint8(np.clip(cv2.cvtColor(old+delta, cv2.COLOR_LAB2RGB)*255+.5, 0, 255))
    output[~active] = before[~active]
    return output
