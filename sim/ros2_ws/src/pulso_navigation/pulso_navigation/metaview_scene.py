"""Compact, evidence-only scene contract for the interactive operator MetaView.

The browser receives geometry already expressed in ``map`` coordinates.  This
keeps rosbridge bandwidth bounded and avoids asking the UI to reproduce tf2 or
SLAM semantics.  OccupancyGrid remains 2.5D: no wall height is invented.  The
only true 3D samples are the phone depth points transformed by tf2.
"""

from __future__ import annotations

import math
from typing import Sequence

import numpy as np

from .frontier import FrontierCandidate, GridSpec


def build_metaview_scene(
    occupancy: np.ndarray,
    spec: GridSpec,
    robot: tuple[float, float, float],
    candidates: Sequence[FrontierCandidate],
    *,
    captured_ns: int,
    map_seq: int,
    navigation_revision: int,
    scan_footprint: Sequence[tuple[float, float]] = (),
    selected_id: str | None = None,
    depth_points_map: np.ndarray | Sequence[Sequence[float]] = (),
    max_map_points: int = 4_500,
    max_depth_points: int = 1_600,
) -> dict:
    """Build the bounded JSON scene consumed by Mission Control.

    Free/occupied points are cell centres sampled deterministically from the
    current OccupancyGrid.  Unknown cells are intentionally omitted.  A client
    can therefore orbit the scene without receiving simulator ground truth.
    """

    if occupancy.ndim != 2:
        raise ValueError("occupancy must be a 2D array")
    height, width = occupancy.shape
    free_rows, free_cols = np.nonzero((occupancy >= 0) & (occupancy <= 20))
    occupied_rows, occupied_cols = np.nonzero(occupancy >= 65)
    free = _sample_cells(free_rows, free_cols, spec, max_map_points)
    occupied = _sample_cells(occupied_rows, occupied_cols, spec, max_map_points)
    depth = _sample_depth(depth_points_map, max_depth_points)

    routes = []
    for index, candidate in enumerate(candidates[:6]):
        routes.append(
            {
                "id": candidate.candidate_id,
                "type": candidate.kind,
                "label": chr(ord("A") + index),
                "selected": candidate.candidate_id == selected_id,
                "position_m": [_round(candidate.x), _round(candidate.y), 0.0],
                "path_m": [[_round(x), _round(y), 0.0] for x, y in candidate.path],
                "risk": round(float(candidate.risk), 3),
                "information_gain": round(float(candidate.information_gain), 3),
            }
        )

    known_rows, known_cols = np.nonzero(occupancy >= 0)
    bounds = _bounds(
        known_rows,
        known_cols,
        spec,
        robot,
        candidates,
        depth,
    )
    return {
        "contract_version": "pulso.metaview-scene.v1",
        "captured_monotonic_ns": int(captured_ns),
        "frame_id": "map",
        "sensor_map_seq": int(map_seq),
        "navigation_revision": int(navigation_revision),
        "map": {
            "resolution_m": round(float(spec.resolution), 4),
            "origin_m": [_round(spec.origin_x), _round(spec.origin_y)],
            "width": int(width),
            "height": int(height),
            "free_points_m": free,
            "occupied_points_m": occupied,
            "known_cells": int(np.count_nonzero(occupancy >= 0)),
            "unknown_cells": int(np.count_nonzero(occupancy < 0)),
        },
        "robot": {
            "position_m": [_round(robot[0]), _round(robot[1]), 0.0],
            "heading_deg": round(math.degrees(robot[2]), 2),
        },
        "depth": {
            "source": "/pulso/phone/depth/points",
            "frame_id": "map",
            "points_m": depth,
            "sample_count": len(depth),
        },
        "scan_footprint_m": [[_round(x), _round(y), 0.02] for x, y in scan_footprint],
        "routes": routes,
        "bounds_m": bounds,
    }


def transform_xyz(points: np.ndarray, translation, rotation) -> np.ndarray:
    """Transform Nx3 xyz samples with a geometry_msgs-style transform."""

    if points.size == 0:
        return np.empty((0, 3), dtype=np.float32)
    qx, qy, qz, qw = (
        float(rotation.x),
        float(rotation.y),
        float(rotation.z),
        float(rotation.w),
    )
    norm = math.sqrt(qx * qx + qy * qy + qz * qz + qw * qw)
    if norm <= 1e-9:
        matrix = np.eye(3, dtype=np.float32)
    else:
        qx, qy, qz, qw = qx / norm, qy / norm, qz / norm, qw / norm
        matrix = np.asarray(
            [
                [1 - 2 * (qy * qy + qz * qz), 2 * (qx * qy - qz * qw), 2 * (qx * qz + qy * qw)],
                [2 * (qx * qy + qz * qw), 1 - 2 * (qx * qx + qz * qz), 2 * (qy * qz - qx * qw)],
                [2 * (qx * qz - qy * qw), 2 * (qy * qz + qx * qw), 1 - 2 * (qx * qx + qy * qy)],
            ],
            dtype=np.float32,
        )
    offset = np.asarray(
        [float(translation.x), float(translation.y), float(translation.z)],
        dtype=np.float32,
    )
    return points.astype(np.float32, copy=False) @ matrix.T + offset


def _sample_cells(rows, cols, spec: GridSpec, maximum: int) -> list[list[float]]:
    count = len(rows)
    if count == 0 or maximum <= 0:
        return []
    indices = _even_indices(count, maximum)
    return [
        [
            _round(spec.origin_x + (int(cols[index]) + 0.5) * spec.resolution),
            _round(spec.origin_y + (int(rows[index]) + 0.5) * spec.resolution),
        ]
        for index in indices
    ]


def _sample_depth(points, maximum: int) -> list[list[float]]:
    array = np.asarray(points, dtype=np.float32)
    if array.size == 0 or maximum <= 0:
        return []
    array = array.reshape((-1, 3))
    finite = array[np.isfinite(array).all(axis=1)]
    if finite.size == 0:
        return []
    indices = _even_indices(len(finite), maximum)
    return [[_round(value) for value in finite[index]] for index in indices]


def _even_indices(count: int, maximum: int) -> np.ndarray:
    if count <= maximum:
        return np.arange(count, dtype=int)
    return np.linspace(0, count - 1, maximum, dtype=int)


def _bounds(rows, cols, spec, robot, candidates, depth) -> list[float]:
    xs = [float(robot[0])]
    ys = [float(robot[1])]
    if len(rows):
        xs.extend(
            [
                spec.origin_x + (int(np.min(cols)) + 0.5) * spec.resolution,
                spec.origin_x + (int(np.max(cols)) + 0.5) * spec.resolution,
            ]
        )
        ys.extend(
            [
                spec.origin_y + (int(np.min(rows)) + 0.5) * spec.resolution,
                spec.origin_y + (int(np.max(rows)) + 0.5) * spec.resolution,
            ]
        )
    for candidate in candidates:
        xs.extend(point[0] for point in candidate.path)
        ys.extend(point[1] for point in candidate.path)
        xs.append(candidate.x)
        ys.append(candidate.y)
    for x, y, _ in depth:
        xs.append(x)
        ys.append(y)
    padding = 0.4
    return [
        _round(min(xs) - padding),
        _round(min(ys) - padding),
        _round(max(xs) + padding),
        _round(max(ys) + padding),
    ]


def _round(value: float) -> float:
    return round(float(value), 3)
