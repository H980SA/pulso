"""JSON-native observation construction with no ROS dependencies."""

from __future__ import annotations

from typing import Any


def build_observation(
    *,
    sequence: int,
    captured_ns: int,
    pose: tuple[float, float, float],
    heading_deg: float,
    pose_confidence: float,
    tracking_state: str,
    tracking_epoch: int,
    tracking_quality: float,
    motion_state: str,
    battery_fraction: float,
    flashlight_on: bool,
    front_range_m: float | None,
    bumper_pressed: bool,
) -> dict[str, Any]:
    return {
        "contract_version": "pulso.observation.v1",
        "observation_id": f"OBS-{sequence:08d}",
        "source": "GAZEBO_HIL",
        "captured_monotonic_ns": max(0, int(captured_ns)),
        "frame_id": "map",
        "tracking": {
            "state": tracking_state,
            "epoch": max(0, int(tracking_epoch)),
            "quality": min(1.0, max(0.0, float(tracking_quality))),
            "cause": None if tracking_state == "TRACKING" else "VIO_DEGRADED",
        },
        "robot": {
            "pose": {
                "position_m": [float(pose[0]), float(pose[1]), float(pose[2])],
                "heading_deg": float(heading_deg),
                "confidence": min(1.0, max(0.0, float(pose_confidence))),
            },
            "motion_state": motion_state,
            "battery_fraction": min(1.0, max(0.0, float(battery_fraction))),
            "flashlight_on": bool(flashlight_on),
            "front_range_m": None if front_range_m is None else max(0.0, float(front_range_m)),
            "bumper_pressed": bool(bumper_pressed),
        },
        "artifacts": [
            {
                "artifact_id": f"RGB-{sequence:08d}",
                "kind": "EGO_RGB",
                "captured_monotonic_ns": max(0, int(captured_ns)),
                "uri": "ros:///pulso/phone/rgb/image",
                "valid_for_ms": 250,
            },
            {
                "artifact_id": f"DEPTH-{sequence:08d}",
                "kind": "RAW_DEPTH",
                "captured_monotonic_ns": max(0, int(captured_ns)),
                "uri": "ros:///pulso/phone/depth/raw",
                "valid_for_ms": 350,
            },
            {
                "artifact_id": f"CLOUD-{sequence:08d}",
                "kind": "DENSE_POINT_CLOUD",
                "captured_monotonic_ns": max(0, int(captured_ns)),
                "uri": "ros:///pulso/phone/depth/points",
                "valid_for_ms": 350,
            },
        ],
    }
