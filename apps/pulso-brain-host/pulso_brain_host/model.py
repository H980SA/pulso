from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import json
from typing import Any, Callable

from .config import BrainConfig
from .tooling import ToolSpec


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: dict[str, Any]


class NativeModelSession:
    """One hot engine and one turn-scoped conversation on a dedicated thread."""

    def __init__(
        self,
        config: BrainConfig,
        system_prompt: str,
        specs: tuple[ToolSpec, ...],
        loader: Callable[..., tuple[Any, Callable[[], Any]]] | None = None,
    ) -> None:
        self.config = config
        self.system_prompt = system_prompt
        self.specs = specs
        self._loader = loader or _load_litert
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pulso-litert")
        self._engine: Any | None = None
        self._conversation_factory: Callable[[], Any] | None = None
        self._conversation: Any | None = None

    async def warm(self) -> None:
        if self._engine is not None:
            return
        loop = asyncio.get_running_loop()
        self._engine, self._conversation_factory = await loop.run_in_executor(
            self._executor,
            lambda: self._loader(self.config, self.system_prompt, self.specs),
        )

    async def start_turn(self) -> None:
        if self._engine is None or self._conversation_factory is None:
            raise RuntimeError("LiteRT-LM engine is not warm")
        if self._conversation is not None:
            raise RuntimeError("A Gemma turn is already active")
        loop = asyncio.get_running_loop()
        self._conversation = await loop.run_in_executor(
            self._executor, self._conversation_factory
        )

    async def end_turn(self) -> None:
        if self._conversation is None:
            return
        conversation = self._conversation
        self._conversation = None
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(self._executor, conversation.close)

    async def send(self, message: dict[str, Any]) -> dict[str, Any]:
        if self._conversation is None:
            raise RuntimeError("LiteRT-LM conversation is not warm")
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(
            self._executor, lambda: self._conversation.send_message(message)
        )
        if not isinstance(response, dict):
            raise RuntimeError("LiteRT-LM returned a non-object response")
        return response

    async def token_count(self) -> int | None:
        if self._conversation is None:
            return None
        loop = asyncio.get_running_loop()
        try:
            return int(
                await loop.run_in_executor(
                    self._executor, lambda: self._conversation.token_count
                )
            )
        except Exception:
            return None

    async def close(self) -> None:
        await self.end_turn()
        if self._engine is not None:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(self._executor, self._engine.close)
            self._engine = None
        self._executor.shutdown(wait=True, cancel_futures=True)


def parse_tool_calls(response: dict[str, Any]) -> list[ToolCall]:
    raw_calls = response.get("tool_calls", [])
    if not isinstance(raw_calls, list):
        raw_calls = []
    content = response.get("content")
    if isinstance(content, list):
        raw_calls = [
            *raw_calls,
            *(item for item in content if isinstance(item, dict) and item.get("type") == "tool_call"),
        ]
    calls: list[ToolCall] = []
    for raw in raw_calls:
        if not isinstance(raw, dict):
            continue
        function = raw.get("function") if isinstance(raw.get("function"), dict) else raw
        name = function.get("name")
        arguments = function.get("arguments", {})
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                arguments = {}
        if isinstance(name, str) and isinstance(arguments, dict):
            calls.append(ToolCall(name=name, arguments=arguments))
    return calls


def public_response_text(response: dict[str, Any]) -> str:
    """Extract ordinary answer text only; channels/private reasoning are ignored."""
    content = response.get("content")
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    pieces = [
        item.get("text", "")
        for item in content
        if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str)
    ]
    return " ".join(piece.strip() for piece in pieces if piece.strip()).strip()


def _load_litert(
    config: BrainConfig,
    system_prompt: str,
    specs: tuple[ToolSpec, ...],
) -> tuple[Any, Callable[[], Any]]:
    import litert_lm

    litert_lm.set_min_log_severity(litert_lm.LogSeverity.ERROR)
    backend = litert_lm.Backend.GPU() if config.backend == "gpu" else litert_lm.Backend.CPU()

    class DeclaredTool(litert_lm.Tool):
        def __init__(self, spec: ToolSpec) -> None:
            self.spec = spec

        def get_tool_description(self) -> dict[str, Any]:
            return self.spec.openapi()

        def execute(self, param) -> Any:
            raise RuntimeError("Automatic tool execution is disabled by PULSO")

    engine = litert_lm.Engine(
        str(config.model_path),
        backend=backend,
        vision_backend=backend,
        max_num_tokens=config.max_num_tokens,
    )
    declared_tools = [DeclaredTool(spec) for spec in specs]

    def create_turn_conversation():
        return engine.create_conversation(
            tools=declared_tools,
            automatic_tool_calling=False,
            filter_channel_content_from_kv_cache=True,
            sampler_config=litert_lm.SamplerConfig(
                temperature=config.temperature,
                top_k=20,
                top_p=0.9,
                seed=42,
            ),
            system_message=system_prompt,
        )

    return engine, create_turn_conversation
