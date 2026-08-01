"""Pure frontier extraction used by both runtime and contract tests."""

from __future__ import annotations

from dataclasses import dataclass
import heapq
import math

import cv2
import numpy as np


@dataclass(frozen=True)
class GridSpec:
    resolution: float
    origin_x: float
    origin_y: float


@dataclass(frozen=True)
class FrontierCandidate:
    candidate_id: str
    x: float
    y: float
    path: tuple[tuple[float, float], ...]
    path_length_m: float
    risk: float
    information_gain: float
    frontier_cells: int
    kind: str = "FRONTIER"
    rotation_only: bool = False
    target_revision: int | None = None


def world_to_cell(x: float, y: float, spec: GridSpec) -> tuple[int, int]:
    return (
        int(math.floor((x - spec.origin_x) / spec.resolution)),
        int(math.floor((y - spec.origin_y) / spec.resolution)),
    )


def cell_to_world(col: int, row: int, spec: GridSpec) -> tuple[float, float]:
    return (
        spec.origin_x + (col + 0.5) * spec.resolution,
        spec.origin_y + (row + 0.5) * spec.resolution,
    )


def _stable_id(x: float, y: float) -> str:
    # A 25 cm bucket survives harmless pixel-level map growth while still
    # changing when a frontier moves materially.
    return f"F_{round(x / 0.25):+04d}_{round(y / 0.25):+04d}"


def _astar(
    traversable: np.ndarray,
    start: tuple[int, int],
    goal: tuple[int, int],
) -> list[tuple[int, int]] | None:
    height, width = traversable.shape
    sx, sy = start
    gx, gy = goal
    if not (0 <= sx < width and 0 <= sy < height and 0 <= gx < width and 0 <= gy < height):
        return None
    walkable = traversable.copy()
    walkable[sy, sx] = True
    walkable[gy, gx] = True
    neighbors = (
        (-1, 0, 1.0), (1, 0, 1.0), (0, -1, 1.0), (0, 1, 1.0),
        (-1, -1, math.sqrt(2.0)), (1, -1, math.sqrt(2.0)),
        (-1, 1, math.sqrt(2.0)), (1, 1, math.sqrt(2.0)),
    )
    queue: list[tuple[float, float, int, int]] = [(0.0, 0.0, sx, sy)]
    best = {(sx, sy): 0.0}
    parent: dict[tuple[int, int], tuple[int, int]] = {}
    while queue:
        _, cost, x, y = heapq.heappop(queue)
        if (x, y) == (gx, gy):
            path = [(x, y)]
            while path[-1] != (sx, sy):
                path.append(parent[path[-1]])
            return list(reversed(path))
        if cost > best.get((x, y), float("inf")):
            continue
        for dx, dy, step in neighbors:
            nx, ny = x + dx, y + dy
            if not (0 <= nx < width and 0 <= ny < height and walkable[ny, nx]):
                continue
            candidate_cost = cost + step
            if candidate_cost >= best.get((nx, ny), float("inf")):
                continue
            best[(nx, ny)] = candidate_cost
            parent[(nx, ny)] = (x, y)
            heuristic = math.hypot(gx - nx, gy - ny)
            heapq.heappush(queue, (candidate_cost + heuristic, candidate_cost, nx, ny))
    return None


def extract_frontiers(
    occupancy: np.ndarray,
    spec: GridSpec,
    robot_xy: tuple[float, float],
    *,
    max_candidates: int = 6,
    # OpenBot half-width is 8.5 cm; 10 cm includes a small mapping margin.
    # Near-field sonar / bumper remain the independent last-resort guard.
    inflation_m: float = 0.10,
    information_radius_m: float = 0.75,
    outside_is_unknown: bool = False,
    minimum_travel_distance_m: float = 0.18,
) -> list[FrontierCandidate]:
    """Return reachable, stable frontier candidates from an occupancy grid.

    Occupancy values follow ROS: -1 unknown, 0 free, 100 occupied. No simulator
    labels or ground-truth poses are consumed here. Both planned path length
    and direct goal separation must clear ``minimum_travel_distance_m`` so a
    winding path cannot disguise a target already inside the arrival envelope.
    """
    if (
        occupancy.ndim != 2
        or occupancy.size == 0
        or spec.resolution <= 0
        or not math.isfinite(minimum_travel_distance_m)
        or minimum_travel_distance_m < 0.0
    ):
        return []
    free = (occupancy >= 0) & (occupancy <= 20)
    unknown = occupancy < 0
    occupied = occupancy >= 65
    if not np.any(free) or (not np.any(unknown) and not outside_is_unknown):
        return []

    if outside_is_unknown:
        # slam_toolbox publishes a grid cropped to its currently observed
        # bounds. Cells beyond that border are unexplored even though they are
        # absent from the message. Other callers may represent a bounded map,
        # so this behavior is explicit rather than silently global.
        padded_unknown = np.pad(unknown, 1, mode="constant", constant_values=True)
        unknown_neighbor = (
            cv2.dilate(padded_unknown.astype(np.uint8), np.ones((3, 3), np.uint8))[
                1:-1, 1:-1
            ]
            > 0
        )
    else:
        unknown_neighbor = (
            cv2.dilate(unknown.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
        )
    frontier = free & unknown_neighbor
    inflation_cells = max(0, int(math.ceil(inflation_m / spec.resolution)))
    kernel_size = inflation_cells * 2 + 1
    inflated = cv2.dilate(
        occupied.astype(np.uint8), np.ones((kernel_size, kernel_size), np.uint8)
    ) > 0
    traversable = free & ~inflated

    robot_col, robot_row = world_to_cell(robot_xy[0], robot_xy[1], spec)
    robot_col = int(np.clip(robot_col, 0, occupancy.shape[1] - 1))
    robot_row = int(np.clip(robot_row, 0, occupancy.shape[0] - 1))
    if not traversable[robot_row, robot_col]:
        safe_free = np.argwhere(traversable)
        if safe_free.size == 0:
            return []
        nearest = int(
            np.argmin(
                (safe_free[:, 1] - robot_col) ** 2
                + (safe_free[:, 0] - robot_row) ** 2
            )
        )
        robot_row, robot_col = (int(value) for value in safe_free[nearest])
    labels_count, labels, stats, centroids = cv2.connectedComponentsWithStats(
        frontier.astype(np.uint8), connectivity=8
    )
    clearance = cv2.distanceTransform((~occupied).astype(np.uint8), cv2.DIST_L2, 5)
    info_radius_cells = max(1, int(round(information_radius_m / spec.resolution)))
    possible: list[tuple[float, FrontierCandidate]] = []

    for label in range(1, labels_count):
        cell_count = int(stats[label, cv2.CC_STAT_AREA])
        if cell_count < 3:
            continue
        points = np.argwhere((labels == label) & traversable)
        if points.size == 0:
            continue
        centroid_col, centroid_row = centroids[label]
        nearest_index = int(
            np.argmin(
                (points[:, 1] - centroid_col) ** 2 + (points[:, 0] - centroid_row) ** 2
            )
        )
        target_row, target_col = (int(v) for v in points[nearest_index])
        path_cells = _astar(traversable, (robot_col, robot_row), (target_col, target_row))
        if not path_cells or len(path_cells) < 2:
            continue
        path_length = sum(
            math.hypot(b[0] - a[0], b[1] - a[1]) * spec.resolution
            for a, b in zip(path_cells, path_cells[1:])
        )
        if path_length > 12.0 or path_length + 1e-9 < minimum_travel_distance_m:
            continue
        x, y = cell_to_world(target_col, target_row, spec)
        if (
            math.hypot(x - robot_xy[0], y - robot_xy[1]) + 1e-9
            < minimum_travel_distance_m
        ):
            continue
        sampled_path = path_cells[:: max(1, len(path_cells) // 24)]
        if sampled_path[-1] != path_cells[-1]:
            sampled_path.append(path_cells[-1])
        world_path = tuple(cell_to_world(col, row, spec) for col, row in sampled_path)
        minimum_clearance = min(float(clearance[row, col]) for col, row in path_cells) * spec.resolution
        risk = 1.0 - float(np.clip((minimum_clearance - 0.10) / 0.45, 0.0, 1.0))

        y0, y1 = max(0, target_row - info_radius_cells), min(occupancy.shape[0], target_row + info_radius_cells + 1)
        x0, x1 = max(0, target_col - info_radius_cells), min(occupancy.shape[1], target_col + info_radius_cells + 1)
        yy, xx = np.ogrid[y0:y1, x0:x1]
        circle = (xx - target_col) ** 2 + (yy - target_row) ** 2 <= info_radius_cells ** 2
        unknown_count = int(np.count_nonzero(unknown[y0:y1, x0:x1] & circle))
        capacity = max(1, int(math.pi * info_radius_cells * info_radius_cells * 0.55))
        information_gain = float(np.clip(unknown_count / capacity, 0.0, 1.0))
        candidate = FrontierCandidate(
            candidate_id=_stable_id(x, y),
            x=x,
            y=y,
            path=world_path,
            path_length_m=path_length,
            risk=risk,
            information_gain=information_gain,
            frontier_cells=cell_count,
        )
        score = information_gain - 0.55 * risk - 0.025 * path_length + min(cell_count, 40) / 400.0
        possible.append((score, candidate))

    possible.sort(key=lambda item: item[0], reverse=True)
    unique: list[FrontierCandidate] = []
    used_ids: set[str] = set()
    for _, candidate in possible:
        if candidate.candidate_id in used_ids:
            continue
        if any(math.hypot(candidate.x - prior.x, candidate.y - prior.y) < 0.45 for prior in unique):
            continue
        unique.append(candidate)
        used_ids.add(candidate.candidate_id)
        if len(unique) >= max_candidates:
            break
    return unique
