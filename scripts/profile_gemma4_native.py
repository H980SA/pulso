#!/usr/bin/env python3
"""Run one bounded, real LiteRT-LM tool-selection profile without ROS.

The report intentionally stores only public response text and structured tool
calls. It never records private model channels or chain-of-thought.
"""

from __future__ import annotations

import argparse
import asyncio
from hashlib import sha256
import json
import os
from pathlib import Path
import platform
import sys
import time
from typing import Any


def file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


async def profile(model_path: Path, backend: str) -> dict[str, Any]:
    from pulso_brain_host.config import BrainConfig
    from pulso_brain_host.model import (
        NativeModelSession,
        parse_tool_calls,
        public_response_text,
    )
    from pulso_brain_host.prompts import system_prompt
    from pulso_brain_host.tooling import tool_specs

    config = BrainConfig(
        rosbridge_url="ws://127.0.0.1:1",
        model_path=model_path,
        backend=backend,
        max_num_tokens=2048,
        temperature=0.2,
        min_cycle_interval_s=0.5,
        max_tool_calls_per_turn=4,
    )
    config.validate()
    session = NativeModelSession(config, system_prompt(), tool_specs())
    warm_started = time.monotonic_ns()
    await session.warm()
    warm_ms = (time.monotonic_ns() - warm_started) // 1_000_000
    try:
        await session.start_turn()
        prompt = (
            "WORLD 1. Active goal G-SEARCH-01: explore safely. Tracking is "
            "TRACKING and the rover is STOPPED. One fresh valid candidate exists: "
            "FRONTIER:F_SAFE, path 0.8m, risk 0.10, information gain 0.82. "
            "No human clue is present. Choose the next mission action using one tool."
        )
        inference_started = time.monotonic_ns()
        response = await session.send(
            {"role": "user", "content": [{"type": "text", "text": prompt}]}
        )
        inference_ms = (time.monotonic_ns() - inference_started) // 1_000_000
        calls = parse_tool_calls(response)
        token_count = await session.token_count()
        return {
            "contract_version": "pulso.native-model-profile.v1",
            "captured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "model_id": config.model_id,
            "model_path": str(model_path),
            "model_bytes": model_path.stat().st_size,
            "model_sha256": file_sha256(model_path),
            "backend": backend,
            "warm_ms": warm_ms,
            "inference_ms": inference_ms,
            "token_count": token_count,
            "prompt_sha256": sha256(prompt.encode("utf-8")).hexdigest(),
            "tool_calls": [
                {"name": call.name, "arguments": call.arguments} for call in calls
            ],
            "public_text": public_response_text(response),
            "expected": {"tool": "move_to", "target_type": "FRONTIER", "target_id": "F_SAFE"},
            "passed": any(
                call.name == "move_to"
                and call.arguments.get("target_type") == "FRONTIER"
                and call.arguments.get("target_id") == "F_SAFE"
                for call in calls
            ),
        }
    finally:
        await session.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("model", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--backend", choices=("cpu", "gpu"), default="gpu")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = asyncio.run(profile(args.model.expanduser().resolve(), args.backend))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)
    exit_code = 0 if report["passed"] else 1
    if platform.system() == "Linux" and os.getenv("PULSO_LITERT_LINUX_CLEAN_EXIT", "hard") != "python":
        os._exit(exit_code)
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
