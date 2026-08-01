"""Pure status normalization and formatting for the RViz operator overlay."""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from typing import Mapping


@dataclass(frozen=True)
class DiagnosticState:
    level: int
    state: str
    reason: str | None = None
    quality: float | None = None


@dataclass(frozen=True)
class ActionState:
    action_id: str
    accepted: bool
    status: str
    target_id: str | None = None


@dataclass
class StatusState:
    battery_fraction: float | None = None
    battery_at_ns: int = 0
    front_range_m: float | None = None
    front_range_at_ns: int = 0
    bumper_pressed: bool | None = None
    bumper_at_ns: int = 0
    safety: DiagnosticState | None = None
    safety_at_ns: int = 0
    vio: DiagnosticState | None = None
    vio_at_ns: int = 0
    imu_norm_mps2: float | None = None
    imu_at_ns: int = 0
    action: ActionState | None = None


@dataclass(frozen=True)
class StatusLine:
    label: str
    value: str
    severity: str


def diagnostic_from_fields(
    message: str,
    level: object,
    values: Mapping[str, str],
) -> DiagnosticState:
    """Normalize one ROS diagnostic without depending on ROS message classes."""

    state = _clean_text(values.get("state") or message, "UNKNOWN").upper()
    reason_value = _clean_text(values.get("reason"), "")
    reason = reason_value.upper() or None
    quality = _finite_fraction(values.get("quality"))
    return DiagnosticState(
        level=_diagnostic_level(level),
        state=state,
        reason=reason,
        quality=quality,
    )


def parse_action_result(raw_json: str) -> ActionState | None:
    """Parse only the bounded fields useful to a human watching RViz."""

    if not isinstance(raw_json, str) or len(raw_json.encode("utf-8")) > 16_384:
        return None
    try:
        payload = json.loads(raw_json)
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("contract_version") != "pulso.action-result.v1":
        return None
    action_id = _clean_text(payload.get("action_id"), "")
    status = _clean_text(payload.get("status"), "").upper()
    accepted = payload.get("accepted")
    if not action_id or not status or not isinstance(accepted, bool):
        return None
    data = payload.get("data")
    target_id = None
    if isinstance(data, dict):
        target_value = _clean_text(data.get("target_id"), "")
        target_id = target_value or None
    return ActionState(
        action_id=action_id,
        accepted=accepted,
        status=status,
        target_id=target_id,
    )


def merge_action_state(
    previous: ActionState | None, current: ActionState
) -> ActionState:
    """Keep the accepted target visible when a terminal result omits it."""

    if (
        current.target_id is None
        and previous is not None
        and previous.action_id == current.action_id
        and previous.target_id is not None
    ):
        return ActionState(
            action_id=current.action_id,
            accepted=current.accepted,
            status=current.status,
            target_id=previous.target_id,
        )
    return current


def format_status_lines(
    state: StatusState,
    now_ns: int,
    stale_after_ns: int,
) -> tuple[StatusLine, ...]:
    """Build a stable six-line overlay while making stale telemetry explicit."""

    return (
        _battery_line(state, now_ns, stale_after_ns),
        _sonar_line(state, now_ns, stale_after_ns),
        _bumper_line(state, now_ns, stale_after_ns),
        _diagnostic_line(
            "SAFETY", state.safety, state.safety_at_ns, now_ns, stale_after_ns
        ),
        _diagnostic_line("VIO", state.vio, state.vio_at_ns, now_ns, stale_after_ns),
        _imu_line(state, now_ns, stale_after_ns),
        _action_line(state.action),
    )


def _battery_line(state: StatusState, now_ns: int, stale_after_ns: int) -> StatusLine:
    availability = _availability(state.battery_at_ns, now_ns, stale_after_ns)
    if availability is not None:
        return StatusLine("BATTERY", availability, "unknown")
    fraction = state.battery_fraction
    if fraction is None or not math.isfinite(fraction) or not 0.0 <= fraction <= 1.0:
        return StatusLine("BATTERY", "NO DATA", "unknown")
    severity = "critical" if fraction < 0.15 else "warning" if fraction < 0.30 else "ok"
    return StatusLine("BATTERY", f"{fraction * 100:.0f}%", severity)


def _sonar_line(state: StatusState, now_ns: int, stale_after_ns: int) -> StatusLine:
    availability = _availability(state.front_range_at_ns, now_ns, stale_after_ns)
    if availability is not None:
        return StatusLine("SONAR", availability, "unknown")
    distance = state.front_range_m
    if distance is None or not math.isfinite(distance) or distance < 0.0:
        return StatusLine("SONAR", "NO RETURN", "unknown")
    return StatusLine("SONAR", f"{distance:.2f} m", "info")


def _bumper_line(state: StatusState, now_ns: int, stale_after_ns: int) -> StatusLine:
    availability = _availability(state.bumper_at_ns, now_ns, stale_after_ns)
    if availability is not None:
        return StatusLine("BUMPER", availability, "unknown")
    if state.bumper_pressed is None:
        return StatusLine("BUMPER", "NO DATA", "unknown")
    if state.bumper_pressed:
        return StatusLine("BUMPER", "PRESSED", "critical")
    return StatusLine("BUMPER", "CLEAR", "ok")


def _diagnostic_line(
    label: str,
    diagnostic: DiagnosticState | None,
    sampled_at_ns: int,
    now_ns: int,
    stale_after_ns: int,
) -> StatusLine:
    availability = _availability(sampled_at_ns, now_ns, stale_after_ns)
    if availability is not None:
        return StatusLine(label, availability, "unknown")
    if diagnostic is None:
        return StatusLine(label, "NO STATUS", "unknown")
    value = diagnostic.state
    if diagnostic.reason and diagnostic.reason not in {"NONE", "OK"}:
        value = f"{value} · {diagnostic.reason}"
    if label == "VIO" and diagnostic.quality is not None:
        value = f"{value} · {diagnostic.quality * 100:.0f}%"
    severity = _diagnostic_severity(diagnostic)
    return StatusLine(label, value, severity)


def _action_line(action: ActionState | None) -> StatusLine:
    if action is None:
        return StatusLine("ACTION", "WAITING", "unknown")
    subject = action.target_id or action.action_id
    value = f"{action.status} · {subject}"
    if action.status == "SUCCEEDED":
        severity = "ok"
    elif action.status == "ACTIVE":
        severity = "info"
    elif not action.accepted or action.status in {"CANCELLED", "FAILED", "ERROR"}:
        severity = "warning"
    else:
        severity = "info"
    return StatusLine("ACTION", value, severity)


def _imu_line(state: StatusState, now_ns: int, stale_after_ns: int) -> StatusLine:
    availability = _availability(state.imu_at_ns, now_ns, stale_after_ns)
    if availability is not None:
        return StatusLine("IMU", availability, "unknown")
    magnitude = state.imu_norm_mps2
    if magnitude is None or not math.isfinite(magnitude) or magnitude < 0.0:
        return StatusLine("IMU", "NO DATA", "unknown")
    return StatusLine("IMU", f"{magnitude:.2f} m/s²", "info")


def _diagnostic_severity(diagnostic: DiagnosticState) -> str:
    state = diagnostic.state.upper()
    if state in {"LOST", "ERROR", "FAILED"} or diagnostic.level == 2:
        return "critical"
    if state in {"LIMITED", "STOPPED", "WARN", "WARNING"} or diagnostic.level == 1:
        return "warning"
    if state in {"CLEAR", "TRACKING", "OK"} and diagnostic.level == 0:
        return "ok"
    return "unknown"


def _availability(sampled_at_ns: int, now_ns: int, stale_after_ns: int) -> str | None:
    if sampled_at_ns <= 0:
        return "WAITING"
    age_ns = now_ns - sampled_at_ns
    if age_ns < 0 or age_ns > stale_after_ns:
        return "STALE"
    return None


def _finite_fraction(value: object) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return max(0.0, min(1.0, parsed))


def _diagnostic_level(value: object) -> int:
    """Accept Humble's one-byte uint8 representation and normal integers."""

    if isinstance(value, (bytes, bytearray)):
        return int(value[0]) if value else 0
    return int(value)


def _clean_text(value: object, default: str, max_length: int = 64) -> str:
    if not isinstance(value, str):
        return default
    normalized = " ".join(value.split())
    return normalized[:max_length] or default
