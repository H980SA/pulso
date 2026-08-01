"""Environment-backed gateway configuration for the supervised ExoMy field cut."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class Settings:
    api_token: str
    database_path: Path
    bind_host: str = "127.0.0.1"
    bind_port: int = 8765
    stage: str = "SHADOW"
    allow_actuation: bool = False
    exclusive_control_confirmed: bool = False
    ground_supervised_confirmed: bool = False
    rosbridge_url: str = "ws://127.0.0.1:9090"
    rosbridge_host: str = "127.0.0.1"
    rosbridge_port: int = 9090
    camera_health_url: str = "http://127.0.0.1:8080/"
    camera_snapshot_url: str = "http://127.0.0.1:8080/snapshot?topic=/pi_cam/image_raw"
    max_lease_seconds: int = 30
    max_duration_ms: int = 500
    heartbeat_timeout_ms: int = 300

    def __post_init__(self) -> None:
        if not self.api_token:
            raise ValueError("PULSO_API_TOKEN must be set")
        if self.stage not in {"SHADOW", "BENCH", "WHEELS_UP", "GROUND"}:
            raise ValueError("PULSO_STAGE must be SHADOW, BENCH, WHEELS_UP, or GROUND")
        if self.allow_actuation and not self.exclusive_control_confirmed:
            raise ValueError("Actuation requires PULSO_EXCLUSIVE_CONTROL_CONFIRMED=true")
        if self.stage == "SHADOW" and self.allow_actuation:
            raise ValueError("Actuation cannot be enabled in SHADOW")
        if self.allow_actuation and self.stage not in {"WHEELS_UP", "GROUND"}:
            raise ValueError("Actuation is restricted to WHEELS_UP or supervised GROUND")
        if self.allow_actuation and self.stage == "GROUND":
            if not self.ground_supervised_confirmed:
                raise ValueError("GROUND requires PULSO_GROUND_SUPERVISED_CONFIRMED=true")
            if self.max_duration_ms > 150:
                raise ValueError("GROUND max_duration_ms must be <=150")

    @classmethod
    def from_env(cls) -> "Settings":
        token = os.getenv("PULSO_API_TOKEN", "")
        token_file = os.getenv("PULSO_API_TOKEN_FILE")
        if not token and token_file:
            token_path = Path(token_file)
            if token_path.stat().st_mode & 0o077:
                raise ValueError("PULSO_API_TOKEN_FILE must not be accessible by group or others")
            token = token_path.read_text(encoding="utf-8").strip()
        return cls(
            api_token=token,
            database_path=Path(os.getenv("PULSO_DATABASE_PATH", ".state/pulso-rover.sqlite3")),
            bind_host=os.getenv("PULSO_BIND_HOST", "127.0.0.1"),
            bind_port=int(os.getenv("PULSO_BIND_PORT", "8765")),
            stage=os.getenv("PULSO_STAGE", "SHADOW").upper(),
            allow_actuation=_env_bool("PULSO_ALLOW_ACTUATION"),
            exclusive_control_confirmed=_env_bool("PULSO_EXCLUSIVE_CONTROL_CONFIRMED"),
            ground_supervised_confirmed=_env_bool("PULSO_GROUND_SUPERVISED_CONFIRMED"),
            rosbridge_url=os.getenv("PULSO_ROSBRIDGE_URL", "ws://127.0.0.1:9090"),
            rosbridge_host=os.getenv("PULSO_ROSBRIDGE_HOST", "127.0.0.1"),
            rosbridge_port=int(os.getenv("PULSO_ROSBRIDGE_PORT", "9090")),
            camera_health_url=os.getenv("PULSO_CAMERA_HEALTH_URL", "http://127.0.0.1:8080/"),
            camera_snapshot_url=os.getenv(
                "PULSO_CAMERA_SNAPSHOT_URL",
                "http://127.0.0.1:8080/snapshot?topic=/pi_cam/image_raw",
            ),
            max_lease_seconds=int(os.getenv("PULSO_MAX_LEASE_SECONDS", "30")),
            max_duration_ms=int(os.getenv("PULSO_MAX_DURATION_MS", "500")),
            heartbeat_timeout_ms=int(os.getenv("PULSO_HEARTBEAT_TIMEOUT_MS", "300")),
        )
