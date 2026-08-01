from __future__ import annotations

import asyncio
from dataclasses import replace
from typing import Any

from .context import navigation_decision_signature, parse_navigation, parse_observation
from .models import ImageFrame, LiveState, RequestedVisual


class WorldStateStore:
    """Single-event-loop owner of live HIL evidence and compact mission memory."""

    def __init__(self) -> None:
        self.state = LiveState()
        self.decision_signal = asyncio.Event()
        self.immediate_decision_signal = asyncio.Event()
        self._image_condition = asyncio.Condition()

    def update_observation(self, payload: dict[str, Any]) -> None:
        robot = parse_observation(payload)
        previous = self.state.robot
        self.state.robot = robot
        self.state.world_seq += 1
        changed = previous is None or (
            previous.tracking_state != robot.tracking_state
            or previous.tracking_epoch != robot.tracking_epoch
            or previous.motion_state != robot.motion_state
            or previous.flashlight_on != robot.flashlight_on
        )
        if changed:
            immediate = previous is not None and (
                previous.tracking_epoch != robot.tracking_epoch
                or (
                    previous.tracking_state != robot.tracking_state
                    and robot.tracking_state in {"LOST", "LIMITED"}
                )
            )
            self._request_decision(immediate=immediate)

    def update_navigation(self, payload: dict[str, Any]) -> None:
        navigation = parse_navigation(payload)
        previous = self.state.navigation
        self.state.navigation = navigation
        self.state.world_seq += 1
        if previous is None or (
            navigation_decision_signature(previous)
            != navigation_decision_signature(navigation)
        ):
            self._request_decision()

    async def update_image(self, frame: ImageFrame) -> None:
        async with self._image_condition:
            self.state.images[frame.kind] = frame
            self._image_condition.notify_all()

    async def wait_for_image_after(
        self,
        kind: str,
        baseline_ns: int,
        minimum_ns: int,
        timeout_s: float,
    ) -> ImageFrame:
        def fresh() -> ImageFrame | None:
            frame = self.state.images.get(kind)
            if frame and frame.captured_ns > baseline_ns and frame.captured_ns >= minimum_ns:
                return frame
            return None

        async def wait() -> ImageFrame:
            async with self._image_condition:
                while (frame := fresh()) is None:
                    await self._image_condition.wait()
                return frame

        return await asyncio.wait_for(wait(), timeout=timeout_s)

    def set_requested_visual(self, visual: RequestedVisual) -> None:
        self.state.requested_visual = visual
        self.state.world_seq += 1
        # A requested capture is the evidence the current turn explicitly
        # waited for; admit its one follow-up turn without thermal cooldown.
        self._request_decision(immediate=True)

    def consume_requested_visual(self, expected: RequestedVisual | None) -> None:
        if expected is not None and self.state.requested_visual == expected:
            self.state.requested_visual = None

    def record_action_result(
        self,
        *,
        kind: str,
        target_id: str | None,
        status: str,
        detail: str,
    ) -> None:
        summary = " · ".join(part for part in (kind, target_id, status, detail) if part)
        memory = self.state.memory
        rejected = memory.rejected_alternatives
        findings = memory.durable_findings
        if status == "BLOCKED" and target_id:
            rejected = (*rejected, f"{target_id} bloqueado: {detail}")[-6:]
        elif status == "SUCCEEDED" and kind in {"MOVE_TO", "LOOK_AT"}:
            findings = (*findings, f"{kind} {target_id or ''} completado: {detail}")[-8:]
        self.state.memory = replace(
            memory,
            last_action_summary=summary,
            durable_findings=findings,
            rejected_alternatives=rejected,
        )
        self.state.world_seq += 1
        self._request_decision()

    def record_skill(self, skill_id: str) -> None:
        self.state.memory = replace(self.state.memory, active_skill_id=skill_id)
        self.state.world_seq += 1

    def request_fresh_packet_turn(self) -> None:
        """Coalesce any number of freshness failures into one semantic turn."""
        self._request_decision()

    def consume_decision_request(self) -> bool:
        """Clear the coalesced request and return whether it bypasses cooldown."""
        immediate = self.immediate_decision_signal.is_set()
        self.decision_signal.clear()
        self.immediate_decision_signal.clear()
        return immediate

    def clear_decision_signal(self) -> None:
        """Backward-compatible clear for callers that do not need priority."""
        self.consume_decision_request()

    def reset_live_inputs(self) -> None:
        """Invalidate geometry and images after a transport/session boundary."""
        self.state.robot = None
        self.state.navigation = None
        self.state.images.clear()
        self.state.requested_visual = None
        self.state.world_seq += 1
        self.decision_signal.clear()
        self.immediate_decision_signal.clear()

    def latest_image_ns(self, kind: str) -> int:
        frame = self.state.images.get(kind)
        return frame.captured_ns if frame else -1

    def is_ready_and_idle(self) -> bool:
        return self.state.ready and self.state.robot is not None and (
            self.state.robot.motion_state != "MOVING"
        )

    def _request_decision(self, *, immediate: bool = False) -> None:
        self.decision_signal.set()
        if immediate:
            self.immediate_decision_signal.set()
