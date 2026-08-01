from __future__ import annotations

from dataclasses import replace
from typing import Any

from .models import (
    Candidate,
    CognitiveMemory,
    LiveState,
    NavigationSnapshot,
    RobotSnapshot,
    SelectedPacket,
)


MISSION_ID = "M-001"
MISSION_TITLE = "Explorar y localizar posibles sobrevivientes"
GOAL_ID = "G-001"
GOAL_TITLE = "Expandir cobertura sin comprometer el rover"
SUCCESS_CONDITION = "Mapear rutas transitables y priorizar evidencia humana verificable."


def parse_observation(payload: dict[str, Any]) -> RobotSnapshot:
    if payload.get("contract_version") != "pulso.observation.v1":
        raise ValueError("Unsupported observation contract")
    tracking = _object(payload, "tracking")
    robot = _object(payload, "robot")
    pose = _object(robot, "pose")
    position = pose.get("position_m")
    if not isinstance(position, list) or len(position) < 2:
        raise ValueError("robot.pose.position_m is missing")
    return RobotSnapshot(
        captured_ns=_integer(payload, "captured_monotonic_ns"),
        source=str(payload.get("source", "UNKNOWN")),
        tracking_state=str(tracking.get("state", "LOST")),
        tracking_quality=_number(tracking.get("quality"), 0.0),
        tracking_epoch=int(tracking.get("epoch", 0)),
        x=_number(position[0]),
        y=_number(position[1]),
        heading_deg=_number(pose.get("heading_deg")),
        pose_confidence=_number(pose.get("confidence"), 0.0),
        motion_state=str(robot.get("motion_state", "STOPPED")),
        battery_fraction=_number(robot.get("battery_fraction"), 0.0),
        flashlight_on=robot.get("flashlight_on") is True,
        front_range_m=(
            _number(robot.get("front_range_m"))
            if robot.get("front_range_m") is not None
            else None
        ),
    )


def parse_navigation(payload: dict[str, Any]) -> NavigationSnapshot:
    if payload.get("contract_version") != "pulso.navigation.candidates.v1":
        raise ValueError("Unsupported candidates contract")
    candidates: list[Candidate] = []
    for raw in payload.get("candidates", []):
        if not isinstance(raw, dict):
            continue
        position = raw.get("position_m")
        if not isinstance(position, list) or len(position) < 2:
            continue
        target_type = str(raw.get("type", ""))
        target_id = str(raw.get("id", ""))
        capability = str(raw.get("capability", ""))
        if not target_type or not target_id or len(capability) < 16:
            continue
        target_revision = raw.get("target_revision")
        candidates.append(
            Candidate(
                target_type=target_type,
                target_id=target_id,
                label=str(raw.get("label", target_id)),
                purpose=str(raw.get("purpose", "")),
                x=_number(position[0]),
                y=_number(position[1]),
                path_length_m=_number(raw.get("path_length_m")),
                risk=_number(raw.get("risk"), 1.0),
                information_gain=_number(raw.get("information_gain")),
                capability=capability,
                target_revision=int(target_revision) if target_revision is not None else None,
            )
        )
    return NavigationSnapshot(
        captured_ns=_integer(payload, "captured_monotonic_ns"),
        sensor_map_seq=_integer(payload, "sensor_map_seq"),
        navigation_revision=_integer(payload, "navigation_revision"),
        valid_until_ns=_integer(payload, "valid_until_monotonic_ns"),
        candidates=tuple(candidates),
    )


def decision_need(robot: RobotSnapshot, navigation: NavigationSnapshot) -> str:
    if robot.tracking_state in {"LOST", "LIMITED"}:
        return "RECOVER_TRACKING"
    if any(item.target_type == "TARGET" for item in navigation.candidates):
        return "INSPECT_TARGET"
    return "CHOOSE_ROUTE"


def select_packet(state: LiveState) -> SelectedPacket:
    if state.robot is None or state.navigation is None:
        raise ValueError("World state is not ready")
    robot = state.robot
    navigation = state.navigation
    need = decision_need(robot, navigation)
    current_ns = max(robot.captured_ns, navigation.captured_ns)
    if current_ns > navigation.valid_until_ns:
        candidates: tuple[Candidate, ...] = ()
    else:
        matching = tuple(item for item in navigation.candidates if _candidate_matches(item, need))
        candidates = tuple(
            sorted(matching, key=lambda item: (-item.information_gain, item.risk))[:5]
        )
    visual = state.requested_visual
    if visual is not None and visual.navigation_revision != navigation.navigation_revision:
        visual = None
    memory = replace(state.memory, question=_question_for(need))
    prompt = _render_prompt(state.world_seq, robot, navigation, candidates, visual, memory, need)
    return SelectedPacket(
        world_seq=state.world_seq,
        decision_need=need,
        navigation_revision=navigation.navigation_revision,
        tracking_epoch=robot.tracking_epoch,
        prompt_text=prompt,
        candidates=candidates,
        visual=visual,
        memory=memory,
    )


def navigation_decision_signature(
    navigation: NavigationSnapshot,
) -> tuple[tuple[str, ...], ...]:
    """Order-independent candidate semantics at the precision Gemma sees."""
    return tuple(
        sorted(
            (
                item.target_type,
                item.target_id,
                item.label,
                item.purpose,
                f"{item.path_length_m:.2f}",
                f"{item.risk:.2f}",
                f"{item.information_gain:.2f}",
            )
            for item in navigation.candidates
        )
    )


def _render_prompt(
    world_seq: int,
    robot: RobotSnapshot,
    navigation: NavigationSnapshot,
    candidates: tuple[Candidate, ...],
    visual,
    memory: CognitiveMemory,
    need: str,
) -> str:
    lines = [
        "CURRENT WORLD PACKET",
        f"World sequence: {world_seq}. Decision need: {need}.",
        f"Mission {MISSION_ID}: {MISSION_TITLE}",
        f"Active goal {GOAL_ID}: {GOAL_TITLE}",
        f"Success means: {SUCCESS_CONDITION}",
        (
            f"Robot is {robot.motion_state.lower()} at ({robot.x:.2f}, {robot.y:.2f})m, "
            f"heading {robot.heading_deg:.0f}°, pose confidence {_percent(robot.pose_confidence)}."
        ),
        (
            f"VIO {robot.tracking_state} at {_percent(robot.tracking_quality)}; "
            f"battery {_percent(robot.battery_fraction)}; "
            f"flashlight {'on' if robot.flashlight_on else 'off'}."
        ),
    ]
    if robot.front_range_m is not None:
        lines.append(f"Nearest forward return is {robot.front_range_m:.2f}m.")
    if memory.last_action_summary:
        lines.append(f"Last action outcome: {memory.last_action_summary}")
    target_candidates = [item for item in candidates if item.target_type == "TARGET"]
    for item in target_candidates[:3]:
        lines.append(
            f"Target clue {item.target_id}: {item.label}; purpose={item.purpose}. "
            "This is a detector/navigation clue, not a confirmed person."
        )
    lines.extend(["", "Candidate IDs you may reference:"])
    if not candidates:
        lines.append("- No fresh candidate is currently valid.")
    for item in candidates:
        allowed_actions = {
            "FRONTIER": "move_to,request_view",
            "VIEWPOINT": "look_at,request_view",
            "TARGET": "look_at,request_view",
            "ANCHOR": "look_at,request_view",
        }.get(item.target_type, "request_view")
        lines.append(
            f"- {item.target_type}:{item.target_id} "
            f"(target_type={item.target_type}; target_id={item.target_id}) — "
            f"{item.label}; purpose={item.purpose}; "
            f"path={item.path_length_m:.2f}m; risk={item.risk:.2f}; "
            f"info_gain={item.information_gain:.2f}; allowed_actions={allowed_actions}"
        )
    if not any(item.target_type == "FRONTIER" for item in candidates):
        lines.append(
            "No translational FRONTIER is eligible now. Do not call move_to; "
            "use look_at on a VIEWPOINT to expand SLAM."
        )
    if visual is None:
        lines.append("No visual view is attached for this decision.")
    else:
        lines.append(
            f"Visual view attached: {visual.view_kind}; target "
            f"{visual.target_type}:{visual.target_id}; JPEG sha256={visual.frame.sha256}."
        )
        lines.append(
            "Consume this requested image now; do not request the identical view again."
        )
    lines.append(f"Checkpoint goal: {GOAL_ID}.")
    for finding in memory.durable_findings[-8:]:
        lines.append(f"Known: {finding}")
    for rejected in memory.rejected_alternatives[-6:]:
        lines.append(f"Rejected: {rejected}")
    for unresolved in memory.unresolved[-6:]:
        lines.append(f"Unresolved: {unresolved}")
    if memory.active_skill_id:
        lines.append(
            f"Checkpoint skill result: {memory.active_skill_id} was loaded in an earlier turn; "
            "reload it only if its instructions are needed again."
        )
    lines.extend(
        [
            f"Current question: {memory.question}",
            f"Current plan: {memory.plan_summary}",
            "Choose the next useful action. Use a tool for every physical action.",
        ]
    )
    return "\n".join(lines)


def _candidate_matches(candidate: Candidate, need: str) -> bool:
    if need == "CHOOSE_ROUTE":
        return candidate.target_type in {"VIEWPOINT", "FRONTIER"}
    if need == "INSPECT_TARGET":
        return candidate.target_type in {"VIEWPOINT", "FRONTIER", "TARGET"}
    if need == "RECOVER_TRACKING":
        return candidate.target_type in {"ANCHOR", "VIEWPOINT"}
    return candidate.target_type != "VIEWPOINT"


def _question_for(need: str) -> str:
    return {
        "CHOOSE_ROUTE": "¿Qué candidato expande cobertura con mejor relación información/riesgo?",
        "INSPECT_TARGET": "¿Qué vista permite verificar la pista humana sin asumir que ya es una persona?",
        "RECOVER_TRACKING": "¿Qué acción segura recupera VIO antes de trasladarse?",
    }.get(need, "¿Qué observación o acción segura aporta más a la misión ahora?")


def _object(value: dict[str, Any], key: str) -> dict[str, Any]:
    result = value.get(key)
    if not isinstance(result, dict):
        raise ValueError(f"{key} is missing")
    return result


def _integer(value: dict[str, Any], key: str) -> int:
    result = value.get(key)
    if isinstance(result, bool) or not isinstance(result, int) or result < 0:
        raise ValueError(f"{key} must be a non-negative integer")
    return result


def _number(value: Any, fallback: float = 0.0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return fallback
    return float(value)


def _percent(value: float) -> str:
    return f"{int(max(0.0, min(1.0, value)) * 100)}%"
