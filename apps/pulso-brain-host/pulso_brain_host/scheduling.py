from __future__ import annotations

import asyncio
from enum import Enum
import time
from typing import Callable


class GateWake(str, Enum):
    READY = "READY"
    IMMEDIATE = "IMMEDIATE"
    STOP = "STOP"
    DISCONNECTED = "DISCONNECTED"


class SemanticTurnGate:
    """Bound expensive semantic turns while leaving control events interruptible."""

    def __init__(
        self,
        cooldown_s: float,
        *,
        clock_ns: Callable[[], int] = time.monotonic_ns,
    ) -> None:
        self.cooldown_s = cooldown_s
        self._clock_ns = clock_ns
        self._last_turn_completed_ns: int | None = None

    def mark_turn_completed(self) -> None:
        self._last_turn_completed_ns = self._clock_ns()

    def remaining_s(self) -> float:
        if self._last_turn_completed_ns is None:
            return 0.0
        elapsed_s = (self._clock_ns() - self._last_turn_completed_ns) / 1_000_000_000
        return max(0.0, self.cooldown_s - elapsed_s)

    async def wait_until_admitted(
        self,
        immediate_signal: asyncio.Event,
        stop_event: asyncio.Event,
        disconnected: asyncio.Event,
    ) -> GateWake:
        remaining_s = self.remaining_s()
        if remaining_s <= 0:
            return GateWake.READY

        immediate_task = asyncio.create_task(immediate_signal.wait())
        stop_task = asyncio.create_task(stop_event.wait())
        disconnect_task = asyncio.create_task(disconnected.wait())
        tasks = {immediate_task, stop_task, disconnect_task}
        done, pending = await asyncio.wait(
            tasks,
            timeout=remaining_s,
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        if not done:
            return GateWake.READY
        if stop_task in done:
            return GateWake.STOP
        if disconnect_task in done:
            return GateWake.DISCONNECTED
        return GateWake.IMMEDIATE
