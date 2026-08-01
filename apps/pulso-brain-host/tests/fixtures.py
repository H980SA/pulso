from __future__ import annotations

import base64
import json


def observation(*, captured_ns: int = 10_000, motion: str = "STOPPED", tracking: str = "TRACKING"):
    return {
        "contract_version": "pulso.observation.v1",
        "observation_id": "OBS-1",
        "source": "GAZEBO_HIL",
        "captured_monotonic_ns": captured_ns,
        "frame_id": "map",
        "tracking": {"state": tracking, "epoch": 4, "quality": 0.91},
        "robot": {
            "pose": {"position_m": [1.0, 2.0, 0.0], "heading_deg": 30.0, "confidence": 0.9},
            "motion_state": motion,
            "battery_fraction": 0.8,
            "flashlight_on": False,
            "front_range_m": 0.9,
        },
    }


def candidates(*, captured_ns: int = 10_000, revision: int = 7):
    return {
        "contract_version": "pulso.navigation.candidates.v1",
        "captured_monotonic_ns": captured_ns,
        "sensor_map_seq": 12,
        "navigation_revision": revision,
        "valid_until_monotonic_ns": captured_ns + 20_000_000_000,
        "candidates": [
            {
                "type": "FRONTIER",
                "id": "F_A",
                "capability": "capability_1234567890abcd",
                "target_revision": None,
                "label": "Camino A",
                "purpose": "Expandir mapa",
                "position_m": [1.8, 2.1],
                "path_length_m": 0.82,
                "risk": 0.15,
                "information_gain": 0.88,
            },
            {
                "type": "FRONTIER",
                "id": "F_B",
                "capability": "capability_abcdefghijklmno",
                "target_revision": None,
                "label": "Camino B",
                "purpose": "Expandir mapa",
                "position_m": [0.4, 2.4],
                "path_length_m": 1.5,
                "risk": 0.4,
                "information_gain": 0.5,
            },
        ],
    }


def compressed_image(jpeg: bytes, captured_ns: int):
    return {
        "header": {
            "stamp": {
                "sec": captured_ns // 1_000_000_000,
                "nanosec": captured_ns % 1_000_000_000,
            },
            "frame_id": "phone_camera_optical_frame",
        },
        "format": "jpeg",
        "data": base64.b64encode(jpeg).decode("ascii"),
    }


def ros_frame(topic: str, message: dict):
    return json.dumps({"op": "publish", "topic": topic, "msg": message})


def std_frame(topic: str, payload: dict):
    return ros_frame(topic, {"data": json.dumps(payload)})
