"""Metric transforms and sensor projection for the top-down MetaView."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence

import cv2
import numpy as np

from .frontier import FrontierCandidate, GridSpec


@dataclass(frozen=True)
class MapViewport:
    """One metric transform shared by the occupancy map and all overlays."""

    output_width: int
    output_height: int
    plot_left: int
    plot_top: int
    plot_right: int
    plot_bottom: int
    world_min_x: float
    world_min_y: float
    world_max_x: float
    world_max_y: float
    pixels_per_metre: float

    def project_world(self, x: float, y: float) -> tuple[int, int]:
        return (
            int(round(self.plot_left + (x - self.world_min_x) * self.pixels_per_metre)),
            int(round(self.plot_top + (self.world_max_y - y) * self.pixels_per_metre)),
        )


def horizontal_fov_from_intrinsics(
    image_width: int, intrinsics: Sequence[float]
) -> float | None:
    """Return horizontal camera FOV without assuming a Python list message."""
    if image_width <= 0 or len(intrinsics) == 0:
        return None
    focal_x = float(intrinsics[0])
    if not math.isfinite(focal_x) or focal_x <= 0.0:
        return None
    horizontal_fov = 2.0 * math.atan(float(image_width) / (2.0 * focal_x))
    return horizontal_fov if 0.1 <= horizontal_fov < math.pi else None


def frontier_mask(occupancy: np.ndarray) -> np.ndarray:
    """Return free cells that border unexplored space, including map edges."""
    if occupancy.ndim != 2 or occupancy.size == 0:
        return np.zeros_like(occupancy, dtype=bool)
    free = (occupancy >= 0) & (occupancy <= 20)
    unknown = occupancy < 0
    padded = np.pad(unknown, 1, mode="constant", constant_values=True)
    touches_unknown = cv2.dilate(
        padded.astype(np.uint8), np.ones((3, 3), dtype=np.uint8)
    )[1:-1, 1:-1] > 0
    return free & touches_unknown


def scan_footprint_world(
    *,
    robot: tuple[float, float, float],
    ranges: Sequence[float],
    angle_min: float,
    angle_increment: float,
    range_min: float,
    range_max: float,
    horizontal_fov_rad: float,
    max_points: int = 96,
) -> tuple[tuple[float, float], ...]:
    """Project the current depth-derived LaserScan footprint into map space.

    Positive infinity means the sensor observed no return before ``range_max``;
    NaN and sub-minimum samples provide no evidence and are omitted.
    """
    if (
        len(ranges) == 0
        or not math.isfinite(angle_increment)
        or angle_increment == 0.0
        or not math.isfinite(range_max)
        or range_max <= 0.0
        or not math.isfinite(horizontal_fov_rad)
        or horizontal_fov_rad <= 0.0
    ):
        return ()
    half_fov = horizontal_fov_rad / 2.0
    endpoints: list[tuple[float, float]] = []
    robot_x, robot_y, robot_yaw = robot
    for index, raw_range in enumerate(ranges):
        relative_angle = angle_min + index * angle_increment
        if abs(relative_angle) > half_fov + 1e-9:
            continue
        if math.isinf(raw_range) and raw_range > 0:
            distance = range_max
        elif math.isfinite(raw_range) and raw_range >= range_min:
            distance = min(raw_range, range_max)
        else:
            continue
        world_angle = robot_yaw + relative_angle
        endpoints.append(
            (
                robot_x + math.cos(world_angle) * distance,
                robot_y + math.sin(world_angle) * distance,
            )
        )
    if len(endpoints) < 2:
        return ()
    if len(endpoints) > max_points:
        indices = np.linspace(0, len(endpoints) - 1, max_points, dtype=int)
        endpoints = [endpoints[int(index)] for index in indices]
    return ((robot_x, robot_y), *endpoints)


def build_viewport(
    occupancy: np.ndarray,
    spec: GridSpec,
    *,
    robot: tuple[float, float, float],
    candidates: Sequence[FrontierCandidate],
    scan_footprint: Sequence[tuple[float, float]],
    output_width: int,
    output_height: int,
) -> MapViewport:
    """Fit all current map evidence without stretching metric geometry."""
    if occupancy.ndim != 2 or occupancy.size == 0 or spec.resolution <= 0.0:
        raise ValueError("MetaView needs a non-empty metric occupancy grid")
    points: list[tuple[float, float]] = []
    known = np.argwhere(occupancy >= 0)
    if known.size:
        min_row, min_col = known.min(axis=0)
        max_row, max_col = known.max(axis=0)
        points.extend(
            (
                (spec.origin_x + min_col * spec.resolution,
                 spec.origin_y + min_row * spec.resolution),
                (spec.origin_x + (max_col + 1) * spec.resolution,
                 spec.origin_y + (max_row + 1) * spec.resolution),
            )
        )
    else:
        height, width = occupancy.shape
        points.extend(
            (
                (spec.origin_x, spec.origin_y),
                (spec.origin_x + width * spec.resolution,
                 spec.origin_y + height * spec.resolution),
            )
        )
    points.append((robot[0], robot[1]))
    # A no-return depth ray can legitimately reach the 12 m sensor maximum.
    # It is evidence, but it must not zoom the discovered map into a thumbnail.
    # The FOV polygon is clipped to the map/candidate viewport at render time.
    for candidate in candidates:
        points.extend(candidate.path)
        points.append((candidate.x, candidate.y))

    xs, ys = zip(*points)
    min_x, max_x = min(xs) - 0.35, max(xs) + 0.35
    min_y, max_y = min(ys) - 0.35, max(ys) + 0.35
    center_x, center_y = (min_x + max_x) / 2.0, (min_y + max_y) / 2.0
    # The first honest SLAM map can be below one square metre. Keep enough
    # context for heading and routes without reducing that map to a thumbnail.
    span_x = max(1.6, max_x - min_x)
    span_y = max(1.6, max_y - min_y)

    plot_left, plot_right = 54, output_width - 42
    plot_top, plot_bottom = 62, output_height - 58
    plot_width = max(1, plot_right - plot_left)
    plot_height = max(1, plot_bottom - plot_top)
    target_ratio = plot_width / plot_height
    if span_x / span_y < target_ratio:
        span_x = span_y * target_ratio
    else:
        span_y = span_x / target_ratio
    min_x, max_x = center_x - span_x / 2.0, center_x + span_x / 2.0
    min_y, max_y = center_y - span_y / 2.0, center_y + span_y / 2.0
    return MapViewport(
        output_width=output_width,
        output_height=output_height,
        plot_left=plot_left,
        plot_top=plot_top,
        plot_right=plot_right,
        plot_bottom=plot_bottom,
        world_min_x=min_x,
        world_min_y=min_y,
        world_max_x=max_x,
        world_max_y=max_y,
        pixels_per_metre=plot_width / span_x,
    )


def rasterize_mask(
    mask: np.ndarray,
    spec: GridSpec,
    viewport: MapViewport,
    *,
    interpolation: int = cv2.INTER_LINEAR,
) -> np.ndarray:
    """Place an OccupancyGrid mask into the shared metric canvas."""
    height, width = mask.shape
    upper_left = viewport.project_world(
        spec.origin_x, spec.origin_y + height * spec.resolution
    )
    lower_right = viewport.project_world(
        spec.origin_x + width * spec.resolution, spec.origin_y
    )
    left, top = upper_left
    right, bottom = lower_right
    target_width, target_height = max(1, right - left), max(1, bottom - top)
    resized = cv2.resize(
        np.flipud(mask.astype(np.float32)),
        (target_width, target_height),
        interpolation=interpolation,
    )
    canvas = np.zeros((viewport.output_height, viewport.output_width), dtype=np.float32)
    dst_left, dst_top = max(0, left), max(0, top)
    dst_right, dst_bottom = min(viewport.output_width, right), min(viewport.output_height, bottom)
    if dst_left >= dst_right or dst_top >= dst_bottom:
        return canvas
    src_left, src_top = dst_left - left, dst_top - top
    src_right, src_bottom = src_left + (dst_right - dst_left), src_top + (dst_bottom - dst_top)
    canvas[dst_top:dst_bottom, dst_left:dst_right] = resized[
        src_top:src_bottom, src_left:src_right
    ]
    return np.clip(canvas, 0.0, 1.0)
