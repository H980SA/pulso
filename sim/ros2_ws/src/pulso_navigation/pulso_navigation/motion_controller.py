"""Local odometry-frame motion controller beneath the cognitive action layer."""

from dataclasses import dataclass, replace
import math
from typing import Callable

from geometry_msgs.msg import Twist
import numpy as np
from rclpy.duration import Duration
from rclpy.time import Time
from tf2_ros import TransformException

from .frontier import FrontierCandidate


_NEAR_FIELD_BLOCK_REASON = "NEAR_FIELD_OBSTACLE"
_SUSTAINED_BLOCK_NS = 1_500_000_000


@dataclass
class ActiveMotion:
    action_id: str
    kind: str
    candidate: FrontierCandidate
    started_ns: int
    start_x: float | None = None
    start_y: float | None = None
    frame_id: str = "odom"


class MotionController:
    def __init__(
        self,
        node,
        tf_buffer,
        desired_publisher,
        pose_provider: Callable[[str], tuple[float, float, float] | None],
        result_publisher: Callable,
        bootstrap_completed: Callable[[], None],
        *,
        move_goal_tolerance_m: float = 0.10,
        minimum_move_displacement_m: float = 0.05,
    ) -> None:
        if not math.isfinite(move_goal_tolerance_m) or move_goal_tolerance_m <= 0.0:
            raise ValueError("move_goal_tolerance_m must be finite and positive")
        if (
            not math.isfinite(minimum_move_displacement_m)
            or minimum_move_displacement_m < 0.0
        ):
            raise ValueError("minimum_move_displacement_m must be finite and non-negative")
        self._node = node
        self._tf_buffer = tf_buffer
        self._desired_pub = desired_publisher
        self._pose_provider = pose_provider
        self._publish_result = result_publisher
        self._bootstrap_completed = bootstrap_completed
        self._move_goal_tolerance_m = move_goal_tolerance_m
        self._minimum_move_displacement_m = minimum_move_displacement_m
        self._active: ActiveMotion | None = None
        self._blocked_since_ns: int | None = None

    @property
    def active(self) -> ActiveMotion | None:
        return self._active

    def start(
        self, action_id: str, kind: str, candidate: FrontierCandidate
    ) -> tuple[str, str] | None:
        if self._active is not None:
            return "BUSY", "Another motion is active; STOP it first."
        local_candidate = self._candidate_in_odom(candidate)
        if local_candidate is None:
            return (
                "LOCALIZATION_UNAVAILABLE",
                "Could not snapshot the map candidate into the local odometry frame.",
            )
        start_x = None
        start_y = None
        if kind == "MOVE_TO":
            pose = self._pose_provider("odom")
            if pose is None:
                return (
                    "LOCALIZATION_UNAVAILABLE",
                    "Could not measure the rover pose in the local odometry frame.",
                )
            start_x, start_y, _ = pose
            minimum_travel_m = (
                self._move_goal_tolerance_m + self._minimum_move_displacement_m
            )
            direct_distance_m = math.hypot(
                local_candidate.x - start_x, local_candidate.y - start_y
            )
            if (
                local_candidate.path_length_m + 1e-9 < minimum_travel_m
                or direct_distance_m + 1e-9 < minimum_travel_m
            ):
                return (
                    "TARGET_TOO_CLOSE",
                    (
                        f"MOVE_TO requires at least {minimum_travel_m:.3f} m of "
                        "initial path and separation so arrival can include meaningful "
                        f"motion; path={local_candidate.path_length_m:.3f} m, "
                        f"separation={direct_distance_m:.3f} m. Refresh candidates."
                    ),
                )
        self._active = ActiveMotion(
            action_id,
            kind,
            local_candidate,
            self._node.get_clock().now().nanoseconds,
            start_x,
            start_y,
        )
        self._blocked_since_ns = None
        return None

    def stop(self) -> str | None:
        cancelled = self._active.action_id if self._active is not None else None
        self._active = None
        self._blocked_since_ns = None
        self._desired_pub.publish(Twist())
        return cancelled

    def observe_safety_reason(self, reason: str) -> None:
        """Track a sustained near-field veto without weakening the safety gate."""
        active = self._active
        if (
            active is None
            or active.kind != "MOVE_TO"
            or reason != _NEAR_FIELD_BLOCK_REASON
        ):
            self._blocked_since_ns = None
            return
        if self._blocked_since_ns is None:
            self._blocked_since_ns = self._node.get_clock().now().nanoseconds

    def tick(self) -> None:
        active = self._active
        if active is None:
            return
        now_ns = self._node.get_clock().now().nanoseconds
        if (
            self._blocked_since_ns is not None
            and now_ns - self._blocked_since_ns >= _SUSTAINED_BLOCK_NS
        ):
            candidate_id = active.candidate.candidate_id
            self.stop()
            self._publish_result(
                active.action_id,
                False,
                "BLOCKED",
                "Near-field safety held forward motion for 1.5 seconds.",
                {
                    "candidate_id": candidate_id,
                    "reason": _NEAR_FIELD_BLOCK_REASON,
                },
            )
            return
        timeout_ns = 18_000_000_000 if active.kind == "LOOK_AT" else 60_000_000_000
        if now_ns - active.started_ns > timeout_ns:
            self.stop()
            self._publish_result(active.action_id, False, "TIMEOUT", "Motion deadline expired.")
            return
        pose = self._pose_provider(active.frame_id)
        if pose is None:
            return
        x, y, yaw = pose
        goal = active.candidate
        goal_distance = math.hypot(goal.x - x, goal.y - y)
        displacement_m = (
            math.hypot(x - active.start_x, y - active.start_y)
            if active.start_x is not None and active.start_y is not None
            else 0.0
        )
        if (
            active.kind == "MOVE_TO"
            and goal_distance <= self._move_goal_tolerance_m
            and displacement_m + 1e-9 >= self._minimum_move_displacement_m
        ):
            self.stop()
            self._publish_result(
                active.action_id,
                True,
                "SUCCEEDED",
                "Frontier viewpoint reached.",
                {
                    "candidate_id": goal.candidate_id,
                    "odometry_displacement_m": round(displacement_m, 4),
                    "remaining_goal_distance_m": round(goal_distance, 4),
                },
            )
            return
        lookahead = self._lookahead(active, x, y)
        desired_heading = math.atan2(lookahead[1] - y, lookahead[0] - x)
        error = math.atan2(math.sin(desired_heading - yaw), math.cos(desired_heading - yaw))
        if active.kind == "LOOK_AT" and abs(error) <= math.radians(5.0):
            self.stop()
            if active.candidate.candidate_id.startswith("VP_INIT_"):
                self._bootstrap_completed()
            self._publish_result(active.action_id, True, "SUCCEEDED", "Candidate centered.")
            return
        command = Twist()
        angular_limit = float(self._node.get_parameter("angular_speed_rps").value)
        command.angular.z = float(np.clip(error * 1.8, -angular_limit, angular_limit))
        if active.kind == "MOVE_TO" and abs(error) < 0.58:
            speed_limit = float(self._node.get_parameter("linear_speed_mps").value)
            heading_scale = max(0.12, 1.0 - abs(error) / 0.58)
            command.linear.x = min(speed_limit, max(0.055, goal_distance * 0.45)) * heading_scale
        self._desired_pub.publish(command)

    def _lookahead(self, active: ActiveMotion, x: float, y: float) -> tuple[float, float]:
        goal = active.candidate
        if active.kind != "MOVE_TO":
            return goal.x, goal.y
        path = goal.path
        nearest = min(
            range(len(path)), key=lambda index: math.hypot(path[index][0] - x, path[index][1] - y)
        )
        for point in path[nearest:]:
            if math.hypot(point[0] - x, point[1] - y) >= 0.28:
                return point
        return path[-1]

    def _candidate_in_odom(self, candidate: FrontierCandidate) -> FrontierCandidate | None:
        try:
            transform = self._tf_buffer.lookup_transform(
                "odom", "map", Time(), timeout=Duration(seconds=0.08)
            ).transform
        except TransformException:
            return None
        q = transform.rotation
        yaw = math.atan2(2.0 * (q.w * q.z + q.x * q.y), 1.0 - 2.0 * (q.y * q.y + q.z * q.z))
        cosine, sine = math.cos(yaw), math.sin(yaw)

        def project(point: tuple[float, float]) -> tuple[float, float]:
            x, y = point
            return (
                transform.translation.x + cosine * x - sine * y,
                transform.translation.y + sine * x + cosine * y,
            )

        x, y = project((candidate.x, candidate.y))
        return replace(candidate, x=x, y=y, path=tuple(project(point) for point in candidate.path))
