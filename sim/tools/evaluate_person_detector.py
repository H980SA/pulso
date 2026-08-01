#!/usr/bin/env python3
"""Evaluate the exact YOLO11n-pose ONNX asset packaged by the Android app."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics
import time

import cv2
import numpy as np
import onnxruntime as ort


INPUT_SIZE = 640
KEYPOINT_COUNT = 17


def letterbox(image: np.ndarray) -> tuple[np.ndarray, float, float, float]:
    height, width = image.shape[:2]
    scale = min(INPUT_SIZE / width, INPUT_SIZE / height)
    scaled_width, scaled_height = max(1, int(width * scale)), max(1, int(height * scale))
    resized = cv2.resize(image, (scaled_width, scaled_height), interpolation=cv2.INTER_LINEAR)
    pad_x, pad_y = (INPUT_SIZE - scaled_width) / 2.0, (INPUT_SIZE - scaled_height) / 2.0
    canvas = np.full((INPUT_SIZE, INPUT_SIZE, 3), 114, dtype=np.uint8)
    left, top = int(pad_x), int(pad_y)
    canvas[top : top + scaled_height, left : left + scaled_width] = resized
    rgb = cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB)
    tensor = np.transpose(rgb.astype(np.float32) / 255.0, (2, 0, 1))[None]
    return tensor, scale, pad_x, pad_y


def intersection_over_union(first: list[float], second: list[float]) -> float:
    left, top = max(first[0], second[0]), max(first[1], second[1])
    right, bottom = min(first[2], second[2]), min(first[3], second[3])
    intersection = max(0.0, right - left) * max(0.0, bottom - top)
    first_area = max(0.0, first[2] - first[0]) * max(0.0, first[3] - first[1])
    second_area = max(0.0, second[2] - second[0]) * max(0.0, second[3] - second[1])
    union = first_area + second_area - intersection
    return 0.0 if union <= 0.0 else intersection / union


def decode(
    channels: np.ndarray,
    image_width: int,
    image_height: int,
    scale: float,
    pad_x: float,
    pad_y: float,
    threshold: float,
) -> list[dict]:
    candidates = []
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
        visible = sum(
            channels[5 + keypoint * 3 + 2, anchor] >= 0.25
            for keypoint in range(KEYPOINT_COUNT)
        )
        candidates.append(
            {
                "score": float(channels[4, anchor]),
                "box_px": box,
                "visible_keypoints": int(visible),
            }
        )
    remaining = sorted(candidates, key=lambda item: item["score"], reverse=True)
    selected = []
    while remaining and len(selected) < 4:
        best = remaining.pop(0)
        selected.append(best)
        remaining = [
            item
            for item in remaining
            if intersection_over_union(best["box_px"], item["box_px"]) <= 0.45
        ]
    for item in selected:
        item["score"] = round(item["score"], 4)
        item["box_px"] = [round(value, 1) for value in item["box_px"]]
    return selected


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--threshold", type=float, default=0.18)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("images", type=Path, nargs="+")
    args = parser.parse_args()

    session = ort.InferenceSession(
        args.model.as_posix(),
        providers=["CPUExecutionProvider"],
    )
    input_name = session.get_inputs()[0].name
    output = []
    for image_path in args.images:
        image = cv2.imread(image_path.as_posix(), cv2.IMREAD_COLOR)
        if image is None:
            raise SystemExit(f"Could not decode {image_path}")
        tensor, scale, pad_x, pad_y = letterbox(image)
        session.run(None, {input_name: tensor})
        timings = []
        channels = None
        for _ in range(max(1, args.runs)):
            started = time.perf_counter()
            channels = session.run(None, {input_name: tensor})[0][0]
            timings.append((time.perf_counter() - started) * 1000.0)
        assert channels is not None
        people = decode(
            channels,
            image.shape[1],
            image.shape[0],
            scale,
            pad_x,
            pad_y,
            args.threshold,
        )
        output.append(
            {
                "image": image_path.as_posix(),
                "width": image.shape[1],
                "height": image.shape[0],
                "inference_ms_median": round(statistics.median(timings), 2),
                "people": people,
            }
        )
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
