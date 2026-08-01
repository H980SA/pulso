import pytest

from pulso_sim_adapter.perception_telemetry import build_perception_telemetry


def test_builds_the_closed_v1_contract_with_gpu_provenance():
    payload = build_perception_telemetry(
        published_ns=123,
        source_capture_ns=98,
        model_id="yolo11n-pose-onnx",
        provider="CUDAExecutionProvider",
        status="live",
        detection_count=2,
        inference_latency_ms=8.6,
        semantic_revision=7,
    )
    assert payload == {
        "contract_version": "pulso.perception-telemetry.v1",
        "published_monotonic_ns": 123,
        "source_capture_ns": 98,
        "model_id": "yolo11n-pose-onnx",
        "provider": "CUDAExecutionProvider",
        "status": "LIVE",
        "detection_count": 2,
        "inference_latency_ms": 9,
        "semantic_revision": 7,
    }


def test_rejects_noncanonical_ready_status():
    with pytest.raises(ValueError):
        build_perception_telemetry(
            published_ns=0,
            source_capture_ns=0,
            model_id="model",
            provider="CPUExecutionProvider",
            status="READY",
            detection_count=0,
            inference_latency_ms=0,
            semantic_revision=0,
        )
