"""Real YOLO11n-pose saliency sensor for Gazebo's simulated phone camera."""

from __future__ import annotations

import json
from pathlib import Path
import time

import cv2
import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import CameraInfo, CompressedImage
from std_msgs.msg import String

from .perception_telemetry import build_perception_telemetry
from .yolo_pose import StablePersonTracker, bearing_degrees, decode, letterbox


MODEL_ID = "yolo11n-pose-onnx"


class PersonPerceptionNode(Node):
    def __init__(self) -> None:
        super().__init__("pulso_person_perception")
        self.declare_parameter("model_path", "")
        self.declare_parameter("provider", "cuda")
        self.declare_parameter("threshold", 0.18)
        self.declare_parameter("inference_period_s", 0.65)
        model_path = Path(str(self.get_parameter("model_path").value)).expanduser()
        if not model_path.is_file():
            raise RuntimeError(f"YOLO11n-pose model not found: {model_path}")

        import onnxruntime as ort

        provider = str(self.get_parameter("provider").value).lower()
        if provider == "cuda":
            ort.preload_dlls(directory="")
            requested = ["CUDAExecutionProvider", "CPUExecutionProvider"]
        else:
            requested = ["CPUExecutionProvider"]
        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        self._model_path = model_path
        self._session_options = options
        self._cpu_fallback_attempted = False
        self._session = ort.InferenceSession(
            model_path.as_posix(), sess_options=options, providers=requested
        )
        self._input_name = self._session.get_inputs()[0].name
        self._provider = self._session.get_providers()[0]
        self._camera: CameraInfo | None = None
        self._last_inference_ns = 0
        self._revision = 0
        self._tracker = StablePersonTracker()
        self._tracks_pub = self.create_publisher(
            String, "/pulso/hil/perception_tracks", 10
        )
        self._telemetry_pub = self.create_publisher(
            String, "/pulso/hil/perception_telemetry", 10
        )
        self.create_subscription(
            CameraInfo,
            "/pulso/phone/rgb/camera_info",
            self._on_camera_info,
            qos_profile_sensor_data,
        )
        self.create_subscription(
            CompressedImage,
            "/pulso/phone/rgb/compressed",
            self._on_image,
            qos_profile_sensor_data,
        )
        self.get_logger().info(
            f"Real {MODEL_ID} loaded from {model_path.name} on {self._provider}"
        )
        self._publish_telemetry("WARMING", 0, 0.0, 0, 0)

    def _run_model(self, tensor: np.ndarray) -> np.ndarray:
        try:
            return self._session.run(None, {self._input_name: tensor})[0]
        except Exception as failure:
            if (
                self._provider != "CUDAExecutionProvider"
                or self._cpu_fallback_attempted
            ):
                raise
            self._cpu_fallback_attempted = True
            self.get_logger().warning(
                "CUDA inference unavailable; switching YOLO to CPU: "
                f"{str(failure)[:240]}"
            )
            import onnxruntime as ort

            self._session = ort.InferenceSession(
                self._model_path.as_posix(),
                sess_options=self._session_options,
                providers=["CPUExecutionProvider"],
            )
            self._input_name = self._session.get_inputs()[0].name
            self._provider = self._session.get_providers()[0]
            self._publish_telemetry("WARMING", 0, 0.0, self._revision, 0)
            return self._session.run(None, {self._input_name: tensor})[0]

    def _on_camera_info(self, message: CameraInfo) -> None:
        self._camera = message

    def _on_image(self, message: CompressedImage) -> None:
        now_ns = time.monotonic_ns()
        source_capture_ns = (
            int(message.header.stamp.sec) * 1_000_000_000
            + int(message.header.stamp.nanosec)
        )
        period_ns = int(
            max(0.2, float(self.get_parameter("inference_period_s").value))
            * 1_000_000_000
        )
        if now_ns - self._last_inference_ns < period_ns:
            return
        self._last_inference_ns = now_ns
        encoded = np.frombuffer(bytes(message.data), dtype=np.uint8)
        image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
        if image is None:
            self._publish_telemetry(
                "ERROR", 0, 0.0, self._revision, source_capture_ns
            )
            return
        tensor, scale, pad_x, pad_y = letterbox(image)
        started = time.perf_counter_ns()
        try:
            raw = self._run_model(tensor)
            latency_ms = (time.perf_counter_ns() - started) / 1_000_000.0
            detections = decode(
                raw,
                image_width=image.shape[1],
                image_height=image.shape[0],
                scale=scale,
                pad_x=pad_x,
                pad_y=pad_y,
                threshold=float(self.get_parameter("threshold").value),
            )
        except Exception as failure:
            self.get_logger().error(f"YOLO inference failed: {failure}")
            self._publish_telemetry(
                "ERROR", 0, 0.0, self._revision, source_capture_ns
            )
            return
        tracked = self._tracker.update(detections)
        self._revision += 1
        camera = self._camera
        fx = float(camera.k[0]) if camera is not None else float(image.shape[1])
        cx = float(camera.k[2]) if camera is not None else image.shape[1] / 2.0
        tracks = []
        for item in tracked:
            left, top, right, bottom = item["box_px"]
            center_x = (left + right) / 2.0
            tracks.append(
                {
                    "id": item["id"],
                    "label": "person",
                    "confidence": round(float(item["confidence"]), 4),
                    "bearing_deg": round(bearing_degrees(center_x, fx, cx), 2),
                    "box_norm": [
                        round(left / image.shape[1], 5),
                        round(top / image.shape[0], 5),
                        round(right / image.shape[1], 5),
                        round(bottom / image.shape[0], 5),
                    ],
                    "revision": int(item["revision"]),
                    "model_id": MODEL_ID,
                    "inference_latency_ms": round(latency_ms, 2),
                    "visible_keypoints": int(item["visible_keypoints"]),
                }
            )
        payload = {
            "contract_version": "pulso.perception.tracks.v1",
            "captured_monotonic_ns": now_ns,
            "frame_id": message.header.frame_id or "phone_camera_optical_frame",
            "tracks": tracks,
        }
        self._tracks_pub.publish(
            String(data=json.dumps(payload, separators=(",", ":")))
        )
        self._publish_telemetry(
            "LIVE", len(tracks), latency_ms, self._revision, source_capture_ns
        )

    def _publish_telemetry(
        self,
        status: str,
        count: int,
        latency_ms: float,
        revision: int,
        source_capture_ns: int,
    ) -> None:
        payload = build_perception_telemetry(
            published_ns=time.monotonic_ns(),
            source_capture_ns=source_capture_ns,
            model_id=MODEL_ID,
            provider=self._provider,
            status=status,
            detection_count=count,
            inference_latency_ms=latency_ms,
            semantic_revision=revision,
        )
        self._telemetry_pub.publish(
            String(data=json.dumps(payload, separators=(",", ":")))
        )


def main(args=None) -> None:
    rclpy.init(args=args)
    node = None
    try:
        node = PersonPerceptionNode()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
