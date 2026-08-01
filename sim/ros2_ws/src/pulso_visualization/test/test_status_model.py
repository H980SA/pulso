import math

from pulso_visualization.status_model import (
    DiagnosticState,
    StatusState,
    diagnostic_from_fields,
    format_status_lines,
    merge_action_state,
    parse_action_result,
)


def _lines_by_label(state: StatusState, now_ns: int = 10_000_000_000):
    return {
        line.label: line
        for line in format_status_lines(state, now_ns=now_ns, stale_after_ns=2_000_000_000)
    }


def test_formats_every_live_status_source() -> None:
    sampled_ns = 9_500_000_000
    state = StatusState(
        battery_fraction=0.76,
        battery_at_ns=sampled_ns,
        front_range_m=1.234,
        front_range_at_ns=sampled_ns,
        bumper_pressed=False,
        bumper_at_ns=sampled_ns,
        safety=DiagnosticState(level=0, state="CLEAR", reason="NONE"),
        safety_at_ns=sampled_ns,
        vio=DiagnosticState(level=0, state="TRACKING", quality=0.981),
        vio_at_ns=sampled_ns,
        imu_norm_mps2=9.806,
        imu_at_ns=sampled_ns,
        action=parse_action_result(
            '{"contract_version":"pulso.action-result.v1",'
            '"action_id":"move-17","accepted":true,"status":"ACTIVE",'
            '"detail":"moving","data":{"target_id":"frontier-a"}}'
        ),
    )

    lines = _lines_by_label(state)

    assert tuple(lines) == (
        "BATTERY", "SONAR", "BUMPER", "SAFETY", "VIO", "IMU", "ACTION"
    )
    assert lines["BATTERY"].value == "76%"
    assert lines["SONAR"].value == "1.23 m"
    assert lines["BUMPER"].value == "CLEAR"
    assert lines["SAFETY"].value == "CLEAR"
    assert lines["VIO"].value == "TRACKING · 98%"
    assert lines["IMU"].value == "9.81 m/s²"
    assert lines["ACTION"].value == "ACTIVE · frontier-a"
    assert lines["ACTION"].severity == "info"


def test_stale_samples_are_never_presented_as_live() -> None:
    state = StatusState(
        battery_fraction=0.9,
        battery_at_ns=1,
        front_range_m=None,
        front_range_at_ns=1,
        bumper_pressed=False,
        bumper_at_ns=1,
        safety=DiagnosticState(level=0, state="CLEAR"),
        safety_at_ns=1,
        vio=DiagnosticState(level=0, state="TRACKING", quality=0.9),
        vio_at_ns=1,
        imu_norm_mps2=9.8,
        imu_at_ns=1,
    )

    lines = _lines_by_label(state)

    for label in ("BATTERY", "SONAR", "BUMPER", "SAFETY", "VIO", "IMU"):
        assert lines[label].value == "STALE"
        assert lines[label].severity == "unknown"
    assert lines["ACTION"].value == "WAITING"


def test_diagnostics_normalize_quality_and_safe_text() -> None:
    diagnostic = diagnostic_from_fields(
        message="tracking\nnow",
        level=0,
        values={"state": " tracking ", "quality": "1.4", "reason": " none\t"},
    )

    assert diagnostic == DiagnosticState(
        level=0,
        state="TRACKING",
        reason="NONE",
        quality=1.0,
    )


def test_diagnostics_accept_humble_uint8_bytes() -> None:
    diagnostic = diagnostic_from_fields(
        message="LIMITED",
        level=b"\x01",
        values={"reason": "SONAR_NEAR"},
    )

    assert diagnostic.level == 1
    assert diagnostic.state == "LIMITED"


def test_action_result_parser_rejects_bad_contract_and_bounds_text() -> None:
    assert parse_action_result("not json") is None
    assert parse_action_result('{"contract_version":"other"}') is None

    action = parse_action_result(
        '{"contract_version":"pulso.action-result.v1",'
        '"action_id":"inspect\\n17","accepted":false,"status":"cancelled",'
        '"detail":"x","data":{"target_id":"' + ("a" * 200) + '"}}'
    )

    assert action is not None
    assert action.action_id == "inspect 17"
    assert action.status == "CANCELLED"
    assert action.target_id is not None
    assert len(action.target_id) == 64


def test_terminal_action_keeps_target_from_active_result() -> None:
    active = parse_action_result(
        '{"contract_version":"pulso.action-result.v1",'
        '"action_id":"move-17","accepted":true,"status":"ACTIVE",'
        '"detail":"moving","data":{"target_id":"F_A"}}'
    )
    terminal = parse_action_result(
        '{"contract_version":"pulso.action-result.v1",'
        '"action_id":"move-17","accepted":true,"status":"SUCCEEDED",'
        '"detail":"done","data":{}}'
    )

    assert active is not None and terminal is not None
    assert merge_action_state(active, terminal).target_id == "F_A"


def test_non_finite_sensor_values_are_shown_as_unavailable() -> None:
    sampled_ns = 9_500_000_000
    state = StatusState(
        battery_fraction=math.nan,
        battery_at_ns=sampled_ns,
        front_range_m=math.inf,
        front_range_at_ns=sampled_ns,
    )

    lines = _lines_by_label(state)

    assert lines["BATTERY"].value == "NO DATA"
    assert lines["SONAR"].value == "NO RETURN"
