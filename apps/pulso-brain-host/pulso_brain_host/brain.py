from __future__ import annotations

import base64
from pathlib import Path
import time
from typing import Any
from uuid import uuid4

from .context import GOAL_ID, select_packet
from .model import NativeModelSession, parse_tool_calls, public_response_text
from .models import SelectedPacket
from .state import WorldStateStore
from .telemetry import (
    InputEvidence,
    TelemetryPublisher,
    public_tool_arguments,
    public_tool_result,
)
from .tooling import ActionToolExecutor


FRESH_PACKET_STATUSES = frozenset(
    {
        "STALE_OR_UNKNOWN_TARGET",
        "STALE_CAPABILITY",
        "EXPIRED_CAPABILITY",
        "STALE_NAVIGATION_REVISION",
        "STALE_TRACKING_EPOCH",
        "STALE_TARGET_REVISION",
        "TARGET_TOO_CLOSE",
    }
)


class BrainController:
    def __init__(
        self,
        model: NativeModelSession,
        telemetry: TelemetryPublisher,
        state: WorldStateStore,
        bridge,
        skills_dir: Path,
        max_tool_calls: int,
    ) -> None:
        self.model = model
        self.telemetry = telemetry
        self.state = state
        self.bridge = bridge
        self.skills_dir = skills_dir
        self.max_tool_calls = max_tool_calls

    async def run_decision(self) -> None:
        packet = select_packet(self.state.state)
        turn_id = f"T-{uuid4().hex[:16]}"
        started = time.monotonic_ns()
        used_tools = 0
        await self.model.start_turn()
        try:
            await self.telemetry.trace(
                turn_id=turn_id,
                world_seq=packet.world_seq,
                category="CONTEXT",
                label="WorldPacket selected",
                summary=f"{packet.decision_need} · {len(packet.candidates)} current candidates",
                attributes={
                    "candidate_count": len(packet.candidates),
                    "decision_need": packet.decision_need,
                    "goal_id": GOAL_ID,
                    "checkpoint": f"{len(packet.memory.durable_findings)} findings",
                    "question": packet.memory.question,
                    "plan_summary": packet.memory.plan_summary,
                    **(
                        {"active_skill_id": packet.memory.active_skill_id}
                        if packet.memory.active_skill_id
                        else {}
                    ),
                },
            )
            response = await self._send_with_evidence(
                turn_id=turn_id,
                packet=packet,
                input_kind="WORLD_PACKET",
                message=_world_message(packet),
                prompt_text=packet.prompt_text,
            )
            executor = ActionToolExecutor(self.bridge, self.state, packet, self.skills_dir)
            while True:
                calls = parse_tool_calls(response)
                if not calls:
                    break
                remaining = self.max_tool_calls - used_tools
                if remaining <= 0:
                    await self.telemetry.trace(
                        turn_id=turn_id,
                        world_seq=packet.world_seq,
                        category="ERROR",
                        label="Tool budget",
                        summary="Tool-call budget exhausted; physical loop stopped for this turn.",
                    )
                    break
                tool_messages: list[dict[str, Any]] = []
                fresh_packet_status: str | None = None
                for call in calls[:remaining]:
                    used_tools += 1
                    safe_args = public_tool_arguments(call.name, call.arguments)
                    await self.telemetry.trace(
                        turn_id=turn_id,
                        world_seq=packet.world_seq,
                        category="TOOL_REQUEST",
                        label=call.name,
                        summary=_summary(safe_args, "No public arguments"),
                        attributes=safe_args,
                    )
                    result_started = time.monotonic_ns()
                    result = await executor.execute(call.name, call.arguments)
                    latency_ms = (time.monotonic_ns() - result_started) // 1_000_000
                    safe_result = public_tool_result(result)
                    await self.telemetry.trace(
                        turn_id=turn_id,
                        world_seq=packet.world_seq,
                        category="TOOL_RESULT",
                        label=call.name,
                        summary=_summary(safe_result, "Tool completed"),
                        latency_ms=latency_ms,
                        attributes=safe_result,
                    )
                    tool_messages.append(
                        {"type": "tool_response", "name": call.name, "response": result}
                    )
                    status = result.get("status")
                    if isinstance(status, str) and status in FRESH_PACKET_STATUSES:
                        fresh_packet_status = status
                        break
                response = await self._send_with_evidence(
                    turn_id=turn_id,
                    packet=packet,
                    input_kind="TOOL_RESULT",
                    message={"role": "tool", "content": tool_messages},
                    prompt_text=None,
                )
                if fresh_packet_status is not None:
                    self.state.request_fresh_packet_turn()
                    await self.telemetry.trace(
                        turn_id=turn_id,
                        world_seq=self.state.state.world_seq,
                        category="CONTEXT",
                        label="Fresh packet scheduled",
                        summary=(
                            f"{fresh_packet_status} ended this turn after one reported tool "
                            "result; one current WorldPacket turn is pending."
                        ),
                        attributes={"status": fresh_packet_status},
                    )
                    break
            final_text = public_response_text(response)
            if final_text:
                await self.telemetry.trace(
                    turn_id=turn_id,
                    world_seq=packet.world_seq,
                    category="MODEL_RESPONSE",
                    label="Gemma decision",
                    summary=final_text,
                )
            elapsed_ms = (time.monotonic_ns() - started) // 1_000_000
            await self.telemetry.trace(
                turn_id=turn_id,
                world_seq=packet.world_seq,
                category="CYCLE_COMPLETE",
                label="Decision cycle complete",
                summary=f"{elapsed_ms}ms end to end · {used_tools} tool calls",
                latency_ms=elapsed_ms,
                attributes={"tool_calls": used_tools},
            )
            self.state.consume_requested_visual(packet.visual)
        finally:
            await self.model.end_turn()

    async def _send_with_evidence(
        self,
        *,
        turn_id: str,
        packet: SelectedPacket,
        input_kind: str,
        message: dict[str, Any],
        prompt_text: str | None,
    ) -> dict[str, Any]:
        tokens = await self.model.token_count()
        image = packet.visual.frame if input_kind == "WORLD_PACKET" and packet.visual else None
        await self.telemetry.publish_input(
            InputEvidence(
                turn_id=turn_id,
                world_seq=packet.world_seq,
                input_kind=input_kind,
                exact_message=message,
                prompt_text=prompt_text,
                image=image,
                context_tokens_before=tokens,
            )
        )
        return await self.model.send(message)


def _world_message(packet: SelectedPacket) -> dict[str, Any]:
    content: list[dict[str, Any]] = [{"type": "text", "text": packet.prompt_text}]
    if packet.visual is not None:
        content.append(
            {
                "type": "image",
                "blob": base64.b64encode(packet.visual.frame.jpeg).decode("ascii"),
            }
        )
    return {"role": "user", "content": content}


def _summary(values: dict[str, Any], fallback: str) -> str:
    if not values:
        return fallback
    return " · ".join(f"{key}={value}" for key, value in values.items())
