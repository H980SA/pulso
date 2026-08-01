"""Strict validation for untrusted HIL action JSON."""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any


ACTION_ID = re.compile(r"^[A-Za-z0-9._:+-]{1,96}$")
MAX_ACTION_BYTES = 16_384
ACTION_KINDS = {
    "STOP",
    "MOVE_TO",
    "LOOK_AT",
    "REQUEST_VIEW",
    "SET_FLASHLIGHT",
    "SPEAK",
    "LISTEN",
    "SET_MISSION_FOCUS",
    "UPSERT_HYPOTHESIS",
    "LOAD_SKILL",
}
TARGET_TYPES = {"VIEWPOINT", "FRONTIER", "TARGET", "ANCHOR"}
CAPABILITY = re.compile(r"^[A-Za-z0-9_-]{16,128}$")


class ActionContractError(ValueError):
    def __init__(self, status: str, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


@dataclass(frozen=True)
class ValidatedAction:
    action_id: str
    mission_id: str
    issued_monotonic_ns: int
    kind: str
    target_type: str | None
    target_id: str | None
    candidate_capability: str | None
    expected_navigation_revision: int | None
    expected_tracking_epoch: int | None
    expected_target_revision: int | None
    parameters: dict[str, Any]


def parse_action(raw_json: str) -> ValidatedAction:
    if not isinstance(raw_json, str) or len(raw_json.encode("utf-8")) > MAX_ACTION_BYTES:
        raise ActionContractError("INVALID_CONTRACT", "Action intent exceeds 16 KiB.")
    try:
        payload = json.loads(raw_json)
    except (TypeError, json.JSONDecodeError) as failure:
        raise ActionContractError("INVALID_JSON", "Action intent is not valid JSON.") from failure
    if not isinstance(payload, dict):
        raise ActionContractError("INVALID_CONTRACT", "Action intent must be a JSON object.")
    if payload.get("contract_version") != "pulso.action.v1":
        raise ActionContractError("INVALID_CONTRACT", "Unsupported action contract version.")
    action_id = payload.get("action_id")
    if not isinstance(action_id, str) or ACTION_ID.fullmatch(action_id) is None:
        raise ActionContractError("INVALID_ACTION_ID", "Action ID must be 1-96 safe characters.")
    mission_id = payload.get("mission_id")
    if not isinstance(mission_id, str) or ACTION_ID.fullmatch(mission_id) is None:
        raise ActionContractError("INVALID_MISSION_ID", "Mission ID must be 1-96 safe characters.")
    issued_ns = payload.get("issued_monotonic_ns")
    if isinstance(issued_ns, bool) or not isinstance(issued_ns, int) or issued_ns < 0:
        raise ActionContractError("INVALID_TIMESTAMP", "issued_monotonic_ns must be non-negative.")
    kind = payload.get("kind")
    if not isinstance(kind, str) or kind.upper() not in ACTION_KINDS:
        raise ActionContractError("INVALID_ACTION_KIND", "Unknown action kind.")
    kind = kind.upper()
    parameters = payload.get("parameters") or {}
    if not isinstance(parameters, dict) or len(parameters) > 16:
        raise ActionContractError("INVALID_PARAMETERS", "Parameters must be a small JSON object.")

    target_type = None
    target_id = None
    capability = None
    expected_navigation_revision = None
    expected_tracking_epoch = None
    expected_target_revision = None
    target = payload.get("target")
    if kind in {"MOVE_TO", "LOOK_AT", "REQUEST_VIEW"}:
        if not isinstance(target, dict):
            raise ActionContractError("INVALID_TARGET", "A typed target is required.")
        target_type = target.get("type")
        target_id = target.get("id")
        if target_type not in TARGET_TYPES:
            raise ActionContractError("INVALID_TARGET", "Unknown target type.")
        if not isinstance(target_id, str) or ACTION_ID.fullmatch(target_id) is None:
            raise ActionContractError("INVALID_TARGET", "Target ID must be 1-96 safe characters.")
        capability = payload.get("candidate_capability")
        if not isinstance(capability, str) or CAPABILITY.fullmatch(capability) is None:
            raise ActionContractError("INVALID_CAPABILITY", "A current candidate capability is required.")
        expected_navigation_revision = _non_negative_int(
            payload.get("expected_navigation_revision"), "expected_navigation_revision"
        )
        expected_tracking_epoch = _non_negative_int(
            payload.get("expected_tracking_epoch"), "expected_tracking_epoch"
        )
        expected_target_revision = payload.get("expected_target_revision")
        if expected_target_revision is not None:
            expected_target_revision = _non_negative_int(
                expected_target_revision, "expected_target_revision"
            )
    return ValidatedAction(
        action_id,
        mission_id,
        issued_ns,
        kind,
        target_type,
        target_id,
        capability,
        expected_navigation_revision,
        expected_tracking_epoch,
        expected_target_revision,
        parameters,
    )


def _non_negative_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ActionContractError("INVALID_CAPABILITY", f"{field} must be non-negative.")
    return value


class ActionReplayGuard:
    """Bounded in-memory replay protection for one navigation process."""

    def __init__(self, capacity: int = 256) -> None:
        self._capacity = capacity
        self._seen: dict[str, int] = {}

    def accept(self, action_id: str, received_ns: int) -> bool:
        if action_id in self._seen:
            return False
        self._seen[action_id] = received_ns
        if len(self._seen) > self._capacity:
            self._seen.pop(min(self._seen, key=self._seen.get), None)
        return True
