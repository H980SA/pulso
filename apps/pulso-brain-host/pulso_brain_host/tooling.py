from __future__ import annotations

import asyncio
from dataclasses import dataclass
import time
from typing import Any
from uuid import uuid4

from .context import MISSION_ID
from .models import Candidate, RequestedVisual, SelectedPacket
from .prompts import SKILL_CATALOG, load_skill
from .rosbridge import ACTION_INTENT_TOPIC, RosbridgeClient
from .state import WorldStateStore


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]

    def openapi(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


def tool_specs() -> tuple[ToolSpec, ...]:
    def targeted(*target_types: str) -> dict[str, Any]:
        return {
        "type": "object",
        "properties": {
            "target_type": {
                "type": "string",
                "enum": list(target_types),
                "description": "Exact type shown beside the candidate ID.",
            },
            "target_id": {
                "type": "string",
                "description": "Exact ID value after the colon; do not repeat the target_type prefix.",
            },
        },
        "required": ["target_type", "target_id"],
        }
    move_target = targeted("FRONTIER")
    look_target = targeted("VIEWPOINT", "TARGET", "ANCHOR")
    view_target = targeted("VIEWPOINT", "FRONTIER", "TARGET", "ANCHOR")
    return (
        ToolSpec("move_to", "Translate safely to a current FRONTIER ID only.", move_target),
        ToolSpec("look_at", "Rotate toward a current VIEWPOINT, TARGET, or ANCHOR ID.", look_target),
        ToolSpec(
            "request_view",
            "Capture a fresh MetaView or ego camera view for a current candidate ID.",
            {
                "type": "object",
                "properties": {
                    **view_target["properties"],
                    "view_kind": {
                        "type": "string",
                        "enum": ["META_VIEW", "CANDIDATE_VIEW", "TARGET_VIEW"],
                    },
                },
                "required": ["target_type", "target_id", "view_kind"],
            },
        ),
        ToolSpec(
            "stop",
            "Stop rover motion and confirm the navigation controller accepted it.",
            {"type": "object", "properties": {}, "required": []},
        ),
        ToolSpec(
            "set_flashlight",
            "Turn the phone flashlight on or off and return confirmed actuator state.",
            {
                "type": "object",
                "properties": {"enabled": {"type": "boolean"}},
                "required": ["enabled"],
            },
        ),
        ToolSpec(
            "load_skill",
            "Load temporary procedural information; this does not actuate the rover.",
            {
                "type": "object",
                "properties": {
                    "skill_id": {"type": "string", "enum": list(SKILL_CATALOG)},
                    "reason": {"type": "string"},
                },
                "required": ["skill_id", "reason"],
            },
        ),
    )


class ActionToolExecutor:
    def __init__(
        self,
        bridge: RosbridgeClient,
        state: WorldStateStore,
        packet: SelectedPacket,
        skills_dir,
    ) -> None:
        self.bridge = bridge
        self.state = state
        self.packet = packet
        self.skills_dir = skills_dir

    async def execute(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name == "load_skill":
            return self._load_skill(arguments)
        if name == "stop":
            return await self._dispatch("STOP", None, {}, timeout_s=5.0)
        if name == "set_flashlight":
            enabled = arguments.get("enabled")
            if not isinstance(enabled, bool):
                return _failure("INVALID_ARGUMENT", "enabled must be boolean")
            return await self._dispatch(
                "SET_FLASHLIGHT", None, {"enabled": enabled}, timeout_s=5.0
            )
        if name not in {"move_to", "look_at", "request_view"}:
            return _failure("UNKNOWN_TOOL", f"Unknown tool: {name}")
        candidate = self._current_candidate(arguments)
        if isinstance(candidate, dict):
            return candidate
        if name == "move_to" and candidate.target_type not in {"FRONTIER", "VIEWPOINT"}:
            return _failure("INVALID_TARGET", "move_to requires FRONTIER or VIEWPOINT")
        if name == "look_at" and candidate.target_type not in {"TARGET", "VIEWPOINT", "ANCHOR"}:
            return _failure("INVALID_TARGET", "look_at requires TARGET, VIEWPOINT, or ANCHOR")
        if name == "request_view":
            return await self._request_view(candidate, arguments)
        kind = "MOVE_TO" if name == "move_to" else "LOOK_AT"
        timeout = 65.0 if kind == "MOVE_TO" else 20.0
        return await self._dispatch(kind, candidate, {}, timeout_s=timeout)

    def _current_candidate(self, arguments: dict[str, Any]) -> Candidate | dict[str, Any]:
        target_type = arguments.get("target_type")
        target_id = arguments.get("target_id")
        if not isinstance(target_type, str) or not isinstance(target_id, str):
            return _failure("INVALID_TARGET", "Use an exact typed candidate from WorldPacket")
        normalized_type = target_type.strip().upper()
        raw_id = target_id.strip()
        typed_prefix = f"{normalized_type}:"
        normalized_id = (
            raw_id[len(typed_prefix) :]
            if raw_id.upper().startswith(typed_prefix)
            else raw_id
        )
        selected = self.packet.candidate(normalized_type, normalized_id)
        if selected is None:
            selected = _unique_near_candidate(
                self.packet.candidates,
                normalized_type,
                normalized_id,
            )
        navigation = self.state.state.navigation
        if selected is None or navigation is None:
            return _failure(
                "STALE_OR_UNKNOWN_TARGET",
                f"{normalized_type}:{normalized_id} is unavailable",
            )
        current = next(
            (
                item
                for item in navigation.candidates
                if item.target_type == selected.target_type and item.target_id == selected.target_id
            ),
            None,
        )
        if (
            current is None
            or navigation.navigation_revision != self.packet.navigation_revision
            or current.capability != selected.capability
            or self.state.state.robot is None
            or self.state.state.robot.tracking_epoch != self.packet.tracking_epoch
        ):
            return _failure(
                "STALE_OR_UNKNOWN_TARGET",
                f"{normalized_type}:{normalized_id} changed after packet selection",
            )
        return current

    async def _request_view(
        self, candidate: Candidate, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        view_kind = arguments.get("view_kind")
        if view_kind not in {"META_VIEW", "CANDIDATE_VIEW", "TARGET_VIEW"}:
            return _failure("INVALID_ARGUMENT", "Unknown view_kind")
        image_kind = "META_VIEW" if view_kind == "META_VIEW" else "EGO_RGB"
        baseline_ns = self.state.latest_image_ns(image_kind)
        result = await self._dispatch(
            "REQUEST_VIEW", candidate, {"view_kind": view_kind}, timeout_s=5.0
        )
        if not result.get("accepted") or result.get("status") != "SUCCEEDED":
            return result
        minimum_ns = int(result.get("data", {}).get("request_after_monotonic_ns", -1))
        try:
            frame = await self.state.wait_for_image_after(
                image_kind, baseline_ns, minimum_ns, timeout_s=3.0
            )
        except asyncio.TimeoutError:
            return _failure(
                "VIEW_CAPTURE_TIMEOUT",
                f"No fresh {view_kind} frame arrived after the real request",
            )
        visual = RequestedVisual(
            view_kind=view_kind,
            target_type=candidate.target_type,
            target_id=candidate.target_id,
            navigation_revision=self.packet.navigation_revision,
            frame=frame,
        )
        self.state.set_requested_visual(visual)
        return {
            **result,
            "view_kind": view_kind,
            "artifact_capture_ns": frame.captured_ns,
            "jpeg_sha256": frame.sha256,
            "image_ready_next_turn": True,
        }

    async def _dispatch(
        self,
        kind: str,
        candidate: Candidate | None,
        parameters: dict[str, Any],
        *,
        timeout_s: float,
    ) -> dict[str, Any]:
        action_id = f"BH-{uuid4().hex[:20]}"
        payload: dict[str, Any] = {
            "contract_version": "pulso.action.v1",
            "action_id": action_id,
            "mission_id": MISSION_ID,
            "issued_monotonic_ns": time.monotonic_ns(),
            "kind": kind,
            "target": None,
            "parameters": parameters,
        }
        if candidate is not None:
            payload.update(
                {
                    "target": {"type": candidate.target_type, "id": candidate.target_id},
                    "candidate_capability": candidate.capability,
                    "expected_navigation_revision": self.packet.navigation_revision,
                    "expected_tracking_epoch": self.packet.tracking_epoch,
                    "expected_target_revision": candidate.target_revision,
                }
            )
        try:
            result = await self.bridge.publish_action(
                payload,
                kind=kind,
                target_id=candidate.target_id if candidate else None,
                timeout_s=timeout_s,
            )
        except asyncio.TimeoutError:
            if kind in {"MOVE_TO", "LOOK_AT"}:
                await self._best_effort_stop("brain_action_timeout")
            return _failure(
                "ACTION_RESULT_TIMEOUT",
                f"No terminal {kind} result arrived in {timeout_s:.0f}s",
                action_id=action_id,
            )
        return {**result, "action_id": action_id}

    async def _best_effort_stop(self, reason: str) -> None:
        payload = {
            "contract_version": "pulso.action.v1",
            "action_id": f"STOP-{uuid4().hex[:20]}",
            "mission_id": MISSION_ID,
            "issued_monotonic_ns": time.monotonic_ns(),
            "kind": "STOP",
            "target": None,
            "parameters": {"reason": reason},
        }
        await self.bridge.publish_json_string(ACTION_INTENT_TOPIC, payload)

    def _load_skill(self, arguments: dict[str, Any]) -> dict[str, Any]:
        skill_id = arguments.get("skill_id")
        reason = arguments.get("reason")
        if not isinstance(skill_id, str) or not isinstance(reason, str) or not reason.strip():
            return _failure("INVALID_ARGUMENT", "skill_id and reason are required")
        skill = load_skill(self.skills_dir, skill_id)
        if skill is None:
            return _failure("UNKNOWN_SKILL", f"Unknown skill: {skill_id}")
        self.state.record_skill(skill_id)
        return {
            "accepted": True,
            "status": "SKILL_LOADED",
            "detail": "Procedural information loaded into this conversation.",
            "skill_id": skill.skill_id,
            "when_useful": skill.when_useful,
            "instructions": skill.instructions,
        }


def _failure(status: str, detail: str, **extra: Any) -> dict[str, Any]:
    return {"accepted": False, "status": status, "detail": detail, **extra}


def _unique_near_candidate(
    candidates: tuple[Candidate, ...], target_type: str, target_id: str
) -> Candidate | None:
    """Repair a minor small-model copy error only when resolution is unique.

    The candidate capability and live revision are still checked after this
    lookup.  Ambiguous IDs are never guessed, which keeps fuzzy text handling
    outside the physical authorization boundary.
    """
    typed = [item for item in candidates if item.target_type == target_type]
    if not typed:
        return None
    limit = 2 if len(target_id) >= 8 else 1
    ranked = sorted(
        ((_edit_distance(target_id, item.target_id, limit), item) for item in typed),
        key=lambda pair: pair[0],
    )
    best_distance, best = ranked[0]
    if best_distance > limit:
        return None
    if len(ranked) > 1 and ranked[1][0] == best_distance:
        return None
    return best


def _edit_distance(left: str, right: str, cutoff: int) -> int:
    """Bounded Levenshtein distance; values above cutoff collapse to cutoff+1."""
    if left == right:
        return 0
    if abs(len(left) - len(right)) > cutoff:
        return cutoff + 1
    previous = list(range(len(right) + 1))
    for row, left_char in enumerate(left, start=1):
        current = [row]
        row_minimum = row
        for column, right_char in enumerate(right, start=1):
            value = min(
                current[-1] + 1,
                previous[column] + 1,
                previous[column - 1] + (left_char != right_char),
            )
            current.append(value)
            row_minimum = min(row_minimum, value)
        if row_minimum > cutoff:
            return cutoff + 1
        previous = current
    return previous[-1]
