import json

import pytest

from pulso_navigation.action_contract import ActionContractError, ActionReplayGuard, parse_action


def valid_action(**updates):
    payload = {
        "contract_version": "pulso.action.v1",
        "action_id": "A-1",
        "mission_id": "M-1",
        "issued_monotonic_ns": 1,
        "kind": "LOOK_AT",
        "target": {"type": "TARGET", "id": "PERSON_1"},
        "candidate_capability": "abcdefghijklmnopqrstuvwxyz_123456",
        "expected_navigation_revision": 4,
        "expected_tracking_epoch": 1,
        "expected_target_revision": 2,
        "parameters": {},
    }
    payload.update(updates)
    return json.dumps(payload)


def test_valid_typed_action_is_normalized():
    action = parse_action(valid_action(kind="look_at"))
    assert action.kind == "LOOK_AT"
    assert action.target_type == "TARGET"
    assert action.target_id == "PERSON_1"


def test_generated_signed_frontier_id_round_trips_through_contract():
    action = parse_action(
        valid_action(target={"type": "FRONTIER", "id": "F_+001_-001"})
    )
    assert action.target_id == "F_+001_-001"


@pytest.mark.parametrize(
    "payload,status",
    [
        ("[]", "INVALID_CONTRACT"),
        (valid_action(contract_version="other"), "INVALID_CONTRACT"),
        (valid_action(action_id="x" * 97), "INVALID_ACTION_ID"),
        (valid_action(mission_id=""), "INVALID_MISSION_ID"),
        (valid_action(issued_monotonic_ns=-1), "INVALID_TIMESTAMP"),
        (valid_action(kind="EXEC_SHELL"), "INVALID_ACTION_KIND"),
        (valid_action(target=None), "INVALID_TARGET"),
        (valid_action(candidate_capability="guess"), "INVALID_CAPABILITY"),
        (valid_action(expected_navigation_revision=-1), "INVALID_CAPABILITY"),
    ],
)
def test_untrusted_actions_are_rejected(payload, status):
    with pytest.raises(ActionContractError) as failure:
        parse_action(payload)
    assert failure.value.status == status


def test_action_payload_and_replays_are_bounded():
    with pytest.raises(ActionContractError):
        parse_action(valid_action(parameters={"text": "x" * 17_000}))
    guard = ActionReplayGuard(capacity=2)
    assert guard.accept("A-1", 1)
    assert not guard.accept("A-1", 2)
    assert guard.accept("A-2", 3)
    assert guard.accept("A-3", 4)
    assert guard.accept("A-1", 5)
