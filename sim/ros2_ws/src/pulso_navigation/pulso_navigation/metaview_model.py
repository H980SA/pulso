"""Pure, evidence-backed rendering for Pulso's live top-down MetaView."""

from __future__ import annotations

import math
from typing import Sequence

import cv2
import numpy as np

from .frontier import FrontierCandidate, GridSpec
from .metaview_geometry import (
    MapViewport,
    build_viewport,
    frontier_mask,
    rasterize_mask,
)


# OpenCV colors are BGR. The map intentionally mirrors the visual language in
# rescue thermal / depth products: explored floor is cool, physical structure
# is warm, and decisions use colors that cannot be confused with either.
BACKGROUND = (22, 13, 7)
FREE_SPACE = (214, 72, 8)
UNCERTAIN = (38, 142, 248)
OBSTACLE_GLOW = (28, 118, 255)
OBSTACLE_CORE = (20, 82, 238)
OBSTACLE_EDGE = (55, 218, 255)
FRONTIER_COLOR = (236, 220, 32)
FOV_COLOR = (244, 214, 24)
ROBOT_COLOR = (94, 255, 128)
ROUTE_COLORS = (
    (24, 225, 255),   # A yellow
    (226, 68, 255),   # B magenta
    (255, 220, 38),   # C cyan
    (30, 126, 255),   # D orange
    (92, 255, 118),   # E green
    (255, 128, 132),  # F light blue
)


def _blend(image: np.ndarray, color: tuple[int, int, int], alpha: np.ndarray) -> None:
    clipped = np.clip(alpha, 0.0, 1.0)[..., None]
    image[:] = np.clip(
        image.astype(np.float32) * (1.0 - clipped)
        + np.asarray(color, dtype=np.float32) * clipped,
        0,
        255,
    ).astype(np.uint8)


def _draw_metric_grid(image: np.ndarray, viewport: MapViewport) -> None:
    start_x = math.floor(viewport.world_min_x / 0.5) * 0.5
    start_y = math.floor(viewport.world_min_y / 0.5) * 0.5
    x = start_x
    while x <= viewport.world_max_x + 1e-6:
        px, _ = viewport.project_world(x, 0.0)
        major = abs(x - round(x)) < 1e-6
        cv2.line(
            image,
            (px, viewport.plot_top),
            (px, viewport.plot_bottom),
            (35, 27, 18) if major else (28, 21, 14),
            1,
            cv2.LINE_AA,
        )
        x += 0.5
    y = start_y
    while y <= viewport.world_max_y + 1e-6:
        _, py = viewport.project_world(0.0, y)
        major = abs(y - round(y)) < 1e-6
        cv2.line(
            image,
            (viewport.plot_left, py),
            (viewport.plot_right, py),
            (35, 27, 18) if major else (28, 21, 14),
            1,
            cv2.LINE_AA,
        )
        y += 0.5


def _draw_routes(
    image: np.ndarray,
    viewport: MapViewport,
    candidates: Sequence[FrontierCandidate],
    selected_id: str | None,
) -> None:
    for index, candidate in enumerate(candidates[: len(ROUTE_COLORS)]):
        color = ROUTE_COLORS[index]
        points = np.asarray(
            [viewport.project_world(x, y) for x, y in candidate.path], dtype=np.int32
        )
        selected = candidate.candidate_id == selected_id
        if len(points) >= 2:
            cv2.polylines(image, [points], False, (4, 7, 12), 12 if selected else 9, cv2.LINE_AA)
            cv2.polylines(image, [points], False, color, 7 if selected else 5, cv2.LINE_AA)
        target = viewport.project_world(candidate.x, candidate.y)
        cv2.circle(image, target, 22 if selected else 19, (4, 7, 12), -1, cv2.LINE_AA)
        cv2.circle(image, target, 17 if selected else 15, color, -1, cv2.LINE_AA)
        label = chr(ord("A") + index)
        size = cv2.getTextSize(label, cv2.FONT_HERSHEY_DUPLEX, 0.72, 2)[0]
        cv2.putText(
            image,
            label,
            (target[0] - size[0] // 2, target[1] + size[1] // 2),
            cv2.FONT_HERSHEY_DUPLEX,
            0.72,
            (4, 8, 12),
            2,
            cv2.LINE_AA,
        )
        if selected:
            cv2.circle(image, target, 25, (245, 245, 245), 2, cv2.LINE_AA)


def _draw_robot(
    image: np.ndarray, viewport: MapViewport, robot: tuple[float, float, float]
) -> None:
    center = viewport.project_world(robot[0], robot[1])
    yaw = robot[2]

    def local(radius: float, angle: float) -> tuple[int, int]:
        return (
            int(round(center[0] + math.cos(yaw + angle) * radius)),
            int(round(center[1] - math.sin(yaw + angle) * radius)),
        )

    cv2.line(image, center, local(42, 0.0), (245, 250, 255), 3, cv2.LINE_AA)
    outer = np.asarray((local(22, 0.0), local(15, 2.48), local(15, -2.48)), dtype=np.int32)
    inner = np.asarray((local(17, 0.0), local(11, 2.48), local(11, -2.48)), dtype=np.int32)
    cv2.fillConvexPoly(image, outer, (245, 250, 255), cv2.LINE_AA)
    cv2.fillConvexPoly(image, inner, ROBOT_COLOR, cv2.LINE_AA)
    cv2.circle(image, center, 27, ROBOT_COLOR, 2, cv2.LINE_AA)


def _draw_chrome(
    image: np.ndarray,
    viewport: MapViewport,
    *,
    occupancy: np.ndarray,
    spec: GridSpec,
    map_seq: int,
    navigation_revision: int,
    has_scan_footprint: bool,
) -> None:
    cv2.putText(
        image, "PULSO / METAVIEW", (viewport.plot_left, 37),
        cv2.FONT_HERSHEY_DUPLEX, 0.78, (244, 232, 215), 2, cv2.LINE_AA,
    )
    observed_area = float(np.count_nonzero(occupancy >= 0)) * spec.resolution ** 2
    cv2.putText(
        image,
        f"MAP {map_seq:04d}   NAV {navigation_revision:03d}   OBSERVED {observed_area:.1f} m2",
        (viewport.plot_left + 250, 36),
        cv2.FONT_HERSHEY_SIMPLEX, 0.48, (154, 172, 190), 1, cv2.LINE_AA,
    )
    legend = (
        (FREE_SPACE, "FREE / OBSERVED"),
        (OBSTACLE_EDGE, "OBSTACLE"),
        (FRONTIER_COLOR, "FRONTIER"),
    )
    x = viewport.plot_left
    baseline = viewport.output_height - 22
    for color, label in legend:
        cv2.circle(image, (x + 4, baseline - 4), 4, color, -1, cv2.LINE_AA)
        cv2.putText(
            image, label, (x + 15, baseline), cv2.FONT_HERSHEY_SIMPLEX,
            0.39, (168, 185, 202), 1, cv2.LINE_AA,
        )
        x += 150
    if has_scan_footprint:
        cv2.circle(image, (x + 4, baseline - 4), 4, FOV_COLOR, 1, cv2.LINE_AA)
        cv2.putText(
            image, "LIVE DEPTH FOV", (x + 15, baseline), cv2.FONT_HERSHEY_SIMPLEX,
            0.39, (168, 185, 202), 1, cv2.LINE_AA,
        )
    bar_pixels = max(1, int(round(viewport.pixels_per_metre)))
    bar_y = viewport.plot_bottom - 18
    bar_x = viewport.plot_right - bar_pixels
    cv2.line(image, (bar_x, bar_y), (viewport.plot_right, bar_y), (238, 242, 246), 3, cv2.LINE_AA)
    cv2.line(image, (bar_x, bar_y - 5), (bar_x, bar_y + 5), (238, 242, 246), 2, cv2.LINE_AA)
    cv2.line(image, (viewport.plot_right, bar_y - 5), (viewport.plot_right, bar_y + 5), (238, 242, 246), 2, cv2.LINE_AA)
    cv2.putText(
        image, "1 m", (bar_x, bar_y - 9), cv2.FONT_HERSHEY_SIMPLEX,
        0.4, (220, 228, 235), 1, cv2.LINE_AA,
    )


def render_metaview(
    occupancy: np.ndarray,
    spec: GridSpec,
    robot: tuple[float, float, float],
    candidates: Sequence[FrontierCandidate],
    *,
    map_seq: int,
    navigation_revision: int,
    scan_footprint: Sequence[tuple[float, float]] = (),
    selected_id: str | None = None,
    output_width: int = 800,
    output_height: int = 800,
) -> tuple[np.ndarray, MapViewport]:
    """Render a legible top-down decision view from live navigation evidence."""
    viewport = build_viewport(
        occupancy,
        spec,
        robot=robot,
        candidates=candidates,
        scan_footprint=scan_footprint,
        output_width=output_width,
        output_height=output_height,
    )
    image = np.full((output_height, output_width, 3), BACKGROUND, dtype=np.uint8)
    _draw_metric_grid(image, viewport)

    free = rasterize_mask((occupancy >= 0) & (occupancy <= 20), spec, viewport)
    uncertain = rasterize_mask((occupancy > 20) & (occupancy < 65), spec, viewport)
    occupied = rasterize_mask(occupancy >= 65, spec, viewport)
    _blend(image, FREE_SPACE, free * 0.94)
    _blend(image, UNCERTAIN, uncertain * 0.88)
    glow = cv2.GaussianBlur(occupied, (0, 0), sigmaX=8.0, sigmaY=8.0)
    _blend(image, OBSTACLE_GLOW, glow * 0.72)
    _blend(image, OBSTACLE_CORE, occupied * 0.98)
    obstacle_binary = (occupied > 0.38).astype(np.uint8)
    contours, _ = cv2.findContours(obstacle_binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(image, contours, -1, OBSTACLE_EDGE, 2, cv2.LINE_AA)

    frontier = rasterize_mask(
        frontier_mask(occupancy), spec, viewport, interpolation=cv2.INTER_NEAREST
    )
    frontier_contours, _ = cv2.findContours(
        (frontier > 0.5).astype(np.uint8), cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE
    )
    cv2.drawContours(image, frontier_contours, -1, FRONTIER_COLOR, 2, cv2.LINE_AA)

    if len(scan_footprint) >= 3:
        polygon = np.asarray(
            [viewport.project_world(x, y) for x, y in scan_footprint], dtype=np.int32
        )
        overlay = image.copy()
        cv2.fillPoly(overlay, [polygon], FOV_COLOR, cv2.LINE_AA)
        image[:] = cv2.addWeighted(overlay, 0.13, image, 0.87, 0.0)
        cv2.polylines(image, [polygon], True, FOV_COLOR, 2, cv2.LINE_AA)

    _draw_routes(image, viewport, candidates, selected_id)
    _draw_robot(image, viewport, robot)
    _draw_chrome(
        image,
        viewport,
        occupancy=occupancy,
        spec=spec,
        map_seq=map_seq,
        navigation_revision=navigation_revision,
        has_scan_footprint=len(scan_footprint) >= 3,
    )
    return image, viewport
