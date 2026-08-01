from __future__ import annotations

import asyncio
import unittest

from pulso_brain_host.scheduling import GateWake, SemanticTurnGate


class SemanticTurnGateTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.now_ns = 10_000_000_000
        self.gate = SemanticTurnGate(8.0, clock_ns=lambda: self.now_ns)

    async def test_first_turn_is_immediate_then_cooldown_is_bounded(self):
        self.assertEqual(self.gate.remaining_s(), 0.0)
        self.gate.mark_turn_completed()
        self.assertEqual(self.gate.remaining_s(), 8.0)

        self.now_ns += 3_000_000_000
        self.assertEqual(self.gate.remaining_s(), 5.0)
        self.now_ns += 6_000_000_000
        self.assertEqual(self.gate.remaining_s(), 0.0)

    async def test_immediate_priority_signal_interrupts_semantic_cooldown(self):
        self.gate.mark_turn_completed()
        immediate = asyncio.Event()
        stop = asyncio.Event()
        disconnected = asyncio.Event()
        waiting = asyncio.create_task(
            self.gate.wait_until_admitted(immediate, stop, disconnected)
        )
        await asyncio.sleep(0)

        immediate.set()

        self.assertEqual(await asyncio.wait_for(waiting, timeout=1), GateWake.IMMEDIATE)

    async def test_stop_and_disconnect_are_not_delayed_by_semantic_cooldown(self):
        self.gate.mark_turn_completed()
        immediate = asyncio.Event()
        stop = asyncio.Event()
        disconnected = asyncio.Event()
        stop.set()
        self.assertEqual(
            await self.gate.wait_until_admitted(immediate, stop, disconnected),
            GateWake.STOP,
        )

        stop.clear()
        disconnected.set()
        self.assertEqual(
            await self.gate.wait_until_admitted(immediate, stop, disconnected),
            GateWake.DISCONNECTED,
        )


if __name__ == "__main__":
    unittest.main()
