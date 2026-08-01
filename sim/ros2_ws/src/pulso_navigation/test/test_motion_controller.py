from types import SimpleNamespace

from pulso_navigation.frontier import FrontierCandidate
from pulso_navigation.motion_controller import MotionController


class FakeClock:
    def __init__(self):
        self.nanoseconds = 0

    def now(self):
        return SimpleNamespace(nanoseconds=self.nanoseconds)


class FakeNode:
    def __init__(self):
        self.clock = FakeClock()

    def get_clock(self):
        return self.clock

    def get_parameter(self, name):
        values = {"angular_speed_rps": 0.38, "linear_speed_mps": 0.12}
        return SimpleNamespace(value=values[name])


class FakeTransformBuffer:
    def lookup_transform(self, *_args, **_kwargs):
        return SimpleNamespace(
            transform=SimpleNamespace(
                translation=SimpleNamespace(x=0.0, y=0.0),
                rotation=SimpleNamespace(x=0.0, y=0.0, z=0.0, w=1.0),
            )
        )


class FakePublisher:
    def __init__(self):
        self.messages = []

    def publish(self, message):
        self.messages.append(message)


def candidate(*, x=1.0, path_length_m=1.0):
    return FrontierCandidate(
        "F_+001_+001",
        x,
        0.0,
        ((0.0, 0.0), (x, 0.0)),
        path_length_m,
        0.2,
        0.8,
        8,
    )


def controller(*, pose=None):
    node = FakeNode()
    publisher = FakePublisher()
    results = []
    pose = pose if pose is not None else [0.0, 0.0, 0.0]
    motion = MotionController(
        node,
        FakeTransformBuffer(),
        publisher,
        lambda _frame: tuple(pose),
        lambda *args: results.append(args),
        lambda: None,
    )
    return node, publisher, results, motion


def test_sustained_near_field_veto_finishes_move_as_blocked():
    node, publisher, results, motion = controller()
    assert motion.start("A-1", "MOVE_TO", candidate()) is None

    motion.observe_safety_reason("NEAR_FIELD_OBSTACLE")
    node.clock.nanoseconds = 1_499_000_000
    motion.tick()
    assert motion.active is not None
    assert results == []

    node.clock.nanoseconds = 1_500_000_000
    motion.tick()

    assert motion.active is None
    assert publisher.messages[-1].linear.x == 0.0
    assert results == [
        (
            "A-1",
            False,
            "BLOCKED",
            "Near-field safety held forward motion for 1.5 seconds.",
            {
                "candidate_id": "F_+001_+001",
                "reason": "NEAR_FIELD_OBSTACLE",
            },
        )
    ]


def test_clear_safety_resets_block_timer():
    node, _publisher, results, motion = controller()
    assert motion.start("A-2", "MOVE_TO", candidate()) is None

    motion.observe_safety_reason("NEAR_FIELD_OBSTACLE")
    node.clock.nanoseconds = 1_000_000_000
    motion.observe_safety_reason("NONE")
    node.clock.nanoseconds = 2_000_000_000
    motion.observe_safety_reason("NEAR_FIELD_OBSTACLE")
    node.clock.nanoseconds = 3_499_000_000
    motion.tick()

    assert motion.active is not None
    assert results == []


def test_move_target_inside_arrival_envelope_is_rejected():
    _node, _publisher, results, motion = controller()

    failure = motion.start(
        "A-near",
        "MOVE_TO",
        candidate(x=0.14, path_length_m=0.14),
    )

    assert failure is not None
    assert failure[0] == "TARGET_TOO_CLOSE"
    assert "0.150 m" in failure[1]
    assert motion.active is None
    assert results == []


def test_move_success_requires_goal_tolerance_and_measured_displacement():
    pose = [0.0, 0.0, 0.0]
    _node, publisher, results, motion = controller(pose=pose)
    assert motion.start(
        "A-move",
        "MOVE_TO",
        candidate(x=0.22, path_length_m=0.22),
    ) is None

    pose[0] = 0.04
    motion.tick()
    assert motion.active is not None
    assert results == []

    pose[0] = 0.121
    motion.tick()

    assert motion.active is None
    assert publisher.messages[-1].linear.x == 0.0
    assert len(results) == 1
    action_id, accepted, status, detail, data = results[0]
    assert (action_id, accepted, status, detail) == (
        "A-move",
        True,
        "SUCCEEDED",
        "Frontier viewpoint reached.",
    )
    assert data["candidate_id"] == "F_+001_+001"
    assert data["odometry_displacement_m"] >= 0.05
    assert data["remaining_goal_distance_m"] <= 0.16
