"""Aggregate normalized ROS topics into the Android HIL observation contract."""

from __future__ import annotations

import json
import math

from diagnostic_msgs.msg import DiagnosticArray
from nav_msgs.msg import Odometry
import rclpy
from rclpy.duration import Duration
from rclpy.node import Node
from rclpy.time import Time
from sensor_msgs.msg import BatteryState, Range
from std_msgs.msg import Bool, String
from tf2_ros import Buffer, TransformException, TransformListener

from .observation import build_observation


class HilGatewayNode(Node):
    def __init__(self) -> None:
        super().__init__("pulso_hil_gateway")
        self.declare_parameter("publish_rate_hz", 2.0)
        self._tf_buffer = Buffer(cache_time=Duration(seconds=10.0))
        self._tf_listener = TransformListener(self._tf_buffer, self)
        self._sequence = 0
        self._tracking_state = "LOST"
        self._tracking_quality = 0.0
        self._tracking_epoch = 0
        self._previous_tracking_state = "LOST"
        self._linear_speed = 0.0
        self._angular_speed = 0.0
        self._battery = 1.0
        self._flashlight = False
        self._front_range: float | None = None
        self._bumper = False
        self._safety_stopped = True
        self._publisher = self.create_publisher(String, "/pulso/hil/observation", 10)
        self.create_subscription(Odometry, "/pulso/phone/vio/odom", self._on_odom, 20)
        self.create_subscription(
            DiagnosticArray, "/pulso/phone/vio/status", self._on_tracking, 10
        )
        self.create_subscription(BatteryState, "/pulso/base/battery", self._on_battery, 10)
        self.create_subscription(Range, "/pulso/base/sonar/front", self._on_range, 10)
        self.create_subscription(Bool, "/pulso/base/bumper", self._on_bumper, 10)
        self.create_subscription(
            Bool, "/pulso/phone/flashlight/state", self._on_flashlight, 10
        )
        self.create_subscription(
            DiagnosticArray, "/pulso/base/safety/status", self._on_safety, 10
        )
        period = 1.0 / max(0.2, float(self.get_parameter("publish_rate_hz").value))
        self.create_timer(period, self._publish)

    def _on_odom(self, message: Odometry) -> None:
        self._linear_speed = float(message.twist.twist.linear.x)
        self._angular_speed = float(message.twist.twist.angular.z)

    def _on_tracking(self, message: DiagnosticArray) -> None:
        if not message.status:
            return
        status = message.status[0]
        values = {item.key: item.value for item in status.values}
        state = values.get("state", status.message or "LOST").upper()
        if state not in {"TRACKING", "LIMITED", "LOST"}:
            state = "LIMITED"
        if self._previous_tracking_state == "LOST" and state == "TRACKING":
            self._tracking_epoch += 1
        self._previous_tracking_state = state
        self._tracking_state = state
        try:
            self._tracking_quality = float(values.get("quality", "0"))
        except ValueError:
            self._tracking_quality = 0.0

    def _on_battery(self, message: BatteryState) -> None:
        if math.isfinite(message.percentage):
            self._battery = float(message.percentage)

    def _on_range(self, message: Range) -> None:
        self._front_range = float(message.range) if math.isfinite(message.range) else None

    def _on_bumper(self, message: Bool) -> None:
        self._bumper = bool(message.data)

    def _on_flashlight(self, message: Bool) -> None:
        self._flashlight = bool(message.data)

    def _on_safety(self, message: DiagnosticArray) -> None:
        if message.status:
            self._safety_stopped = message.status[0].message.upper() == "STOPPED"

    def _map_pose(self) -> tuple[float, float, float] | None:
        try:
            transform = self._tf_buffer.lookup_transform(
                "map", "base_footprint", Time(), timeout=Duration(seconds=0.08)
            ).transform
        except TransformException:
            return None
        q = transform.rotation
        yaw = math.atan2(2.0 * (q.w * q.z + q.x * q.y), 1.0 - 2.0 * (q.y * q.y + q.z * q.z))
        return transform.translation.x, transform.translation.y, yaw

    def _publish(self) -> None:
        pose = self._map_pose()
        if pose is None:
            return
        moving = abs(self._linear_speed) > 0.01 or abs(self._angular_speed) > 0.03
        if self._bumper:
            motion_state = "BLOCKED"
        elif moving and not self._safety_stopped:
            motion_state = "MOVING"
        else:
            motion_state = "STOPPED"
        self._sequence += 1
        now_ns = self.get_clock().now().nanoseconds
        payload = build_observation(
            sequence=self._sequence,
            captured_ns=now_ns,
            pose=(pose[0], pose[1], 0.0),
            heading_deg=math.degrees(pose[2]),
            pose_confidence=self._tracking_quality,
            tracking_state=self._tracking_state,
            tracking_epoch=self._tracking_epoch,
            tracking_quality=self._tracking_quality,
            motion_state=motion_state,
            battery_fraction=self._battery,
            flashlight_on=self._flashlight,
            front_range_m=self._front_range,
            bumper_pressed=self._bumper,
        )
        self._publisher.publish(String(data=json.dumps(payload, separators=(",", ":"))))


def main(args=None) -> None:
    rclpy.init(args=args)
    node = HilGatewayNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
