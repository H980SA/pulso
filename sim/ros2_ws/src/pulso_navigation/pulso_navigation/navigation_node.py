"""Discover frontiers, render MetaView, and execute typed navigation intents."""

from __future__ import annotations

import json
import math
from typing import Any

from cv_bridge import CvBridge
from diagnostic_msgs.msg import DiagnosticArray
from geometry_msgs.msg import Twist
from nav_msgs.msg import OccupancyGrid
import numpy as np
import rclpy
from rclpy.duration import Duration
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from rclpy.time import Time
from sensor_msgs.msg import CameraInfo, CompressedImage, Image, LaserScan, PointCloud2
from sensor_msgs_py import point_cloud2
from std_msgs.msg import Bool, String
from tf2_ros import Buffer, TransformException, TransformListener

from .bootstrap import bootstrap_viewpoints
from .action_contract import ActionContractError, ActionReplayGuard, parse_action
from .candidate_contract import candidate_contract
from .candidate_capability import (
    CandidateCapabilitySet,
    CapabilitySnapshot,
    validate_candidate_grant,
)
from .candidate_cooldown import CandidateCooldowns
from .frontier import FrontierCandidate, GridSpec, extract_frontiers
from .metaview import publish_metaview
from .metaview_geometry import horizontal_fov_from_intrinsics, scan_footprint_world
from .metaview_scene import build_metaview_scene, transform_xyz
from .motion_controller import MotionController
from .perception_tracks import PerceptionTrack, build_target_candidates, parse_tracks
from .rviz_visualization import NavigationVisualization
from .tracking_epoch import TrackingEpoch


class NavigationNode(Node):
    def __init__(self) -> None:
        super().__init__("pulso_navigation")
        self.declare_parameter("candidate_period_s", 0.5)
        self.declare_parameter("max_candidates", 6)
        self.declare_parameter("linear_speed_mps", 0.12)
        self.declare_parameter("move_goal_tolerance_m", 0.10)
        self.declare_parameter("minimum_move_displacement_m", 0.05)
        # The first cropped SLAM boundary is typically 19--20 cm away. 18 cm
        # breaks that exploration bootstrap deadlock while the controller's
        # independent 10 cm arrival envelope still requires >=5 cm measured
        # translation before success.
        self.declare_parameter("minimum_frontier_travel_m", 0.18)
        # Phone depth is rolling / asynchronous; a slower survey turn keeps
        # SLAM from treating a bootstrap sweep as a distorted scan.
        self.declare_parameter("angular_speed_rps", 0.38)
        self._move_goal_tolerance_m = float(
            self.get_parameter("move_goal_tolerance_m").value
        )
        self._minimum_move_displacement_m = float(
            self.get_parameter("minimum_move_displacement_m").value
        )
        configured_frontier_travel_m = float(
            self.get_parameter("minimum_frontier_travel_m").value
        )
        if (
            not math.isfinite(configured_frontier_travel_m)
            or configured_frontier_travel_m < 0.0
        ):
            raise ValueError(
                "minimum_frontier_travel_m must be finite and non-negative"
            )
        self._minimum_frontier_travel_m = max(
            configured_frontier_travel_m,
            self._move_goal_tolerance_m + self._minimum_move_displacement_m,
        )
        self._bridge = CvBridge()
        self._tf_buffer = Buffer(cache_time=Duration(seconds=10.0))
        self._tf_listener = TransformListener(self._tf_buffer, self)
        self._map: OccupancyGrid | None = None
        self._map_array: np.ndarray | None = None
        self._map_seq = 0
        self._navigation_revision = 0
        self._candidates: dict[str, FrontierCandidate] = {}
        self._capability_state = CapabilitySnapshot(0, 0, {})
        self._capabilities = CandidateCapabilitySet()
        self._candidate_cooldowns = CandidateCooldowns()
        self._tracking_epoch = TrackingEpoch()
        self._pending_flashlight: tuple[str, bool, int] | None = None
        self._perception_tracks: dict[str, PerceptionTrack] = {}
        self._latest_scan: LaserScan | None = None
        self._latest_scan_received_ns = 0
        self._latest_depth_points = np.empty((0, 3), dtype=np.float32)
        self._latest_depth_frame = ""
        self._latest_depth_received_ns = 0
        self._camera_horizontal_fov_rad: float | None = None
        self._bootstrap_step = 0
        self._replay_guard = ActionReplayGuard()

        self._candidate_pub = self.create_publisher(
            String, "/pulso/navigation/candidates", 10
        )
        self._metaview_pub = self.create_publisher(
            Image, "/pulso/navigation/metaview", 2
        )
        self._metaview_compressed_pub = self.create_publisher(
            CompressedImage, "/pulso/navigation/metaview/compressed", 2
        )
        self._metaview_scene_pub = self.create_publisher(
            String, "/pulso/navigation/metaview_scene", 2
        )
        self._desired_pub = self.create_publisher(
            Twist, "/pulso/base/cmd_vel_desired", 10
        )
        self._flashlight_pub = self.create_publisher(
            Bool, "/pulso/phone/flashlight/cmd", 10
        )
        self._result_pub = self.create_publisher(
            String, "/pulso/hil/action_result", 10
        )
        self._visualization = NavigationVisualization(self)
        self._motion = MotionController(
            self,
            self._tf_buffer,
            self._desired_pub,
            self._robot_pose,
            self._publish_result,
            self._advance_bootstrap,
            move_goal_tolerance_m=self._move_goal_tolerance_m,
            minimum_move_displacement_m=self._minimum_move_displacement_m,
        )
        self.create_subscription(OccupancyGrid, "/map", self._on_map, 10)
        self.create_subscription(
            LaserScan,
            "/pulso/navigation/scan",
            self._on_scan,
            qos_profile_sensor_data,
        )
        self.create_subscription(
            CameraInfo,
            "/pulso/phone/rgb/camera_info",
            self._on_camera_info,
            qos_profile_sensor_data,
        )
        self.create_subscription(
            PointCloud2,
            "/pulso/phone/depth/points",
            self._on_depth_points,
            qos_profile_sensor_data,
        )
        self.create_subscription(
            String, "/pulso/hil/action_intent", self._on_action, 10
        )
        self.create_subscription(
            Bool, "/pulso/phone/flashlight/state", self._on_flashlight_state, 10
        )
        self.create_subscription(
            String, "/pulso/hil/perception_tracks", self._on_perception_tracks, 10
        )
        self.create_subscription(
            DiagnosticArray, "/pulso/phone/vio/status", self._on_tracking, 10
        )
        self.create_subscription(
            DiagnosticArray,
            "/pulso/base/safety/status",
            self._on_safety_status,
            10,
        )
        self.create_timer(
            float(self.get_parameter("candidate_period_s").value), self._refresh_candidates
        )
        self.create_timer(0.1, self._motion.tick)
        self.create_timer(0.1, self._control_flashlight_timeout)

    def _on_map(self, message: OccupancyGrid) -> None:
        expected = int(message.info.width * message.info.height)
        if expected <= 0 or len(message.data) != expected:
            return
        self._map = message
        self._map_array = np.asarray(message.data, dtype=np.int16).reshape(
            (message.info.height, message.info.width)
        )
        self._map_seq += 1

    def _on_scan(self, message: LaserScan) -> None:
        self._latest_scan = message
        self._latest_scan_received_ns = self.get_clock().now().nanoseconds

    def _on_camera_info(self, message: CameraInfo) -> None:
        horizontal_fov = horizontal_fov_from_intrinsics(message.width, message.k)
        if horizontal_fov is not None:
            self._camera_horizontal_fov_rad = horizontal_fov

    def _on_depth_points(self, message: PointCloud2) -> None:
        """Keep a bounded sample; tf2 projection happens with the scene tick."""

        try:
            if hasattr(point_cloud2, "read_points_numpy"):
                points = point_cloud2.read_points_numpy(
                    message, field_names=("x", "y", "z"), skip_nans=True
                )
                array = np.asarray(points, dtype=np.float32).reshape((-1, 3))
            else:
                points = point_cloud2.read_points(
                    message, field_names=("x", "y", "z"), skip_nans=True
                )
                array = np.asarray(list(points), dtype=np.float32).reshape((-1, 3))
        except (TypeError, ValueError, AttributeError):
            return
        if len(array) > 2_400:
            indices = np.linspace(0, len(array) - 1, 2_400, dtype=int)
            array = array[indices]
        self._latest_depth_points = array
        self._latest_depth_frame = message.header.frame_id
        self._latest_depth_received_ns = self.get_clock().now().nanoseconds

    def _robot_pose(self, frame_id: str = "map") -> tuple[float, float, float] | None:
        try:
            transform = self._tf_buffer.lookup_transform(
                frame_id, "base_footprint", Time(), timeout=Duration(seconds=0.08)
            ).transform
        except TransformException:
            return None
        q = transform.rotation
        yaw = math.atan2(2.0 * (q.w * q.z + q.x * q.y), 1.0 - 2.0 * (q.y * q.y + q.z * q.z))
        return transform.translation.x, transform.translation.y, yaw

    def _refresh_candidates(self) -> None:
        occupancy, message, robot = self._map_array, self._map, self._robot_pose()
        if robot is None:
            return
        if occupancy is None or message is None:
            # SLAM needs a changed heading before its first usable map. These
            # are rotation-only evidence viewpoints, not invented free space.
            spec = GridSpec(0.05, robot[0] - 2.0, robot[1] - 2.0)
            occupancy = np.full((80, 80), -1, dtype=np.int16)
            candidates = bootstrap_viewpoints(robot, self._bootstrap_step)
        else:
            spec = GridSpec(
                resolution=float(message.info.resolution),
                origin_x=float(message.info.origin.position.x),
                origin_y=float(message.info.origin.position.y),
            )
            candidates = extract_frontiers(
                occupancy,
                spec,
                (robot[0], robot[1]),
                max_candidates=int(self.get_parameter("max_candidates").value),
                outside_is_unknown=True,
                minimum_travel_distance_m=self._minimum_frontier_travel_m,
            )
            if not candidates:
                candidates = bootstrap_viewpoints(robot, self._bootstrap_step)
        now = self.get_clock().now()
        now_ns = now.nanoseconds
        stamp = now.to_msg()
        scan_footprint = self._current_scan_footprint(robot, now_ns)
        candidates = self._target_candidates(robot, now_ns) + candidates
        candidates = self._candidate_cooldowns.available(candidates, now_ns)
        if not candidates:
            candidates = bootstrap_viewpoints(robot, self._bootstrap_step)
        self._capability_state = self._capabilities.refresh(candidates, now_ns)
        self._navigation_revision = self._capability_state.navigation_revision
        self._candidates = {item.candidate_id: item for item in candidates}
        payload = candidate_contract(
            candidates,
            captured_ns=now_ns,
            sensor_map_seq=self._map_seq,
            navigation_revision=self._navigation_revision,
            valid_until_ns=self._capability_state.valid_until_ns,
            capabilities=self._capability_state.capabilities,
        )
        self._candidate_pub.publish(String(data=json.dumps(payload, separators=(",", ":"))))
        self._visualization.record_pose(robot, stamp)
        self._visualization.publish_candidates(candidates, stamp)
        publish_metaview(
            occupancy,
            spec,
            robot,
            candidates,
            map_seq=self._map_seq,
            navigation_revision=self._navigation_revision,
            scan_footprint=scan_footprint,
            selected_id=self._visualization.selected_id,
            bridge=self._bridge,
            raw_publisher=self._metaview_pub,
            compressed_publisher=self._metaview_compressed_pub,
            stamp=stamp,
        )
        scene = build_metaview_scene(
            occupancy,
            spec,
            robot,
            candidates,
            captured_ns=now_ns,
            map_seq=self._map_seq,
            navigation_revision=self._navigation_revision,
            scan_footprint=scan_footprint,
            selected_id=self._visualization.selected_id,
            depth_points_map=self._current_depth_points(now_ns),
        )
        self._metaview_scene_pub.publish(
            String(data=json.dumps(scene, separators=(",", ":")))
        )

    def _current_scan_footprint(
        self, robot: tuple[float, float, float], now_ns: int
    ) -> tuple[tuple[float, float], ...]:
        scan = self._latest_scan
        horizontal_fov = self._camera_horizontal_fov_rad
        age_ns = now_ns - self._latest_scan_received_ns
        if scan is None or horizontal_fov is None or age_ns < 0 or age_ns > 1_000_000_000:
            return ()
        return scan_footprint_world(
            robot=robot,
            ranges=scan.ranges,
            angle_min=float(scan.angle_min),
            angle_increment=float(scan.angle_increment),
            range_min=float(scan.range_min),
            range_max=float(scan.range_max),
            horizontal_fov_rad=horizontal_fov,
        )

    def _current_depth_points(self, now_ns: int) -> np.ndarray:
        age_ns = now_ns - self._latest_depth_received_ns
        if (
            self._latest_depth_points.size == 0
            or not self._latest_depth_frame
            or age_ns < 0
            or age_ns > 1_000_000_000
        ):
            return np.empty((0, 3), dtype=np.float32)
        try:
            transform = self._tf_buffer.lookup_transform(
                "map",
                self._latest_depth_frame,
                Time(),
                timeout=Duration(seconds=0.04),
            ).transform
        except TransformException:
            return np.empty((0, 3), dtype=np.float32)
        return transform_xyz(
            self._latest_depth_points, transform.translation, transform.rotation
        )

    def _on_perception_tracks(self, message: String) -> None:
        now_ns = self.get_clock().now().nanoseconds
        tracks = parse_tracks(message.data, now_ns)
        if tracks is not None:
            self._perception_tracks = tracks

    def _on_tracking(self, message: DiagnosticArray) -> None:
        if self._tracking_epoch.update(message):
            self._capabilities.invalidate()

    def _on_safety_status(self, message: DiagnosticArray) -> None:
        for status in message.status:
            if status.name != "pulso_motion_safety":
                continue
            reason = next(
                (item.value for item in status.values if item.key == "reason"),
                "",
            )
            self._motion.observe_safety_reason(reason)
            return

    def _target_candidates(
        self, robot: tuple[float, float, float], now_ns: int
    ) -> list[FrontierCandidate]:
        candidates, live_tracks = build_target_candidates(
            self._perception_tracks, robot, now_ns
        )
        self._perception_tracks = live_tracks
        return candidates

    def _on_action(self, message: String) -> None:
        try:
            intent = parse_action(message.data)
        except ActionContractError as failure:
            self._publish_result("invalid", False, failure.status, failure.detail)
            return
        action_id = intent.action_id
        kind = intent.kind
        now_ns = self.get_clock().now().nanoseconds
        if not self._replay_guard.accept(action_id, now_ns):
            self._publish_result(action_id, False, "DUPLICATE_ACTION", "Action ID was already processed.")
            return
        if kind == "STOP":
            cancelled_id = self._motion.stop()
            if cancelled_id is not None:
                self._publish_result(
                    cancelled_id, False, "CANCELLED", "Motion cancelled by STOP."
                )
            self._publish_result(action_id, True, "SUCCEEDED", "Rover stopped.")
            return
        if kind == "SET_FLASHLIGHT":
            enabled = intent.parameters.get("enabled")
            if not isinstance(enabled, bool):
                self._publish_result(
                    action_id, False, "INVALID_PARAMETERS", "enabled must be a boolean."
                )
                return
            self._pending_flashlight = (action_id, enabled, self.get_clock().now().nanoseconds)
            self._flashlight_pub.publish(Bool(data=enabled))
            return
        target_id = intent.target_id or ""
        candidate = self._candidates.get(target_id)
        if kind in {"MOVE_TO", "LOOK_AT", "REQUEST_VIEW"} and candidate is None:
            self._publish_result(
                action_id, False, "STALE_OR_UNKNOWN_TARGET", f"{target_id} is not a current candidate."
            )
            return
        if candidate is not None and candidate.kind != intent.target_type:
            self._publish_result(
                action_id,
                False,
                "TARGET_TYPE_MISMATCH",
                f"{target_id} is {candidate.kind}, not {intent.target_type}.",
            )
            return
        if candidate is not None:
            grant_error = validate_candidate_grant(
                intent,
                candidate,
                self._capability_state,
                self._tracking_epoch.value,
                now_ns,
            )
            if grant_error is not None:
                self._publish_result(action_id, False, grant_error[0], grant_error[1])
                return
        if kind == "REQUEST_VIEW" and candidate is not None:
            view_kind = str(intent.parameters.get("view_kind") or "CANDIDATE_VIEW")
            if view_kind not in {"META_VIEW", "CANDIDATE_VIEW", "TARGET_VIEW"}:
                self._publish_result(
                    action_id, False, "INVALID_PARAMETERS", "Unknown view_kind."
                )
                return
            artifact_topic = (
                "/pulso/phone/rgb/compressed"
                if view_kind in {"TARGET_VIEW", "CANDIDATE_VIEW"}
                else "/pulso/navigation/metaview/compressed"
            )
            self._publish_result(
                action_id,
                True,
                "SUCCEEDED",
                f"{view_kind} requested; the client must attach the next camera capture.",
                {
                    "artifact_topic": artifact_topic,
                    "view_kind": view_kind,
                    "navigation_revision": self._navigation_revision,
                    "target_id": target_id,
                    "request_after_monotonic_ns": now_ns,
                },
            )
            return
        if kind in {"MOVE_TO", "LOOK_AT"} and candidate is not None:
            if kind == "MOVE_TO" and candidate.rotation_only:
                self._publish_result(
                    action_id,
                    False,
                    "ROTATION_ONLY_VIEWPOINT",
                    "This bootstrap viewpoint may only be inspected with LOOK_AT.",
                )
                return
            motion_error = self._motion.start(action_id, kind, candidate)
            if motion_error is not None:
                self._publish_result(action_id, False, motion_error[0], motion_error[1])
                return
            self._visualization.select(
                action_id,
                candidate,
                self._robot_pose(),
                self.get_clock().now().to_msg(),
            )
            self._publish_result(
                action_id,
                True,
                "ACTIVE",
                f"{kind} accepted for {target_id}; local controller and safety gate own motion.",
                {"target_id": target_id, "navigation_revision": self._navigation_revision},
            )
            return
        self._publish_result(action_id, False, "UNSUPPORTED_ACTION", f"{kind} is not owned by navigation.")

    def _on_flashlight_state(self, message: Bool) -> None:
        pending = self._pending_flashlight
        if pending is None or message.data != pending[1]:
            return
        self._pending_flashlight = None
        self._publish_result(
            pending[0], True, "SUCCEEDED", f"Flashlight confirmed {'on' if message.data else 'off'}.",
            {"enabled": message.data},
        )

    def _advance_bootstrap(self) -> None:
        self._bootstrap_step += 1

    def _control_flashlight_timeout(self) -> None:
        pending = self._pending_flashlight
        if pending and self.get_clock().now().nanoseconds - pending[2] > 2_000_000_000:
            self._pending_flashlight = None
            self._publish_result(pending[0], False, "ACTUATOR_TIMEOUT", "Flashlight state was not confirmed.")

    def _publish_result(
        self,
        action_id: str,
        accepted: bool,
        status: str,
        detail: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        now = self.get_clock().now()
        result_data = data or {}
        if status == "BLOCKED":
            blocked_id = str(result_data.get("candidate_id") or "")
            self._candidate_cooldowns.mark(blocked_id, now.nanoseconds)
            self._candidates.pop(blocked_id, None)
            self._capabilities.invalidate()
        if status != "ACTIVE" and self._visualization.is_tracking(action_id):
            self._visualization.finish(action_id, self._robot_pose(), now.to_msg())
        payload = {
            "contract_version": "pulso.action-result.v1",
            "action_id": action_id,
            "accepted": accepted,
            "status": status,
            "detail": detail,
            "captured_monotonic_ns": now.nanoseconds,
            "data": result_data,
        }
        self._result_pub.publish(String(data=json.dumps(payload, separators=(",", ":"))))


def main(args=None) -> None:
    rclpy.init(args=args)
    node = NavigationNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if rclpy.ok():
            try:
                node._motion.stop()
            except RuntimeError:
                # ROS launch can invalidate the shared context before this
                # process receives its shutdown callback. The safety gate has
                # its own command watchdog, so shutdown still fails stopped.
                pass
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
