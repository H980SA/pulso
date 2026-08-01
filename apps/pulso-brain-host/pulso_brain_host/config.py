from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True)
class BrainConfig:
    rosbridge_url: str
    model_path: Path
    backend: str = "gpu"
    max_num_tokens: int = 4096
    temperature: float = 0.2
    # Kept so existing profiling callers remain source-compatible. Runtime
    # scheduling now uses semantic_cooldown_s instead of a polling interval.
    min_cycle_interval_s: float = 0.5
    max_tool_calls_per_turn: int = 4
    semantic_cooldown_s: float = 8.0

    @classmethod
    def from_env(cls, project_root: Path) -> "BrainConfig":
        return cls(
            rosbridge_url=os.getenv("PULSO_ROSBRIDGE_URL", "ws://192.168.18.51:9091"),
            model_path=Path(
                os.getenv(
                    "PULSO_GEMMA_MODEL",
                    str(project_root / ".tools/models/gemma-4-E4B-it.litertlm"),
                )
            ).expanduser().resolve(),
            backend=os.getenv("PULSO_LITERT_BACKEND", "gpu").lower(),
            max_num_tokens=int(os.getenv("PULSO_MAX_CONTEXT_TOKENS", "4096")),
            temperature=float(os.getenv("PULSO_TEMPERATURE", "0.2")),
            min_cycle_interval_s=float(os.getenv("PULSO_MIN_CYCLE_INTERVAL_S", "0.5")),
            max_tool_calls_per_turn=int(os.getenv("PULSO_MAX_TOOL_CALLS", "4")),
            semantic_cooldown_s=float(os.getenv("PULSO_SEMANTIC_COOLDOWN_S", "8.0")),
        )

    @property
    def model_id(self) -> str:
        """Public artifact identity without leaking its host filesystem path."""
        return self.model_path.name

    def validate(self) -> None:
        if not self.model_path.is_file():
            raise FileNotFoundError(f"LiteRT-LM model not found: {self.model_path}")
        if self.backend not in {"cpu", "gpu"}:
            raise ValueError("PULSO_LITERT_BACKEND must be cpu or gpu")
        if self.max_num_tokens < 1024:
            raise ValueError("PULSO_MAX_CONTEXT_TOKENS must be at least 1024")
        if not 0 <= self.temperature <= 2:
            raise ValueError("PULSO_TEMPERATURE must be between 0 and 2")
        if not 0 <= self.semantic_cooldown_s <= 60:
            raise ValueError("PULSO_SEMANTIC_COOLDOWN_S must be between 0 and 60 seconds")
