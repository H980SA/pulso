import math

import numpy as np
import pytest

from pulso_navigation.frontier import FrontierCandidate, GridSpec
from pulso_navigation.metaview_geometry import (
    build_viewport,
    frontier_mask,
    horizontal_fov_from_intrinsics,
    scan_footprint_world,
)
from pulso_navigation.metaview_model import ROUTE_COLORS, render_metaview


def _candidate() -> FrontierCandidate:
    return FrontierCandidate(
        candidate_id="F_EAST",
        x=0.85,
        y=0.05,
        path=((-0.25, 0.05), (0.25, 0.05), (0.85, 0.05)),
        path_length_m=1.1,
        risk=0.2,
        information_gain=0.8,
        frontier_cells=8,
    )


def test_viewport_projects_world_coordinates_with_map_y_pointing_up() -> None:
    occupancy = np.full((20, 30), -1, dtype=np.int16)
    occupancy[4:16, 5:25] = 0
    spec = GridSpec(resolution=0.1, origin_x=-1.5, origin_y=-1.0)
    candidate = _candidate()

    viewport = build_viewport(
        occupancy,
        spec,
        robot=(-0.25, 0.05, 0.0),
        candidates=[candidate],
        scan_footprint=(),
        output_width=960,
        output_height=720,
    )

    lower = viewport.project_world(-0.25, -0.4)
    upper = viewport.project_world(-0.25, 0.4)
    left = viewport.project_world(-0.8, 0.0)
    right = viewport.project_world(0.8, 0.0)
    assert upper[1] < lower[1]
    assert left[0] < right[0]
    assert viewport.plot_left <= left[0] <= viewport.plot_right
    assert viewport.plot_top <= upper[1] <= viewport.plot_bottom


def test_distant_no_return_fov_does_not_shrink_discovered_map() -> None:
    occupancy = np.full((20, 20), -1, dtype=np.int16)
    occupancy[7:13, 7:13] = 0
    spec = GridSpec(resolution=0.1, origin_x=-1.0, origin_y=-1.0)
    common = dict(
        occupancy=occupancy,
        spec=spec,
        robot=(0.0, 0.0, 0.0),
        candidates=[_candidate()],
        output_width=960,
        output_height=720,
    )

    baseline = build_viewport(scan_footprint=(), **common)
    no_return = build_viewport(
        scan_footprint=((0.0, 0.0), (12.0, -3.0), (12.0, 3.0)),
        **common,
    )

    assert no_return.pixels_per_metre == pytest.approx(baseline.pixels_per_metre)


def test_small_bootstrap_map_remains_readable_in_square_operator_view() -> None:
    occupancy = np.full((20, 20), -1, dtype=np.int16)
    occupancy[7:13, 7:13] = 0
    viewport = build_viewport(
        occupancy,
        GridSpec(resolution=0.1, origin_x=-1.0, origin_y=-1.0),
        robot=(0.0, 0.0, 0.0),
        candidates=[],
        scan_footprint=(),
        output_width=800,
        output_height=800,
    )

    # The 60 cm observed patch receives at least 200 px instead of becoming a
    # tiny glyph next to a long no-return depth ray.
    assert viewport.pixels_per_metre * 0.6 >= 200.0


def test_frontier_mask_is_real_free_unknown_boundary_not_occupied_cells() -> None:
    occupancy = np.full((9, 9), -1, dtype=np.int16)
    occupancy[2:7, 2:7] = 0
    occupancy[4, 6] = 100

    mask = frontier_mask(occupancy)

    assert mask[2, 4]
    assert mask[4, 2]
    assert not mask[4, 4]
    assert not mask[4, 6]


def test_scan_footprint_uses_live_ranges_camera_fov_and_robot_pose() -> None:
    footprint = scan_footprint_world(
        robot=(1.0, 2.0, math.pi / 2.0),
        ranges=(float("inf"), 2.0, 1.0, 2.0, float("inf")),
        angle_min=-0.5,
        angle_increment=0.25,
        range_min=0.1,
        range_max=3.0,
        horizontal_fov_rad=0.6,
    )

    assert footprint[0] == pytest.approx((1.0, 2.0))
    assert len(footprint) == 4
    # The middle ray is one metre forward at a +90 degree robot heading.
    assert footprint[2] == pytest.approx((1.0, 3.0))


def test_camera_fov_accepts_ros_numpy_intrinsics_without_boolean_coercion() -> None:
    intrinsics = np.asarray(
        [462.0, 0.0, 320.0, 0.0, 462.0, 240.0, 0.0, 0.0, 1.0],
        dtype=np.float64,
    )

    result = horizontal_fov_from_intrinsics(640, intrinsics)

    assert result == pytest.approx(2.0 * math.atan(640.0 / (2.0 * 462.0)))


def test_rendered_metaview_colors_map_evidence_and_exact_candidate_route() -> None:
    occupancy = np.full((24, 32), -1, dtype=np.int16)
    occupancy[4:20, 4:28] = 0
    occupancy[4:20, 22:24] = 100
    spec = GridSpec(resolution=0.1, origin_x=-1.6, origin_y=-1.2)
    robot = (-0.25, 0.05, 0.0)
    candidate = _candidate()

    image, viewport = render_metaview(
        occupancy,
        spec,
        robot,
        [candidate],
        map_seq=12,
        navigation_revision=4,
        scan_footprint=(),
        output_width=960,
        output_height=720,
    )

    assert image.shape == (720, 960, 3)
    free_x, free_y = viewport.project_world(-0.8, 0.55)
    wall_x, wall_y = viewport.project_world(0.7, 0.55)
    route_x, route_y = viewport.project_world(0.25, 0.05)
    free_b, free_g, free_r = (int(value) for value in image[free_y, free_x])
    wall_b, wall_g, wall_r = (int(value) for value in image[wall_y, wall_x])
    assert free_b > free_g > free_r
    assert wall_r > wall_g > wall_b
    assert np.linalg.norm(
        image[route_y, route_x].astype(np.int16)
        - np.asarray(ROUTE_COLORS[0], dtype=np.int16)
    ) < 45
