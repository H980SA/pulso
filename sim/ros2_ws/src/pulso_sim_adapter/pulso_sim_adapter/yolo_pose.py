"""YOLO11n-pose preprocessing, decoding and short-lived stable IDs."""

from __future__ import annotations

from dataclasses import dataclass
import math

import cv2
import numpy as np


INPUT_SIZE = 640
KEYPOINT_COUNT = 17


def letterbox(image: np.ndarray) -> tuple[np.ndarray, float, float, float]:
    height, width = image.shape[:2]
    scale = min(INPUT_SIZE / width, INPUT_SIZE / height)
    scaled_width = max(1, int(round(width * scale)))
    scaled_height = max(1, int(round(height * scale)))
    resized = cv2.resize(image, (scaled_width, scaled_height), interpolation=cv2.INTER_LINEAR)
    left = (INPUT_SIZE - scaled_width) // 2
    top = (INPUT_SIZE - scaled_height) // 2
    canvas = np.full((INPUT_SIZE, INPUT_SIZE, 3), 114, dtype=np.uint8)
    canvas[top : top + scaled_height, left : left + scaled_width] = resized
    rgb = cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB)
    tensor = np.transpose(rgb.astype(np.float32) / 255.0, (2, 0, 1))[None]
    return tensor, scale, float(left), float(top)


def decode(
    output: np.ndarray,
    *,
    image_width: int,
    image_height: int,
    scale: float,
    pad_x: float,
    pad_y: float,
    threshold: float,
    max_people: int = 6,
) -> list[dict]:
    channels = _channels_first(output)
    if channels.shape[0] < 5 + KEYPOINT_COUNT * 3:
        raise ValueError(f"unexpected YOLO pose channels: {channels.shape}")
    candidates: list[dict] = []
    for anchor in np.flatnonzero(channels[4] >= threshold):
        center_x, center_y, width, height = channels[:4, anchor]
        box = [
            float(np.clip((center_x - width / 2 - pad_x) / scale, 0, image_width)),
            float(np.clip((center_y - height / 2 - pad_y) / scale, 0, image_height)),
            float(np.clip((center_x + width / 2 - pad_x) / scale, 0, image_width)),
            float(np.clip((center_y + height / 2 - pad_y) / scale, 0, image_height)),
        ]
        if box[2] - box[0] < 4 or box[3] - box[1] < 4:
            continue
        visible = int(
            sum(
                channels[5 + keypoint * 3 + 2, anchor] >= 0.25
                for keypoint in range(KEYPOINT_COUNT)
            )
        )
        candidates.append(
            {
                "confidence": float(channels[4, anchor]),
                "box_px": box,
                "visible_keypoints": visible,
            }
        )
    remaining = sorted(candidates, key=lambda item: item["confidence"], reverse=True)
    selected: list[dict] = []
    while remaining and len(selected) < max_people:
        best = remaining.pop(0)
        selected.append(best)
        remaining = [
            item for item in remaining if intersection_over_union(best["box_px"], item["box_px"]) <= 0.45
        ]
    return selected


def intersection_over_union(first: list[float], second: list[float]) -> float:
    left, top = max(first[0], second[0]), max(first[1], second[1])
    right, bottom = min(first[2], second[2]), min(first[3], second[3])
    intersection = max(0.0, right - left) * max(0.0, bottom - top)
    first_area = max(0.0, first[2] - first[0]) * max(0.0, first[3] - first[1])
    second_area = max(0.0, second[2] - second[0]) * max(0.0, second[3] - second[1])
    union = first_area + second_area - intersection
    return 0.0 if union <= 0.0 else intersection / union


@dataclass
class _Prior:
    track_id: str
    box_px: list[float]
    revision: int
    missed: int = 0


class StablePersonTracker:
    """Small IoU tracker; it stabilizes IDs but never manufactures detections."""

    def __init__(self, *, match_iou: float = 0.28, max_missed: int = 3) -> None:
        self.match_iou = match_iou
        self.max_missed = max_missed
        self._next_id = 1
        self._prior: list[_Prior] = []

    def update(self, detections: list[dict]) -> list[dict]:
        unmatched = set(range(len(self._prior)))
        output: list[dict] = []
        next_prior: list[_Prior] = []
        for detection in detections:
            match = max(
                unmatched,
                key=lambda index: intersection_over_union(
                    self._prior[index].box_px, detection["box_px"]
                ),
                default=None,
            )
            overlap = (
                intersection_over_union(self._prior[match].box_px, detection["box_px"])
                if match is not None
                else 0.0
            )
            if match is not None and overlap >= self.match_iou:
                prior = self._prior[match]
                unmatched.remove(match)
                revision = prior.revision + (1 if overlap < 0.72 else 0)
                track_id = prior.track_id
            else:
                track_id = f"PERSON_SIM_{self._next_id:03d}"
                self._next_id += 1
                revision = 1
            enriched = {**detection, "id": track_id, "revision": revision}
            output.append(enriched)
            next_prior.append(_Prior(track_id, list(detection["box_px"]), revision))
        for index in unmatched:
            prior = self._prior[index]
            if prior.missed + 1 <= self.max_missed:
                next_prior.append(
                    _Prior(prior.track_id, prior.box_px, prior.revision, prior.missed + 1)
                )
        self._prior = next_prior
        return output


def bearing_degrees(center_x: float, fx: float, cx: float) -> float:
    if fx <= 0:
        return 0.0
    return math.degrees(math.atan2(center_x - cx, fx))


def _channels_first(output: np.ndarray) -> np.ndarray:
    array = np.asarray(output)
    while array.ndim > 2 and array.shape[0] == 1:
        array = array[0]
    if array.ndim != 2:
        raise ValueError(f"unexpected YOLO output rank: {array.shape}")
    expected = 5 + KEYPOINT_COUNT * 3
    if array.shape[0] == expected:
        return array
    if array.shape[1] == expected:
        return array.T
    return array if array.shape[0] <= array.shape[1] else array.T
