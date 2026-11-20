"""Focused regression for reference lighting with different compositions."""
import numpy as np
from PIL import Image
import pytest

from stable_shift.global_color import fit_scunet_color
from stable_shift import scunet_cleanup
from stable_shift.engine import Options


def palette_scene():
    colors = np.random.default_rng(180).integers(20, 210, (8, 10, 3), dtype=np.uint8)
    return np.repeat(np.repeat(colors, 24, axis=0), 24, axis=1)


@pytest.mark.parametrize('gains', [(0.8, 0.5, 0.3), (0.35, 0.55, 0.8)])
def test_recomposed_reference_still_darkens_and_transfers_warm_or_cool_lighting(gains):
    source = palette_scene()
    expected = np.uint8(np.clip(source.astype(float)*gains+.5, 0, 255))
    reference = Image.fromarray(expected[:, ::-1].copy())
    model, report = fit_scunet_color(reference, source)
    assert report['selected_method'] == 'Global palette'
    corrected = model.apply(source)
    assert np.abs(corrected.astype(float)-expected).mean() < 1
    assert corrected.mean() < source.mean()*.70
    # A single global mapping cannot copy reference edges into equal colors.
    for color in source[::24, ::24].reshape(-1, 3):
        same = np.all(source == color, axis=2)
        assert len(np.unique(corrected[same], axis=0)) == 1


def test_constant_channel_and_disabled_reference_have_explicit_behavior():
    source = np.full((48, 64, 3), 130, np.uint8)
    reference = Image.new('RGB', (83, 71), (65, 45, 25))
    model, report = fit_scunet_color(reference, source)
    assert report['selected_method'] == 'Global palette'
    np.testing.assert_array_equal(model.apply(source), np.full_like(source, (65, 45, 25)))
    model, report = fit_scunet_color(reference, source, enabled=False)
    assert model is None and report['selected_method'] == 'Off'


def test_scunet_preparation_keeps_reference_lighting_at_every_cached_strength(monkeypatch):
    source = palette_scene()
    reference = Image.fromarray(np.uint8(source[:, ::-1].astype(float)*[.8, .5, .3]+.5))
    calls = []
    def model(rgb, progress):
        calls.append(True)
        return rgb.copy(), {'device_name': 'Test stub'}
    monkeypatch.setattr(scunet_cleanup, 'denoise', model)
    preview = scunet_cleanup.prepare_scunet_cleanup(reference, Image.fromarray(source), Options(color_match=True))
    first = np.array(preview.render(100)[0])
    for strength in (0, 100, 200, 100):
        image, report = preview.render(strength)
        assert np.array(image).mean() < source.mean()*.70
        assert report['color_correction']['selected_method'] == 'Global palette'
        assert report['same_color_transform']
    np.testing.assert_array_equal(preview.render(100)[0], first)
    assert len(calls) == 1
