"""Short-lived memory for physically blocked candidate routes."""

from __future__ import annotations

from .frontier import FrontierCandidate


class CandidateCooldowns:
    """Suppress an exact candidate briefly after the safety gate blocks it.

    This is not route selection: Gemma still chooses among the remaining live
    candidates. It prevents an already disproven capability from being issued
    again before SLAM has had time to incorporate the obstacle.
    """

    def __init__(self, duration_ns: int = 20_000_000_000) -> None:
        self._duration_ns = max(1, int(duration_ns))
        self._blocked_until: dict[str, int] = {}

    def mark(self, candidate_id: str, now_ns: int) -> None:
        if candidate_id:
            self._blocked_until[candidate_id] = int(now_ns) + self._duration_ns

    def available(
        self, candidates: list[FrontierCandidate], now_ns: int
    ) -> list[FrontierCandidate]:
        now_ns = int(now_ns)
        self._blocked_until = {
            candidate_id: deadline
            for candidate_id, deadline in self._blocked_until.items()
            if deadline > now_ns
        }
        return [
            candidate
            for candidate in candidates
            if candidate.candidate_id not in self._blocked_until
        ]

