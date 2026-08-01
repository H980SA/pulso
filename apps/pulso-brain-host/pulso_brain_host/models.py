from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any


TARGET_TYPES = frozenset({"VIEWPOINT", "FRONTIER", "TARGET", "ANCHOR"})


@dataclass(frozen=True)
class RobotSnapshot:
    captured_ns: int
    source: str
    tracking_state: str
    tracking_quality: float
    tracking_epoch: int
    x: float
    y: float
    heading_deg: float
    pose_confidence: float
    motion_state: str
    battery_fraction: float
    flashlight_on: bool
    front_range_m: float | None


@dataclass(frozen=True)
class Candidate:
    target_type: str
    target_id: str
    label: str
    purpose: str
    x: float
    y: float
    path_length_m: float
    risk: float
    information_gain: float
    capability: str
    target_revision: int | None = None


@dataclass(frozen=True)
class NavigationSnapshot:
    captured_ns: int
    sensor_map_seq: int
    navigation_revision: int
    valid_until_ns: int
    candidates: tuple[Candidate, ...]


@dataclass(frozen=True)
class ImageFrame:
    kind: str
    source_topic: str
    captured_ns: int
    format: str
    jpeg: bytes
    ros_message: dict[str, Any]

    @property
    def sha256(self) -> str:
        return sha256(self.jpeg).hexdigest()


@dataclass(frozen=True)
class RequestedVisual:
    view_kind: str
    target_type: str
    target_id: str
    navigation_revision: int
    frame: ImageFrame


@dataclass(frozen=True)
class CognitiveMemory:
    question: str = "¿Qué observación o acción segura aporta más a la misión ahora?"
    plan_summary: str = "Expandir cobertura y verificar evidencia humana sin arriesgar el rover."
    active_skill_id: str | None = None
    last_action_summary: str | None = None
    durable_findings: tuple[str, ...] = ()
    rejected_alternatives: tuple[str, ...] = ()
    unresolved: tuple[str, ...] = (
        "Qué rutas siguen siendo transitables",
        "Si existe evidencia humana verificable",
    )


@dataclass(frozen=True)
class SelectedPacket:
    world_seq: int
    decision_need: str
    navigation_revision: int
    tracking_epoch: int
    prompt_text: str
    candidates: tuple[Candidate, ...]
    visual: RequestedVisual | None
    memory: CognitiveMemory

    def candidate(self, target_type: str, target_id: str) -> Candidate | None:
        return next(
            (
                item
                for item in self.candidates
                if item.target_type == target_type and item.target_id == target_id
            ),
            None,
        )


@dataclass
class LiveState:
    world_seq: int = 0
    robot: RobotSnapshot | None = None
    navigation: NavigationSnapshot | None = None
    images: dict[str, ImageFrame] = field(default_factory=dict)
    memory: CognitiveMemory = field(default_factory=CognitiveMemory)
    requested_visual: RequestedVisual | None = None

    @property
    def ready(self) -> bool:
        return self.robot is not None and self.navigation is not None
