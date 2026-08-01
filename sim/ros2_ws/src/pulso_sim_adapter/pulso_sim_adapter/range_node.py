"""Convert Gazebo's seven-ray cone into the OpenBot front range contract."""

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import LaserScan, Range

from .range_model import quantized_nearest


class RangeAdapterNode(Node):
    def __init__(self) -> None:
        super().__init__("pulso_range_adapter")
        self._publisher = self.create_publisher(Range, "/pulso/base/sonar/front", 10)
        self.create_subscription(LaserScan, "/pulso/sim/base/front_scan", self._on_scan, 10)

    def _on_scan(self, scan: LaserScan) -> None:
        message = Range()
        message.header = scan.header
        message.header.frame_id = "sonar_front_link"
        message.radiation_type = Range.ULTRASOUND
        message.field_of_view = max(0.01, scan.angle_max - scan.angle_min)
        message.min_range = scan.range_min
        message.max_range = scan.range_max
        message.range = quantized_nearest(scan.ranges, scan.range_min, scan.range_max)
        self._publisher.publish(message)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = RangeAdapterNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
