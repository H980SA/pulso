from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import time
from typing import Any
from uuid import uuid4

from .models import ImageFrame
from .rosbridge import BRAIN_TRACE_TOPIC, GEMMA_INPUT_TOPIC, GEMMA_VIEW_TOPIC, RosbridgeClient


@dataclass(frozen=True)
class InputEvidence:
    turn_id: str
    world_seq: int
    input_kind: str
    exact_message: dict[str, Any]
    prompt_text: str | None
    image: ImageFrame | None
    context_tokens_before: int | None


class TelemetryPublisher:
    def __init__(
        self,
        bridge: RosbridgeClient,
        *,
        model_id: str,
        system_prompt: str,
        tool_schemas: list[dict[str, Any]],
    ) -> None:
        if not model_id.strip():
            raise ValueError("model_id must identify the configured artifact")
        self.bridge = bridge
        self.model_id = model_id
        self.system_prompt = system_prompt
        self.tool_schemas = tool_schemas
        canonical_tools = json.dumps(tool_schemas, sort_keys=True, separators=(",", ":"))
        self.system_prompt_sha256 = sha256(system_prompt.encode("utf-8")).hexdigest()
        self.tool_schemas_sha256 = sha256(canonical_tools.encode("utf-8")).hexdigest()

    async def trace(
        self,
        *,
        turn_id: str | None,
        world_seq: int | None,
        category: str,
        label: str,
        summary: str,
        latency_ms: int | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> None:
        safe_attributes = _public_attributes(attributes or {})
        payload: dict[str, Any] = {
            "contract_version": "pulso.brain-trace.v1",
            "event_id": f"BT-{uuid4().hex[:20]}",
            "captured_monotonic_ns": time.monotonic_ns(),
            "category": category,
            "label": _one_line(label, 160),
            "summary": _one_line(summary, 900),
            "attributes": safe_attributes,
        }
        if turn_id:
            payload["turn_id"] = turn_id
        if world_seq is not None:
            payload["selected_world_seq"] = world_seq
        if latency_ms is not None:
            payload["latency_ms"] = max(0, int(latency_ms))
        await self.bridge.publish_json_string(BRAIN_TRACE_TOPIC, payload)

    async def publish_input(self, evidence: InputEvidence) -> None:
        image_meta = None
        if evidence.image is not None:
            image_meta = {
                "kind": evidence.image.kind,
                "source_topic": evidence.image.source_topic,
                "captured_monotonic_ns": evidence.image.captured_ns,
                "format": evidence.image.format,
                "jpeg_sha256": evidence.image.sha256,
                "byte_length": len(evidence.image.jpeg),
                "audit_topic": GEMMA_VIEW_TOPIC,
            }
        payload: dict[str, Any] = {
            "contract_version": "pulso.gemma-input.v1",
            "input_id": f"GI-{uuid4().hex[:20]}",
            "published_monotonic_ns": time.monotonic_ns(),
            "turn_id": evidence.turn_id,
            "selected_world_seq": evidence.world_seq,
            "model_id": self.model_id,
            "input_kind": evidence.input_kind,
            "exact_message": _message_without_image_blob(evidence.exact_message),
            "prompt_text": evidence.prompt_text,
            "image": image_meta,
            "system_prompt": self.system_prompt,
            "system_prompt_sha256": self.system_prompt_sha256,
            "tool_schemas": self.tool_schemas,
            "tool_schemas_sha256": self.tool_schemas_sha256,
            "conversation_scope": "TURN",
            "conversation_reused_within_turn": True,
            "conversation_reused_across_turns": False,
        }
        if evidence.context_tokens_before is not None:
            payload["context_tokens_before"] = max(0, evidence.context_tokens_before)
        await self.bridge.publish_json_string(GEMMA_INPUT_TOPIC, payload)
        if evidence.image is not None:
            # Metadata opens the dashboard turn; the exact JPEG then fills it.
            await self.bridge.publish_message(GEMMA_VIEW_TOPIC, evidence.image.ros_message)


def public_tool_arguments(name: str, values: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "move_to": {"target_type", "target_id"},
        "look_at": {"target_type", "target_id"},
        "request_view": {"target_type", "target_id", "view_kind"},
        "stop": set(),
        "set_flashlight": {"enabled"},
        "load_skill": {"skill_id", "reason"},
    }.get(name, set())
    return _public_attributes({key: value for key, value in values.items() if key in allowed})


def public_tool_result(values: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "accepted",
        "status",
        "detail",
        "action_id",
        "target_id",
        "candidate_id",
        "navigation_revision",
        "reason",
        "enabled",
        "skill_id",
        "artifact_topic",
        "view_kind",
        "artifact_capture_ns",
        "jpeg_sha256",
        "image_ready_next_turn",
    }
    return _public_attributes({key: value for key, value in values.items() if key in allowed})


def _public_attributes(values: dict[str, Any]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in list(values.items())[:16]:
        if isinstance(value, bool):
            output[str(key)] = value
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            output[str(key)] = value
        elif isinstance(value, str):
            output[str(key)] = _one_line(value, 360 if key == "detail" else 160)
    return output


def _one_line(value: str, limit: int) -> str:
    return " ".join(value.split())[:limit]


def _message_without_image_blob(message: dict[str, Any]) -> dict[str, Any]:
    """Keep exact text/order; the byte-exact JPEG is emitted on GEMMA_VIEW_TOPIC."""
    content = message.get("content")
    if not isinstance(content, list):
        return message
    projected: list[Any] = []
    for item in content:
        if isinstance(item, dict) and item.get("type") == "image" and "blob" in item:
            raw = item["blob"]
            projected.append(
                {
                    "type": "image",
                    "bytes_transport": GEMMA_VIEW_TOPIC,
                    "base64_length": len(raw) if isinstance(raw, str) else None,
                }
            )
        else:
            projected.append(item)
    return {**message, "content": projected}
