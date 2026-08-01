from __future__ import annotations

import asyncio
import json
import logging
import unittest

from pulso_brain_host.rosbridge import (
    ACTION_RESULT_TOPIC,
    CANDIDATES_TOPIC,
    METAVIEW_TOPIC,
    OBSERVATION_TOPIC,
    RosbridgeClient,
)
from pulso_brain_host.state import WorldStateStore

from fixtures import candidates, compressed_image, observation, ros_frame, std_frame


class FakeWebSocket:
    def __init__(self):
        self.sent: list[dict] = []
        self.closed = False
        self.queue: asyncio.Queue[str | None] = asyncio.Queue()

    async def send(self, value: str):
        self.sent.append(json.loads(value))

    def __aiter__(self):
        return self

    async def __anext__(self):
        value = await self.queue.get()
        if value is None:
            raise StopAsyncIteration
        return value

    async def close(self):
        self.closed = True
        await self.queue.put(None)


class RosbridgeClientTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.socket = FakeWebSocket()

        async def connect(_url, **_kwargs):
            return self.socket

        self.state = WorldStateStore()
        self.client = RosbridgeClient("ws://test", self.state, connect)
        await self.client.connect()

    async def asyncTearDown(self):
        await self.client.close()

    async def test_fake_websocket_updates_real_contract_state_and_exact_jpeg(self):
        await self.client.handle_raw(std_frame(OBSERVATION_TOPIC, observation()))
        await self.client.handle_raw(std_frame(CANDIDATES_TOPIC, candidates()))
        await self.client.handle_raw(
            ros_frame(METAVIEW_TOPIC, compressed_image(b"same-jpeg-bytes", 11_000))
        )

        self.assertTrue(self.state.state.ready)
        self.assertEqual(self.state.state.images["META_VIEW"].jpeg, b"same-jpeg-bytes")
        advertised = {item.get("topic") for item in self.socket.sent if item.get("op") == "advertise"}
        self.assertIn("/pulso/hil/gemma_input", advertised)
        self.assertIn("/pulso/hil/gemma_view/compressed", advertised)

    async def test_action_waits_for_terminal_result_not_active(self):
        task = asyncio.create_task(
            self.client.publish_action(
                {"action_id": "A-1"}, kind="MOVE_TO", target_id="F_A", timeout_s=1
            )
        )
        await asyncio.sleep(0)
        await self.client.handle_raw(
            std_frame(
                ACTION_RESULT_TOPIC,
                {"action_id": "A-1", "accepted": True, "status": "ACTIVE", "detail": "moving"},
            )
        )
        self.assertFalse(task.done())
        await self.client.handle_raw(
            std_frame(
                ACTION_RESULT_TOPIC,
                {"action_id": "A-1", "accepted": True, "status": "SUCCEEDED", "detail": "arrived"},
            )
        )
        result = await task
        self.assertEqual(result["status"], "SUCCEEDED")
        self.assertIn("arrived", self.state.state.memory.last_action_summary)

    async def test_remote_close_sets_reconnect_signal(self):
        with self.assertLogs("pulso_brain_host.rosbridge", logging.WARNING) as captured:
            await self.socket.queue.put(None)
            await asyncio.wait_for(self.client.disconnected.wait(), timeout=1)

        self.assertTrue(self.client.disconnected.is_set())
        self.assertIn("connection closed by peer", "\n".join(captured.output))


if __name__ == "__main__":
    unittest.main()
