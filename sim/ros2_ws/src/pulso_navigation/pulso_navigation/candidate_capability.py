"""Issue short-lived opaque grants for exact navigation candidate snapshots."""

from dataclasses import dataclass
import secrets

from .frontier import FrontierCandidate


@dataclass(frozen=True)
class CapabilitySnapshot:
    navigation_revision: int
    valid_until_ns: int
    capabilities: dict[str, str]


class CandidateCapabilitySet:
    def __init__(self, lifetime_ns: int = 20_000_000_000) -> None:
        self._lifetime_ns = lifetime_ns
        self._signature: tuple[str, ...] = ()
        self._revision = 0
        self._valid_until_ns = 0
        self._capabilities: dict[str, str] = {}

    def invalidate(self) -> None:
        self._valid_until_ns = 0

    def refresh(
        self, candidates: list[FrontierCandidate], now_ns: int
    ) -> CapabilitySnapshot:
        signature = tuple(
            sorted(
                f"{item.kind}:{item.candidate_id}:{item.target_revision}"
                for item in candidates
            )
        )
        if signature != self._signature or now_ns >= self._valid_until_ns:
            self._signature = signature
            self._revision += 1
            self._valid_until_ns = now_ns + self._lifetime_ns
            self._capabilities = {
                item.candidate_id: secrets.token_urlsafe(24) for item in candidates
            }
        return CapabilitySnapshot(
            self._revision,
            self._valid_until_ns,
            dict(self._capabilities),
        )


def validate_candidate_grant(
    intent,
    candidate: FrontierCandidate,
    snapshot: CapabilitySnapshot,
    tracking_epoch: int,
    now_ns: int,
) -> tuple[str, str] | None:
    if now_ns > snapshot.valid_until_ns:
        return "EXPIRED_CAPABILITY", "The candidate grant expired before execution."
    if snapshot.capabilities.get(candidate.candidate_id) != intent.candidate_capability:
        return "STALE_CAPABILITY", "The candidate grant is not current."
    if intent.expected_navigation_revision != snapshot.navigation_revision:
        return "STALE_NAVIGATION_REVISION", "Navigation changed after Gemma saw the candidate."
    if intent.expected_tracking_epoch != tracking_epoch:
        return "STALE_TRACKING_EPOCH", "Localization reset after Gemma saw the candidate."
    if (
        candidate.kind == "TARGET"
        and intent.expected_target_revision != candidate.target_revision
    ):
        return "STALE_TARGET_REVISION", "Target evidence changed before execution."
    return None
