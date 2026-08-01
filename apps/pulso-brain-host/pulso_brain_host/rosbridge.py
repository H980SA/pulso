from __future__ import annotations

import asyncio
import base64
import binascii
import json
import logging
from typing import Any, Awaitable, Callable

import websockets

from .models import ImageFrame
from .state import WorldStateStore


LOGGER = logging.getLogger(__name__)

OBSERVATION_TOPIC = "/pulso/hil/observation"
CANDIDATES_TOPIC = "/pulso/navigation/candidates"
ACTION_RESULT_TOPIC = "/pulso/hil/action_result"
METAVIEW_TOPIC = "/pulso/navigation/metaview/compressed"
RGB_TOPIC = "/pulso/phone/rgb/compressed"
ACTION_INTENT_TOPIC = "/pulso/hil/action_intent"
BRAIN_TRACE_TOPIC = "/pulso/hil/brain_trace"
GEMMA_INPUT_TOPIC = "/pulso/hil/gemma_input"
GEMMA_VIEW_TOPIC = "/pulso/hil/gemma_view/compressed"

TERMINAL_STATUSES = frozenset(
    {
        "SUCCEEDED",
        "BLOCKED",
        "CANCELLED",
        "REJECTED",
        "TIMEOUT",
        "ACTUATOR_TIMEOUT",
        "BUSY",
        "DUPLICATE_ACTION",
        "INVALID_CONTRACT",
        "INVALID_ACTION_ID",
        "INVALID_MISSION_ID",
        "INVALID_TIMESTAMP",
        "INVALID_ACTION_KIND",
        "INVALID_PARAMETERS",
        "INVALID_TARGET",
        "INVALID_CAPABILITY",
        "STALE_OR_UNKNOWN_TARGET",
        "STALE_CAPABILITY",
        "EXPIRED_CAPABILITY",
        "STALE_NAVIGATION_REVISION",
        "STALE_TRACKING_EPOCH",
        "STALE_TARGET_REVISION",
        "TARGET_TYPE_MISMATCH",
        "TARGET_TOO_CLOSE",
        "ROTATION_ONLY_VIEWPOINT",
        "LOCALIZATION_UNAVAILABLE",
        "UNSUPPORTED_ACTION",
    }
)


class RosbridgeClient:
    def __init__(
        self,
        url: str,
        state: WorldStateStore,
        connect_factory: Callable[..., Awaitable[Any]] = websockets.connect,
    ) -> None:
        self.url = url
        self.state = state
        self._connect_factory = connect_factory
        self._socket: Any | None = None
        self._receiver: asyncio.Task[None] | None = None
        self._send_lock = asyncio.Lock()
        self._pending_actions: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._action_metadata: dict[str, tuple[str, str | None]] = {}
        self.disconnected = asyncio.Event()
        self._closing = False

    async def connect(self) -> None:
        if self._socket is not None:
            return
        self._closing = False
        self._socket = await self._connect_factory(self.url, max_size=8_000_000)
        self.disconnected.clear()
        await self._register_topics()
        self._receiver = asyncio.create_task(self._receive_loop(), name="pulso-rosbridge-rx")

    async def close(self) -> None:
        self._closing = True
        if self._receiver:
            self._receiver.cancel()
            await asyncio.gather(self._receiver, return_exceptions=True)
        self._receiver = None
        if self._socket:
            try:
                await self._socket.close()
            except Exception:
                pass
        self._socket = None
        for future in self._pending_actions.values():
            if not future.done():
                future.set_exception(ConnectionError("rosbridge closed"))
        self._pending_actions.clear()

    async def reconnect(self) -> None:
        await self.close()
        self._closing = False
        await self.connect()

    async def publish_json_string(self, topic: str, payload: dict[str, Any]) -> None:
        await self.publish_message(topic, {"data": json.dumps(payload, separators=(",", ":"))})

    async def publish_message(self, topic: str, message: dict[str, Any]) -> None:
        await self._send({"op": "publish", "topic": topic, "msg": message})

    async def publish_action(
        self,
        payload: dict[str, Any],
        *,
        kind: str,
        target_id: str | None,
        timeout_s: float,
    ) -> dict[str, Any]:
        action_id = str(payload["action_id"])
        loop = asyncio.get_running_loop()
        future: asyncio.Future[dict[str, Any]] = loop.create_future()
        self._pending_actions[action_id] = future
        self._action_metadata[action_id] = (kind, target_id)
        try:
            await self.publish_json_string(ACTION_INTENT_TOPIC, payload)
            return await asyncio.wait_for(future, timeout=timeout_s)
        finally:
            self._pending_actions.pop(action_id, None)
            self._action_metadata.pop(action_id, None)

    async def _register_topics(self) -> None:
        for topic, message_type, throttle in (
            (OBSERVATION_TOPIC, "std_msgs/msg/String", 0),
            (CANDIDATES_TOPIC, "std_msgs/msg/String", 0),
            (ACTION_RESULT_TOPIC, "std_msgs/msg/String", 0),
            (METAVIEW_TOPIC, "sensor_msgs/msg/CompressedImage", 250),
            (RGB_TOPIC, "sensor_msgs/msg/CompressedImage", 250),
        ):
            await self._send(
                {
                    "op": "subscribe",
                    "id": f"brain-sub-{topic}",
                    "topic": topic,
                    "type": message_type,
                    "throttle_rate": throttle,
                    "queue_length": 1,
                }
            )
        for topic, message_type in (
            (ACTION_INTENT_TOPIC, "std_msgs/msg/String"),
            (BRAIN_TRACE_TOPIC, "std_msgs/msg/String"),
            (GEMMA_INPUT_TOPIC, "std_msgs/msg/String"),
            (GEMMA_VIEW_TOPIC, "sensor_msgs/msg/CompressedImage"),
        ):
            await self._send(
                {"op": "advertise", "id": f"brain-pub-{topic}", "topic": topic, "type": message_type}
            )

    async def _receive_loop(self) -> None:
        assert self._socket is not None
        try:
            async for raw in self._socket:
                await self.handle_raw(raw)
            if not self._closing:
                close_code = getattr(self._socket, "close_code", None)
                close_reason = getattr(self._socket, "close_reason", None)
                LOGGER.warning(
                    "rosbridge connection closed by peer: code=%s reason=%s",
                    close_code if close_code is not None else "unknown",
                    close_reason if close_reason else "none",
                )
        except asyncio.CancelledError:
            raise
        except Exception as failure:
            if not self._closing:
                LOGGER.warning("rosbridge connection lost: %s", failure)
            for future in self._pending_actions.values():
                if not future.done():
                    future.set_exception(failure)
        finally:
            if not self._closing:
                self.disconnected.set()

    async def handle_raw(self, raw: str | bytes) -> None:
        try:
            outer = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return
        if not isinstance(outer, dict) or outer.get("op") != "publish":
            return
        topic = outer.get("topic")
        message = outer.get("msg")
        if not isinstance(topic, str) or not isinstance(message, dict):
            return
        try:
            if topic == OBSERVATION_TOPIC:
                self.state.update_observation(_std_string_payload(message))
            elif topic == CANDIDATES_TOPIC:
                self.state.update_navigation(_std_string_payload(message))
            elif topic == ACTION_RESULT_TOPIC:
                self._handle_action_result(_std_string_payload(message))
            elif topic in {METAVIEW_TOPIC, RGB_TOPIC}:
                await self.state.update_image(_image_frame(topic, message))
        except (KeyError, TypeError, ValueError, binascii.Error) as failure:
            LOGGER.warning("Rejected malformed %s frame: %s", topic, failure)

    def _handle_action_result(self, result: dict[str, Any]) -> None:
        action_id = result.get("action_id")
        status = str(result.get("status", "UNKNOWN"))
        if not isinstance(action_id, str):
            return
        metadata = self._action_metadata.get(action_id)
        if status in TERMINAL_STATUSES and metadata:
            kind, target_id = metadata
            self.state.record_action_result(
                kind=kind,
                target_id=target_id,
                status=status,
                detail=str(result.get("detail", "")),
            )
        future = self._pending_actions.get(action_id)
        if future is not None and not future.done() and status in TERMINAL_STATUSES:
            future.set_result(result)

    async def _send(self, payload: dict[str, Any]) -> None:
        if self._socket is None:
            raise ConnectionError("rosbridge is not connected")
        encoded = json.dumps(payload, separators=(",", ":"))
        async with self._send_lock:
            try:
                await self._socket.send(encoded)
            except Exception:
                self.disconnected.set()
                raise


def _std_string_payload(message: dict[str, Any]) -> dict[str, Any]:
    data = message.get("data")
    if not isinstance(data, str):
        raise ValueError("std_msgs/String.data is missing")
    parsed = json.loads(data)
    if not isinstance(parsed, dict):
        raise ValueError("std_msgs/String payload is not an object")
    return parsed


def _image_frame(topic: str, message: dict[str, Any]) -> ImageFrame:
    data = message.get("data")
    if not isinstance(data, str):
        raise ValueError("CompressedImage.data is missing")
    stamp = message.get("header", {}).get("stamp", {})
    seconds = int(stamp.get("sec", 0))
    nanoseconds = int(stamp.get("nanosec", 0))
    kind = "META_VIEW" if topic == METAVIEW_TOPIC else "EGO_RGB"
    return ImageFrame(
        kind=kind,
        source_topic=topic,
        captured_ns=seconds * 1_000_000_000 + nanoseconds,
        format=str(message.get("format", "jpeg")),
        jpeg=base64.b64decode(data, validate=True),
        ros_message=message,
    )
