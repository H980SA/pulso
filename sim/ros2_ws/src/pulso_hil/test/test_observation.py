from pulso_hil.observation import build_observation


def test_observation_matches_required_contract_shape():
    observation = build_observation(
        sequence=7,
        captured_ns=123,
        pose=(1.0, 2.0, 0.0),
        heading_deg=45.0,
        pose_confidence=0.9,
        tracking_state="TRACKING",
        tracking_epoch=2,
        tracking_quality=0.87,
        motion_state="MOVING",
        battery_fraction=0.8,
        flashlight_on=True,
        front_range_m=0.7,
        bumper_pressed=False,
    )
    assert observation["contract_version"] == "pulso.observation.v1"
    assert observation["source"] == "GAZEBO_HIL"
    assert observation["tracking"]["epoch"] == 2
    assert observation["robot"]["pose"]["position_m"] == [1.0, 2.0, 0.0]
    assert {artifact["kind"] for artifact in observation["artifacts"]} == {
        "EGO_RGB", "RAW_DEPTH", "DENSE_POINT_CLOUD"
    }


def test_observation_clamps_probabilities_and_range():
    observation = build_observation(
        sequence=1,
        captured_ns=-1,
        pose=(0.0, 0.0, 0.0),
        heading_deg=0.0,
        pose_confidence=2.0,
        tracking_state="LIMITED",
        tracking_epoch=-3,
        tracking_quality=-1.0,
        motion_state="STOPPED",
        battery_fraction=4.0,
        flashlight_on=False,
        front_range_m=-2.0,
        bumper_pressed=False,
    )
    assert observation["captured_monotonic_ns"] == 0
    assert observation["tracking"]["quality"] == 0.0
    assert observation["tracking"]["epoch"] == 0
    assert observation["robot"]["battery_fraction"] == 1.0
    assert observation["robot"]["front_range_m"] == 0.0
