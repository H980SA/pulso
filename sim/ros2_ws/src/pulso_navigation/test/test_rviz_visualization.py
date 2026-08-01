import pytest
from builtin_interfaces.msg import Time
from visualization_msgs.msg import Marker

from pulso_navigation.frontier import FrontierCandidate
from pulso_navigation.rviz_visualization import (
    NavigationVisualization,
    candidate_marker_array,
    candidate_path,
    trajectory_path,
)


def _candidate(
    candidate_id: str,
    path: tuple[tuple[float, float], ...],
    *,
    kind: str = "FRONTIER",
) -> FrontierCandidate:
    return FrontierCandidate(
        candidate_id=candidate_id,
        x=path[-1][0],
        y=path[-1][1],
        path=path,
        path_length_m=1.0,
        risk=0.2,
        information_gain=0.8,
        frontier_cells=12,
        kind=kind,
    )


def test_candidate_markers_are_labeled_colored_and_clear_stale_routes() -> None:
    stamp = Time(sec=7, nanosec=11)
    candidates = [
        _candidate("F_NORTH", ((0.0, 0.0), (0.5, 0.5))),
        _candidate("victim_1", ((0.0, 0.0), (0.8, -0.2)), kind="TARGET"),
    ]

    array = candidate_marker_array(candidates, selected_id="victim_1", stamp=stamp)

    assert array.markers[0].action == Marker.DELETEALL
    assert len(array.markers) == 7
    routes = [marker for marker in array.markers if marker.ns == "candidate_routes"]
    goals = [marker for marker in array.markers if marker.ns == "candidate_goals"]
    labels = [marker for marker in array.markers if marker.ns == "candidate_labels"]
    assert all(marker.header.frame_id == "map" for marker in array.markers)
    assert routes[0].color.r != routes[1].color.r
    assert routes[1].scale.x > routes[0].scale.x
    assert goals[1].scale.x > goals[0].scale.x
    assert labels[0].text == "A FRONTIER"
    assert labels[1].text == "B SELECTED"


def test_selected_path_preserves_candidate_geometry_in_map_frame() -> None:
    stamp = Time(sec=9, nanosec=3)
    candidate = _candidate(
        "F_EAST",
        ((-0.2, 0.1), (0.4, 0.2), (1.0, 0.25)),
    )

    message = candidate_path(candidate, stamp)

    assert message.header.frame_id == "map"
    assert message.header.stamp == stamp
    assert [(pose.pose.position.x, pose.pose.position.y) for pose in message.poses] == [
        (-0.2, 0.1),
        (0.4, 0.2),
        (1.0, 0.25),
    ]
    assert all(pose.pose.orientation.w == pytest.approx(1.0) for pose in message.poses)


def test_trajectory_path_keeps_each_recorded_pose_timestamp() -> None:
    first = Time(sec=1, nanosec=10)
    second = Time(sec=2, nanosec=20)

    message = trajectory_path(
        ((0.0, 0.1, 0.2, first), (0.4, 0.5, -0.3, second)),
        second,
    )

    assert message.header.frame_id == "map"
    assert [pose.header.stamp for pose in message.poses] == [first, second]
    assert message.poses[1].pose.position.x == pytest.approx(0.4)
    assert message.poses[1].pose.orientation.z == pytest.approx(-0.1494381)
    assert message.poses[1].pose.orientation.w == pytest.approx(0.9887711)


class _Publisher:
    def __init__(self) -> None:
        self.messages = []

    def publish(self, message) -> None:
        self.messages.append(message)


class _Node:
    def __init__(self) -> None:
        self.publishers = {}

    def create_publisher(self, _message_type, topic: str, _depth: int) -> _Publisher:
        publisher = _Publisher()
        self.publishers[topic] = publisher
        return publisher


def test_visualization_tracks_only_the_active_selected_action() -> None:
    node = _Node()
    visualization = NavigationVisualization(node, trajectory_limit=2)
    candidate = _candidate("F_NORTH", ((0.0, 0.0), (0.5, 0.5)))
    first = Time(sec=1)
    second = Time(sec=2)
    third = Time(sec=3)

    visualization.publish_candidates([candidate], first)
    visualization.select("move-1", candidate, (0.0, 0.0, 0.0), first)
    assert visualization.is_tracking("move-1")
    visualization.record_pose((0.0, 0.0, 0.0), second)
    visualization.record_pose((0.2, 0.0, 0.1), second)
    visualization.finish("another-action", (0.3, 0.0, 0.1), third)
    visualization.record_pose((0.4, 0.0, 0.2), third)
    visualization.finish("move-1", (0.5, 0.0, 0.2), third)
    assert not visualization.is_tracking("move-1")
    visualization.record_pose((0.8, 0.0, 0.2), third)

    trajectory_messages = node.publishers[
        "/pulso/navigation/executed_trajectory"
    ].messages
    assert len(trajectory_messages) == 5
    assert [pose.pose.position.x for pose in trajectory_messages[-1].poses] == [
        pytest.approx(0.4),
        pytest.approx(0.5),
    ]
    selected_markers = node.publishers["/pulso/navigation/candidate_markers"].messages[-1]
    assert any("SELECTED" in marker.text for marker in selected_markers.markers)
