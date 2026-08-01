from pulso_navigation.candidate_cooldown import CandidateCooldowns
from pulso_navigation.frontier import FrontierCandidate


def candidate(candidate_id: str) -> FrontierCandidate:
    return FrontierCandidate(
        candidate_id,
        1.0,
        0.0,
        ((0.0, 0.0), (1.0, 0.0)),
        1.0,
        0.2,
        0.8,
        8,
    )


def test_blocked_candidate_is_suppressed_then_returns_after_cooldown():
    cooldowns = CandidateCooldowns(duration_ns=20)
    first, second = candidate("F_A"), candidate("F_B")

    cooldowns.mark("F_A", 100)

    assert cooldowns.available([first, second], 119) == [second]
    assert cooldowns.available([first, second], 120) == [first, second]


def test_empty_candidate_id_does_not_suppress_anything():
    cooldowns = CandidateCooldowns(duration_ns=20)
    current = candidate("F_A")

    cooldowns.mark("", 100)

    assert cooldowns.available([current], 101) == [current]

