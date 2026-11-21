"""Image-based strength recommendations; analysis never masks output pixels."""
import cv2
import numpy as np


def _percent(value, low, high):
    return float(5*round(float(np.clip((value-low)/(high-low), 0, 1))*20))


def analyze_noise(rgb):
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32)
    flat = bool(np.all(rgb == rgb[0, 0]))
    guide = cv2.GaussianBlur(gray, (0, 0), 1.)
    gx, gy = cv2.Sobel(guide, -1, 1, 0)/8, cv2.Sobel(guide, -1, 0, 1)/8
    edges = np.hypot(gx, gy) > 3.
    interior = cv2.dilate(edges.astype(np.uint8), np.ones((5, 5), np.uint8)) == 0
    kernel = np.array([[1, -2, 1], [-2, 4, -2], [1, -2, 1]], np.float32)
    scatter = np.abs(cv2.filter2D(gray, -1, kernel))/(6*.67449)
    values = scatter[interior]
    fallback = values.size < 64
    if fallback:
        values = scatter.reshape(-1)
    sigma = float(np.percentile(values, 65))
    strength = 0. if flat else _percent(sigma, .08, .40)
    return {'fine_sigma_rgb': sigma, 'interior_samples': int(interior.sum()),
            'busy_image_estimate': fallback, 'flat_image': flat,
            'denoise': strength,
            'note': 'Native high-frequency scatter, excluding strong edges where possible. Texture can also contribute.'}


def analyze_surfaces(rgb):
    lab = cv2.cvtColor(rgb.astype(np.float32)/255, cv2.COLOR_RGB2LAB)
    guide = cv2.GaussianBlur(lab, (0, 0), 1.)
    gx, gy = cv2.Sobel(guide, -1, 1, 0)/8, cv2.Sobel(guide, -1, 0, 1)/8
    xx = cv2.GaussianBlur(np.sum(gx*gx, axis=2), (0, 0), 4.)
    yy = cv2.GaussianBlur(np.sum(gy*gy, axis=2), (0, 0), 4.)
    xy = cv2.GaussianBlur(np.sum(gx*gy, axis=2), (0, 0), 4.)
    coherence = np.sqrt((xx-yy)**2+4*xy*xy)/(xx+yy+1e-6)
    edges = np.sqrt(np.sum(gx*gx+gy*gy, axis=2)) > 1.2
    interior = (cv2.dilate(edges.astype(np.uint8), np.ones((9, 9), np.uint8)) == 0) & (coherence < .85)
    band = cv2.GaussianBlur(lab, (0, 0), 3.)-cv2.GaussianBlur(lab, (0, 0), 12.)
    amplitudes = np.sqrt(np.sum(band*band, axis=2))[interior]
    patch = float(np.median(amplitudes)) if amplitudes.size >= 64 else 0.
    light = lab[..., 0]
    neutral = (light > 75) & (np.linalg.norm(lab[..., 1:], axis=2) < 12)
    detail = np.abs(light-cv2.GaussianBlur(light, (0, 0), 1.5))
    near_dark = cv2.dilate(np.uint8(light < 50), np.ones((7, 7), np.uint8)) > 0
    bright_texture = float(np.mean(neutral & (detail > .8) & ~near_dark))
    strength = min(200., _percent(patch, .05, .50)+_percent(bright_texture, .015, .040))
    return {'surface_patch_lab': patch, 'interior_samples': int(interior.sum()),
            'bright_texture_fraction': bright_texture, 'deblotch': strength,
            'note': 'Selects a global amount of the accepted filter. Coherent shading is excluded from the estimate, not copied back into the result. Bright texture is not a semantic sparkle/halo detector.'}
