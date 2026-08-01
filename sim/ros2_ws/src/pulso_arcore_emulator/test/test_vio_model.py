import math

import pytest

from pulso_arcore_emulator.vio_model import (
    relative_planar_pose,
    wrap_angle,
    yaw_from_quaternion,
)


def test_first_truth_sample_is_the_vio_origin() -> None:
    origin = (3.06, -0.52, math.pi)
    assert relative_planar_pose(*origin, origin) == pytest.approx((0.0, 0.0, 0.0))


def test_world_negative_x_is_local_forward_at_pi_yaw() -> None:
    origin = (3.06, -0.52, math.pi)
    assert relative_planar_pose(2.96, -0.52, math.pi, origin) == pytest.approx(
        (0.10, 0.0, 0.0), abs=1e-9
    )


def test_yaw_stays_continuous_across_pi_branch() -> None:
    origin = (3.06, -0.52, math.pi)
    _, _, relative_yaw = relative_planar_pose(
        3.06, -0.52, -math.pi + 0.2, origin
    )
    assert relative_yaw == pytest.approx(0.2)


def test_quaternion_yaw_and_wrapping() -> None:
    yaw = -1.3
    assert yaw_from_quaternion(0.0, 0.0, math.sin(yaw / 2.0), math.cos(yaw / 2.0)) == pytest.approx(yaw)
    assert wrap_angle(2.0 * math.pi + 0.25) == pytest.approx(0.25)
