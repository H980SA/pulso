import math

from pulso_sim_adapter.range_model import quantized_nearest


def test_returns_nearest_quantized_valid_ray():
    assert quantized_nearest([2.1, 0.487, 1.2], 0.03, 4.0) == 0.49


def test_rejects_non_finite_and_out_of_range_values():
    assert math.isinf(quantized_nearest([math.nan, math.inf, 0.01, 5.0], 0.03, 4.0))
