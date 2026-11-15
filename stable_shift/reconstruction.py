"""Experimental source-only quarter -> half -> full surface reconstruction.

The supplied layers have already been independently denoised. Color references
never enter this module. No raw full-resolution surface residual is restored.
"""
import cv2
import numpy as np


def _lab(rgb):
    return cv2.cvtColor(rgb.astype(np.float32)/255, cv2.COLOR_RGB2LAB)


def _rgb(lab):
    return np.uint8(np.clip(cv2.cvtColor(lab.astype(np.float32), cv2.COLOR_LAB2RGB)*255+.5, 0, 255))


def _ramp(low, high, value):
    t = np.clip((value-low)/(high-low), 0, 1)
    return t*t*(3-2*t)


def _guided(guide, value, radius=3, epsilon=1.):
    size = (radius*2+1, radius*2+1)
    def mean(x):
        return cv2.boxFilter(x, -1, size, borderType=cv2.BORDER_REFLECT)
    g, p = mean(guide), mean(value)
    a = (mean(guide*value)-g*p)/(np.maximum(0, mean(guide*guide)-g*g)+epsilon)
    output = mean(a)*guide+mean(p-a*g)
    kernel = np.ones(size, np.uint8)
    # Guide structure can move a coarse boundary, but cannot invent a darker
    # or brighter paint value outside this local coarse-field envelope.
    return np.minimum(cv2.dilate(value, kernel), np.maximum(cv2.erode(value, kernel), output))


def _up(layer, guide):
    h, w = guide.shape[:2]
    up = cv2.resize(layer, (w, h), interpolation=cv2.INTER_LINEAR)
    guide = cv2.GaussianBlur(guide, (0, 0), .65)
    channels = []
    for c in range(3):
        luminance = _guided(guide[:, :, 0], up[:, :, c])
        if c:
            chroma = _guided(guide[:, :, c], up[:, :, c], epsilon=1.5)
            luminance = .65*luminance+.35*chroma
        channels.append(luminance)
    return np.stack(channels, axis=2)


def _edge_regions(lab, protected):
    # Boundaries come from sharp, scale-supported edges, not palette bins.
    # A gradual halo must not become a closed paint region merely because it
    # has a slightly different color from the surrounding white surface.
    gradients = []
    for sigma in (.8, 4.):
        guide = cv2.GaussianBlur(lab, (0, 0), sigma)
        gradients.append(np.stack([cv2.Sobel(guide, cv2.CV_32F, dx, dy)/8
                                    for dx, dy in ((1, 0), (0, 1))], axis=-1))
    fine, broad = gradients
    ef, eb = np.sum(fine*fine, axis=(2, 3)), np.sum(broad*broad, axis=(2, 3))
    alignment = np.sum(fine*broad, axis=(2, 3))/np.maximum(1e-6, np.sqrt(ef*eb))
    sharp = (np.sqrt(ef) > .20) & (np.sqrt(eb) > .04)
    sharp &= np.sqrt(ef)/(np.sqrt(eb)+.01) > 1.35
    sharp &= alignment > .65
    edges = np.zeros(lab.shape[:2], np.uint8)
    for channel in range(3):
        dx = np.int16(np.clip(fine[:, :, channel, 0]*1024, -32000, 32000))
        dy = np.int16(np.clip(fine[:, :, channel, 1]*1024, -32000, 32000))
        edges |= cv2.Canny(dx, dy, .12*1024, .30*1024, L2gradient=True)
    edges = np.uint8((edges > 0) & sharp)
    count, pieces, stats, _ = cv2.connectedComponentsWithStats(edges, connectivity=8)
    keep = stats[:, cv2.CC_STAT_AREA] >= 12
    keep[0] = False
    barriers = np.maximum(keep[pieces].astype(np.uint8), protected.astype(np.uint8))
    barriers = cv2.morphologyEx(barriers, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    count, labels = cv2.connectedComponents(1-barriers, connectivity=4)
    seeds = labels > 0
    if np.any(seeds):
        # Assign boundary pixels to an adjacent paint region. This only assigns
        # a region ID; it never fills them with original surface texture.
        _, nearest = cv2.distanceTransformWithLabels(np.uint8(~seeds), cv2.DIST_L2, 5,
                                                     labelType=cv2.DIST_LABEL_PIXEL)
        lookup = np.r_[0, labels[seeds]]
        labels = lookup[nearest]
    labels[protected] = 0
    return labels, barriers


def _region_colors(labels, pyramid, half, quarter):
    colors = np.zeros((int(labels.max())+1, 3), np.float32)
    samples = [_samples(labels, quarter), _samples(labels, half),
               _samples(labels, pyramid, interior=False)]
    colors[0] = np.median(quarter.reshape(-1, 3), axis=0)
    for group in range(1, len(colors)):
        colors[group] = colors[0]
        for _, values, offsets in samples:
            part = values[offsets[group]:offsets[group+1]]
            if len(part):
                colors[group] = np.median(part, axis=0)
                if len(part) >= 4:
                    break
    return colors


def _samples(labels, layer, interior=True):
    h, w = layer.shape[:2]
    groups = cv2.resize(labels, (w, h), interpolation=cv2.INTER_NEAREST)
    same = groups > 0
    if interior:
        same[1:] &= groups[1:] == groups[:-1]
        same[:-1] &= groups[:-1] == groups[1:]
        same[:, 1:] &= groups[:, 1:] == groups[:, :-1]
        same[:, :-1] &= groups[:, :-1] == groups[:, 1:]
    y, x = np.nonzero(same)
    ids = groups[y, x]
    order = np.argsort(ids, kind='stable')
    counts = np.bincount(ids, minlength=int(labels.max())+1)
    offsets = np.r_[0, np.cumsum(counts)]
    # Coordinates use the same unit square at every resolution.
    xy = np.stack(((x+.5)/w, (y+.5)/h), axis=1).astype(np.float32)
    return xy[order], layer[y, x][order], offsets


def _plane(xy, colors):
    center = xy.mean(axis=0)
    scale = np.maximum(.01, np.ptp(xy, axis=0))
    basis = np.c_[np.ones(len(xy)), (xy-center)/scale]
    coefficient = np.linalg.lstsq(basis, colors, rcond=1e-5)[0]
    return coefficient, center, scale


def _predict(model, xy):
    coefficient, center, scale = model
    return np.c_[np.ones(len(xy)), (xy-center)/scale] @ coefficient


def _gradient_models(labels, half, quarter, forbidden):
    samples = [_samples(labels, layer) for layer in (half, quarter)]
    models = {}
    reports = []
    for group in range(1, int(labels.max())+1):
        values = []
        for xy, colors, offsets in samples:
            part = slice(offsets[group], offsets[group+1])
            values.append((xy[part], colors[part]))
        if len(values[0][0]) < 40 or len(values[1][0]) < 16:
            continue
        xy, colors = values[1]
        qx = np.floor(xy[:, 0]*quarter.shape[1]).astype(np.int32)
        qy = np.floor(xy[:, 1]*quarter.shape[0]).astype(np.int32)
        validation = (qx//2+qy//2) % 3 == 0
        if validation.sum() < 5 or (~validation).sum() < 8:
            continue
        model = _plane(xy[~validation], colors[~validation])
        pred = _predict(model, xy[validation])
        baseline = np.median(colors[~validation], axis=0)
        flat_error = float(np.mean(np.sum((colors[validation]-baseline)**2, axis=1)))
        plane_error = float(np.mean(np.sum((colors[validation]-pred)**2, axis=1)))
        prediction = _predict(model, xy)
        span = float(np.linalg.norm(np.percentile(prediction, 95, axis=0)-np.percentile(prediction, 5, axis=0)))
        second = _plane(*values[0])
        other = _predict(second, xy)
        a, b = prediction-prediction.mean(axis=0), other-other.mean(axis=0)
        energy_a, energy_b = np.sum(a*a), np.sum(b*b)
        agreement = float(np.sum(a*b)/max(1e-6, np.sqrt(energy_a*energy_b)))
        amplitude_ratio = float(np.sqrt(energy_b/max(1e-6, energy_a)))
        # No native pixels are exempted from cleanup. A smooth plane must be
        # independently supported at half/quarter size; texture permission can
        # veto that classification around noisy bright surfaces.
        region = labels == group
        veto = float(forbidden[region].mean()) if forbidden is not None else 0.
        accepted = (flat_error > .1 and plane_error < flat_error*.65 and
                    1.5 <= span <= 16 and agreement > .90 and
                    .5 <= amplitude_ratio <= 2 and veto < .2)
        reports.append({'region': group, 'flat_error': flat_error, 'plane_error': plane_error,
                        'span_lab': span, 'scale_agreement': agreement,
                        'amplitude_ratio': amplitude_ratio, 'texture_veto': veto, 'accepted': accepted})
        if accepted:
            joined_xy = np.concatenate([v[0] for v in values])
            joined_colors = np.concatenate([v[1] for v in values])
            models[group] = _plane(joined_xy, joined_colors)
    return models, reports


def pyramid_field(full, half, quarter, capture_paint=False):
    """Rebuild LAB paint once; optionally expose the clean coarse field."""
    half_rebuilt = .5*_up(quarter, half)+.5*half
    pyramid = _up(half_rebuilt, full)
    paint = pyramid.copy() if capture_paint else None
    # Restore a denoised fine difference only where its gradient direction is
    # also supported by the already rebuilt coarse image.
    gradients = []
    for layer in (full, pyramid):
        guide = cv2.GaussianBlur(layer, (0, 0), 1.)
        gradients.append(np.stack([cv2.Sobel(guide, cv2.CV_32F, dx, dy)/8 for dx, dy in ((1, 0), (0, 1))], axis=-1))
    a, b = gradients
    ea, eb = np.sum(a*a, axis=(2, 3)), np.sum(b*b, axis=(2, 3))
    alignment = np.maximum(0, np.sum(a*b, axis=(2, 3))/np.maximum(1e-6, np.sqrt(ea*eb)))
    detail_weight = _ramp(.08, .30, np.sqrt(eb))*_ramp(.65, .95, alignment)
    pyramid += (full-pyramid)*detail_weight[:, :, None]
    del gradients, a, b, ea, eb, alignment
    return pyramid, paint, detail_weight


def reconstruct(full_rgb, half_rgb, quarter_rgb, protected=None, texture_permission=None):
    """Return three full-strength candidates and explicit diagnostic evidence.

    Hard colors fills edge-bounded paint regions. Gradient-aware hard colors can
    replace a flat fill with a fitted plane, never with a native texture field.
    A sharp outline is not evidence that its interior must have constant color.
    """
    for value in (full_rgb, half_rgb, quarter_rgb):
        if value.dtype != np.uint8 or value.ndim != 3 or value.shape[2] != 3 or min(value.shape[:2]) < 1:
            raise ValueError('Reconstruction layers must be nonempty uint8 RGB arrays.')
    h, w = full_rgb.shape[:2]
    if not (h >= half_rgb.shape[0] >= quarter_rgb.shape[0] and
            w >= half_rgb.shape[1] >= quarter_rgb.shape[1]):
        raise ValueError('Reconstruction layers must be ordered full, half, quarter.')
    core = np.zeros((h, w), bool) if protected is None else np.asarray(protected, bool)
    if core.shape != (h, w):
        raise ValueError('Source protection must match full resolution.')
    if texture_permission is not None and np.shape(texture_permission) != (h, w):
        raise ValueError('Texture permission must match full resolution.')
    full, half, quarter = [_lab(a) for a in (full_rgb, half_rgb, quarter_rgb)]
    pyramid, _, detail_weight = pyramid_field(full, half, quarter)
    pyramid_rgb = _rgb(pyramid)
    pyramid_rgb[core] = full_rgb[core]
    labels, barriers = _edge_regions(pyramid, core)
    colors = _region_colors(labels, pyramid, half, quarter)
    hard_lab = colors[labels]
    hard_rgb = _rgb(colors[None, :, :])[0][labels]
    hard_rgb[core] = full_rgb[core]
    models, reports = _gradient_models(labels, half, quarter, texture_permission)
    gradient_lab = hard_lab.copy()
    gradient_mask = np.zeros((h, w), np.float32)
    for group, model in models.items():
        y, x = np.nonzero(labels == group)
        xy = np.stack(((x+.5)/w, (y+.5)/h), axis=1)
        predicted = _predict(model, xy)
        # Keep the region's estimated paint color; add only its smooth trend.
        delta = predicted-predicted.mean(axis=0)
        delta *= np.minimum(1, 6/np.maximum(1e-6, np.linalg.norm(delta, axis=1)))[:, None]
        gradient_lab[y, x] += delta
        gradient_mask[y, x] = 1
    gradient_rgb = hard_rgb.copy()
    changed = gradient_mask > 0
    gradient_rgb[changed] = _rgb(gradient_lab)[changed]
    gradient_rgb[core] = full_rgb[core]
    return {'pyramid': pyramid_rgb, 'hard': hard_rgb, 'gradients': gradient_rgb}, {
        'reconstruction_full_detail_weight': detail_weight.astype(np.float32),
        'reconstruction_regions': labels, 'reconstruction_gradient_regions': gradient_mask,
        'reconstruction_region_boundaries': barriers,
    }, {'paint_regions': int(labels.max()),
        'gradient_regions': len(models), 'gradient_fits': reports,
        'note': 'Experimental full-strength source-only candidates. Gradient evidence is not semantic recognition of iridescence or halos.'}
