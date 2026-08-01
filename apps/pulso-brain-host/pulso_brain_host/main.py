from __future__ import annotations

import argparse
import asyncio
import logging
import os
from pathlib import Path
import signal
import sys
import time

from .brain import BrainController
from .config import BrainConfig
from .model import NativeModelSession
from .prompts import system_prompt
from .rosbridge import RosbridgeClient
from .scheduling import GateWake, SemanticTurnGate
from .state import WorldStateStore
from .telemetry import TelemetryPublisher
from .tooling import tool_specs


LOGGER = logging.getLogger(__name__)


async def run(config: BrainConfig, app_dir: Path) -> None:
    config.validate()
    state = WorldStateStore()
    bridge = RosbridgeClient(config.rosbridge_url, state)
    prompt = system_prompt()
    specs = tool_specs()
    model = NativeModelSession(config, prompt, specs)
    telemetry = TelemetryPublisher(
        bridge,
        model_id=config.model_id,
        system_prompt=prompt,
        tool_schemas=[spec.openapi() for spec in specs],
    )
    brain = BrainController(
        model=model,
        telemetry=telemetry,
        state=state,
        bridge=bridge,
        skills_dir=app_dir / "skills",
        max_tool_calls=config.max_tool_calls_per_turn,
    )
    stop_event = asyncio.Event()
    semantic_gate = SemanticTurnGate(config.semantic_cooldown_s)
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)
    try:
        try:
            await bridge.connect()
        except Exception as failure:
            LOGGER.warning("Initial rosbridge connection failed: %s", failure)
            bridge.disconnected.set()
            await _reconnect(bridge, stop_event)
        if stop_event.is_set():
            return
        LOGGER.info("Connected to rosbridge at %s", config.rosbridge_url)
        warm_started = time.monotonic_ns()
        await model.warm()
        warm_ms = (time.monotonic_ns() - warm_started) // 1_000_000
        LOGGER.info("Gemma engine warm in %dms", warm_ms)
        await telemetry.trace(
            turn_id=None,
            world_seq=None,
            category="CONTEXT",
            label="Gemma ready",
            summary=f"Real LiteRT-LM engine warm · {warm_ms}ms · backend={config.backend}",
            latency_ms=warm_ms,
            attributes={"model_id": config.model_id, "backend": config.backend},
        )
        consecutive_native_failures = 0
        while not stop_event.is_set():
            signal_task = asyncio.create_task(state.decision_signal.wait())
            stop_task = asyncio.create_task(stop_event.wait())
            disconnect_task = asyncio.create_task(bridge.disconnected.wait())
            done, pending = await asyncio.wait(
                {signal_task, stop_task, disconnect_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
            if stop_task in done:
                break
            if disconnect_task in done:
                state.reset_live_inputs()
                await _reconnect(bridge, stop_event)
                continue
            immediate = state.consume_decision_request()
            if not immediate:
                wake = await semantic_gate.wait_until_admitted(
                    state.immediate_decision_signal,
                    stop_event,
                    bridge.disconnected,
                )
                if wake == GateWake.STOP:
                    break
                if wake == GateWake.DISCONNECTED:
                    state.reset_live_inputs()
                    await _reconnect(bridge, stop_event)
                    continue
                # Coalesce all semantic refreshes that arrived during cooldown;
                # an immediate request has already earned this admitted turn.
                state.consume_decision_request()
            if not state.is_ready_and_idle():
                robot = state.state.robot
                LOGGER.info(
                    "Decision deferred: ready=%s motion=%s",
                    state.state.ready,
                    robot.motion_state if robot else "NO_ROBOT",
                )
                continue
            try:
                LOGGER.info(
                    "Starting Gemma turn at world_seq=%d navigation_revision=%d",
                    state.state.world_seq,
                    state.state.navigation.navigation_revision,
                )
                await brain.run_decision()
                consecutive_native_failures = 0
            except Exception as failure:
                consecutive_native_failures += 1
                LOGGER.exception("Gemma decision cycle failed")
                if not bridge.disconnected.is_set():
                    await telemetry.trace(
                        turn_id=None,
                        world_seq=state.state.world_seq,
                        category="ERROR",
                        label="Native brain runtime",
                        summary=str(failure),
                        attributes={
                            "consecutive_failures": consecutive_native_failures,
                            "retry_scheduled": consecutive_native_failures <= 2,
                        },
                    )
                    # LiteRT can reject a malformed function-call serialization
                    # before exposing a response object. Retry from a new,
                    # turn-scoped conversation, bounded by the semantic
                    # cooldown and by this two-attempt failure budget.
                    if consecutive_native_failures <= 2:
                        state.request_fresh_packet_turn()
            finally:
                semantic_gate.mark_turn_completed()
    finally:
        await model.close()
        await bridge.close()


async def _reconnect(bridge: RosbridgeClient, stop_event: asyncio.Event) -> None:
    delay_s = 1.0
    while not stop_event.is_set():
        LOGGER.warning("Rosbridge disconnected; retrying in %.0fs", delay_s)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=delay_s)
            return
        except asyncio.TimeoutError:
            pass
        try:
            await bridge.reconnect()
            LOGGER.info("Reconnected to rosbridge at %s", bridge.url)
            return
        except Exception as failure:
            LOGGER.warning("Rosbridge reconnect failed: %s", failure)
            delay_s = min(8.0, delay_s * 2)


def cli() -> None:
    parser = argparse.ArgumentParser(description="PULSO native Gemma LiteRT-LM HIL brain")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    app_dir = Path(__file__).resolve().parents[1]
    project_root = app_dir.parents[1]
    config = BrainConfig.from_env(project_root)
    asyncio.run(run(config, app_dir))
    logging.shutdown()
    # LiteRT-LM 0.13.1's Linux GPU wheel tears down its global OpenCL state a
    # second time during CPython finalization after Engine.close(), producing a
    # SIGSEGV even though the engine already closed successfully. Bypass only
    # that native global-finalizer phase after a normal, fully awaited stop.
    # Unexpected Python/native failures still reach the supervisor unchanged.
    if (
        sys.platform.startswith("linux")
        and config.backend == "gpu"
        and os.getenv("PULSO_LITERT_LINUX_CLEAN_EXIT", "hard") == "hard"
    ):
        os._exit(0)


if __name__ == "__main__":
    cli()
