"""Full-resolution, boundary-constrained multiscale surface estimates.

All samples come from the supplied edited/denoised image. Small, medium and
broad neighborhoods are estimated independently, then joined with difference
bands. This is a sparse spatial/range estimator, not semantic segmentation.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Callable

import cv2
import numpy as np


@dataclass(frozen=True)
class RegionOptions:
    strength: float = 60.0
    color_range: float = 12.0  # approximate CIELAB color distance, not RGB
    luminance: float = 60.0   # amount of brightness cleanup relative to chroma
    radius: int = 16         # broad neighborhood radius at native resolution

    def validated(self):
        vals = (self.strength, self.color_range, self.luminance, self.radius)
        if not all(math.isfinite(float(v)) for v in vals):
            raise ValueError('Cleanup settings must be finite numbers.')
        if not 0 <= self.strength <= 100 or not 0 <= self.luminance <= 100:
            raise ValueError('Cleanup strength and brightness must be between 0 and 100.')
        if not 2 <= self.color_range <= 40:
            raise ValueError('Color similarity range must be between 2 and 40 LAB units.')
        if int(self.radius) != self.radius or not 2 <= self.radius <= 32:
            raise ValueError('Neighborhood radius must be an integer between 2 and 32.')
        return self


def _pairs(shape, dy, dx, distance=1):
    """Corresponding slices for two pixels separated by an integer offset."""
    h, w = shape[:2]
    oy, ox = dy * distance, dx * distance
    ay0, ay1 = max(0, -oy), min(h, h - oy)
    ax0, ax1 = max(0, -ox), min(w, w - ox)
    if ay1 <= ay0 or ax1 <= ax0:
        return None
    a = (slice(ay0, ay1), slice(ax0, ax1))
    b = (slice(ay0 + oy, ay1 + oy), slice(ax0 + ox, ax1 + ox))
    return a, b


def _distance2(a, b):
    d = a - b
    # Luminance and chroma both define boundaries, including same-brightness edges.
    return np.einsum('...c,...c->...', d, d, optimize=True)


def boundary_graph(lab, color_range, protected=None):
    """Fixed graph; a blocked link cannot pass samples at any neighborhood size.

    A softly filtered image is used ONLY to measure boundaries, never as the
    output color field. Strong native-resolution jumps also block links so thin
    dark lines aren't dependent on surviving the guide filter.
    """
    h, w = lab.shape[:2]
    if protected is not None:
        protected = np.asarray(protected, dtype=bool)
        if protected.shape != (h, w):
            raise ValueError('Source protection and cleanup image dimensions must match.')
    guide = cv2.GaussianBlur(lab, (3, 3), .65, borderType=cv2.BORDER_REFLECT)
    guide_limit2 = max(2.5, color_range * .55) ** 2
    raw_limit2 = (color_range * 1.5) ** 2
    links = {}
    boundary = np.zeros((h, w), np.uint8)
    for dy, dx in ((0, 1), (1, 0)):
        gate = np.zeros((h, w), bool)
        pair = _pairs(lab.shape, dy, dx)
        if pair:
            a, b = pair
            candidates = (_distance2(guide[a], guide[b]) >= guide_limit2)
            candidates |= (_distance2(lab[a], lab[b]) >= raw_limit2)
            # Isolated grain must not turn every neighborhood into a barrier.
            # Require three aligned candidate links in a five-link segment,
            # allowing straight and diagonal contour directions.
            support = np.zeros(candidates.shape, np.float32)
            straight = np.ones((5, 1) if dx else (1, 5), np.float32)
            for kernel in (straight, np.eye(5, dtype=np.float32), np.fliplr(np.eye(5, dtype=np.float32))):
                count = cv2.filter2D(candidates.astype(np.float32), -1, kernel, borderType=cv2.BORDER_CONSTANT)
                np.maximum(support, count, out=support)
            allowed = ~(candidates & (support >= 3))
            if protected is not None:
                # The original linked structure is a hard constraint, even if
                # the denoised image no longer has a detectable local jump.
                allowed &= ~(protected[a] | protected[b])
            gate[a] = allowed
            boundary[a] |= (~allowed).astype(np.uint8)
            boundary[b] |= (~allowed).astype(np.uint8)
        links[(dy, dx)] = gate
    # Both routes around a diagonal must be open: no cutting across corners.
    for dy, dx in ((1, 1), (1, -1)):
        gate = np.zeros((h, w), bool)
        pair = _pairs(lab.shape, dy, dx)
        if pair:
            a, b = pair
            y0, y1, x0, x1 = a[0].start, a[0].stop, a[1].start, a[1].stop
            hleft = slice(x0 if dx > 0 else x0 - 1, x1 if dx > 0 else x1 - 1)
            gate[a] = (
                links[(0, 1)][slice(y0, y1), hleft]
                & links[(0, 1)][slice(y0 + 1, y1 + 1), hleft]
                & links[(1, 0)][slice(y0, y1), slice(x0, x1)]
                & links[(1, 0)][slice(y0, y1), slice(x0 + dx, x1 + dx)]
            )
        links[(dy, dx)] = gate
    return links, boundary


def surface_cleanup(rgb, options=RegionOptions(), diagnostics=True,
                    progress: Callable[[str], None] | None = None, protected=None):
    """Estimate compatible neighboring colors without traversing blocked links.

    Range weights compare each candidate directly with its target, as well as
    testing the entire path. Neighborhoods never grow by chaining color matches.
    Strong boundary pixels are excluded from correction from the outset.
    """
    options = options.validated()
    rgb = np.asarray(rgb)
    if rgb.ndim != 3 or rgb.shape[2] != 3 or rgb.dtype != np.uint8:
        raise ValueError('Cleanup expects an H x W x 3 uint8 RGB image.')
    if min(rgb.shape[:2]) < 1:
        raise ValueError('Image dimensions must be positive.')
    if options.strength == 0:
        return rgb.copy(), {}, {'changed_pixels_percent': 0.0, 'mean_rgb_change': 0.0}
    lab = cv2.cvtColor(rgb.astype(np.float32) / 255, cv2.COLOR_RGB2LAB)
    links, boundary = boundary_graph(lab, options.color_range, protected)
    eligible = boundary == 0
    broad = int(options.radius)
    radii = (min(2, broad), min(6, broad), broad)
    distances = sorted({1, 2, 3, 4, 6, 8, 12, 16, 24, 32, broad} & set(range(1, broad + 1)))
    # Independent sums: none of the three fields is derived from another field.
    sums = [lab.copy() for _ in radii]
    counts = [np.ones(lab.shape[:2], np.float32) for _ in radii]
    sample_count = np.ones(lab.shape[:2], np.float32)
    limit2 = float(options.color_range) ** 2
    for direction, (dy, dx) in enumerate(((0, 1), (1, 0), (1, 1), (1, -1))):
        if progress:
            progress(f'Surface estimates: direction {direction + 1}/4')
        reachable = np.ones(lab.shape[:2], bool)
        gate = links[(dy, dx)]
        for distance in range(1, broad + 1):
            pair = _pairs(lab.shape, dy, dx, distance)
            if pair is None:
                break
            a, b = pair
            offset_y, offset_x = (distance - 1) * dy, (distance - 1) * dx
            path_edge = (slice(a[0].start + offset_y, a[0].stop + offset_y),
                         slice(a[1].start + offset_x, a[1].stop + offset_x))
            reachable[a] &= gate[path_edge]
            if distance not in distances:
                continue
            delta2 = _distance2(lab[a], lab[b])
            # Tukey range weight goes exactly to zero at the color-range limit.
            weight = np.square(np.maximum(0, 1 - delta2 / limit2))
            weight *= reachable[a]
            for side, other in ((a, b), (b, a)):
                target_weight = weight * eligible[side]
                sample_count[side] += (target_weight > .05)
                for level, radius in enumerate(radii):
                    if distance > radius:
                        continue
                    spatial = math.exp(-.5 * (distance / max(1, radius * .6)) ** 2)
                    wgt = target_weight * spatial
                    sums[level][side] += lab[other] * wgt[..., None]
                    counts[level][side] += wgt
    fine, medium, coarse = [s / n[..., None] for s, n in zip(sums, counts)]
    # Near boundaries, favor small neighborhoods; in interiors, favor the broad
    # estimate. This distance rule selects residuals, not cross-boundary samples.
    distance = cv2.distanceTransform(eligible.astype(np.uint8), cv2.DIST_L2, 3)
    near = np.clip(1 - distance / max(3., broad * .6), 0, 1)
    medium_gate = .20 + .80 * near
    fine_gate = .05 + .95 * near * near
    medium_band = medium - coarse
    fine_band = fine - medium
    reconstructed = coarse + medium_gate[..., None] * medium_band + fine_gate[..., None] * fine_band
    correction = reconstructed - lab
    correction[~eligible] = 0
    correction[:, :, 0] *= options.luminance / 100
    result_lab = lab + correction * (options.strength / 100)
    result = np.uint8(np.clip(cv2.cvtColor(result_lab, cv2.COLOR_LAB2RGB) * 255 + .5, 0, 255))
    # These pixels were never eligible for filtering. Keep their RGB exact too,
    # rather than introduce a LAB round-trip quantization change.
    result[~eligible] = rgb[~eligible]
    absolute = np.abs(result.astype(np.float32) - rgb.astype(np.float32))
    report = {
        'changed_pixels_percent': float(100 * np.mean(np.any(result != rgb, axis=2))),
        'mean_rgb_change': float(absolute.mean()),
        'protected_pixels_percent': float(100 * np.mean(~eligible)),
        'sampled_distances': distances,
        'radii': list(radii),
        'cleanup_backend': 'CPU NumPy/OpenCV',
    }
    maps = {}
    if diagnostics:
        maps = {
            'v2_boundaries': boundary.astype(np.float32),
            'v2_changed': np.mean(absolute, axis=2) / 12,
            'v2_sample_support': np.clip((sample_count - 1) / 40, 0, 1),
            'v2_medium_difference': np.linalg.norm(medium_band, axis=2) / options.color_range,
            'v2_fine_difference': np.linalg.norm(fine_band, axis=2) / options.color_range,
            'v2_fine_weight': fine_gate.astype(np.float32),
        }
    return result, maps, report
