from __future__ import annotations

from pathlib import Path
import unittest

from pulso_brain_host.brain import BrainController
from pulso_brain_host.state import WorldStateStore

from fixtures import candidates, observation


REQUEST_VIEW_CALL = {
    "type": "tool_call",
    "name": "request_view",
    "arguments": {
        "target_type": "FRONTIER",
        "target_id": "F_A",
        "view_kind": "META_VIEW",
    },
}
STALE_REQUEST_VIEW = {"content": [REQUEST_VIEW_CALL] * 4}


class RepeatingModel:
    def __init__(self, state: WorldStateStore):
        self.state = state
        self.messages = []
        self.started = 0
        self.ended = 0

    async def start_turn(self):
        self.started += 1

    async def end_turn(self):
        self.ended += 1

    async def token_count(self):
        return 0

    async def send(self, message):
        self.messages.append(message)
        if len(self.messages) == 1:
            # Same candidate semantics, but a new revision/capability makes the
            # packet's grant stale before Gemma's first tool call is executed.
            refreshed = candidates(captured_ns=20_000, revision=8)
            refreshed["candidates"][0]["capability"] = "rotated_capability_1234567890"
            self.state.update_navigation(refreshed)
        return STALE_REQUEST_VIEW


class RecordingTelemetry:
    def __init__(self):
        self.inputs = []
        self.traces = []

    async def publish_input(self, evidence):
        self.inputs.append(evidence)

    async def trace(self, **event):
        self.traces.append(event)


class NoActionBridge:
    async def publish_action(self, *_args, **_kwargs):
        raise AssertionError("A stale target must be rejected before publication")

    async def publish_json_string(self, *_args, **_kwargs):
        raise AssertionError("A stale request_view must not publish an action")


class BrainTurnSchedulingTest(unittest.IsolatedAsyncioTestCase):
    async def test_stale_target_reports_once_then_schedules_one_fresh_packet_turn(self):
        state = WorldStateStore()
        state.update_observation(observation())
        state.update_navigation(candidates())
        state.consume_decision_request()
        model = RepeatingModel(state)
        telemetry = RecordingTelemetry()
        brain = BrainController(
            model=model,
            telemetry=telemetry,
            state=state,
            bridge=NoActionBridge(),
            skills_dir=Path(__file__).parents[1] / "skills",
            max_tool_calls=4,
        )

        await brain.run_decision()

        self.assertEqual(len(model.messages), 2)
        self.assertEqual(len(model.messages[1]["content"]), 1)
        tool_result = model.messages[1]["content"][0]["response"]
        self.assertEqual(tool_result["status"], "STALE_OR_UNKNOWN_TARGET")
        self.assertEqual(model.started, 1)
        self.assertEqual(model.ended, 1)
        self.assertTrue(state.decision_signal.is_set())
        self.assertEqual(
            sum(event.get("label") == "Fresh packet scheduled" for event in telemetry.traces),
            1,
        )

        self.assertFalse(state.consume_decision_request())
        self.assertFalse(state.decision_signal.is_set())
        self.assertEqual(state.state.navigation.navigation_revision, 8)


if __name__ == "__main__":
    unittest.main()
