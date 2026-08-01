"""Pure conversion from a small ray cone to an ultrasonic-style sample."""

import math
from collections.abc import Iterable


def quantized_nearest(
    ranges: Iterable[float],
    min_range: float,
    max_range: float,
    resolution: float = 0.01,
) -> float:
    valid = [value for value in ranges if math.isfinite(value) and min_range <= value <= max_range]
    if not valid:
        return math.inf
    nearest = min(valid)
    return round(nearest / resolution) * resolution
