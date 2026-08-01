"""RViz-facing navigation evidence derived from the live candidate contract."""

from __future__ import annotations

import math
from typing import Any, Iterable, Sequence

from geometry_msgs.msg import Point, PoseStamped
from nav_msgs.msg import Path
from visualization_msgs.msg import Marker, MarkerArray

from .frontier import FrontierCandidate


_PALETTE = (
    (1.00, 0.82, 0.00),  # yellow
    (0.08, 0.95, 1.00),  # cyan
    (1.00, 0.22, 0.72),  # magenta
    (1.00, 0.48, 0.08),  # orange
    (0.32, 1.00, 0.34),  # green
    (0.62, 0.42, 1.00),  # violet
)


def _set_color(marker: Marker, color: tuple[float, float, float], alpha: float) -> None:
    marker.color.r, marker.color.g, marker.color.b = color
    marker.color.a = alpha


def _marker(
    namespace: str,
    marker_id: int,
    marker_type: int,
    stamp: Any,
) -> Marker:
    result = Marker()
    result.header.frame_id = "map"
    result.header.stamp = stamp
    result.ns = namespace
    result.id = marker_id
    result.type = marker_type
    result.action = Marker.ADD
    result.pose.orientation.w = 1.0
    return result


def candidate_marker_array(
    candidates: Sequence[FrontierCandidate],
    *,
    selected_id: str | None,
    stamp: Any,
) -> MarkerArray:
    """Render all current choices with stable labels and high-contrast colors."""
    clear = _marker("candidate_cleanup", 0, Marker.CUBE, stamp)
    clear.action = Marker.DELETEALL
    markers = [clear]
    for index, candidate in enumerate(candidates):
        color = _PALETTE[index % len(_PALETTE)]
        selected = candidate.candidate_id == selected_id

        route = _marker("candidate_routes", index, Marker.LINE_STRIP, stamp)
        route.scale.x = 0.10 if selected else 0.045
        route.points = [Point(x=x, y=y, z=0.07) for x, y in candidate.path]
        _set_color(route, color, 1.0 if selected else 0.78)
        markers.append(route)

        goal = _marker("candidate_goals", index, Marker.SPHERE, stamp)
        goal.pose.position.x = candidate.x
        goal.pose.position.y = candidate.y
        goal.pose.position.z = 0.12
        diameter = 0.27 if selected else 0.17
        goal.scale.x = goal.scale.y = goal.scale.z = diameter
        _set_color(goal, color, 1.0)
        markers.append(goal)

        label = _marker("candidate_labels", index, Marker.TEXT_VIEW_FACING, stamp)
        label.pose.position.x = candidate.x
        label.pose.position.y = candidate.y
        label.pose.position.z = 0.40
        label.scale.z = 0.18 if selected else 0.14
        letter = chr(ord("A") + index) if index < 26 else str(index + 1)
        label.text = f"{letter} {candidate.kind}"
        if selected:
            label.text = f"{letter} SELECTED"
        _set_color(label, color, 1.0)
        markers.append(label)
    return MarkerArray(markers=markers)


def candidate_path(candidate: FrontierCandidate, stamp: Any) -> Path:
    """Convert the exact candidate route used by navigation into a ROS Path."""
    points = candidate.path or ((candidate.x, candidate.y),)
    result = Path()
    result.header.frame_id = "map"
    result.header.stamp = stamp
    for x, y in points:
        pose = PoseStamped()
        pose.header = result.header
        pose.pose.position.x = x
        pose.pose.position.y = y
        pose.pose.orientation.w = 1.0
        result.poses.append(pose)
    return result


def trajectory_path(
    poses: Iterable[tuple[float, float, float, Any]], stamp: Any
) -> Path:
    """Build a bounded executed trajectory while preserving sample timestamps."""
    result = Path()
    result.header.frame_id = "map"
    result.header.stamp = stamp
    for x, y, yaw, captured_stamp in poses:
        pose = PoseStamped()
        pose.header.frame_id = "map"
        pose.header.stamp = captured_stamp
        pose.pose.position.x = x
        pose.pose.position.y = y
        pose.pose.orientation.z = math.sin(yaw / 2.0)
        pose.pose.orientation.w = math.cos(yaw / 2.0)
        result.poses.append(pose)
    return result


class NavigationVisualization:
    """Own the visualization topics without changing navigation decisions."""

    def __init__(self, node: Any, *, trajectory_limit: int = 1200) -> None:
        self._candidate_pub = node.create_publisher(
            MarkerArray, "/pulso/navigation/candidate_markers", 2
        )
        self._selected_path_pub = node.create_publisher(
            Path, "/pulso/navigation/selected_path", 2
        )
        self._trajectory_pub = node.create_publisher(
            Path, "/pulso/navigation/executed_trajectory", 2
        )
        self._trajectory_limit = trajectory_limit
        self._latest_candidates: tuple[FrontierCandidate, ...] = ()
        self._selected_id: str | None = None
        self._selected_path: Path | None = None
        self._active_action_id: str | None = None
        self._trajectory: list[tuple[float, float, float, Any]] = []

    @property
    def selected_id(self) -> str | None:
        return self._selected_id

    def publish_candidates(
        self, candidates: Sequence[FrontierCandidate], stamp: Any
    ) -> None:
        self._latest_candidates = tuple(candidates)
        self._candidate_pub.publish(
            candidate_marker_array(
                self._latest_candidates, selected_id=self._selected_id, stamp=stamp
            )
        )
        if self._selected_path is not None:
            self._selected_path.header.stamp = stamp
            self._selected_path_pub.publish(self._selected_path)
        self._trajectory_pub.publish(trajectory_path(self._trajectory, stamp))

    def select(
        self,
        action_id: str,
        candidate: FrontierCandidate,
        robot_pose: tuple[float, float, float] | None,
        stamp: Any,
    ) -> None:
        self._active_action_id = action_id
        self._selected_id = candidate.candidate_id
        self._selected_path = candidate_path(candidate, stamp)
        self._trajectory.clear()
        if robot_pose is not None:
            self._append_pose(robot_pose, stamp, force=True)
        self._candidate_pub.publish(
            candidate_marker_array(
                self._latest_candidates, selected_id=self._selected_id, stamp=stamp
            )
        )
        self._selected_path_pub.publish(self._selected_path)
        self._trajectory_pub.publish(trajectory_path(self._trajectory, stamp))

    def record_pose(
        self, robot_pose: tuple[float, float, float], stamp: Any
    ) -> None:
        if self._active_action_id is None:
            return
        if self._append_pose(robot_pose, stamp):
            self._trajectory_pub.publish(trajectory_path(self._trajectory, stamp))

    def is_tracking(self, action_id: str) -> bool:
        return action_id == self._active_action_id

    def finish(
        self,
        action_id: str,
        robot_pose: tuple[float, float, float] | None,
        stamp: Any,
    ) -> None:
        if action_id != self._active_action_id:
            return
        if robot_pose is not None:
            self._append_pose(robot_pose, stamp, force=True)
        self._active_action_id = None
        self._trajectory_pub.publish(trajectory_path(self._trajectory, stamp))

    def _append_pose(
        self,
        robot_pose: tuple[float, float, float],
        stamp: Any,
        *,
        force: bool = False,
    ) -> bool:
        x, y, yaw = robot_pose
        if self._trajectory and not force:
            previous_x, previous_y, previous_yaw, _ = self._trajectory[-1]
            moved = math.hypot(x - previous_x, y - previous_y) >= 0.015
            turned = abs(
                math.atan2(
                    math.sin(yaw - previous_yaw), math.cos(yaw - previous_yaw)
                )
            ) >= math.radians(2.0)
            if not moved and not turned:
                return False
        self._trajectory.append((x, y, yaw, stamp))
        if len(self._trajectory) > self._trajectory_limit:
            del self._trajectory[: len(self._trajectory) - self._trajectory_limit]
        return True
