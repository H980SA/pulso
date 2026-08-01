"""Canonical perception health contract shared by simulated sensors."""

from __future__ import annotations


VALID_STATUSES = frozenset({"WARMING", "LIVE", "ERROR"})


def build_perception_telemetry(
    *,
    published_ns: int,
    source_capture_ns: int,
    model_id: str,
    provider: str,
    status: str,
    detection_count: int,
    inference_latency_ms: float,
    semantic_revision: int,
) -> dict:
    normalized_status = status.upper()
    if normalized_status not in VALID_STATUSES:
        raise ValueError(f"Unsupported perception status: {status}")
    return {
        "contract_version": "pulso.perception-telemetry.v1",
        "published_monotonic_ns": max(0, int(published_ns)),
        "source_capture_ns": max(0, int(source_capture_ns)),
        "model_id": str(model_id),
        "provider": str(provider),
        "status": normalized_status,
        "detection_count": max(0, int(detection_count)),
        "inference_latency_ms": max(0, int(round(inference_latency_ms))),
        "semantic_revision": max(0, int(semantic_revision)),
    }
