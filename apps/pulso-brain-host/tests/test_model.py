from __future__ import annotations

from pathlib import Path
import unittest

from pulso_brain_host.config import BrainConfig
from pulso_brain_host.model import NativeModelSession, parse_tool_calls, public_response_text
from pulso_brain_host.tooling import tool_specs


class FakeConversation:
    def __init__(self):
        self.messages = []
        self.token_count = 77
        self.closed = False

    def send_message(self, message):
        self.messages.append(message)
        return {"role": "model", "content": [{"type": "text", "text": "Ruta A."}]}

    def close(self):
        self.closed = True


class FakeEngine:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class ModelRuntimeTest(unittest.IsolatedAsyncioTestCase):
    async def test_engine_and_conversation_warm_once(self):
        calls = []
        engine = FakeEngine()
        conversations = []

        def loader(*args):
            calls.append(args)
            def new_conversation():
                conversation = FakeConversation()
                conversations.append(conversation)
                return conversation
            return engine, new_conversation

        config = BrainConfig("ws://test", Path(__file__), backend="cpu")
        model = NativeModelSession(config, "system", tool_specs(), loader=loader)
        await model.warm()
        await model.warm()
        await model.start_turn()
        response = await model.send({"role": "user", "content": "hello"})

        self.assertEqual(len(calls), 1)
        self.assertEqual(public_response_text(response), "Ruta A.")
        self.assertEqual(await model.token_count(), 77)
        await model.end_turn()
        await model.start_turn()
        await model.send({"role": "user", "content": "second turn"})
        self.assertEqual(len(conversations), 2)
        self.assertIsNot(conversations[0], conversations[1])
        self.assertEqual(conversations[0].messages, [{"role": "user", "content": "hello"}])
        self.assertEqual(conversations[1].messages, [{"role": "user", "content": "second turn"}])
        await model.close()
        self.assertTrue(engine.closed)
        self.assertTrue(all(conversation.closed for conversation in conversations))

    def test_tool_calls_parse_but_private_channels_never_become_public_text(self):
        response = {
            "content": [{"type": "tool_call", "name": "stop", "arguments": {}}],
            "channels": {"analysis": "private chain of thought"},
        }
        self.assertEqual(parse_tool_calls(response)[0].name, "stop")
        self.assertEqual(public_response_text(response), "")


if __name__ == "__main__":
    unittest.main()
