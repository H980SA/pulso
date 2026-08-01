"""Pure planar transforms for the ARCore-like VIO emulator."""

from __future__ import annotations

import math


def wrap_angle(angle: float) -> float:
    """Wrap an angle to [-pi, pi] without a discontinuity at the branch cut."""

    return math.atan2(math.sin(angle), math.cos(angle))


def yaw_from_quaternion(x: float, y: float, z: float, w: float) -> float:
    """Return planar yaw from an xyzw quaternion."""

    return math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))


def relative_planar_pose(
    x: float,
    y: float,
    yaw: float,
    origin: tuple[float, float, float],
) -> tuple[float, float, float]:
    """Express an absolute world pose in the first VIO sample's local frame."""

    x0, y0, yaw0 = origin
    dx = x - x0
    dy = y - y0
    cosine = math.cos(yaw0)
    sine = math.sin(yaw0)
    return (
        cosine * dx + sine * dy,
        -sine * dx + cosine * dy,
        wrap_angle(yaw - yaw0),
    )
