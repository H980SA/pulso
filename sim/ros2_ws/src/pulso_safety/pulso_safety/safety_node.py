"""ROS wrapper around the deterministic, non-bypassable safety policy."""

import math

from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue
from geometry_msgs.msg import Twist
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Range
from std_msgs.msg import Bool

from .policy import MotionCommand, SafetyPolicy
from .estop_latch import EstopLatch


class SafetyGateNode(Node):
    def __init__(self) -> None:
        super().__init__("pulso_safety_gate")
        self._policy = SafetyPolicy()
        self._desired = MotionCommand(0.0, 0.0)
        self._last_command_ns = 0
        self._front_range: float | None = None
        self._last_range_ns = 0
        self._bumper = False
        self._last_bumper_ns = 0
        self._estop = EstopLatch()
        self._safe_pub = self.create_publisher(Twist, "/pulso/base/cmd_vel_safe", 10)
        self._status_pub = self.create_publisher(
            DiagnosticArray, "/pulso/base/safety/status", 10
        )
        self.create_subscription(Twist, "/pulso/base/cmd_vel_desired", self._on_command, 10)
        self.create_subscription(Range, "/pulso/base/sonar/front", self._on_range, 10)
        self.create_subscription(Bool, "/pulso/base/bumper", self._on_bumper, 10)
        self.create_subscription(Bool, "/pulso/base/estop", self._on_estop, 10)
        self.create_timer(1.0 / 30.0, self._tick)

    def _on_command(self, message: Twist) -> None:
        self._desired = MotionCommand(message.linear.x, message.angular.z)
        self._last_command_ns = self.get_clock().now().nanoseconds

    def _on_range(self, message: Range) -> None:
        self._front_range = message.range if math.isfinite(message.range) else None
        self._last_range_ns = self.get_clock().now().nanoseconds

    def _on_bumper(self, message: Bool) -> None:
        self._bumper = message.data
        self._last_bumper_ns = self.get_clock().now().nanoseconds

    def _on_estop(self, message: Bool) -> None:
        self._estop.update(message.data)

    def _tick(self) -> None:
        now_ns = self.get_clock().now().nanoseconds
        age_s = math.inf if self._last_command_ns == 0 else (now_ns - self._last_command_ns) / 1e9
        range_age_s = math.inf if self._last_range_ns == 0 else (now_ns - self._last_range_ns) / 1e9
        bumper_age_s = math.inf if self._last_bumper_ns == 0 else (now_ns - self._last_bumper_ns) / 1e9
        decision = self._policy.evaluate(
            self._desired,
            age_s,
            self._front_range,
            self._bumper,
            self._estop.latched,
            range_age_s,
            bumper_age_s,
        )
        safe = Twist()
        safe.linear.x = decision.command.linear_x
        safe.angular.z = decision.command.angular_z
        self._safe_pub.publish(safe)

        diagnostics = DiagnosticArray()
        diagnostics.header.stamp = self.get_clock().now().to_msg()
        status = DiagnosticStatus()
        status.name = "pulso_motion_safety"
        status.level = (
            DiagnosticStatus.OK if decision.state == "CLEAR" else DiagnosticStatus.WARN
        )
        status.message = decision.state
        status.values = [
            KeyValue(key="reason", value=decision.reason),
            KeyValue(key="command_age_s", value=f"{age_s:.3f}"),
            KeyValue(key="front_range_m", value=str(self._front_range)),
            KeyValue(key="range_age_s", value=f"{range_age_s:.3f}"),
            KeyValue(key="bumper_age_s", value=f"{bumper_age_s:.3f}"),
        ]
        diagnostics.status = [status]
        self._status_pub.publish(diagnostics)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = SafetyGateNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
