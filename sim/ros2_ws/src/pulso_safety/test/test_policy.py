from pulso_safety.policy import MotionCommand, SafetyPolicy


def test_stops_forward_motion_inside_near_field():
    decision = SafetyPolicy().evaluate(MotionCommand(0.2, 0.0), 0.01, 0.12, False, False)
    assert decision.command.linear_x == 0.0
    assert decision.reason == "NEAR_FIELD_OBSTACLE"


def test_watchdog_stops_stale_commands():
    decision = SafetyPolicy().evaluate(MotionCommand(0.2, 0.2), 0.5, 2.0, False, False)
    assert decision.command == MotionCommand(0.0, 0.0)
    assert decision.reason == "COMMAND_WATCHDOG"


def test_slow_zone_scales_forward_speed():
    decision = SafetyPolicy().evaluate(MotionCommand(0.3, 0.1), 0.01, 0.315, False, False)
    assert 0.0 < decision.command.linear_x < 0.3
    assert decision.command.angular_z == 0.1
    assert decision.state == "LIMITED"


def test_reverse_remains_available_to_escape_obstacle():
    decision = SafetyPolicy().evaluate(MotionCommand(-0.2, 0.0), 0.01, 0.08, False, False)
    assert decision.command.linear_x == -0.2


def test_physical_bumper_overrides_rotation_and_translation():
    decision = SafetyPolicy().evaluate(MotionCommand(0.2, 0.6), 0.01, 2.0, True, False)
    assert decision.command == MotionCommand(0.0, 0.0)
    assert decision.reason == "BUMPER"


def test_estop_has_first_priority():
    decision = SafetyPolicy().evaluate(MotionCommand(-0.2, 0.6), 0.01, None, True, True)
    assert decision.command == MotionCommand(0.0, 0.0)
    assert decision.reason == "ESTOP"


def test_missing_or_stale_near_field_sensors_fail_closed_for_forward_motion():
    policy = SafetyPolicy()
    missing = policy.evaluate(MotionCommand(0.2, 0.0), 0.01, None, False, False)
    stale_range = policy.evaluate(
        MotionCommand(0.2, 0.0), 0.01, 2.0, False, False, range_age_s=1.0
    )
    stale_bumper = policy.evaluate(
        MotionCommand(0.2, 0.0), 0.01, 2.0, False, False, bumper_age_s=1.0
    )
    assert missing.reason == "RANGE_WATCHDOG"
    assert stale_range.reason == "RANGE_WATCHDOG"
    assert stale_bumper.reason == "BUMPER_WATCHDOG"


def test_sensor_watchdog_allows_rotation_or_escape_reverse():
    policy = SafetyPolicy()
    rotate = policy.evaluate(
        MotionCommand(0.0, 0.4), 0.01, None, False, False, 2.0, 2.0
    )
    reverse = policy.evaluate(
        MotionCommand(-0.1, 0.0), 0.01, None, False, False, 2.0, 2.0
    )
    assert rotate.command == MotionCommand(0.0, 0.4)
    assert reverse.command == MotionCommand(-0.1, 0.0)
