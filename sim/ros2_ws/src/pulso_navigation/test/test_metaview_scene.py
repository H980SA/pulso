from types import SimpleNamespace

import numpy as np

from pulso_navigation.frontier import FrontierCandidate, GridSpec
from pulso_navigation.metaview_scene import build_metaview_scene, transform_xyz


def candidate() -> FrontierCandidate:
    return FrontierCandidate(
        candidate_id="F_EAST",
        x=1.25,
        y=0.25,
        path=((0.25, 0.25), (0.75, 0.25), (1.25, 0.25)),
        path_length_m=1.0,
        risk=0.2,
        information_gain=0.8,
        frontier_cells=7,
    )


def test_scene_contains_only_live_map_evidence_and_exact_route_geometry():
    grid = np.asarray(
        [
            [-1, -1, -1, -1],
            [-1, 0, 0, 100],
            [-1, 0, 0, 100],
        ],
        dtype=np.int16,
    )
    scene = build_metaview_scene(
        grid,
        GridSpec(0.5, 0.0, 0.0),
        (0.25, 0.75, 0.0),
        [candidate()],
        captured_ns=99,
        map_seq=4,
        navigation_revision=8,
        scan_footprint=((0.25, 0.75), (1.0, 1.0)),
        selected_id="F_EAST",
        depth_points_map=np.asarray([[0.5, 0.5, 0.4], [0.7, 0.5, 0.6]]),
    )
    assert scene["contract_version"] == "pulso.metaview-scene.v1"
    assert scene["map"]["known_cells"] == 6
    assert len(scene["map"]["free_points_m"]) == 4
    assert len(scene["map"]["occupied_points_m"]) == 2
    assert scene["routes"][0]["path_m"] == [
        [0.25, 0.25, 0.0],
        [0.75, 0.25, 0.0],
        [1.25, 0.25, 0.0],
    ]
    assert scene["routes"][0]["selected"] is True
    assert scene["depth"]["sample_count"] == 2
    assert "unknown_points_m" not in scene["map"]


def test_scene_sampling_is_bounded_and_deterministic():
    grid = np.zeros((100, 100), dtype=np.int16)
    first = build_metaview_scene(
        grid,
        GridSpec(0.1, -5.0, -5.0),
        (0.0, 0.0, 0.0),
        [],
        captured_ns=1,
        map_seq=1,
        navigation_revision=1,
        max_map_points=37,
    )
    second = build_metaview_scene(
        grid,
        GridSpec(0.1, -5.0, -5.0),
        (0.0, 0.0, 0.0),
        [],
        captured_ns=2,
        map_seq=1,
        navigation_revision=1,
        max_map_points=37,
    )
    assert len(first["map"]["free_points_m"]) == 37
    assert first["map"]["free_points_m"] == second["map"]["free_points_m"]


def test_depth_transform_preserves_real_xyz_geometry():
    translation = SimpleNamespace(x=1.0, y=2.0, z=3.0)
    rotation = SimpleNamespace(x=0.0, y=0.0, z=0.0, w=1.0)
    result = transform_xyz(np.asarray([[0.25, -0.5, 1.0]]), translation, rotation)
    np.testing.assert_allclose(result, [[1.25, 1.5, 4.0]])
