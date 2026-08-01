"""ROS adapter from clean Gazebo depth to the Pulso depth contract."""

import numpy as np
import rclpy
from cv_bridge import CvBridge
from rclpy.node import Node
from sensor_msgs.msg import Image

from .depth_model import DepthProfile, degrade_depth


class DepthEmulatorNode(Node):
    def __init__(self) -> None:
        super().__init__("pulso_depth_emulator")
        self.declare_parameter("seed", 4127)
        self.declare_parameter("warmup_seconds", 1.5)
        self.declare_parameter("input_topic", "/pulso/sim/phone/depth_clean")
        self._rng = np.random.default_rng(self.get_parameter("seed").value)
        self._profile = DepthProfile()
        self._bridge = CvBridge()
        self._started_ns = self.get_clock().now().nanoseconds

        input_topic = self.get_parameter("input_topic").value
        self.create_subscription(Image, input_topic, self._on_depth, 10)
        self._raw_pub = self.create_publisher(Image, "/pulso/phone/depth/raw", 10)
        self._smooth_pub = self.create_publisher(Image, "/pulso/phone/depth/smoothed", 10)
        self._confidence_pub = self.create_publisher(
            Image, "/pulso/phone/depth/confidence", 10
        )

    def _on_depth(self, message: Image) -> None:
        elapsed_s = (self.get_clock().now().nanoseconds - self._started_ns) / 1e9
        clean = self._bridge.imgmsg_to_cv2(message, desired_encoding="passthrough")
        if message.encoding == "16UC1":
            depth_m = clean.astype(np.float32) / 1000.0
        else:
            depth_m = clean.astype(np.float32)

        if elapsed_s < float(self.get_parameter("warmup_seconds").value):
            raw = np.zeros(depth_m.shape, dtype=np.uint16)
            confidence = np.zeros(depth_m.shape, dtype=np.uint8)
        else:
            raw, confidence = degrade_depth(depth_m, self._rng, self._profile)

        raw_message = self._bridge.cv2_to_imgmsg(raw, encoding="16UC1")
        raw_message.header = message.header
        confidence_message = self._bridge.cv2_to_imgmsg(confidence, encoding="mono8")
        confidence_message.header = message.header

        smooth_mm = np.where(np.isfinite(depth_m), depth_m * 1000.0, 0.0)
        smooth = np.clip(np.rint(smooth_mm), 0, 65535).astype(np.uint16)
        smooth_message = self._bridge.cv2_to_imgmsg(smooth, encoding="16UC1")
        smooth_message.header = message.header

        self._raw_pub.publish(raw_message)
        self._smooth_pub.publish(smooth_message)
        self._confidence_pub.publish(confidence_message)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = DepthEmulatorNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
