import numpy as np

from pulso_sim_adapter.yolo_pose import (
    StablePersonTracker,
    bearing_degrees,
    decode,
    intersection_over_union,
    letterbox,
)


def test_letterbox_preserves_landscape_geometry_and_model_shape():
    image = np.zeros((360, 640, 3), dtype=np.uint8)
    tensor, scale, pad_x, pad_y = letterbox(image)
    assert tensor.shape == (1, 3, 640, 640)
    assert scale == 1.0
    assert pad_x == 0.0
    assert pad_y == 140.0


def test_decoder_filters_pose_candidates_and_normalizes_original_box():
    channels = np.zeros((56, 3), dtype=np.float32)
    channels[:5, 0] = [320, 320, 160, 300, 0.91]
    channels[7::3, 0] = 0.8
    channels[:5, 1] = [322, 321, 158, 298, 0.75]
    channels[7::3, 1] = 0.7
    people = decode(
        channels,
        image_width=640,
        image_height=360,
        scale=1.0,
        pad_x=0.0,
        pad_y=140.0,
        threshold=0.18,
    )
    assert len(people) == 1
    assert people[0]["confidence"] > 0.9
    assert people[0]["visible_keypoints"] == 17
    assert people[0]["box_px"] == [240.0, 30.0, 400.0, 330.0]


def test_tracker_keeps_id_and_only_revises_after_material_motion():
    tracker = StablePersonTracker()
    first = tracker.update([{"box_px": [10, 10, 50, 90], "confidence": 0.8}])[0]
    stable = tracker.update([{"box_px": [11, 10, 51, 90], "confidence": 0.82}])[0]
    moved = tracker.update([{"box_px": [22, 10, 62, 90], "confidence": 0.84}])[0]
    assert first["id"] == stable["id"] == moved["id"]
    assert stable["revision"] == first["revision"]
    assert moved["revision"] > stable["revision"]


def test_bearing_and_iou_are_physical_and_bounded():
    assert bearing_degrees(320, 500, 320) == 0.0
    assert bearing_degrees(420, 500, 320) > 0.0
    assert 0.0 < intersection_over_union([0, 0, 10, 10], [5, 5, 15, 15]) < 1.0
