import cv2
import numpy as np
import pytest

from stable_shift.surface_speckles import clean_surface_speckles
from stable_shift.line_borders import LUMA


PAINT = np.array([110, 125, 140], np.uint8)
INK = np.array([20, 28, 40], np.uint8)


def scene():
    image = np.full((120, 180, 3), PAINT, np.uint8)
    image[8:112, 70:73] = INK
    return image


@pytest.mark.parametrize('color', [[65, 75, 85], [20, 28, 40]])
def test_removes_nearby_dark_specks_without_touching_connected_ink(color):
    clean = scene()
    damaged = clean.copy()
    points = [(20, 78), (40, 81), (65, 77), (85, 82)]
    for y, x in points:
        damaged[y, x] = color
    repaired, active, report = clean_surface_speckles(damaged, np.ones(clean.shape[:2], bool))
    for y, x in points:
        np.testing.assert_array_equal(repaired[y, x], clean[y, x])
    np.testing.assert_array_equal(repaired[8:112, 70:73], clean[8:112, 70:73])
    np.testing.assert_array_equal(repaired[~active], damaged[~active])
    assert report['removed_pixels'] >= len(points)
    assert np.all((repaired.astype(np.float32)@LUMA)[active] > (damaged.astype(np.float32)@LUMA)[active])


@pytest.mark.parametrize('width,length', [(1, 2), (1, 4), (2, 3), (2, 5)])
def test_keeps_short_stitches_and_faint_connecting_lines(width, length):
    image = scene()
    for y in (20, 40, 60, 80):
        image[y:y+width, 79:79+length] = [90, 105, 120]
    image[100, 72:110] = [95, 110, 125]
    repaired, _, _ = clean_surface_speckles(image, np.ones(image.shape[:2], bool))
    np.testing.assert_array_equal(repaired, image)


def test_keeps_distant_dark_details_and_bright_sparkles():
    image = scene()
    image[60, 150] = INK
    image[70, 80] = [250, 250, 250]
    repaired, _, _ = clean_surface_speckles(image, np.ones(image.shape[:2], bool))
    np.testing.assert_array_equal(repaired[60, 150], image[60, 150])
    np.testing.assert_array_equal(repaired[70, 80], image[70, 80])


def test_clean_curves_and_shading_interiors_remain_unchanged():
    image = scene()
    cv2.ellipse(image, (130, 60), (22, 35), 0, 0, 360, tuple(int(c) for c in INK), 2, cv2.LINE_AA)
    image[10:110, 10:45] = np.linspace(80, 125, 100).astype(np.uint8)[:, None, None]
    repaired, _, _ = clean_surface_speckles(image, np.ones(image.shape[:2], bool))
    np.testing.assert_array_equal(repaired, image)


def test_empty_support_does_not_clean_and_inputs_are_not_modified():
    image = scene()
    image[50, 80] = 50
    original = image.copy()
    repaired, active, _ = clean_surface_speckles(image, np.zeros(image.shape[:2], bool))
    np.testing.assert_array_equal(repaired, original)
    np.testing.assert_array_equal(image, original)
    assert not active.any()


@pytest.mark.parametrize('size', [(1, 1), (1, 7), (5, 1), (3, 3)])
def test_tiny_images(size):
    image = np.full((*size, 3), 100, np.uint8)
    repaired, _, _ = clean_surface_speckles(image, np.ones(size, bool))
    np.testing.assert_array_equal(repaired, image)


def test_invalid_shape_is_rejected():
    with pytest.raises(ValueError):
        clean_surface_speckles(np.zeros((5, 5), np.uint8), np.ones((5, 5), bool))
    with pytest.raises(ValueError):
        clean_surface_speckles(scene(), np.ones((4, 7), bool))
