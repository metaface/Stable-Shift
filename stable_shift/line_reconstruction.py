"""Fit smooth stroke centers and widths, then rebuild their pixel coverage.

Only edited-image evidence locates strokes. Ink comes from the cleaned native
image. Signed coverage changes remove ragged protrusions as well as fill weak
parts; minimum-filter darkening is not used as the replacement geometry.
"""
from time import perf_counter
import cv2
import numpy as np
from .line_borders import LUMA, sample


def reconstruct_lines(base, source_core):
    """Return regular/strong analytic stroke candidates on one clean base."""
    started = perf_counter()
    if (base.dtype != np.uint8 or base.ndim != 3 or base.shape[2] != 3 or min(base.shape[:2]) < 1):
        raise ValueError('Line reconstruction needs a nonempty uint8 RGB image.')
    core = np.asarray(source_core, dtype=bool)
    if core.shape != base.shape[:2]:
        raise ValueError('Line support must match the image.')
    src = base.astype(np.float32)
    light = src@LUMA
    background = cv2.morphologyEx(light, cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (13, 13)))
    depth = np.maximum(0, background-light)
    local_depth = cv2.dilate(depth, np.ones((11, 11), np.uint8))
    mask = core & (depth > np.maximum(1.5, .42*local_depth))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(np.uint8(mask), 8)
    keep = stats[:, cv2.CC_STAT_AREA] >= 5
    keep[0] = False
    mask = keep[labels]
    if not np.any(mask):
        return base.copy(), base.copy(), mask, {'modeled_ink_pixels': 0, 'seconds': perf_counter()-started}
    band = cv2.dilate(np.uint8(mask), np.ones((3, 3), np.uint8)) > 0
    # This is an under-ink color estimate, not a replacement image. Signed
    # coverage changes retain the part of native paint not explained as ink.
    surface = cv2.inpaint(base, np.uint8(band)*255, 4, cv2.INPAINT_TELEA).astype(np.float32)
    guide = cv2.GaussianBlur(src, (0, 0), 1.)
    gx, gy = cv2.Scharr(guide, -1, 1, 0), cv2.Scharr(guide, -1, 0, 1)
    xx = cv2.GaussianBlur(np.sum(gx*gx, axis=2), (0, 0), 1.8)
    yy = cv2.GaussianBlur(np.sum(gy*gy, axis=2), (0, 0), 1.8)
    xy = cv2.GaussianBlur(np.sum(gx*gy, axis=2), (0, 0), 1.8)
    angle = .5*np.arctan2(2*xy, xx-yy)
    nx, ny = np.cos(angle), np.sin(angle)
    ink = src.copy()
    h, w = core.shape
    for top in range(0, h, 96):
        bottom = min(h, top+96)
        cy, cx = np.mgrid[top:bottom, :w].astype(np.float32)
        ux, uy = nx[top:bottom], ny[top:bottom]
        darkest = src[top:bottom].copy()
        for shift in (-3., -2., -1., 1., 2., 3.):
            value = sample(src, cx+ux*shift, cy+uy*shift)
            use = value@LUMA < darkest@LUMA
            darkest[use] = value[use]
        ink[top:bottom] = darkest
    ink = cv2.medianBlur(ink, 5)
    vector = surface-ink
    alpha = np.clip(np.sum((surface-src)*vector, axis=2)/np.maximum(1, np.sum(vector*vector, axis=2)), 0, 1)
    alpha[~band | (alpha < .08)] = 0
    residual = src-(surface-alpha[..., None]*vector)
    centers = np.zeros(core.shape, np.float32)
    widths = np.zeros(core.shape, np.float32)
    for top in range(0, h, 96):
        bottom = min(h, top+96)
        cy, cx = np.mgrid[top:bottom, :w].astype(np.float32)
        ux, uy = nx[top:bottom], ny[top:bottom]
        shifts = np.arange(-6, 7, dtype=np.float32)
        values = np.stack([sample(alpha, cx+ux*shift, cy+uy*shift) for shift in shifts])
        occupied = values > .08
        starts = occupied & ~np.concatenate((np.zeros_like(occupied[:1]), occupied[:-1]), axis=0)
        groups = np.cumsum(starts, axis=0)
        anchor = np.argmin(np.where(occupied, np.abs(shifts)[:, None, None], 100), axis=0)
        group = np.take_along_axis(groups, anchor[None], axis=0)
        values = np.where(occupied & (groups == group), values, 0)
        # Integrate only the nearest connected cross-section: nearby parallel
        # seams must not be interpreted as one wider stroke.
        mass = values.sum(axis=0)
        offset = (values*shifts[:, None, None]).sum(axis=0)
        centers[top:bottom] = offset/np.maximum(mass, 1e-5)
        widths[top:bottom] = mass
    geometry = np.stack((nx, ny, centers, widths), axis=2)
    outputs = []
    for sigma in (4., 7.):
        coverage = np.zeros(core.shape, np.float32)
        for top in range(0, h, 96):
            bottom = min(h, top+96)
            cy, cx = np.mgrid[top:bottom, :w].astype(np.float32)
            ux, uy = nx[top:bottom], ny[top:bottom]
            total = np.zeros(cx.shape, np.float32)
            fitted_center = np.zeros(cx.shape, np.float32)
            fitted_width = np.zeros(cx.shape, np.float32)
            for distance in range(-12, 13, 2):
                qx, qy = cx-uy*distance, cy+ux*distance
                g = sample(geometry, qx, qy)
                agreement = ux*g[..., 0]+uy*g[..., 1]
                # Transport nearby measured center positions onto this normal.
                center = (qx-cx+g[..., 0]*g[..., 2])*ux+(qy-cy+g[..., 1]*g[..., 2])*uy
                weight = np.exp(-distance*distance/(2*sigma*sigma))*((g[..., 3] > .6) & (np.abs(agreement) > .7))
                total += weight
                fitted_center += weight*center
                fitted_width += weight*g[..., 3]
            fitted_center /= np.maximum(total, 1e-5)
            fitted_width /= np.maximum(total, 1e-5)
            # 4x4 subpixel area sampling, rather than sharpening/dilating edges.
            for dy in (-.375, -.125, .125, .375):
                for dx in (-.375, -.125, .125, .375):
                    coverage[top:bottom] += (np.abs(fitted_center+dx*ux+dy*uy) < fitted_width/2)/16
        # A normal cross-section must contain current ink. This keeps smoothing
        # from extending along a tangent through intentional gaps between dashes.
        active = band & (widths > .6)
        coverage[~active] = alpha[~active]
        candidate = src+(alpha-coverage)[..., None]*vector-residual*coverage[..., None]
        output = base.copy()
        output[active] = np.uint8(np.clip(candidate+.5, 0, 255))[active]
        outputs.append(output)
    report = {'algorithm': 'fitted stroke centers and integrated widths; signed RGB coverage correction',
        'supersampling': 4, 'regular_tangent_sigma_pixels': 4.,
        'strong_tangent_sigma_pixels': 7., 'modeled_ink_pixels': int(mask.sum()),
        'application_pixels': int(band.sum()), 'seconds': perf_counter()-started,
        'note': 'Both lighter and darker changes smooth boundaries; width is measured, not increased. No fixed black.'}
    return outputs[0], outputs[1], band, report
