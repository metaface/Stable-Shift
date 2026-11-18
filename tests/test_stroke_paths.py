import cv2
import numpy as np
import pytest
from stable_shift.stroke_paths import trace_stroke_paths, _thin
from stable_shift.line_reconstruction import reconstruct_lines, _arc_distance

PAINT = (175, 190, 205)
INK = (30, 55, 80)


def canvas(size=(120, 150)):
    return np.full((*size, 3), PAINT, np.uint8)


def test_connected_long_stroke_has_real_path_ids_and_geodesic_lengths():
    image = canvas()
    image[10:110, 50:53] = INK
    paths = trace_stroke_paths(image, np.ones(image.shape[:2], bool))
    assert paths['report']['accepted_paths'] >= 1
    assert min(paths['report']['accepted_path_lengths_pixels']) >= 12
    assert paths['path_ids'][60, 51] > 0
    assert paths['application'][60, 51]
    assert not paths['application'][60, 90]


def test_large_connected_dirty_grid_cannot_qualify_by_pixel_count():
    image = canvas((100, 120))
    for x in range(30, 47, 4):
        image[30:47, x] = INK
    for y in range(30, 47, 4):
        image[y, 30:47] = INK
    assert np.count_nonzero(image[..., 0] != PAINT[0]) > 100
    paths = trace_stroke_paths(image, np.ones(image.shape[:2], bool))
    assert paths['report']['accepted_paths'] == 0
    assert not paths['application'].any()
    assert not paths['copy_back'].any()  # rejected texture junctions are not anchors
    for result in reconstruct_lines(image, np.ones(image.shape[:2], bool))[:2]:
        np.testing.assert_array_equal(result, image)


@pytest.mark.parametrize('length', [2, 4, 6, 10])
def test_short_marks_are_retained_but_not_fitted_or_joined(length):
    image = canvas()
    image[30:30+length, 50:52] = INK
    image[32+length:32+2*length, 50:52] = INK
    paths = trace_stroke_paths(image, np.ones(image.shape[:2], bool))
    assert not paths['application'].any()
    for result in reconstruct_lines(image, np.ones(image.shape[:2], bool), paths=paths)[:2]:
        np.testing.assert_array_equal(result, image)


def test_tiny_fragments_beside_valid_path_cannot_borrow_its_id_or_ink():
    image = canvas()
    image[10:110, 50:53] = INK
    image[50, 56] = [90, 100, 110]
    image[75:77, 57:59] = [80, 95, 105]
    paths = trace_stroke_paths(image, np.ones(image.shape[:2], bool))
    assert paths['report']['accepted_paths'] > 0
    assert paths['path_ids'][50, 56] == 0
    assert not paths['application'][50, 56]
    for result in reconstruct_lines(image, np.ones(image.shape[:2], bool), paths=paths)[:2]:
        np.testing.assert_array_equal(result[50, 56], image[50, 56])
        np.testing.assert_array_equal(result[75:77, 57:59], image[75:77, 57:59])


def test_asymmetric_filled_nose_and_highlight_keep_their_exact_shape_and_rgb():
    image = canvas()
    polygon = np.int32([[55, 35], [85, 39], [92, 48], [84, 64], [67, 69], [54, 56], [50, 42]])
    cv2.fillPoly(image, [polygon], (45, 35, 25), cv2.LINE_AA)
    cv2.polylines(image, [polygon], True, (15, 13, 10), 2, cv2.LINE_AA)
    image[43:45, 60:69] = (100, 95, 80)
    object_mask = np.any(image != PAINT, axis=2)
    paths = trace_stroke_paths(image, np.ones(image.shape[:2], bool))
    assert np.all(paths['filled'][object_mask])
    for result in reconstruct_lines(image, np.ones(image.shape[:2], bool), paths=paths)[:2]:
        np.testing.assert_array_equal(result[object_mask], image[object_mask])


def test_broad_filled_detail_keeps_its_dark_rim_as_well_as_its_interior():
    image = canvas((160, 200))
    cv2.ellipse(image, (90, 75), (33, 22), -12, 0, 360, (45, 35, 25), -1, cv2.LINE_AA)
    cv2.ellipse(image, (90, 75), (33, 22), -12, 0, 360, (8, 9, 12), 4, cv2.LINE_AA)
    image[67:69, 75:92] = (95, 85, 70)
    object_mask = np.any(image != PAINT, axis=2)
    paths = trace_stroke_paths(image, np.ones(image.shape[:2], bool))
    assert np.all(paths['filled_fit_guard'][object_mask])
    for result in reconstruct_lines(image, np.ones(image.shape[:2], bool), paths=paths)[:2]:
        np.testing.assert_array_equal(result[object_mask], image[object_mask])


def test_disconnected_speck_near_a_filled_shape_is_not_part_of_its_rim():
    image = canvas()
    cv2.ellipse(image, (70, 55), (20, 14), 0, 0, 360, (40, 30, 25), -1, cv2.LINE_AA)
    cv2.ellipse(image, (70, 55), (20, 14), 0, 0, 360, (10, 10, 10), 2, cv2.LINE_AA)
    image[55, 98] = (30, 40, 50)
    paths = trace_stroke_paths(image, np.ones(image.shape[:2], bool))
    assert paths['filled'].any()
    assert not paths['filled_fit_guard'][55, 98]
    assert not paths['application'][55, 98]
    assert not paths['copy_back'][55, 98]


def test_nearby_colored_paths_remain_separate_and_cannot_supply_each_others_ink():
    image = canvas()
    image[10:110, 45:48] = (35, 65, 100)
    image[10:110, 53:56] = (20, 10, 15)
    paths = trace_stroke_paths(image, np.ones(image.shape[:2], bool))
    assert paths['path_ids'][60, 46] > 0
    assert paths['path_ids'][60, 54] > 0
    assert paths['path_ids'][60, 46] != paths['path_ids'][60, 54]
    for result in reconstruct_lines(image, np.ones(image.shape[:2], bool), paths=paths)[:2]:
        assert np.min(result[20:100, 43:50, 1]) >= 64
        assert np.min(result[20:100, 43:50, 2]) >= 99


def test_untraced_dark_detail_cannot_supply_ink_or_be_repainted_as_line_margin():
    image = canvas()
    image[10:110, 50:53] = (80, 100, 120)
    image[60, 53] = (8, 10, 12)
    core = np.zeros(image.shape[:2], bool)
    core[8:112, 49:53] = True
    paths = trace_stroke_paths(image, core)
    assert not paths['candidates'][60, 53]
    assert paths['report']['accepted_paths'] > 0
    for result in reconstruct_lines(image, core, paths=paths)[:2]:
        assert result[20:100, 50:53, 2].min() >= 119
        np.testing.assert_array_equal(result[60, 53], image[60, 53])


def test_faint_long_path_is_not_rejected_by_nearby_heavy_ink_contrast():
    image = canvas()
    image[10:110, 45:48] = (15, 15, 15)
    image[10:110, 54] = (165, 180, 195)
    paths = trace_stroke_paths(image, np.ones(image.shape[:2], bool))
    assert paths['path_ids'][60, 54] > 0
    assert paths['path_ids'][60, 54] != paths['path_ids'][60, 46]


def test_crossing_junctions_are_retained_without_fitting_across_branches():
    image = canvas()
    image[10:110, 70:73] = INK
    image[58:61, 15:135] = INK
    paths = trace_stroke_paths(image, np.ones(image.shape[:2], bool))
    assert paths['report']['accepted_paths'] >= 4
    assert not paths['application'][58:62, 69:74].any()
    for result in reconstruct_lines(image, np.ones(image.shape[:2], bool), paths=paths)[:2]:
        np.testing.assert_array_equal(result[58:62, 69:74], image[58:62, 69:74])


def test_short_attached_spur_is_not_allowed_to_seed_a_reconstructed_stroke():
    image = canvas((180, 160))
    image[10:170, 80:83] = INK
    image[60:63, 83:88] = INK
    paths = trace_stroke_paths(image, np.ones(image.shape[:2], bool))
    assert paths['report']['accepted_paths'] > 0
    assert paths['report']['short_branch_pixels_pruned'] > 0
    assert not paths['application'][61, 87]


def test_tiny_closed_dirty_loop_does_not_qualify_by_perimeter_alone():
    image = canvas()
    cv2.circle(image, (60, 50), 2, INK, 1)
    paths = trace_stroke_paths(image, np.ones(image.shape[:2], bool))
    assert not paths['application'].any()


@pytest.mark.parametrize('closed,expected', [(False, 46), (True, 4)])
def test_arc_distance_cannot_wrap_across_ends_of_an_open_trace(closed, expected):
    assert _arc_distance(np.array([2]), np.array([48]), np.array([50]), np.array([closed]))[0] == expected


def test_open_hairpin_remains_an_open_path_despite_nearby_ends():
    image = canvas()
    points = np.int32([[50, 25], [50, 95], [60, 95], [60, 25]])
    cv2.polylines(image, [points], False, INK, 2, cv2.LINE_AA)
    paths = trace_stroke_paths(image, np.ones(image.shape[:2], bool))
    assert paths['report']['accepted_paths'] > 0
    assert not paths['path_closed'].any()


@pytest.mark.parametrize('size', [(1, 1), (1, 8), (8, 1), (5, 7)])
def test_tiny_inputs_do_not_create_any_stroke(size):
    image = canvas(size)
    paths = trace_stroke_paths(image, np.ones(size, bool))
    assert not paths['accepted'].any()
    assert not paths['application'].any()


def test_thinning_retains_a_single_connected_centerline():
    image = np.zeros((40, 50), bool)
    image[4:36, 20:25] = True
    skeleton = _thin(image)
    assert cv2.connectedComponents(np.uint8(skeleton), 8)[0] == 2
    assert 25 <= skeleton.sum() <= 35
