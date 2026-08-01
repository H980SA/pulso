import json

from pulso_navigation.action_contract import parse_action
from pulso_navigation.candidate_capability import (
    CandidateCapabilitySet,
    validate_candidate_grant,
)
from pulso_navigation.frontier import FrontierCandidate



def valid_action(**updates):
    payload = {
        "contract_version": "pulso.action.v1",
        "action_id": "A-1",
        "mission_id": "M-1",
        "issued_monotonic_ns": 1,
        "kind": "LOOK_AT",
        "target": {"type": "TARGET", "id": "PERSON_1"},
        "candidate_capability": "abcdefghijklmnopqrstuvwxyz_123456",
        "expected_navigation_revision": 1,
        "expected_tracking_epoch": 1,
        "expected_target_revision": 2,
        "parameters": {},
    }
    payload.update(updates)
    return json.dumps(payload)


def target(revision=2):
    return FrontierCandidate(
        "PERSON_1", 1.0, 0.0, ((0.0, 0.0), (1.0, 0.0)), 0.0, 0.1, 0.8, 0,
        kind="TARGET", rotation_only=True, target_revision=revision,
    )


def test_capability_binds_revision_tracking_and_target_evidence():
    grants = CandidateCapabilitySet(lifetime_ns=100)
    candidate = target()
    snapshot = grants.refresh([candidate], 10)
    intent = parse_action(valid_action(
        candidate_capability=snapshot.capabilities[candidate.candidate_id],
        expected_navigation_revision=snapshot.navigation_revision,
    ))
    assert validate_candidate_grant(intent, candidate, snapshot, 1, 20) is None
    assert validate_candidate_grant(intent, candidate, snapshot, 2, 20)[0] == "STALE_TRACKING_EPOCH"
    assert validate_candidate_grant(intent, candidate, snapshot, 1, 111)[0] == "EXPIRED_CAPABILITY"
    assert validate_candidate_grant(intent, target(3), snapshot, 1, 20)[0] == "STALE_TARGET_REVISION"


def test_target_revision_rotates_the_opaque_capability():
    grants = CandidateCapabilitySet(lifetime_ns=100)
    first = grants.refresh([target(1)], 10)
    second = grants.refresh([target(2)], 20)
    assert second.navigation_revision > first.navigation_revision
    assert second.capabilities != first.capabilities
