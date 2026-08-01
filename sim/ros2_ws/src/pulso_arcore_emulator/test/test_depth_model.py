import numpy as np

from pulso_arcore_emulator.depth_model import degrade_depth


def test_degradation_is_reproducible_for_a_seed():
    depth = np.full((24, 32), 2.0, dtype=np.float32)
    first = degrade_depth(depth, np.random.default_rng(7))
    second = degrade_depth(depth, np.random.default_rng(7))
    np.testing.assert_array_equal(first[0], second[0])
    np.testing.assert_array_equal(first[1], second[1])


def test_invalid_and_out_of_range_depth_has_no_confidence():
    depth = np.array([[np.nan, 0.2, 9.0]], dtype=np.float32)
    raw, confidence = degrade_depth(depth, np.random.default_rng(3))
    assert raw.tolist() == [[0, 0, 0]]
    assert confidence.tolist() == [[0, 0, 0]]


def test_far_valid_depth_is_less_confident_than_near_depth():
    depth = np.array([[0.8, 4.5]], dtype=np.float32)
    _, confidence = degrade_depth(depth, np.random.default_rng(99))
    assert int(confidence[0, 0]) > int(confidence[0, 1])
