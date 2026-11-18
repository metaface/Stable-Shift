"""Fit smooth stroke centers and widths, then rebuild their pixel coverage.

Only edited-image evidence locates strokes. Ink comes from the cleaned native
image. Signed coverage changes remove ragged protrusions as well as fill weak
parts; minimum-filter darkening is not used as the replacement geometry.
"""
from time import perf_counter
import cv2
import numpy as np
from .line_borders import LUMA
from .stroke_paths import trace_stroke_paths
from .stroke_cleanup import _ink_quartile


def _arc_distance(first, second, length, closed):
    difference = np.abs(first-second)
    # Only an actually closed graph chain has a modular shortcut. Nearby ends
    # of an open U-shaped line must not exchange samples across their blank gap.
    return np.where(closed, np.minimum(difference, np.abs(length-difference)), difference)


def reconstruct_lines(base, source_core, *, paths=None):
    """Return regular/strong analytic stroke candidates on one clean base."""
    started = perf_counter()
    if (base.dtype != np.uint8 or base.ndim != 3 or base.shape[2] != 3 or min(base.shape[:2]) < 1):
        raise ValueError('Line reconstruction needs a nonempty uint8 RGB image.')
    core = np.asarray(source_core, dtype=bool)
    if core.shape != base.shape[:2]:
        raise ValueError('Line support must match the image.')
    src = base.astype(np.float32)
    if paths is None:
        paths = trace_stroke_paths(base, core)
    band = paths['application']
    mask = paths['candidates'] & band
    if not np.any(band):
        return base.copy(), base.copy(), band, {'modeled_ink_pixels': 0, 'seconds': perf_counter()-started, 'trace_validation': paths['report']}
    path_ids = paths['path_ids'].astype(np.float32)
    sample_ids = paths['sample_path_ids'].astype(np.float32)
    arc = paths['arc_positions']
    path_length = paths['path_lengths'][paths['path_ids']]
    path_closed = paths['path_closed'][paths['path_ids']]
    def native_sample(field, qx, qy):
        # Nearest native samples avoid bilinear mixing across two path IDs at
        # a crossing or narrow gap. Antialiasing is rebuilt from fitted coverage.
        return cv2.remap(field, qx, qy, cv2.INTER_NEAREST, borderMode=cv2.BORDER_REPLICATE)
    def same_path(qx, qy, top, bottom, distance):
        other = cv2.remap(sample_ids, qx, qy, cv2.INTER_NEAREST, borderMode=cv2.BORDER_CONSTANT)
        other_arc = cv2.remap(arc, qx, qy, cv2.INTER_NEAREST, borderMode=cv2.BORDER_CONSTANT)
        difference = _arc_distance(other_arc, arc[top:bottom], path_length[top:bottom], path_closed[top:bottom])
        return (other == path_ids[top:bottom]) & (other > 0) & (difference <= distance)
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
    ink_valid = np.zeros(core.shape, bool)
    observed_ink = np.uint8(paths['candidates'])
    h, w = core.shape
    for top in range(0, h, 96):
        bottom = min(h, top+96)
        cy, cx = np.mgrid[top:bottom, :w].astype(np.float32)
        ux, uy = nx[top:bottom], ny[top:bottom]
        have_ink = paths['candidates'][top:bottom] & (sample_ids[top:bottom] > 0)
        darkest = np.full_like(src[top:bottom], 255)
        darkest[have_ink] = src[top:bottom][have_ink]
        for shift in (-3., -2., -1., 1., 2., 3.):
            qx, qy = cx+ux*shift, cy+uy*shift
            value = native_sample(src, qx, qy)
            observed = (native_sample(observed_ink, qx, qy) > 0) & same_path(qx, qy, top, bottom, 3.)
            use = observed & (~have_ink | (value@LUMA < darkest@LUMA))
            darkest[use] = value[use]
            have_ink |= observed
        darkest[~have_ink] = src[top:bottom][~have_ink]
        ink[top:bottom] = darkest
        ink_valid[top:bottom] = have_ink
    # Color smoothing is confined to the same observed chain as well. A nearby
    # dark nose, crossing or parallel seam cannot supply its ink color.
    smoothed_ink = ink.copy()
    for top in range(0, h, 96):
        bottom = min(h, top+96)
        cy, cx = np.mgrid[top:bottom, :w].astype(np.float32)
        values = [ink[top:bottom]]
        for shift in (-4., -2., 2., 4.):
            qx, qy = cx-ny[top:bottom]*shift, cy+nx[top:bottom]*shift
            value = native_sample(ink, qx, qy)
            valid = same_path(qx, qy, top, bottom, abs(shift)*1.8+3) & (native_sample(np.uint8(ink_valid), qx, qy) > 0)
            value[~valid] = np.nan
            values.append(value)
        smoothed_ink[top:bottom] = _ink_quartile(values)
    ink = smoothed_ink
    vector = surface-ink
    raw_alpha = np.sum((surface-src)*vector, axis=2)/np.maximum(1, np.sum(vector*vector, axis=2))
    alpha = np.clip(raw_alpha, 0, 1)
    model_residual = src-(surface-alpha[..., None]*vector)
    compatible_margin = ((raw_alpha >= -.15) & (raw_alpha <= 1.35)
                         & (np.linalg.norm(model_residual, axis=2) <= 40))
    # A neighboring dark feature that is not observed ink must not be consumed
    # as an antialiased stroke margin merely because it lies in the same cell.
    band = band & ink_valid & (paths['candidates'] | compatible_margin)
    alpha[~band | (alpha < .08)] = 0
    residual = src-(surface-alpha[..., None]*vector)
    centers = np.zeros(core.shape, np.float32)
    widths = np.zeros(core.shape, np.float32)
    for top in range(0, h, 96):
        bottom = min(h, top+96)
        cy, cx = np.mgrid[top:bottom, :w].astype(np.float32)
        ux, uy = nx[top:bottom], ny[top:bottom]
        shifts = np.arange(-6, 7, dtype=np.float32)
        values = np.stack([np.where(same_path(cx+ux*shift, cy+uy*shift, top, bottom, 3.),
            native_sample(alpha, cx+ux*shift, cy+uy*shift), 0) for shift in shifts])
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
    for sigma in (5., 8.):
        coverage = np.zeros(core.shape, np.float32)
        fitted_centers = np.zeros(core.shape, np.float32)
        fitted_widths = np.zeros(core.shape, np.float32)
        for top in range(0, h, 96):
            bottom = min(h, top+96)
            cy, cx = np.mgrid[top:bottom, :w].astype(np.float32)
            ux, uy = nx[top:bottom], ny[top:bottom]
            total = np.zeros(cx.shape, np.float32)
            fitted_center = np.zeros(cx.shape, np.float32)
            fitted_width = np.zeros(cx.shape, np.float32)
            for distance in range(-12, 13, 2):
                qx, qy = cx-uy*distance, cy+ux*distance
                g = native_sample(geometry, qx, qy)
                agreement = ux*g[..., 0]+uy*g[..., 1]
                # Transport nearby measured center positions onto this normal.
                center = (np.rint(qx)-cx+g[..., 0]*g[..., 2])*ux+(np.rint(qy)-cy+g[..., 1]*g[..., 2])*uy
                valid = same_path(qx, qy, top, bottom, abs(distance)*1.8+3)
                weight = np.exp(-distance*distance/(2*sigma*sigma))*((g[..., 3] > .6) & (np.abs(agreement) > .7) & valid)
                total += weight
                fitted_center += weight*center
                fitted_width += weight*g[..., 3]
            fitted_center /= np.maximum(total, 1e-5)
            fitted_width /= np.maximum(total, 1e-5)
            fitted_centers[top:bottom] = fitted_center
            fitted_widths[top:bottom] = fitted_width
            # 4x4 subpixel area sampling, rather than sharpening/dilating edges.
            for dy in (-.375, -.125, .125, .375):
                for dx in (-.375, -.125, .125, .375):
                    coverage[top:bottom] += (np.abs(fitted_center+dx*ux+dy*uy) < fitted_width/2)/16
        # A normal cross-section must contain current ink. This keeps smoothing
        # from extending along a tangent through intentional gaps between dashes.
        active = band & (widths > .6)
        # Preserve each actual path's integrated opacity, rather than letting
        # normal-field jitter silently turn the smoothed curve into wider ink.
        ids = paths['path_ids'][active]
        original_area = np.bincount(ids, weights=alpha[active], minlength=len(paths['path_lengths']))
        fitted_area = np.bincount(ids, weights=coverage[active], minlength=len(paths['path_lengths']))
        ratio = np.ones(len(original_area), np.float32)
        valid = fitted_area > 1
        ratio[valid] = original_area[valid]/fitted_area[valid]
        fitted_widths *= ratio[paths['path_ids']]
        coverage.fill(0)
        for dy in (-.375, -.125, .125, .375):
            for dx in (-.375, -.125, .125, .375):
                coverage += (np.abs(fitted_centers+dx*nx+dy*ny) < fitted_widths/2)/16
        coverage[~active] = alpha[~active]
        candidate = src+(alpha-coverage)[..., None]*vector-residual*coverage[..., None]
        output = base.copy()
        output[active] = np.uint8(np.clip(candidate+.5, 0, 255))[active]
        outputs.append(output)
    report = {'algorithm': 'connected-path stroke fitting; native same-path ink; integrated-width preservation',
        'supersampling': 4, 'regular_tangent_sigma_pixels': 5.,
        'strong_tangent_sigma_pixels': 8., 'modeled_ink_pixels': int(mask.sum()),
        'application_pixels': int(band.sum()), 'seconds': perf_counter()-started,
        'trace_validation': paths['report'],
        'note': 'Both lighter and darker changes smooth boundaries; width is measured, not increased. No fixed black.'}
    return outputs[0], outputs[1], band, report
