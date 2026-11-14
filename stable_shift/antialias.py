"""Optional native-resolution directional edge antialiasing, after color.

An FXAA-style luma direction chooses a short subpixel sampling path along an
edge. Flat/low-contrast areas bypass it; it does not redraw or restore lines.
"""
import math

import cv2
import numpy as np


def validate_strength(strength):
    if not math.isfinite(strength) or not 0 <= strength <= 100:
        raise ValueError('Antialias strength must be between 0 and 100.')


def antialias(rgb, strength=0):
    validate_strength(strength)
    rgb = np.asarray(rgb)
    if strength == 0:
        return rgb.copy()
    if rgb.dtype != np.uint8 or rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError('Antialiasing requires uint8 RGB pixels.')
    source = rgb.astype(np.float32)/255
    luma = source @ np.array([.299, .587, .114], np.float32)
    padded = np.pad(luma, 1, mode='edge')
    nw, ne = padded[:-2, :-2], padded[:-2, 2:]
    sw, se = padded[2:, :-2], padded[2:, 2:]
    low = np.minimum.reduce((luma, nw, ne, sw, se))
    high = np.maximum.reduce((luma, nw, ne, sw, se))
    eligible = high-low >= np.maximum(.04, high*.125)
    dx, dy = -((nw+ne)-(sw+se)), (nw+sw)-(ne+se)
    reduction = np.maximum((nw+ne+sw+se)*.03125, .0078125)
    divisor = np.minimum(np.abs(dx), np.abs(dy))+reduction
    dx, dy = np.clip(dx/divisor, -4, 4), np.clip(dy/divisor, -4, 4)
    yy, xx = np.indices(luma.shape, dtype=np.float32)
    def sample(offset):
        return cv2.remap(source, xx+dx*offset, yy+dy*offset,
                         cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    a = .5*(sample(-1/6)+sample(1/6))
    b = .5*a+.25*(sample(-.5)+sample(.5))
    b_luma = b @ np.array([.299, .587, .114], np.float32)
    filtered = np.where(((b_luma < low) | (b_luma > high))[..., None], a, b)
    output = np.uint8(np.clip((source+(filtered-source)*(strength/100))*255+.5, 0, 255))
    output[~eligible] = rgb[~eligible]
    return output


def refinish_antialias(pre_antialias, maps, strength):
    """Reapply AA from the original post-color pixels, never a prior AA result."""
    from copy import deepcopy
    from time import perf_counter
    started = perf_counter()
    result = antialias(pre_antialias, strength)
    filtered = perf_counter()
    updated = dict(maps)
    old_signed = maps.get('antialias_signed_rgb', np.zeros_like(result, dtype=np.int16))
    signed = result.astype(np.int16)-pre_antialias.astype(np.int16)
    updated['antialias_signed_rgb'] = signed
    updated['antialias_change'] = np.mean(np.abs(signed.astype(np.float32)), axis=2)/16
    updated['total_signed_rgb'] = maps['total_signed_rgb']-old_signed+signed
    updated['total_change'] = np.mean(np.abs(updated['total_signed_rgb'].astype(np.float32)), axis=2)/16
    updated['difference'] = updated['total_change']*(16/70)
    finished = perf_counter()
    report = deepcopy(maps['report'])
    report.setdefault('original_full_run_seconds', report['total_seconds'])
    upstream = report['total_seconds']-report['antialias_seconds']-report['diagnostics_seconds']
    report['antialias_seconds'] = filtered-started
    report['diagnostics_seconds'] = finished-filtered
    report['total_seconds'] = upstream+finished-started
    report['antialias_preview_seconds'] = finished-started
    report['timing_note'] = 'Total combines original upstream timings and latest AA/diagnostics timings. AA preview reruns no denoising or color fitting.'
    report['options']['antialias_strength'] = strength
    report['effective_options']['antialias_strength'] = strength
    updated['report'] = report
    return result, updated
