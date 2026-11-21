"""Accepted SCUNet surface cleanup; both powers start from the same input."""
from time import perf_counter
import cv2
import numpy as np

def _validate_rgb(rgb):
    if not isinstance(rgb,np.ndarray) or rgb.dtype != np.uint8 or rgb.ndim != 3 or rgb.shape[2] != 3 or min(rgb.shape[:2]) < 1:
        raise ValueError('Expected a nonempty uint8 RGB image.')


def cleanup_candidates(rgb, progress=None):
    """Average similar neighboring model colors; keep the two passes independent.

    OpenCV's recursive domain-transform filter limits averaging across color
    differences without a binary protection map. Brightness is included because
    the remaining broad patches are not exclusively chroma noise. No original
    edited pixels or reference pixels can enter the result here.
    """
    _validate_rgb(rgb)
    endpoints, reports = [], []
    flat = bool(np.all(rgb == rgb[0, 0]))
    for strength, spatial, color_range in ((100, 100, .05), (200, 120, .10)):
        if progress:
            progress(f'SCUNet color cleanup: preparing {strength}% endpoint')
        started = perf_counter()
        result = rgb.copy() if flat else cv2.edgePreservingFilter(
            np.ascontiguousarray(rgb), flags=1, sigma_s=spatial, sigma_r=color_range)
        endpoints.append(result)
        reports.append({'strength': strength, 'spatial_sigma_pixels': spatial,
            'color_range': color_range, 'seconds': perf_counter()-started,
            'mean_rgb_change': float(np.abs(result.astype(np.int16)-rgb).mean())})
    return *endpoints, {'method': 'Recursive domain-transform color averaging',
        'endpoints': reports, 'input': 'Uncolored full-strength SCUNet output',
        'channels': 'RGB, including brightness', 'source_copyback': False,
        'binary_protection': False, 'region_fill': False, 'stroke_fitting': False,
        'note': 'Contrast limits averaging; this is not semantic detection of noise. Strong cleanup can soften faint marks, gradients and texture.'}
