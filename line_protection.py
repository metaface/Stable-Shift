"""Trace source-image lines before denoising and retain their shared mask.

This is classical edge linking, not semantic recognition. The palette reference
is deliberately not accepted by this API.
"""
from __future__ import annotations

import cv2
import numpy as np


def _continue_faint_segments(linked, candidates, orientation, gx, gy, maximum_gap=12):
    """Retain observed weak edge pixels between compatible traced anchors.

    Both directions must have an existing anchor within a short, narrow tangent
    corridor. Matching gradient polarity keeps opposite sides of a stroke from
    lending each other false support. No pixels without source edge evidence
    are drawn into a gap, and new pixels never seed further growth.
    """
    rescued = np.zeros(linked.shape, bool)
    size = maximum_gap+1
    # Eight directions avoid restricting a slanted seam to a 45-degree grid.
    # Distances below are native pixels, including the directions with slope 2.
    for sector, (dy, dx) in enumerate(((1, 0), (2, -1), (1, -1), (1, -2),
                                      (0, 1), (1, 2), (1, 1), (2, 1))):
        length = float(np.hypot(dy, dx))
        ty, tx = dy/length, dx/length
        ny, nx = -tx, ty
        forward = np.zeros((2*size+1, 2*size+1), np.uint8)
        for distance in range(1, maximum_gap+1):
            for normal in (-1, 0, 1):
                forward[size+round(ty*distance+ny*normal),
                        size+round(tx*distance+nx*normal)] = 1
        backward = np.flip(forward).copy()
        gradient = gx*nx+gy*ny
        dominant = np.argmax(np.abs(gradient), axis=2)
        difference = np.abs(orientation.astype(np.int16)-sector)
        compatible = np.minimum(difference, 8-difference) <= 2
        target = candidates & (orientation == sector) & ~linked
        if not np.any(target):
            continue
        for channel in range(3):
            for positive in (False, True):
                same = (dominant == channel) & ((gradient[:, :, channel] > 0) == positive)
                anchors = (linked & compatible & same).astype(np.uint8)
                if not np.any(anchors):
                    continue
                ahead = cv2.dilate(anchors, forward, borderType=cv2.BORDER_CONSTANT, borderValue=0)
                behind = cv2.dilate(anchors, backward, borderType=cv2.BORDER_CONSTANT, borderValue=0)
                rescued |= target & same & (ahead > 0) & (behind > 0)
    return rescued


def _normal_samples(field, orientation):
    """Quantized-normal nonmaximum suppression; no image pixels are averaged."""
    padded = np.pad(field, 1, mode='edge')
    h, w = field.shape
    peaks = np.zeros(field.shape, bool)
    for sector, (dy, dx) in enumerate(((0, 1), (1, 1), (1, 0), (1, -1))):
        before = padded[1-dy:1-dy+h, 1-dx:1-dx+w]
        after = padded[1+dy:1+dy+h, 1+dx:1+dx+w]
        peaks |= (orientation == sector) & (field >= before) & (field >= after)
    return peaks


def trace_source_lines(rgb, maps, continue_faint=True):
    """Use original hard AND soft evidence, then link supported weak segments.

    Weak candidates can join a stronger seed, or form a sufficiently long,
    coherent independent segment. They are not required to meet the hard-edge
    threshold themselves. A one-pixel support band retains thin line centers
    lying between the two detected sides of a stroke.
    """
    rgb = np.asarray(rgb, dtype=np.uint8)
    confidence = np.maximum(maps['hard'], maps['soft']).astype(np.float32)
    if confidence.shape != rgb.shape[:2]:
        raise ValueError('Source evidence and edited image dimensions must match.')
    lab = cv2.cvtColor(rgb.astype(np.float32)/255, cv2.COLOR_RGB2LAB)
    guide = cv2.GaussianBlur(lab, (3, 3), .65, borderType=cv2.BORDER_REFLECT)
    gx = cv2.Scharr(guide, cv2.CV_32F, 1, 0)
    gy = cv2.Scharr(guide, cv2.CV_32F, 0, 1)
    xx = np.sum(gx*gx, axis=2)
    yy = np.sum(gy*gy, axis=2)
    xy = np.sum(gx*gy, axis=2)
    tensor_xx = cv2.GaussianBlur(xx, (0, 0), 1.0)
    tensor_yy = cv2.GaussianBlur(yy, (0, 0), 1.0)
    tensor_xy = cv2.GaussianBlur(xy, (0, 0), 1.0)
    total = tensor_xx+tensor_yy
    coherence = np.sqrt((tensor_xx-tensor_yy)**2+4*tensor_xy**2)/(total+1e-6)
    angle = .5*np.arctan2(2*xy, xx-yy)
    orientation = (np.floor((angle % np.pi)/(np.pi/4)+.5).astype(np.uint8) % 4)
    fine_orientation = (np.floor((angle % np.pi)/(np.pi/8)+.5).astype(np.uint8) % 8)
    magnitude = np.sqrt(xx+yy)
    peaks = _normal_samples(magnitude, orientation)
    # Estimate high-frequency scatter, so image-relative legacy percentiles do
    # not turn a featureless noisy surface into an apparently strong edge map.
    noise_kernel = np.array([[1, -2, 1], [-2, 4, -2], [1, -2, 1]], np.float32)
    highpass = cv2.filter2D(lab, -1, noise_kernel, borderType=cv2.BORDER_REFLECT)
    sigma = np.median(np.abs(highpass[::2, ::2]), axis=(0, 1))/(6*.67449)
    impulse = np.zeros((9, 9), np.float32)
    impulse[4, 4] = 1
    filter_response = cv2.Scharr(cv2.GaussianBlur(impulse, (3, 3), .65), -1, 1, 0)
    noise_gradient = float(np.linalg.norm(sigma)*np.linalg.norm(filter_response))
    weak = (confidence >= .06) & (coherence >= .45) & peaks & (magnitude > max(1.5, noise_gradient*1.4))
    # Test continuity along the tangent, including quantization around bends.
    supported = np.zeros(confidence.shape, bool)
    tangent_kernels = (np.ones((5, 1), np.float32), np.fliplr(np.eye(5, dtype=np.float32)),
                       np.ones((1, 5), np.float32), np.eye(5, dtype=np.float32))
    for sector, kernel in enumerate(tangent_kernels):
        # Only nearby normals can support a tangent; unrelated crossing noise
        # must not supply the continuity evidence for a weak line.
        compatible = weak & (((orientation-sector) % 4 != 2))
        count = cv2.filter2D(compatible.astype(np.float32), -1, kernel, borderType=cv2.BORDER_CONSTANT)
        supported |= weak & (orientation == sector) & (count >= 3)
    # One-pixel linking support permits diagonal/staircase continuity. The final
    # core is limited to the observed source candidates; no long gaps are drawn.
    connected = cv2.dilate(supported.astype(np.uint8), np.ones((3, 3), np.uint8))
    number, labels, stats, _ = cv2.connectedComponentsWithStats(connected, 8)
    seeds = supported & ((maps['hard'] >= .65) | (confidence >= .55)) & (magnitude > max(2., noise_gradient*3))
    support_count = np.bincount(labels[supported], minlength=number)
    seed_count = np.bincount(labels[seeds], minlength=number)
    coherent_sum = np.bincount(labels[supported], weights=coherence[supported], minlength=number)
    mean_coherence = coherent_sum/np.maximum(1, support_count)
    keep = ((seed_count > 0) & (support_count >= 3) & (mean_coherence >= .50)) | ((support_count >= 24) & (mean_coherence >= .70))
    keep[0] = False
    linked = supported & keep[labels]
    base_linked = linked.copy()
    old_core = cv2.dilate(linked.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
    rescued = np.zeros(linked.shape, bool)
    if continue_faint:
        relaxed = (confidence >= .02) & (coherence >= .45) & peaks & (magnitude > max(1., noise_gradient*.90))
        # Relax the three-of-five tangent test only between existing anchors.
        # It is not a lower threshold for discovering independent structures.
        candidates = np.zeros(linked.shape, bool)
        for sector, kernel in enumerate(tangent_kernels):
            compatible = relaxed & (((orientation-sector) % 4 != 2))
            count = cv2.filter2D(compatible.astype(np.float32), -1, kernel, borderType=cv2.BORDER_CONSTANT)
            candidates |= relaxed & (orientation == sector) & (count >= 2)
        rescued = _continue_faint_segments(linked, candidates, fine_orientation, gx, gy)
        # A weak point already inside the old protection band needs no extra
        # copy-back. Growing from those points would merely widen edge fringes.
        rescued &= ~old_core
        linked |= rescued
    # Stroke centers may have zero gradient. Include their immediately adjacent
    # pixels, but do not invent a broad halo around entire objects.
    core = cv2.dilate(linked.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
    return {
        'source_line_confidence': confidence,
        'source_line_candidates': supported.astype(np.float32),
        'source_line_seeds': seeds.astype(np.float32),
        'source_line_trace': linked.astype(np.float32),
        'source_line_trace_base': base_linked.astype(np.float32),
        'source_line_rescued': rescued.astype(np.float32),
        'source_line_added_core': (core & ~old_core).astype(np.float32),
        'source_line_core': core.astype(np.float32),
    }
