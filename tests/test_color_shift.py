"""Color math and model-free cumulative previews."""
import numpy as np
from PIL import Image
import pytest

from stable_shift.color_shift import ColorShift, preview


def test_disabled_neutral_and_zero_steps_are_exact_identity():
    source = Image.fromarray(np.random.default_rng(7).integers(0, 256, (37, 53, 3), dtype=np.uint8))
    for shift, count in [(ColorShift(False, -.1, .1, -.1, 5), 10),
                         (ColorShift(True), 10), (ColorShift(True, -.1), 0)]:
        result = shift.apply(source, count)
        assert result.size == source.size and result.tobytes() == source.tobytes()


def test_exposure_is_multiplicative_in_linear_light_and_keeps_black():
    source = Image.new('RGB', (2, 1), (255, 128, 64))
    source.putpixel((1, 0), (0, 0, 0))
    result = ColorShift(True, exposure=-.5).apply(source, 2)
    assert result.getpixel((0, 0)) == (188, 92, 44)
    assert result.getpixel((1, 0)) == (0, 0, 0)


def test_opponent_balances_cover_red_cyan_blue_yellow_and_green_magenta():
    source = Image.new('RGB', (2, 2), (128, 128, 128))
    red = ColorShift(True, red=.1).apply(source).getpixel((0, 0))
    cyan = ColorShift(True, red=-.1).apply(source).getpixel((0, 0))
    blue = ColorShift(True, blue=.1).apply(source).getpixel((0, 0))
    yellow = ColorShift(True, blue=-.1).apply(source).getpixel((0, 0))
    green = ColorShift(True, red=-.1, blue=-.1).apply(source).getpixel((0, 0))
    magenta = ColorShift(True, red=.1, blue=.1).apply(source).getpixel((0, 0))
    assert red[0] > red[1] == red[2] and cyan[0] < cyan[1] == cyan[2]
    assert blue[2] > blue[0] == blue[1] and yellow[2] < yellow[0] == yellow[1]
    assert green[1] > green[0] == green[2] and magenta[1] < magenta[0] == magenta[2]


def test_preview_has_cumulative_checkpoints_and_preserves_neutral_pixels():
    source = Image.new('RGB', (64, 64), (150, 100, 50))
    images = preview(source, 10, exposure=-.1, saturation=-10)
    assert [label for _, label in images] == ['Original', 'After 1 loop', 'After 5 loops', 'After 10 loops']
    brightness = [sum(image.getpixel((0, 0))) for image, _ in images]
    assert all(a > b for a, b in zip(brightness, brightness[1:]))
    neutral = preview(source, 10)
    assert all(image.tobytes() == source.tobytes() for image, _ in neutral)
    large = preview(Image.new('RGB', (2048, 1024)), 1)
    assert all(image.size == (768, 384) for image, _ in large)


def test_invalid_controls_and_preview_counts_are_rejected():
    source = Image.new('RGB', (2, 2))
    for shift in (ColorShift(True, exposure=float('nan')), ColorShift(True, red=.3),
                  ColorShift(True, blue=float('inf')), ColorShift(True, saturation=-26)):
        with pytest.raises(ValueError):
            shift.apply(source)
    for count in (-1, 1.5, float('nan'), 101):
        with pytest.raises(ValueError):
            preview(source, count)
    with pytest.raises(ValueError, match='preview image'):
        preview(None)
