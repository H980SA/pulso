from __future__ import annotations

import unittest

from pulso_brain_host.context import select_packet
from pulso_brain_host.models import ImageFrame, RequestedVisual
from pulso_brain_host.state import WorldStateStore

from fixtures import candidates, compressed_image, observation


class ContextSelectorTest(unittest.TestCase):
    def setUp(self):
        self.state = WorldStateStore()
        self.state.update_observation(observation())
        self.state.update_navigation(candidates())

    def test_selects_current_candidates_without_capabilities_in_prompt(self):
        packet = select_packet(self.state.state)

        self.assertEqual(packet.decision_need, "CHOOSE_ROUTE")
        self.assertEqual([item.target_id for item in packet.candidates], ["F_A", "F_B"])
        self.assertIn("FRONTIER:F_A", packet.prompt_text)
        self.assertIn("allowed_actions=move_to,request_view", packet.prompt_text)
        self.assertNotIn("capability_1234567890abcd", packet.prompt_text)
        self.assertIn("Active goal G-001", packet.prompt_text)

    def test_attaches_only_requested_visual_for_current_navigation_revision(self):
        raw = compressed_image(b"jpeg-exact", 12_000)
        frame = ImageFrame("META_VIEW", "/source", 12_000, "jpeg", b"jpeg-exact", raw)
        self.state.set_requested_visual(RequestedVisual("META_VIEW", "FRONTIER", "F_A", 7, frame))

        packet = select_packet(self.state.state)

        self.assertIs(packet.visual.frame, frame)
        self.assertIn(frame.sha256, packet.prompt_text)
        self.assertIn("do not request the identical view again", packet.prompt_text)
        self.state.update_navigation(candidates(revision=8))
        self.assertIsNone(select_packet(self.state.state).visual)

    def test_expired_candidate_grant_is_not_sent_to_model(self):
        self.state.update_observation(observation(captured_ns=30_000_000_001))

        packet = select_packet(self.state.state)

        self.assertEqual(packet.candidates, ())
        self.assertIn("No fresh candidate", packet.prompt_text)


if __name__ == "__main__":
    unittest.main()
