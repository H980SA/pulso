"""ROS subscriptions and RViz marker publishing for Pulso status."""

from __future__ import annotations

import math

from diagnostic_msgs.msg import DiagnosticArray
from geometry_msgs.msg import Point
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import BatteryState, Imu, Range
from std_msgs.msg import Bool, String
from visualization_msgs.msg import Marker, MarkerArray

from .status_model import (
    StatusLine,
    StatusState,
    diagnostic_from_fields,
    format_status_lines,
    merge_action_state,
    parse_action_result,
)


COLORS = {
    "ok": (0.18, 1.0, 0.48, 1.0),
    "info": (0.25, 0.80, 1.0, 1.0),
    "warning": (1.0, 0.68, 0.12, 1.0),
    "critical": (1.0, 0.12, 0.15, 1.0),
    "unknown": (0.65, 0.68, 0.72, 0.90),
}


class StatusVisualizerNode(Node):
    def __init__(self) -> None:
        super().__init__("pulso_status_visualizer")
        self.declare_parameter("publish_rate_hz", 4.0)
        self.declare_parameter("stale_after_s", 2.0)
        self.declare_parameter("frame_id", "base_link")
        self._state = StatusState()
        self._imu_vector: tuple[float, float, float] | None = None
        self._imu_frame = "phone_imu_link"
        self._publisher = self.create_publisher(
            MarkerArray, "/pulso/visualization/status_markers", 10
        )
        self.create_subscription(
            BatteryState, "/pulso/base/battery", self._on_battery, 10
        )
        self.create_subscription(Range, "/pulso/base/sonar/front", self._on_range, 10)
        self.create_subscription(Bool, "/pulso/base/bumper", self._on_bumper, 10)
        self.create_subscription(
            DiagnosticArray, "/pulso/base/safety/status", self._on_safety, 10
        )
        self.create_subscription(
            DiagnosticArray, "/pulso/phone/vio/status", self._on_vio, 10
        )
        self.create_subscription(Imu, "/pulso/phone/imu/data_raw", self._on_imu, 10)
        self.create_subscription(
            String, "/pulso/hil/action_result", self._on_action_result, 10
        )
        publish_rate = max(0.5, float(self.get_parameter("publish_rate_hz").value))
        self.create_timer(1.0 / publish_rate, self._publish)

    def _now_ns(self) -> int:
        return self.get_clock().now().nanoseconds

    def _on_battery(self, message: BatteryState) -> None:
        self._state.battery_fraction = (
            float(message.percentage)
            if message.present and math.isfinite(message.percentage)
            else None
        )
        self._state.battery_at_ns = self._now_ns()

    def _on_range(self, message: Range) -> None:
        self._state.front_range_m = (
            float(message.range) if math.isfinite(message.range) else None
        )
        self._state.front_range_at_ns = self._now_ns()

    def _on_bumper(self, message: Bool) -> None:
        self._state.bumper_pressed = bool(message.data)
        self._state.bumper_at_ns = self._now_ns()

    def _on_safety(self, message: DiagnosticArray) -> None:
        self._state.safety = self._first_diagnostic(message)
        self._state.safety_at_ns = self._now_ns()

    def _on_vio(self, message: DiagnosticArray) -> None:
        self._state.vio = self._first_diagnostic(message)
        self._state.vio_at_ns = self._now_ns()

    def _on_action_result(self, message: String) -> None:
        action = parse_action_result(message.data)
        if action is not None:
            self._state.action = merge_action_state(self._state.action, action)

    def _on_imu(self, message: Imu) -> None:
        vector = (
            float(message.linear_acceleration.x),
            float(message.linear_acceleration.y),
            float(message.linear_acceleration.z),
        )
        if not all(math.isfinite(component) for component in vector):
            self._imu_vector = None
            self._state.imu_norm_mps2 = None
        else:
            self._imu_vector = vector
            self._state.imu_norm_mps2 = math.sqrt(
                sum(component * component for component in vector)
            )
        self._imu_frame = message.header.frame_id or "phone_imu_link"
        self._state.imu_at_ns = self._now_ns()

    @staticmethod
    def _first_diagnostic(message: DiagnosticArray):
        if not message.status:
            return None
        status = message.status[0]
        values = {item.key: item.value for item in status.values}
        return diagnostic_from_fields(status.message, status.level, values)

    def _publish(self) -> None:
        now = self.get_clock().now()
        stale_after_ns = int(
            max(0.1, float(self.get_parameter("stale_after_s").value)) * 1e9
        )
        lines = format_status_lines(
            self._state,
            now_ns=now.nanoseconds,
            stale_after_ns=stale_after_ns,
        )
        markers = MarkerArray()
        markers.markers = [
            self._text_marker(index, line, now.to_msg())
            for index, line in enumerate(lines)
        ]
        imu_marker = self._imu_marker(now.to_msg(), now.nanoseconds, stale_after_ns)
        if imu_marker is not None:
            markers.markers.append(imu_marker)
        self._publisher.publish(markers)

    def _text_marker(self, index: int, line: StatusLine, stamp) -> Marker:
        marker = Marker()
        marker.header.frame_id = str(self.get_parameter("frame_id").value)
        marker.header.stamp = stamp
        marker.ns = "pulso_status"
        marker.id = index
        marker.type = Marker.TEXT_VIEW_FACING
        marker.action = Marker.ADD
        # The default operator camera is rotated -90 degrees: world X is the
        # screen's vertical axis. Stack the telemetry vertically and keep it
        # clear of the candidate labels around the rover.
        marker.pose.position.x = -0.25 - index * 0.20
        marker.pose.position.y = -1.25
        marker.pose.position.z = 0.58
        marker.pose.orientation.w = 1.0
        marker.scale.z = 0.12
        marker.text = f"{line.label}: {line.value}"
        red, green, blue, alpha = COLORS[line.severity]
        marker.color.r = red
        marker.color.g = green
        marker.color.b = blue
        marker.color.a = alpha
        marker.frame_locked = True
        return marker

    def _imu_marker(self, stamp, now_ns: int, stale_after_ns: int) -> Marker | None:
        vector = self._imu_vector
        age_ns = now_ns - self._state.imu_at_ns
        if vector is None or age_ns < 0 or age_ns > stale_after_ns:
            return None
        marker = Marker()
        marker.header.frame_id = self._imu_frame
        marker.header.stamp = stamp
        marker.ns = "pulso_imu_acceleration"
        marker.id = 100
        marker.type = Marker.ARROW
        marker.action = Marker.ADD
        marker.points = [
            Point(),
            Point(x=vector[0] * 0.03, y=vector[1] * 0.03, z=vector[2] * 0.03),
        ]
        marker.scale.x = 0.025
        marker.scale.y = 0.055
        marker.scale.z = 0.075
        marker.color.r = 0.12
        marker.color.g = 0.88
        marker.color.b = 1.0
        marker.color.a = 1.0
        marker.lifetime.nanosec = 500_000_000
        marker.frame_locked = True
        return marker


def main(args=None) -> None:
    rclpy.init(args=args)
    node = StatusVisualizerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
