"""Validate observed ink as connected centerline paths before using it.

The source guard is only a search area. Filled objects, tiny fragments and
short branch spurs do not authorize fitting. Path IDs also constrain which
neighboring samples may contribute to a fit.
"""
from time import perf_counter
import cv2
import numpy as np
from .line_borders import LUMA, sample


def _thin(mask):
    """Zhang–Suen thinning with fixed background padding; no new dependency."""
    a = np.pad(np.uint8(mask), 1)
    for _ in range(80):
        changed = False
        for second in (False, True):
            p = a[1:-1, 1:-1]
            n = (a[:-2, 1:-1], a[:-2, 2:], a[1:-1, 2:], a[2:, 2:],
                 a[2:, 1:-1], a[2:, :-2], a[1:-1, :-2], a[:-2, :-2])
            count = sum(n)
            transitions = sum((n[i] == 0) & (n[(i+1) % 8] > 0) for i in range(8))
            if second:
                clear = (n[0]*n[2]*n[6] == 0) & (n[0]*n[4]*n[6] == 0)
            else:
                clear = (n[0]*n[2]*n[4] == 0) & (n[2]*n[4]*n[6] == 0)
            remove = (p > 0) & (count >= 2) & (count <= 6) & (transitions == 1) & clear
            if np.any(remove):
                p[remove] = 0
                changed = True
        if not changed:
            break
    return a[1:-1, 1:-1] > 0


def _filled(rgb):
    """Recognize dark-filled closed regions separately from thin strokes.

    The interior must be substantially darker than its outside ring. A dark
    pocket outline around equally colored paint therefore does not qualify.
    """
    light = rgb.astype(np.float32)@LUMA
    median = cv2.medianBlur(np.uint8(np.clip(light+.5, 0, 255)), 31).astype(np.float32)
    binary = np.uint8(median-light > 7)
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    contours, _ = cv2.findContours(binary, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    protected = np.zeros(light.shape, np.uint8)
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < 60:
            continue
        x, y, w, h = cv2.boundingRect(contour)
        compact_limit = max(110, round(min(rgb.shape[:2])*.06))
        if min(w, h) < 8 or max(w, h) > compact_limit:
            continue
        left, top = max(0, x-7), max(0, y-7)
        right, bottom = min(rgb.shape[1], x+w+7), min(rgb.shape[0], y+h+7)
        region = np.zeros((bottom-top, right-left), np.uint8)
        shifted = contour-np.array([[[left, top]]], np.int32)
        cv2.drawContours(region, [shifted], -1, 1, cv2.FILLED)
        distance = cv2.distanceTransform(region, cv2.DIST_L2, 5)
        if distance.max() < 3.5:
            continue
        ring = (cv2.dilate(region, np.ones((11, 11), np.uint8)) > 0) & (region == 0)
        if ring.sum() < 12:
            continue
        values = light[top:bottom, left:right]
        inside, outside = float(np.median(values[distance > 1])), float(np.median(values[ring]))
        ink = float(np.percentile(values[region > 0], 10))
        if inside > outside-12 or (inside-ink) > .6*max(1, outside-ink):
            continue
        # A large connected outline can enclose ordinary paint and other seams.
        # It must not freeze all of those strokes as one supposed filled object.
        keep = region > 0
        patch = protected[top:bottom, left:right]
        patch[keep] = 1
    return cv2.dilate(protected, np.ones((5, 5), np.uint8)) > 0


def _chains(skeleton):
    h, w = skeleton.shape
    pixels = set(int(i) for i in np.flatnonzero(skeleton))
    neighbors = {}
    for index in sorted(pixels):
        y, x = divmod(index, w)
        adjacent = []
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if (dx == dy == 0) or not (0 <= y+dy < h and 0 <= x+dx < w):
                    continue
                other = index+dy*w+dx
                if other not in pixels:
                    continue
                # Avoid diagonal shortcuts that turn an ordinary staircase
                # into a set of artificial three-way junctions.
                if dx and dy and (index+dx in pixels or index+dy*w in pixels):
                    continue
                adjacent.append(other)
        neighbors[index] = adjacent
    visited = set()
    chains = []
    def walk(first, next_index):
        path = [first]
        previous, current = first, next_index
        while True:
            visited.add((min(previous, current), max(previous, current)))
            path.append(current)
            if current == first or len(neighbors[current]) != 2:
                break
            following = next(i for i in neighbors[current] if i != previous)
            previous, current = current, following
            if (min(previous, current), max(previous, current)) in visited:
                break
        return path
    for index, adjacent in neighbors.items():
        if len(adjacent) == 2:
            continue
        if not adjacent:
            chains.append([index])
        for other in adjacent:
            if (min(index, other), max(index, other)) not in visited:
                chains.append(walk(index, other))
    for index, adjacent in neighbors.items():
        for other in adjacent:
            if (min(index, other), max(index, other)) not in visited:
                chains.append(walk(index, other))
    return chains, neighbors


def trace_stroke_paths(rgb, source_core, minimum_length=12.):
    start = perf_counter()
    core = np.asarray(source_core, dtype=bool)
    if rgb.dtype != np.uint8 or rgb.ndim != 3 or rgb.shape[2] != 3 or core.shape != rgb.shape[:2]:
        raise ValueError('Stroke paths need matching native RGB pixels and source evidence.')
    light = rgb.astype(np.float32)@LUMA
    background = cv2.morphologyEx(light, cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (13, 13)))
    depth = np.maximum(0, background-light)
    filled = _filled(rgb)
    guide = cv2.GaussianBlur(rgb.astype(np.float32), (0, 0), 1.)
    gx, gy = cv2.Scharr(guide, -1, 1, 0), cv2.Scharr(guide, -1, 0, 1)
    xx = cv2.GaussianBlur(np.sum(gx*gx, axis=2), (0, 0), 1.8)
    yy = cv2.GaussianBlur(np.sum(gy*gy, axis=2), (0, 0), 1.8)
    xy = cv2.GaussianBlur(np.sum(gx*gy, axis=2), (0, 0), 1.8)
    angle = .5*np.arctan2(2*xy, xx-yy)
    nx, ny = np.cos(angle), np.sin(angle)
    two_sided = np.zeros(core.shape, bool)
    h, w = core.shape
    for top in range(0, h, 96):
        bottom = min(h, top+96)
        cy, cx = np.mgrid[top:bottom, :w].astype(np.float32)
        ux, uy = nx[top:bottom], ny[top:bottom]
        for radius in (2.5, 4., 6.):
            a = sample(light, cx+ux*radius, cy+uy*radius)-light[top:bottom]
            b = sample(light, cx-ux*radius, cy-uy*radius)-light[top:bottom]
            two_sided[top:bottom] |= (a > 1) & (b > 1)
    # Continuity, not the contrast of an unrelated nearby heavy line, decides
    # whether a faint observed stroke is valid.
    candidates = core & two_sided & (depth > 1.5) & ~filled
    skeleton = _thin(candidates)
    original_skeleton = skeleton.copy()
    pruned = np.zeros(core.shape, bool)
    # Remove only short terminal branches attached to a junction. Independent
    # short dashes are retained as observed details, but are not fitted.
    for _ in range(3):
        branches, adjacent = _chains(skeleton)
        remove = []
        for chain in branches:
            if len(chain) < 2:
                continue
            points = np.array([(i % w, i//w) for i in chain], np.float32)
            length = float(np.linalg.norm(np.diff(points, axis=0), axis=1).sum())
            if length >= 6:
                continue
            if len(adjacent[chain[0]]) == 1 and len(adjacent[chain[-1]]) > 2:
                remove.extend(chain[:-1])
            elif len(adjacent[chain[-1]]) == 1 and len(adjacent[chain[0]]) > 2:
                remove.extend(chain[1:])
        if not remove:
            break
        skeleton.flat[remove] = False
        pruned.flat[remove] = True
    chains, neighbors = _chains(skeleton)
    labels = np.zeros(core.shape, np.int32)
    arc = np.zeros(core.shape, np.float32)
    accepted = np.zeros(core.shape, bool)
    short = np.zeros(core.shape, bool)
    noise = pruned.copy()
    freeze = filled.copy()
    lengths = []
    closed_paths = []
    rejected = 0
    for chain in chains:
        points = np.array([(i % w, i//w) for i in chain], np.float32)
        length = float(np.linalg.norm(np.diff(points, axis=0), axis=1).sum())
        extent = float(np.linalg.norm(np.ptp(points, axis=0)))
        if length >= minimum_length and extent >= 8:
            path_id = len(lengths)+1
            lengths.append(length)
            closed_paths.append(chain[0] == chain[-1])
            cumulative = np.r_[0, np.cumsum(np.linalg.norm(np.diff(points, axis=0), axis=1))]
            for position, index in enumerate(chain):
                y, x = divmod(index, w)
                if len(neighbors[index]) == 2:
                    labels[y, x] = path_id
                    arc[y, x] = cumulative[position]
                    accepted[y, x] = True
            if chain[0] != chain[-1]:
                for index in (chain[0], chain[-1]):
                    y, x = divmod(index, w)
                    freeze[y, x] = True
        else:
            rejected += 1
            standalone = (len(chain) >= 2 and chain[0] != chain[-1] and extent >= 1
                and length <= extent*1.5 and all(len(neighbors[i]) <= 2 for i in chain))
            target = short if standalone else noise
            for index in chain:
                target[index//w, index % w] = True
    junctions = np.zeros(core.shape, bool)
    for index, adjacent in neighbors.items():
        # A junction in rejected texture is not a preservation anchor. Only
        # junctions actually reached by a validated chain can freeze pixels.
        if len(adjacent) > 2 and freeze[index//w, index % w]:
            junctions[index//w, index % w] = True
    freeze |= cv2.dilate(np.uint8(junctions), np.ones((3, 3), np.uint8)) > 0
    freeze = cv2.dilate(np.uint8(freeze), np.ones((3, 3), np.uint8)) > 0
    if accepted.any():
        # Rejected skeleton pixels have label zero and keep ownership of their
        # own neighborhood. A nearby accepted line cannot absorb their texture.
        _, nearest = cv2.distanceTransformWithLabels(np.uint8(~original_skeleton), cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL)
        lookup = np.zeros(int(nearest.max())+1, np.int32)
        lookup[nearest[original_skeleton]] = labels[original_skeleton]
        path_ids = lookup[nearest]
        arc_lookup = np.zeros(int(nearest.max())+1, np.float32)
        arc_lookup[nearest[original_skeleton]] = arc[original_skeleton]
        arc_positions = arc_lookup[nearest]
    else:
        path_ids = labels.copy()
        arc_positions = arc.copy()
    owners = path_ids.copy()
    sample_ids = owners.copy()
    # The adaptive filled mask can describe the interior of a dark outlined
    # object. Also exclude its nearby observed rim, rather than fitting that
    # rim as an independent thin stroke and changing the object's silhouette.
    _, object_labels = cv2.connectedComponents(np.uint8(candidates | filled), 8)
    attached_to_fill = np.zeros(int(object_labels.max())+1, bool)
    attached_to_fill[np.unique(object_labels[filled])] = True
    attached_to_fill[0] = False
    rim = ((cv2.dilate(np.uint8(filled), np.ones((13, 13), np.uint8)) > 0)
           & candidates & attached_to_fill[object_labels])
    filled_fit_guard = filled | (cv2.dilate(np.uint8(rim), np.ones((3, 3), np.uint8)) > 0)
    band = (cv2.dilate(np.uint8(candidates & (path_ids > 0)), np.ones((3, 3), np.uint8)) > 0)
    # Nearest labels alone do not authorize a pixel: it must lie beside the
    # actual accepted centerline, not beside a rejected fragment in its cell.
    distance = cv2.distanceTransform(np.uint8(~accepted), cv2.DIST_L2, 5)
    sample_ids[(distance > 4) | filled_fit_guard] = 0
    band &= (distance <= 4) & (path_ids > 0) & ~freeze & ~filled_fit_guard
    path_ids[~band] = 0
    preserved_short = cv2.dilate(np.uint8(short), np.ones((3, 3), np.uint8)) > 0
    fixed_anchors = freeze & core
    copy_back = ((candidates & (owners > 0) & (distance <= 3)) | preserved_short | filled_fit_guard | fixed_anchors)
    copy_back = cv2.dilate(np.uint8(copy_back), np.ones((3, 3), np.uint8)) > 0
    copy_back &= (owners > 0) | preserved_short | filled_fit_guard | fixed_anchors
    report = {'minimum_path_length_pixels': float(minimum_length), 'accepted_paths': len(lengths),
        'accepted_path_lengths_pixels': lengths, 'rejected_chains': rejected,
        'closed_paths': int(sum(closed_paths)),
        'short_branch_pixels_pruned': int(pruned.sum()),
        'filled_pixels_excluded': int(filled_fit_guard.sum()), 'application_pixels': int(band.sum()),
        'seconds': perf_counter()-start,
        'method': 'observed two-sided ink; thinned adjacency graph; chains split at junctions; same-path sampling'}
    return {'candidates': candidates, 'skeleton': skeleton, 'accepted': accepted,
        'path_ids': path_ids, 'sample_path_ids': sample_ids, 'arc_positions': arc_positions, 'path_lengths': np.r_[0, lengths].astype(np.float32),
        'path_closed': np.r_[False, closed_paths].astype(bool),
        'application': band, 'copy_back': copy_back,
        'filled': filled, 'filled_fit_guard': filled_fit_guard, 'freeze': freeze,
        'short': short, 'noise': noise, 'report': report}
