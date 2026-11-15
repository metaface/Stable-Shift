"""Native RGB stroke-profile cleanup along a curved direction field.

The accepted source map locates possible lines. Two-sided color contrast then
distinguishes darker ink from an ordinary color boundary. RGB samples from this
post-color image supply the replacement; no black paint or reference geometry.
At strength 100 the full candidate is applied, without confidence attenuation.
"""
from copy import deepcopy
import math
from time import perf_counter

import cv2
import numpy as np
from PIL import Image


LUMA = np.array([.299, .587, .114], np.float32)
RADIUS = 9
ROWS = 96


def validate_strength(strength):
    if not math.isfinite(strength) or not 0 <= strength <= 100:
        raise ValueError('Stroke cleanup strength must be between 0 and 100.')


def _sample(data, x, y):
    return cv2.remap(data, x, y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)


def _ink_quartile(samples):
    """Choose one actual RGB sample from the darker quarter, not fixed black.

    Intact ink should beat the pale cuts from a colored grid. The quarter rank
    also ignores isolated darkest outliers when several observations exist.
    """
    stack = np.stack(samples)
    light = stack @ LUMA
    count = np.sum(np.isfinite(light), axis=0)
    index = np.floor((count-1)*.25).astype(np.int32)
    order = np.argsort(np.nan_to_num(light, nan=np.inf), axis=0, kind='stable')
    selected = np.take_along_axis(order, index[None, ...], axis=0)
    return np.take_along_axis(stack, np.broadcast_to(selected[..., None], (1, *index.shape, 3)), axis=0)[0]


def clean_strokes(rgb, strength=0, source_core=None, diagnostics=True, progress=None):
    validate_strength(strength)
    rgb = np.asarray(rgb)
    if rgb.dtype != np.uint8 or rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError('Stroke cleanup requires uint8 RGB pixels.')
    if source_core is not None and np.shape(source_core) != rgb.shape[:2]:
        raise ValueError('Stroke source map must match the image dimensions.')
    report = {'strength': float(strength), 'sample_radius_pixels': RADIUS,
              'changed_pixels_percent': 0., 'mean_rgb_change': 0.,
              'algorithm': 'normal-aligned curved RGB profiles; observed ink quartile; short-stroke background rejection',
              'note': 'Full candidate at 100; existing darker strokes only. Source-core protection ends before optional finishing.'}
    if strength == 0:
        return rgb.copy(), {}, report
    if source_core is None:
        from .engine import structure_maps
        from .line_protection import trace_source_lines
        image = Image.fromarray(rgb)
        source_core = trace_source_lines(rgb, structure_maps(image), continue_faint=False)['source_line_core'] > .5
        report['map_origin'] = 'Traced from post-color image because no carried source map was supplied.'
    else:
        source_core = np.asarray(source_core) > .5
        report['map_origin'] = 'Carried source map; replacement colors come from the post-color image.'
    if progress:
        progress('Stroke cleanup: measuring RGB cross-sections and directions')
    src = rgb.astype(np.float32)
    guide = cv2.GaussianBlur(src, (0, 0), .8)
    gx = cv2.Scharr(guide, cv2.CV_32F, 1, 0)
    gy = cv2.Scharr(guide, cv2.CV_32F, 0, 1)
    xx = cv2.GaussianBlur(np.sum(gx*gx, axis=2), (0, 0), 1.35)
    yy = cv2.GaussianBlur(np.sum(gy*gy, axis=2), (0, 0), 1.35)
    xy = cv2.GaussianBlur(np.sum(gx*gy, axis=2), (0, 0), 1.35)
    angle = .5*np.arctan2(2*xy, xx-yy)
    nx, ny = np.cos(angle), np.sin(angle)
    tangent = np.stack((-ny, nx), axis=2).astype(np.float32)
    coherence = np.sqrt((xx-yy)**2+4*xy*xy)/(xx+yy+1e-5)
    h, w = src.shape[:2]
    ridge = np.zeros((h, w), np.float32)
    # An ink cross-section differs in a compatible direction from BOTH flanks.
    # A broad shading/smoke step has a matching flank and is not a thin stroke.
    for top in range(0, h, ROWS):
        bottom = min(h, top+ROWS)
        cy, cx = np.mgrid[top:bottom, :w].astype(np.float32)
        nxx, nyy = nx[top:bottom], ny[top:bottom]
        center = src[top:bottom]
        for radius in (2.5, 4., 6.):
            da = _sample(src, cx+nxx*radius, cy+nyy*radius)-center
            db = _sample(src, cx-nxx*radius, cy-nyy*radius)-center
            a, b = np.linalg.norm(da, axis=2), np.linalg.norm(db, axis=2)
            agreement = np.maximum(0, np.sum(da*db, axis=2)/(a*b+1e-5))
            agreement *= ((da @ LUMA > .8) & (db @ LUMA > .8))
            ridge[top:bottom] = np.maximum(ridge[top:bottom], np.minimum(a, b)*agreement)
    # Extend sample support across the line width, not along dash gaps.
    context = np.zeros((h, w), np.float32)
    center_offset = np.zeros((h, w), np.float32)
    for top in range(0, h, ROWS):
        bottom = min(h, top+ROWS)
        cy, cx = np.mgrid[top:bottom, :w].astype(np.float32)
        weight_sum = np.zeros(cx.shape, np.float32)
        weighted_offset = np.zeros(cx.shape, np.float32)
        for shift in (-3, -2, -1, 0, 1, 2, 3):
            response = _sample(ridge, cx+nx[top:bottom]*shift, cy+ny[top:bottom]*shift)
            context[top:bottom] = np.maximum(context[top:bottom], response)
            weight = np.square(response)
            weight_sum += weight
            weighted_offset += shift*weight
        center_offset[top:bottom] = weighted_offset/np.maximum(weight_sum, 1e-5)
    geometry = np.stack((nx, ny, center_offset), axis=2)
    output = rgb.copy()
    potential = source_core & (context > 5) & (coherence > .1)
    active = np.zeros((h, w), bool)
    continuous_map = np.zeros((h, w), bool)
    if progress:
        progress('Stroke cleanup: replacing along-path fluctuations at requested strength')
    for top in range(0, h, ROWS):
        bottom = min(h, top+ROWS)
        use = potential[top:bottom]
        if not np.any(use):
            continue
        cy, cx = np.mgrid[top:bottom, :w].astype(np.float32)
        center = src[top:bottom]
        originals, isolated = [center], [center]
        ink_samples = [(ridge[top:bottom] > 5).astype(np.float32)]
        distance_from_center = -center_offset[top:bottom]
        initial_normal = np.stack((nx[top:bottom], ny[top:bottom]), axis=2)
        for direction in (-1, 1):
            px = cx+nx[top:bottom]*center_offset[top:bottom]
            py = cy+ny[top:bottom]*center_offset[top:bottom]
            previous = tangent[top:bottom]*direction
            for distance in range(1, RADIUS+1):
                flow = _sample(tangent, px, py)
                sign = np.where(np.sum(flow*previous, axis=2) < 0, -1, 1).astype(np.float32)
                flow *= sign[..., None]
                px += flow[..., 0]
                py += flow[..., 1]
                previous = flow
                if distance % 2 == 0 or distance == RADIUS:
                    normal = _sample(geometry, px, py)
                    px += normal[..., 0]*normal[..., 2]
                    py += normal[..., 1]*normal[..., 2]
                    normal_sign = np.where(np.sum(normal[..., :2]*initial_normal, axis=2) < 0, -1, 1)
                    qx = px+normal[..., 0]*normal_sign*distance_from_center
                    qy = py+normal[..., 1]*normal_sign*distance_from_center
                    value = _sample(src, qx.astype(np.float32), qy.astype(np.float32))
                    # A nearby crossing/outline must not lend black paint to a
                    # pale surface or a differently colored stroke. The range
                    # scales with this pixel's own measured stroke contrast,
                    # so a genuinely faded dark line can still recover its ink.
                    compatible = np.linalg.norm(value-center, axis=2) <= np.maximum(24, ridge[top:bottom]*2.5)
                    observed = value.copy()
                    observed[~compatible] = np.nan
                    originals.append(observed)
                    ink_samples.append(((_sample(ridge, qx.astype(np.float32), qy.astype(np.float32)) > 5) & compatible).astype(np.float32))
                    guarded = value.copy()
                    background = (value @ LUMA) > (center @ LUMA)+np.maximum(3, ridge[top:bottom]*.20)
                    guarded[(_sample(context, qx.astype(np.float32), qy.astype(np.float32)) <= 4) | background | ~compatible] = np.nan
                    isolated.append(guarded)
        # Continuous profiles may regularize their edges. Short dashes use only
        # ink-compatible samples, so surrounding blue cannot erase the stitches.
        continuous = np.mean(np.stack(ink_samples), axis=0) >= .55
        use = use & ((ridge[top:bottom] > 5) | continuous)
        active[top:bottom] = use
        continuous_map[top:bottom] = continuous & use
        candidate = _ink_quartile(isolated)
        ordinary = _ink_quartile(originals)
        candidate[continuous] = ordinary[continuous]
        candidate = np.uint8(np.clip(candidate+.5, 0, 255))
        blended = np.uint8(np.clip(center+(candidate.astype(np.float32)-center)*(strength/100)+.5, 0, 255))
        output[top:bottom][use] = blended[use]
    change = np.abs(output.astype(np.int16)-rgb.astype(np.int16))
    report.update(candidate_pixels_percent=float(100*np.mean(active)),
                  continuous_profile_pixels_percent=float(100*np.mean(continuous_map)),
                  changed_pixels_percent=float(100*np.mean(np.any(change > 0, axis=2))),
                  mean_rgb_change=float(change.mean()), maximum_rgb_change=int(change.max()),
                  mean_rgb_change_on_candidates=float(change[active].mean()) if np.any(active) else 0.)
    maps = {'stroke_support': active.astype(np.float32),
            'stroke_continuous': continuous_map.astype(np.float32),
            'stroke_ridge': ridge/100} if diagnostics else {}
    return output, maps, report


def refinish_strokes(post_color, maps, strength, antialias_strength=0, progress=None):
    """Rebuild finishing from fixed post-color pixels, with actual run metadata."""
    from .antialias import antialias
    started = perf_counter()
    result, detail, stroke_report = clean_strokes(post_color, strength,
        maps.get('source_line_core'), diagnostics=True, progress=progress)
    stroked = perf_counter()
    final = antialias(result, antialias_strength)
    filtered = perf_counter()
    updated = dict(maps)
    for key in ('stroke_support', 'stroke_continuous', 'stroke_ridge'):
        updated.pop(key, None)
    updated.update(detail)
    stroke_signed = result.astype(np.int16)-post_color.astype(np.int16)
    aa_signed = final.astype(np.int16)-result.astype(np.int16)
    old_stroke = maps.get('stroke_signed_rgb', np.zeros_like(result, np.int16))
    old_aa = maps.get('antialias_signed_rgb', np.zeros_like(result, np.int16))
    updated['stroke_signed_rgb'] = stroke_signed
    updated['stroke_change'] = np.mean(np.abs(stroke_signed.astype(np.float32)), axis=2)/16
    updated['antialias_signed_rgb'] = aa_signed
    updated['antialias_change'] = np.mean(np.abs(aa_signed.astype(np.float32)), axis=2)/16
    updated['total_signed_rgb'] = maps['total_signed_rgb']-old_stroke-old_aa+stroke_signed+aa_signed
    updated['total_change'] = np.mean(np.abs(updated['total_signed_rgb'].astype(np.float32)), axis=2)/16
    updated['difference'] = updated['total_change']*(16/70)
    finished = perf_counter()
    report = deepcopy(maps['report'])
    report.setdefault('original_full_run_seconds', report['total_seconds'])
    upstream = report['total_seconds']-report.get('stroke_seconds', 0)-report['antialias_seconds']-report['diagnostics_seconds']
    report.update(stroke_seconds=stroked-started, antialias_seconds=filtered-stroked,
                  diagnostics_seconds=finished-filtered, total_seconds=upstream+finished-started,
                  finishing_preview_seconds=finished-started, stroke_cleanup=stroke_report,
                  timing_note='Original upstream timings plus latest stroke/AA/diagnostics. Finishing preview reruns no denoising or color fitting.')
    report.pop('antialias_preview_seconds', None)
    for key in ('options', 'effective_options'):
        report[key].update(stroke_strength=strength, antialias_strength=antialias_strength)
    updated['report'] = report
    return final, updated
