"""Back-project emulated phone depth into dense and sparse AR-like clouds."""

import cv2
import numpy as np
import rclpy
from cv_bridge import CvBridge
from rclpy.node import Node
from sensor_msgs.msg import CameraInfo, CompressedImage, Image, PointCloud2, PointField
from sensor_msgs_py import point_cloud2


class CloudAdapterNode(Node):
    def __init__(self) -> None:
        super().__init__("pulso_cloud_adapter")
        self.declare_parameter("dense_stride", 4)
        self.declare_parameter("max_features", 280)
        self.declare_parameter("rgb_jpeg_period_ms", 500)
        self.declare_parameter("rgb_jpeg_quality", 84)
        self._bridge = CvBridge()
        self._camera_info: CameraInfo | None = None
        self._depth_mm: np.ndarray | None = None
        self._depth_stamp_ns = 0
        self._last_dense_stamp_ns = 0
        self._last_rgb_jpeg_stamp_ns = 0
        self._dense_pub = self.create_publisher(PointCloud2, "/pulso/phone/depth/points", 5)
        self._sparse_pub = self.create_publisher(
            PointCloud2, "/pulso/phone/arcore/feature_points", 5
        )
        self._rgb_compressed_pub = self.create_publisher(
            CompressedImage, "/pulso/phone/rgb/compressed", 2
        )
        self.create_subscription(
            CameraInfo, "/pulso/phone/rgb/camera_info", self._on_camera_info, 10
        )
        self.create_subscription(Image, "/pulso/phone/depth/raw", self._on_depth, 10)
        self.create_subscription(Image, "/pulso/phone/rgb/image", self._on_rgb, 10)

    def _on_camera_info(self, message: CameraInfo) -> None:
        self._camera_info = message

    def _on_depth(self, message: Image) -> None:
        self._depth_mm = self._bridge.imgmsg_to_cv2(message, "16UC1")
        self._depth_stamp_ns = message.header.stamp.sec * 1_000_000_000 + message.header.stamp.nanosec
        stamp_ns = self._depth_stamp_ns
        if stamp_ns - self._last_dense_stamp_ns < 100_000_000:
            return
        self._last_dense_stamp_ns = stamp_ns
        camera = self._camera_info
        if camera is None or self._depth_mm is None:
            return
        stride = max(1, int(self.get_parameter("dense_stride").value))
        rows, cols = self._depth_mm.shape
        v, u = np.mgrid[0:rows:stride, 0:cols:stride]
        z = self._depth_mm[::stride, ::stride].astype(np.float32) / 1000.0
        valid = z > 0.0
        fx, fy, cx, cy = camera.k[0], camera.k[4], camera.k[2], camera.k[5]
        if fx <= 0.0 or fy <= 0.0:
            return
        x = (u.astype(np.float32) - cx) * z / fx
        y = (v.astype(np.float32) - cy) * z / fy
        points = np.column_stack((x[valid], y[valid], z[valid]))
        header = message.header
        header.frame_id = "phone_camera_optical_frame"
        self._dense_pub.publish(point_cloud2.create_cloud_xyz32(header, points.tolist()))

    def _on_rgb(self, message: Image) -> None:
        rgb_stamp_ns = message.header.stamp.sec * 1_000_000_000 + message.header.stamp.nanosec
        image = self._bridge.imgmsg_to_cv2(message, "rgb8")
        jpeg_period_ns = max(
            100, int(self.get_parameter("rgb_jpeg_period_ms").value)
        ) * 1_000_000
        if rgb_stamp_ns - self._last_rgb_jpeg_stamp_ns >= jpeg_period_ns:
            self._last_rgb_jpeg_stamp_ns = rgb_stamp_ns
            bgr = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
            quality = int(
                np.clip(self.get_parameter("rgb_jpeg_quality").value, 35, 95)
            )
            success, encoded = cv2.imencode(
                ".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, quality]
            )
            if success:
                compressed = CompressedImage()
                compressed.header = message.header
                compressed.format = "jpeg"
                compressed.data = encoded.tobytes()
                self._rgb_compressed_pub.publish(compressed)

        camera = self._camera_info
        depth = self._depth_mm
        if camera is None or depth is None:
            return
        if abs(rgb_stamp_ns - self._depth_stamp_ns) > 180_000_000:
            return
        gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        corners = cv2.goodFeaturesToTrack(
            gray,
            maxCorners=int(self.get_parameter("max_features").value),
            qualityLevel=0.012,
            minDistance=7,
        )
        if corners is None:
            return
        fx, fy, cx, cy = camera.k[0], camera.k[4], camera.k[2], camera.k[5]
        points = []
        for point_id, corner in enumerate(corners.reshape(-1, 2)):
            u, v = (int(round(corner[0])), int(round(corner[1])))
            if not (1 <= v < depth.shape[0] - 1 and 1 <= u < depth.shape[1] - 1):
                continue
            patch = depth[v - 1 : v + 2, u - 1 : u + 2]
            valid = patch[patch > 0]
            if valid.size == 0:
                continue
            z = float(np.median(valid)) / 1000.0
            x = (u - cx) * z / fx
            y = (v - cy) * z / fy
            confidence = min(1.0, valid.size / 9.0)
            points.append((x, y, z, confidence, point_id))
        if not points:
            return
        fields = [
            PointField(name="x", offset=0, datatype=PointField.FLOAT32, count=1),
            PointField(name="y", offset=4, datatype=PointField.FLOAT32, count=1),
            PointField(name="z", offset=8, datatype=PointField.FLOAT32, count=1),
            PointField(name="confidence", offset=12, datatype=PointField.FLOAT32, count=1),
            PointField(name="point_id", offset=16, datatype=PointField.UINT32, count=1),
        ]
        header = message.header
        header.frame_id = "phone_camera_optical_frame"
        self._sparse_pub.publish(point_cloud2.create_cloud(header, fields, points))


def main(args=None) -> None:
    rclpy.init(args=args)
    node = CloudAdapterNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
