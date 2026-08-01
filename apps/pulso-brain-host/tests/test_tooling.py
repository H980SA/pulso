from __future__ import annotations

import asyncio
from pathlib import Path
import unittest

from pulso_brain_host.context import select_packet
from pulso_brain_host.models import ImageFrame
from pulso_brain_host.state import WorldStateStore
from pulso_brain_host.tooling import ActionToolExecutor

from fixtures import candidates, compressed_image, observation


class FakeBridge:
    def __init__(self):
        self.actions = []
        self.published = []

    async def publish_action(self, payload, **metadata):
        self.actions.append((payload, metadata))
        if payload["kind"] == "REQUEST_VIEW":
            return {
                "accepted": True,
                "status": "SUCCEEDED",
                "detail": "captured",
                "data": {"request_after_monotonic_ns": 11_000},
            }
        return {"accepted": True, "status": "SUCCEEDED", "detail": "done", "data": {}}

    async def publish_json_string(self, topic, payload):
        self.published.append((topic, payload))


class ToolExecutorTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.state = WorldStateStore()
        self.state.update_observation(observation())
        self.state.update_navigation(candidates())
        self.packet = select_packet(self.state.state)
        self.bridge = FakeBridge()
        self.executor = ActionToolExecutor(
            self.bridge,
            self.state,
            self.packet,
            Path(__file__).parents[1] / "skills",
        )

    async def test_move_uses_opaque_capability_without_putting_it_in_model_args(self):
        result = await self.executor.execute(
            "move_to", {"target_type": "FRONTIER", "target_id": "F_A"}
        )

        payload = self.bridge.actions[0][0]
        self.assertEqual(result["status"], "SUCCEEDED")
        self.assertEqual(payload["candidate_capability"], "capability_1234567890abcd")
        self.assertEqual(payload["expected_navigation_revision"], 7)
        self.assertEqual(payload["expected_tracking_epoch"], 4)

    async def test_redundant_typed_prefix_from_small_model_is_normalized_safely(self):
        result = await self.executor.execute(
            "move_to", {"target_type": "FRONTIER", "target_id": "FRONTIER:F_A"}
        )

        self.assertEqual(result["status"], "SUCCEEDED")
        self.assertEqual(
            self.bridge.actions[0][0]["target"],
            {"type": "FRONTIER", "id": "F_A"},
        )

    async def test_unique_minor_candidate_copy_error_is_repaired_before_dispatch(self):
        result = await self.executor.execute(
            "move_to", {"target_type": "FRONTIER", "target_id": "F_AA"}
        )

        self.assertEqual(result["status"], "SUCCEEDED")
        self.assertEqual(
            self.bridge.actions[0][0]["target"],
            {"type": "FRONTIER", "id": "F_A"},
        )

    async def test_ambiguous_candidate_copy_error_is_rejected(self):
        result = await self.executor.execute(
            "move_to", {"target_type": "FRONTIER", "target_id": "F_C"}
        )

        self.assertEqual(result["status"], "STALE_OR_UNKNOWN_TARGET")
        self.assertEqual(self.bridge.actions, [])

    async def test_stale_revision_rejects_before_publishing(self):
        self.state.update_navigation(candidates(revision=8))
        result = await self.executor.execute(
            "move_to", {"target_type": "FRONTIER", "target_id": "F_A"}
        )

        self.assertEqual(result["status"], "STALE_OR_UNKNOWN_TARGET")
        self.assertEqual(self.bridge.actions, [])

    async def test_request_view_waits_for_a_new_exact_frame(self):
        old_raw = compressed_image(b"old", 10_500)
        await self.state.update_image(ImageFrame("META_VIEW", "/source", 10_500, "jpeg", b"old", old_raw))

        async def publish_fresh():
            await asyncio.sleep(0.01)
            raw = compressed_image(b"fresh-byte-exact", 12_000)
            await self.state.update_image(
                ImageFrame("META_VIEW", "/source", 12_000, "jpeg", b"fresh-byte-exact", raw)
            )

        update = asyncio.create_task(publish_fresh())
        result = await self.executor.execute(
            "request_view",
            {"target_type": "FRONTIER", "target_id": "F_A", "view_kind": "META_VIEW"},
        )
        await update

        self.assertTrue(result["image_ready_next_turn"])
        self.assertEqual(self.state.state.requested_visual.frame.jpeg, b"fresh-byte-exact")
        self.assertEqual(result["jpeg_sha256"], self.state.state.requested_visual.frame.sha256)

    async def test_load_skill_is_information_only(self):
        result = await self.executor.execute(
            "load_skill", {"skill_id": "vio_recovery", "reason": "tracking lost"}
        )

        self.assertEqual(result["status"], "SKILL_LOADED")
        self.assertIn("Stop translation", result["instructions"])
        self.assertEqual(self.bridge.actions, [])
        self.assertEqual(self.bridge.published, [])


if __name__ == "__main__":
    unittest.main()
