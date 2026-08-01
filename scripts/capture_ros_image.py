#!/usr/bin/env python3
"""Capture one ROS Image message for simulator visual QA."""

import argparse
from pathlib import Path

import cv2
from cv_bridge import CvBridge
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image


class OneImageCapture(Node):
    def __init__(self, topic: str, output: Path) -> None:
        super().__init__("pulso_one_image_capture")
        self._bridge = CvBridge()
        self._output = output
        self.complete = False
        self.create_subscription(Image, topic, self._on_image, 10)

    def _on_image(self, message: Image) -> None:
        if self.complete:
            return
        image = self._bridge.imgmsg_to_cv2(message, "bgr8")
        self._output.parent.mkdir(parents=True, exist_ok=True)
        if not cv2.imwrite(str(self._output), image):
            raise RuntimeError(f"Could not write {self._output}")
        self.complete = True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--topic", default="/pulso/phone/rgb/image")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    rclpy.init()
    node = OneImageCapture(args.topic, args.output)
    try:
        while rclpy.ok() and not node.complete:
            rclpy.spin_once(node, timeout_sec=1.0)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
