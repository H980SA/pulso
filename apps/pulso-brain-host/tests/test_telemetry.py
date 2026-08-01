from __future__ import annotations

import unittest

from pulso_brain_host.models import ImageFrame
from pulso_brain_host.telemetry import InputEvidence, TelemetryPublisher

from fixtures import compressed_image


class FakeBridge:
    def __init__(self):
        self.messages = []
        self.json_strings = []
        self.events = []

    async def publish_message(self, topic, message):
        self.messages.append((topic, message))
        self.events.append(("message", topic))

    async def publish_json_string(self, topic, payload):
        self.json_strings.append((topic, payload))
        self.events.append(("json", topic))


class TelemetryTest(unittest.IsolatedAsyncioTestCase):
    async def test_publishes_byte_exact_image_and_exact_text_without_private_output(self):
        bridge = FakeBridge()
        telemetry = TelemetryPublisher(
            bridge,
            model_id="gemma-4-E4B-custom.litertlm",
            system_prompt="exact system",
            tool_schemas=[{"name": "stop"}],
        )
        raw = compressed_image(b"jpeg-byte-exact", 12_000)
        frame = ImageFrame("META_VIEW", "/source", 12_000, "jpeg", b"jpeg-byte-exact", raw)
        message = {
            "role": "user",
            "content": [
                {"type": "text", "text": "exact prompt"},
                {"type": "image", "blob": "an-image-blob"},
            ],
        }
        await telemetry.publish_input(InputEvidence("T-1", 9, "WORLD_PACKET", message, "exact prompt", frame, 4))

        self.assertIs(bridge.messages[0][1], raw)
        self.assertEqual(
            bridge.events,
            [
                ("json", "/pulso/hil/gemma_input"),
                ("message", "/pulso/hil/gemma_view/compressed"),
            ],
        )
        payload = bridge.json_strings[0][1]
        self.assertEqual(payload["model_id"], "gemma-4-E4B-custom.litertlm")
        self.assertEqual(payload["prompt_text"], "exact prompt")
        self.assertEqual(payload["system_prompt"], "exact system")
        self.assertEqual(payload["conversation_scope"], "TURN")
        self.assertFalse(payload["conversation_reused_across_turns"])
        self.assertEqual(payload["image"]["jpeg_sha256"], frame.sha256)
        self.assertNotIn("an-image-blob", str(payload["exact_message"]))
        self.assertEqual(
            payload["exact_message"]["content"][1]["bytes_transport"],
            "/pulso/hil/gemma_view/compressed",
        )

    async def test_rejects_an_empty_configured_model_identity(self):
        with self.assertRaisesRegex(ValueError, "configured artifact"):
            TelemetryPublisher(
                FakeBridge(), model_id="  ", system_prompt="system", tool_schemas=[]
            )


if __name__ == "__main__":
    unittest.main()
