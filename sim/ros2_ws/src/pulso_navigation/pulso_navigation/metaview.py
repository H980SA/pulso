"""ROS publication adapter for the evidence-backed top-down MetaView."""

from __future__ import annotations

from typing import Sequence

import cv2
from cv_bridge import CvBridge
import numpy as np
from sensor_msgs.msg import CompressedImage

from .frontier import FrontierCandidate, GridSpec
from .metaview_model import render_metaview as render_metaview_frame


def render_metaview(
    occupancy: np.ndarray,
    spec: GridSpec,
    robot: tuple[float, float, float],
    candidates: Sequence[FrontierCandidate],
    *,
    map_seq: int,
    navigation_revision: int,
    scan_footprint: Sequence[tuple[float, float]] = (),
    selected_id: str | None = None,
    output_width: int = 800,
    output_height: int = 800,
) -> np.ndarray:
    """Preserve the image-only renderer contract used by ROS callers."""
    image, _ = render_metaview_frame(
        occupancy,
        spec,
        robot,
        candidates,
        map_seq=map_seq,
        navigation_revision=navigation_revision,
        scan_footprint=scan_footprint,
        selected_id=selected_id,
        output_width=output_width,
        output_height=output_height,
    )
    return image


def publish_metaview(
    occupancy: np.ndarray,
    spec: GridSpec,
    robot: tuple[float, float, float],
    candidates: Sequence[FrontierCandidate],
    *,
    map_seq: int,
    navigation_revision: int,
    scan_footprint: Sequence[tuple[float, float]],
    selected_id: str | None,
    bridge: CvBridge,
    raw_publisher,
    compressed_publisher,
    stamp,
) -> None:
    image = render_metaview(
        occupancy,
        spec,
        robot,
        candidates,
        map_seq=map_seq,
        navigation_revision=navigation_revision,
        scan_footprint=scan_footprint,
        selected_id=selected_id,
    )
    raw = bridge.cv2_to_imgmsg(image, encoding="bgr8")
    raw.header.stamp = stamp
    raw.header.frame_id = "map"
    raw_publisher.publish(raw)

    success, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if success:
        compressed = CompressedImage()
        compressed.header = raw.header
        compressed.format = "jpeg"
        compressed.data = encoded.tobytes()
        compressed_publisher.publish(compressed)
