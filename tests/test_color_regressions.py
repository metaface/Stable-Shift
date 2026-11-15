"""Color correction must not bring pre-cleanup blotches back into flat paint."""
import numpy as np
from PIL import Image

from stable_shift.engine import Options, correct_palette
from stable_shift.global_color import fit_global_color
from tests.test_finishing import colors, shifted


def cleaned_pair():
    cleaned = colors()
    yy, xx = np.indices(cleaned.shape[:2])
    # Coherent, smooth contamination that broad cleanup has already removed.
    blotches = 8*np.sin(xx/17)+5*np.cos((xx+yy)/29)
    earlier = np.uint8(np.clip(cleaned.astype(float)+blotches[..., None], 0, 255))
    return cleaned, earlier, Image.fromarray(shifted(cleaned))


def test_flat_cleaned_colors_stay_uniform_despite_blotchy_earlier_baseline():
    cleaned, earlier, reference = cleaned_pair()
    result, report = correct_palette(reference, earlier, cleaned,
        Options(method='Region cleanup only', color_method='Robust global', blotch_strength=100))
    assert report['selected_method'] == 'Robust global', report
    checked = 0
    for color in np.unique(cleaned.reshape(-1, 3), axis=0):
        same_color = np.all(cleaned == color, axis=2)
        if same_color.sum() > 40:
            checked += 1
            assert len(np.unique(result[same_color], axis=0)) == 1, color
    assert checked > 100


def test_complete_color_stage_is_exactly_the_accepted_global_rgb_mapping():
    cleaned, earlier, reference = cleaned_pair()
    model, fit = fit_global_color(reference, earlier)
    assert fit['selected_method'] == 'Robust global', fit
    result, _ = correct_palette(reference, earlier, cleaned,
        Options(color_method='Robust global', blotch_strength=100))
    assert np.array_equal(result, model.apply(cleaned))


def test_full_color_stage_handles_repeated_small_drift_without_accumulating():
    reference = colors()
    value = reference.copy()
    for _ in range(6):
        value = np.uint8(np.clip(value.astype(float)*[.99, .98, .985]+[1, 2, 1]+.5, 0, 255))
        value, _ = correct_palette(Image.fromarray(reference), value, value,
            Options(method='Color only', color_method='Robust global'))
    assert np.abs(value.astype(float)-reference).mean() < 1.5
