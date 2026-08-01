import numpy as np

from pulso_navigation.frontier import GridSpec, extract_frontiers


def test_reachable_frontier_is_proposed_without_ground_truth():
    grid = np.full((30, 40), -1, dtype=np.int8)
    grid[10:20, 4:25] = 0
    grid[13:17, 14:16] = 100
    candidates = extract_frontiers(grid, GridSpec(0.1, 0.0, 0.0), (0.8, 1.5))
    assert candidates
    assert all(candidate.candidate_id.startswith("F_") for candidate in candidates)
    assert all(candidate.path for candidate in candidates)
    assert all(0.0 <= candidate.risk <= 1.0 for candidate in candidates)


def test_enclosed_unknown_region_does_not_create_reachable_candidate():
    grid = np.zeros((24, 24), dtype=np.int8)
    grid[8:16, 8:16] = 100
    grid[10:14, 10:14] = -1
    candidates = extract_frontiers(grid, GridSpec(0.1, 0.0, 0.0), (0.3, 0.3))
    assert candidates == []


def test_candidate_id_ignores_sub_bucket_pixel_growth():
    base = np.full((30, 40), -1, dtype=np.int8)
    base[10:20, 4:25] = 0
    first = extract_frontiers(base, GridSpec(0.05, 0.0, 0.0), (0.3, 0.75))
    grown = base.copy()
    grown[10:20, 25] = 0
    second = extract_frontiers(grown, GridSpec(0.05, 0.0, 0.0), (0.3, 0.75))
    assert first and second
    assert {item.candidate_id for item in first} & {item.candidate_id for item in second}


def test_pose_inside_inflation_margin_uses_nearest_safe_start():
    grid = np.full((30, 40), -1, dtype=np.int8)
    grid[8:22, 4:30] = 0
    grid[13:17, 4:6] = 100
    # The reported pose is physically valid but lies inside the conservative
    # occupancy inflation around the wall. Planning must begin at the nearest
    # safe free cell instead of declaring every frontier unreachable.
    candidates = extract_frontiers(
        grid,
        GridSpec(0.1, 0.0, 0.0),
        (0.6, 1.5),
        inflation_m=0.1,
    )
    assert candidates
    assert all(candidate.path_length_m > 0.0 for candidate in candidates)


def test_cropped_slam_map_keeps_reachable_border_as_frontier():
    # slam_toolbox can crop the OccupancyGrid to only known cells. The edge of
    # that grid is unexplored space, not a hard world boundary.
    grid = np.zeros((14, 40), dtype=np.int8)
    candidates = extract_frontiers(
        grid,
        GridSpec(0.05, -0.5, -0.35),
        (0.0, 0.0),
        inflation_m=0.10,
        outside_is_unknown=True,
    )
    assert candidates
    assert any(candidate.frontier_cells >= 3 for candidate in candidates)
    assert all(candidate.path_length_m > 0.0 for candidate in candidates)


def test_frontier_inside_minimum_travel_envelope_is_not_offered():
    grid = np.full((15, 15), -1, dtype=np.int8)
    grid[5:10, 5:10] = 0
    spec = GridSpec(0.1, 0.0, 0.0)
    robot_xy = (0.75, 0.75)

    nearby = extract_frontiers(
        grid,
        spec,
        robot_xy,
        minimum_travel_distance_m=0.0,
    )
    eligible = extract_frontiers(
        grid,
        spec,
        robot_xy,
        minimum_travel_distance_m=0.25,
    )

    assert nearby
    assert max(candidate.path_length_m for candidate in nearby) < 0.25
    assert eligible == []
