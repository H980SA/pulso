from __future__ import annotations

import unittest

from pulso_brain_host.models import ImageFrame, RequestedVisual
from pulso_brain_host.state import WorldStateStore

from fixtures import candidates, compressed_image, observation


class WorldStateSchedulingTest(unittest.TestCase):
    def setUp(self):
        self.state = WorldStateStore()
        self.state.update_observation(observation())
        self.state.update_navigation(candidates())
        self.state.consume_decision_request()

    def test_grant_revision_and_order_churn_do_not_request_a_semantic_turn(self):
        refresh = candidates(captured_ns=20_000, revision=8)
        refresh["sensor_map_seq"] = 13
        refresh["valid_until_monotonic_ns"] += 5_000_000_000
        refresh["candidates"].reverse()
        for index, candidate in enumerate(refresh["candidates"]):
            candidate["capability"] = f"rotated_capability_{index:016d}"
            candidate["target_revision"] = 100 + index

        self.state.update_navigation(refresh)

        self.assertFalse(self.state.decision_signal.is_set())

    def test_model_visible_candidate_change_requests_a_semantic_turn(self):
        refresh = candidates(captured_ns=20_000, revision=8)
        refresh["candidates"][0]["risk"] = 0.16

        self.state.update_navigation(refresh)

        self.assertTrue(self.state.decision_signal.is_set())
        self.assertFalse(self.state.consume_decision_request())

    def test_sub_prompt_precision_jitter_is_not_material(self):
        refresh = candidates(captured_ns=20_000, revision=8)
        refresh["candidates"][0]["risk"] = 0.151

        self.state.update_navigation(refresh)

        self.assertFalse(self.state.decision_signal.is_set())

    def test_tracking_loss_is_immediate_but_normal_semantic_change_is_not(self):
        flashlight = observation(captured_ns=20_000)
        flashlight["robot"]["flashlight_on"] = True
        self.state.update_observation(flashlight)
        self.assertFalse(self.state.consume_decision_request())

        self.state.update_observation(observation(captured_ns=30_000, tracking="LOST"))
        self.assertTrue(self.state.immediate_decision_signal.is_set())
        self.assertTrue(self.state.consume_decision_request())
        self.assertFalse(self.state.decision_signal.is_set())
        self.assertFalse(self.state.immediate_decision_signal.is_set())

    def test_requested_visual_bypasses_cooldown_for_its_follow_up_turn(self):
        raw = compressed_image(b"fresh-evidence", 30_000)
        frame = ImageFrame(
            "META_VIEW", "/source", 30_000, "jpeg", b"fresh-evidence", raw
        )

        self.state.set_requested_visual(
            RequestedVisual("META_VIEW", "FRONTIER", "F_A", 7, frame)
        )

        self.assertTrue(self.state.immediate_decision_signal.is_set())
        self.assertTrue(self.state.consume_decision_request())


if __name__ == "__main__":
    unittest.main()
