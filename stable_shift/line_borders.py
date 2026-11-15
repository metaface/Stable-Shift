"""Clean paint next to ink without restoring an oversized source fringe.

Ink is detected using two-sided RGB profiles in the native working image.
Same-side paint comes from reconstructed coarse layers. Rays stop at another
observed ink profile; native surface texture and reference pixels are not used
as replacement paint. Existing RGB ink/antialiasing is retained at higher ink
coverage. This is a source-image measurement, not semantic line recognition.
"""
import math
from time import perf_counter
import cv2
import numpy as np
LUMA = np.array([0.299, 0.587, 0.114], np.float32)

def sample(a, x, y):
    return cv2.remap(a, x.astype(np.float32), y.astype(np.float32), cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)

def clean_line_borders(original, full, paint, core, strength=100.0, diagnostics=True):
    """Finish pre-palette pyramid RGB using its native and coarse paint fields.

    ``original`` contains the old wide source copy-back; ``full`` is the native
    working image before broad cleanup; ``paint`` is the coarse reconstruction
    before fine residuals. All use the same source RGB color space.
    """
    start = perf_counter()
    if not math.isfinite(float(strength)) or not 0 <= strength <= 100:
        raise ValueError('Line border strength must be between 0 and 100.')
    for value in (original, full, paint):
        if value.dtype != np.uint8 or value.ndim != 3 or value.shape[2] != 3 or (value.shape != original.shape) or (min(value.shape[:2]) < 1):
            raise ValueError('Line border inputs must be matching nonempty uint8 RGB arrays.')
    core = np.asarray(core, dtype=bool)
    if core.shape != original.shape[:2]:
        raise ValueError('Line border source map must match the image.')
    if strength == 0:
        return (original.copy(), {}, {'strength': 0.0, 'changed_pixels_percent': 0.0, 'ink_pixels_changed': 0, 'seconds': perf_counter() - start})
    src = full.astype(np.float32)
    paint_float = paint.astype(np.float32)
    guide = cv2.GaussianBlur(src, (0, 0), 0.8)
    gx = cv2.Scharr(guide, cv2.CV_32F, 1, 0)
    gy = cv2.Scharr(guide, cv2.CV_32F, 0, 1)
    xx = cv2.GaussianBlur(np.sum(gx * gx, axis=2), (0, 0), 1.35)
    yy = cv2.GaussianBlur(np.sum(gy * gy, axis=2), (0, 0), 1.35)
    xy = cv2.GaussianBlur(np.sum(gx * gy, axis=2), (0, 0), 1.35)
    angle = 0.5 * np.arctan2(2 * xy, xx - yy)
    nx, ny = (np.cos(angle), np.sin(angle))
    coherence = np.sqrt((xx - yy) ** 2 + 4 * xy * xy) / (xx + yy + 1e-05)
    h, w = core.shape
    ink = np.zeros_like(core)
    light = src @ LUMA
    # Source evidence locates candidates; the two-sided profile selects ink.
    for top in range(0, h, 96):
        bottom = min(h, top + 96)
        cy, cx = np.mgrid[top:bottom, :w].astype(np.float32)
        nxx, nyy = (nx[top:bottom], ny[top:bottom])
        center = src[top:bottom]
        minimum = light[top:bottom].copy()
        for r in (-2, -1, 1, 2):
            minimum = np.minimum(minimum, sample(light, cx + nxx * r, cy + nyy * r))
        for r in (2.5, 4.0, 6.0):
            a = sample(src, cx + nxx * r, cy + nyy * r)
            b = sample(src, cx - nxx * r, cy - nyy * r)
            da, db = (a - center, b - center)
            both = (da @ LUMA > 1) & (db @ LUMA > 1)
            same = np.sum(da * db, axis=2) > 0
            flank = np.minimum(a @ LUMA, b @ LUMA)
            central = light[top:bottom] <= minimum + 0.2 * np.maximum(0, flank - minimum) + 0.5
            ink[top:bottom] |= core[top:bottom] & both & same & central & (coherence[top:bottom] > 0.1)
    if not np.any(ink):
        return (original.copy(), {'border_ink': ink.astype(np.float32)} if diagnostics else {}, {'strength': float(strength), 'changed_pixels_percent': 0.0, 'ink_pixels_changed': 0, 'seconds': perf_counter() - start, 'reason': 'No supported dark ink profiles.'})
    distance, nearest = cv2.distanceTransformWithLabels(np.uint8(~ink), cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL)
    yy0, xx0 = np.nonzero(ink)
    key = np.zeros((int(nearest.max()) + 1, 2), np.int32)
    key[nearest[ink]] = np.stack((xx0, yy0), axis=1)
    sy, sx = np.mgrid[:h, :w].astype(np.float32)
    origin = key[nearest]
    vx, vy = (sx - origin[:, :, 0], sy - origin[:, :, 1])
    norm = np.maximum(1e-05, np.hypot(vx, vy))
    vx = vx / norm
    vy = vy / norm
    ink_byte = np.uint8(ink)
    output = original.copy()
    active = np.zeros_like(core)
    alpha_map = np.ones(core.shape, np.float32)
    for top in range(0, h, 96):
        bottom = min(h, top + 96)
        cy, cx = np.mgrid[top:bottom, :w].astype(np.float32)
        ux, uy = (vx[top:bottom].astype(np.float32), vy[top:bottom].astype(np.float32))
        eligible = (distance[top:bottom] > 0) & (distance[top:bottom] <= 6)
        clear = np.ones(eligible.shape, bool)
        values = []
        weights = []
        # Sample outward on this side of the stroke, stopping at another ink.
        for step in range(1, 8):
            qx, qy = (cx + ux * step, cy + uy * step)
            crossed = cv2.remap(ink_byte, qx, qy, cv2.INTER_NEAREST, borderMode=cv2.BORDER_REPLICATE) > 0
            clear &= ~crossed
            if step in (3, 5, 7):
                value = sample(paint_float, qx, qy)
                values.append(value)
                weights.append(clear.copy())
        count = np.sum(weights, axis=0)
        stack = np.stack(values)
        surface = np.zeros_like(stack[0])
        for value, valid in zip(values, weights):
            surface = np.where(valid[:, :, None], value, surface)
        curvature = np.linalg.norm(stack[0] - 2 * stack[1] + stack[2], axis=2)
        trend = (stack[2] - stack[0]) / 4
        # Extrapolate only a gentle consistent trend, preserving clean shading.
        extrapolated = np.mean(stack, axis=0) - 5 * trend
        extrapolated = np.minimum(surface + 6, np.maximum(surface - 6, extrapolated))
        linear = (count == 3) & (curvature < 2) & (np.max(np.abs(trend), axis=2) < 1.5)
        surface[linear] = extrapolated[linear]
        keys = origin[top:bottom]
        ink_rgb = src[keys[:, :, 1], keys[:, :, 0]]
        vector = surface - ink_rgb
        # Coverage is one at ink and zero at paint. It is not a blend weight
        # for adding native texture back into the reconstructed surface.
        alpha = np.sum((surface - src[top:bottom]) * vector, axis=2) / np.maximum(1, np.sum(vector * vector, axis=2))
        alpha_map[top:bottom] = alpha
        residual = src[top:bottom] - (surface - alpha[:, :, None] * vector)
        compatible = np.linalg.norm(residual, axis=2) <= 24
        # Old wide-core pixels already contain native ink coverage. Project
        # their edge colors onto observed ink/clean paint, preserving that
        # coverage while removing off-color contamination. Outside the old
        # core, clean paint only; do not restore a native opacity residual.
        edge = core[top:bottom] & (alpha < 0.8)
        background = ~core[top:bottom] & (alpha <= 0.25)
        replacement = surface.copy()
        mixed = surface - np.clip(alpha, 0, 1)[:, :, None] * vector
        replacement[edge] = mixed[edge]
        bounded = np.linalg.norm(replacement - src[top:bottom], axis=2) <= 90
        use = eligible & (count >= 2) & (edge | background) & ~ink[top:bottom] & compatible & bounded
        fade = np.clip(6 - distance[top:bottom], 0, 1)
        candidate = output[top:bottom].astype(np.float32) + (replacement - output[top:bottom]) * fade[:, :, None] * (strength / 100)
        output[top:bottom][use] = np.uint8(np.clip(candidate + 0.5, 0, 255))[use]
        active[top:bottom] = use
    signed = output.astype(np.int16) - original.astype(np.int16)
    changed = np.any(signed != 0, axis=2)
    report = {
        'strength': float(strength),
        'changed_pixels_percent': float(changed.mean() * 100),
        'mean_rgb_change': float(np.abs(signed).mean()),
        'maximum_rgb_change': int(np.abs(signed).max()),
        'ink_seed_pixels': int(ink.sum()),
        'ink_pixels_changed': int(np.any(signed[ink] != 0, axis=1).sum()),
        'old_core_pixels_changed': int((changed & core).sum()),
        'old_core_pixels': int(core.sum()),
        'reach_pixels': 6,
        'maximum_replacement_rgb_distance': 90,
        'maximum_profile_residual': 24,
        'algorithm': 'one-sided coarse paint; observed ink coverage; blocked sampling paths',
        'note': 'Old wide core may change. Measured ink and stronger coverage remain. Antialiased colors may change using observed ink/clean paint; no fixed black.',
        'seconds': perf_counter() - start,
    }
    maps = {
        'border_ink': ink.astype(np.float32),
        'border_surface_candidates': active.astype(np.float32),
        'border_ink_coverage': np.clip(alpha_map, 0, 1),
        'border_signed_rgb': signed,
        'border_change': np.mean(np.abs(signed).astype(np.float32), axis=2) / 16,
    } if diagnostics else {}
    return (output, maps, report)
