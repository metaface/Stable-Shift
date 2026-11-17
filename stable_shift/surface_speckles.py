"""Lighten compact dark paint fragments in each cached final-color view.

A local outlier map keeps the whole gray shading shape from being mistaken for
one connected line. A separate coherent-ink mask protects actual strokes and
antialiased borders. This is local restoration, not semantic spot recognition.
"""
from time import perf_counter
import cv2
import numpy as np
from .line_borders import LUMA


def clean_surface_speckles(rgb, source_core):
    start = perf_counter()
    if rgb.dtype != np.uint8 or rgb.ndim != 3 or rgb.shape[2] != 3 or min(rgb.shape[:2]) < 1:
        raise ValueError('Speckle cleanup needs a nonempty uint8 RGB image.')
    core = np.asarray(source_core, dtype=bool)
    if core.shape != rgb.shape[:2]:
        raise ValueError('Speckle source support must match the image.')
    light = rgb.astype(np.float32)@LUMA
    median = cv2.medianBlur(rgb, 5)
    deficit = median.astype(np.float32)@LUMA-light
    background = cv2.morphologyEx(light, cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (13, 13)))
    depth = np.maximum(0, background-light)
    peak = cv2.dilate(depth, np.ones((17, 17), np.uint8))
    # A broad dark shape (the nose, for example) has no black-hat response in
    # its interior. Include its observed color range so medium-gray pepper
    # beside it cannot declare itself the darkest available ink.
    neighborhood = np.ones((17, 17), np.uint8)
    high = cv2.dilate(light, neighborhood)
    spread = high-cv2.erode(light, neighborhood)
    peak = np.maximum(peak, spread)
    ink = depth > np.maximum(3, .60*peak)
    number, labels, stats, _ = cv2.connectedComponentsWithStats(np.uint8(ink), 8)
    keep = ((stats[:, cv2.CC_STAT_AREA] >= 5)
            | (stats[:, cv2.CC_STAT_WIDTH] >= 6)
            | (stats[:, cv2.CC_STAT_HEIGHT] >= 6))
    keep[0] = False
    established = keep[labels]
    # Protect the actual ink center and its immediate antialiased border.
    protected = cv2.dilate(np.uint8(established), np.ones((3, 3), np.uint8)) > 0
    anchors = established | (core & (spread > 8) & (light < high-.6*spread))
    number, anchor_labels, anchor_stats, _ = cv2.connectedComponentsWithStats(np.uint8(anchors), 8)
    anchor_keep = ((anchor_stats[:, cv2.CC_STAT_AREA] >= 5)
                   | (anchor_stats[:, cv2.CC_STAT_WIDTH] >= 6)
                   | (anchor_stats[:, cv2.CC_STAT_HEIGHT] >= 6))
    anchor_keep[0] = False
    anchors = anchor_keep[anchor_labels]
    distance = cv2.distanceTransform(np.uint8(~anchors), cv2.DIST_L2, 5)
    allowed = cv2.dilate(np.uint8(core), np.ones((7, 7), np.uint8)) > 0
    possible = (deficit > 4) & allowed & ~protected & (distance <= 14)
    number, labels, stats, _ = cv2.connectedComponentsWithStats(np.uint8(possible), 8)
    small = ((stats[:, cv2.CC_STAT_AREA] <= 48)
             & (stats[:, cv2.CC_STAT_WIDTH] <= 10)
             & (stats[:, cv2.CC_STAT_HEIGHT] <= 10))
    small[0] = False
    active = np.zeros(core.shape, bool)
    for label in np.flatnonzero(small):
        left, top, width, height, area = stats[label]
        patch = labels[top:top+height, left:left+width] == label
        yy, xx = np.nonzero(patch)
        # A small but elongated mark can be a stitch or faint connecting line.
        if min(width, height) == 1 and max(width, height) >= 2:
            continue
        if max(width, height) >= 1.5*min(width, height) and area >= .75*width*height:
            continue
        if area >= 2:
            coords = np.stack((xx, yy), axis=1).astype(np.float32)
            centered = coords-coords.mean(axis=0)
            values = np.linalg.eigvalsh(centered.T@centered/area)
            if values[-1] > 6*(values[0]+.1):
                continue
        active[top:top+height, left:left+width] |= patch
    output = rgb.copy()
    output[active] = median[active]
    report = {'algorithm': 'compact dark paint outliers; independent coherent-ink exclusion; local median',
        'removed_pixels': int(active.sum()), 'changed_pixels_percent': float(active.mean()*100),
        'maximum_component_pixels': 48, 'maximum_component_span': 10,
        'maximum_ink_distance_pixels': 14, 'minimum_luminance_deficit': 4,
        'seconds': perf_counter()-start,
        'note': 'Baseline cleanup remains on at reconstruction zero. Connected ink, elongated marks and distant details are excluded.'}
    return output, active, report
