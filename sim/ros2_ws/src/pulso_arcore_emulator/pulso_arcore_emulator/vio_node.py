"""Publish a drifting VIO estimate while keeping Gazebo truth private."""

import copy
import math

from geometry_msgs.msg import TransformStamped
import rclpy
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue
from nav_msgs.msg import Odometry
from rclpy.node import Node
from tf2_ros import TransformBroadcaster

from .vio_model import relative_planar_pose, wrap_angle, yaw_from_quaternion


class VioEmulatorNode(Node):
    def __init__(self) -> None:
        super().__init__("pulso_vio_emulator")
        self.declare_parameter("translation_drift_m_per_min", 0.025)
        self.declare_parameter("yaw_drift_deg_per_min", 0.8)
        self._origin_ns = self.get_clock().now().nanoseconds
        self._truth_origin: tuple[float, float, float] | None = None
        self._odom_pub = self.create_publisher(Odometry, "/pulso/phone/vio/odom", 20)
        self._status_pub = self.create_publisher(
            DiagnosticArray, "/pulso/phone/vio/status", 10
        )
        self._tf_broadcaster = TransformBroadcaster(self)
        self.create_subscription(
            Odometry, "/pulso/sim/ground_truth/odom", self._on_truth, 20
        )

    def _on_truth(self, truth: Odometry) -> None:
        elapsed_min = (self.get_clock().now().nanoseconds - self._origin_ns) / 60e9
        drift_m = float(self.get_parameter("translation_drift_m_per_min").value) * elapsed_min
        drift_yaw = math.radians(
            float(self.get_parameter("yaw_drift_deg_per_min").value) * elapsed_min
        )

        truth_position = truth.pose.pose.position
        truth_orientation = truth.pose.pose.orientation
        truth_yaw = yaw_from_quaternion(
            truth_orientation.x,
            truth_orientation.y,
            truth_orientation.z,
            truth_orientation.w,
        )
        if self._truth_origin is None:
            self._truth_origin = (truth_position.x, truth_position.y, truth_yaw)
        relative_x, relative_y, relative_yaw = relative_planar_pose(
            truth_position.x,
            truth_position.y,
            truth_yaw,
            self._truth_origin,
        )

        estimate = Odometry()
        estimate.header = copy.deepcopy(truth.header)
        estimate.header.frame_id = "odom"
        estimate.child_frame_id = "base_link"
        estimate.pose.pose.position.x = relative_x + drift_m
        estimate.pose.pose.position.y = relative_y
        estimate.pose.pose.position.z = 0.0
        estimate_yaw = wrap_angle(relative_yaw + drift_yaw)
        estimate.pose.pose.orientation.z = math.sin(estimate_yaw / 2.0)
        estimate.pose.pose.orientation.w = math.cos(estimate_yaw / 2.0)
        estimate.twist = copy.deepcopy(truth.twist)
        estimate.pose.covariance[0] = 0.0025 + drift_m * drift_m
        estimate.pose.covariance[7] = 0.0025 + drift_m * drift_m
        estimate.pose.covariance[35] = math.radians(1.0) ** 2 + drift_yaw * drift_yaw
        self._odom_pub.publish(estimate)

        # VIO owns odom -> base_footprint. The fixed robot description then
        # supplies base_footprint -> base_link -> phone optical frames. Keeping
        # this transform on the degraded estimate prevents SLAM from seeing
        # Gazebo truth through TF.
        transform = TransformStamped()
        transform.header = estimate.header
        transform.header.frame_id = "odom"
        transform.child_frame_id = "base_footprint"
        transform.transform.translation.x = estimate.pose.pose.position.x
        transform.transform.translation.y = estimate.pose.pose.position.y
        transform.transform.translation.z = 0.0
        transform.transform.rotation = estimate.pose.pose.orientation
        self._tf_broadcaster.sendTransform(transform)

        diagnostics = DiagnosticArray()
        diagnostics.header = truth.header
        status = DiagnosticStatus()
        status.level = DiagnosticStatus.OK
        status.name = "pulso_vio_tracking"
        status.message = "TRACKING"
        status.values = [
            KeyValue(key="state", value="TRACKING"),
            KeyValue(key="quality", value=f"{max(0.55, 0.98 - elapsed_min * 0.01):.3f}"),
            KeyValue(key="profile", value="PROVISIONAL_UNCALIBRATED"),
        ]
        diagnostics.status = [status]
        self._status_pub.publish(diagnostics)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = VioEmulatorNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
