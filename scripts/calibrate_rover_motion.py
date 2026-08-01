#!/usr/bin/env python3
"""Measure commanded OpenBot motion against truth, wheel odometry and VIO.

Run this only against an otherwise idle Pulso simulation. The script publishes
through the normal desired-velocity boundary, so the production safety gate is
part of the measurement rather than bypassed.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
import statistics
import time

from diagnostic_msgs.msg import DiagnosticArray
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
import rclpy
from rclpy.node import Node


SOURCES = {
    "truth": "/pulso/sim/ground_truth/odom",
    "wheel": "/pulso/base/wheel/odom",
    "vio": "/pulso/phone/vio/odom",
}


def wrap_angle(angle: float) -> float:
    return math.atan2(math.sin(angle), math.cos(angle))


def yaw_from_odom(message: Odometry) -> float:
    q = message.pose.pose.orientation
    return math.atan2(
        2.0 * (q.w * q.z + q.x * q.y),
        1.0 - 2.0 * (q.y * q.y + q.z * q.z),
    )


@dataclass(frozen=True)
class Pose2D:
    x: float
    y: float
    yaw: float


@dataclass(frozen=True)
class Delta2D:
    forward_m: float
    left_m: float
    yaw_rad: float


def local_delta(start: Pose2D, end: Pose2D) -> Delta2D:
    dx, dy = end.x - start.x, end.y - start.y
    cosine, sine = math.cos(start.yaw), math.sin(start.yaw)
    return Delta2D(
        forward_m=cosine * dx + sine * dy,
        left_m=-sine * dx + cosine * dy,
        yaw_rad=wrap_angle(end.yaw - start.yaw),
    )


class CalibrationNode(Node):
    def __init__(self) -> None:
        super().__init__("pulso_rover_motion_calibration")
        self.poses: dict[str, Pose2D] = {}
        self.safe_commands: list[tuple[float, float]] = []
        self.safety_reasons: list[str] = []
        self.publisher = self.create_publisher(Twist, "/pulso/base/cmd_vel_desired", 10)
        for source, topic in SOURCES.items():
            self.create_subscription(
                Odometry,
                topic,
                lambda message, source=source: self._on_odom(source, message),
                20,
            )
        self.create_subscription(
            Twist, "/pulso/base/cmd_vel_safe", self._on_safe_command, 20
        )
        self.create_subscription(
            DiagnosticArray, "/pulso/base/safety/status", self._on_safety, 20
        )

    def _on_odom(self, source: str, message: Odometry) -> None:
        point = message.pose.pose.position
        self.poses[source] = Pose2D(point.x, point.y, yaw_from_odom(message))

    def _on_safe_command(self, message: Twist) -> None:
        self.safe_commands.append((float(message.linear.x), float(message.angular.z)))

    def _on_safety(self, message: DiagnosticArray) -> None:
        if not message.status:
            return
        reason = next(
            (item.value for item in message.status[0].values if item.key == "reason"),
            message.status[0].message,
        )
        self.safety_reasons.append(reason)

    def command(self, linear: float, angular: float) -> None:
        message = Twist()
        message.linear.x = linear
        message.angular.z = angular
        self.publisher.publish(message)


def spin_for(
    node: CalibrationNode,
    duration_s: float,
    linear: float = 0.0,
    angular: float = 0.0,
) -> None:
    deadline = time.monotonic() + duration_s
    next_publish = 0.0
    while time.monotonic() < deadline:
        now = time.monotonic()
        if now >= next_publish:
            node.command(linear, angular)
            next_publish = now + 0.04
        rclpy.spin_once(node, timeout_sec=0.01)


def wait_for_inputs(node: CalibrationNode, timeout_s: float) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        rclpy.spin_once(node, timeout_sec=0.05)
        if set(node.poses) == set(SOURCES) and node.safe_commands:
            return
    missing = sorted(set(SOURCES) - set(node.poses))
    raise RuntimeError(f"Calibration inputs did not become ready: {missing}")


def summarize_phase(
    node: CalibrationNode,
    name: str,
    duration_s: float,
    linear: float,
    angular: float,
) -> dict:
    spin_for(node, 0.5)
    starts = dict(node.poses)
    command_index = len(node.safe_commands)
    reason_index = len(node.safety_reasons)
    spin_for(node, duration_s, linear, angular)
    spin_for(node, 0.4)
    ends = dict(node.poses)
    commands = node.safe_commands[command_index:]
    reasons = node.safety_reasons[reason_index:]
    deltas = {
        source: asdict(local_delta(starts[source], ends[source])) for source in SOURCES
    }
    return {
        "name": name,
        "duration_s": duration_s,
        "requested": {"linear_mps": linear, "angular_rps": angular},
        "safe_command_median": {
            "linear_mps": statistics.median(item[0] for item in commands),
            "angular_rps": statistics.median(item[1] for item in commands),
        },
        "safety_reasons": sorted(set(reasons)),
        "start": {source: asdict(pose) for source, pose in starts.items()},
        "end": {source: asdict(pose) for source, pose in ends.items()},
        "delta": deltas,
    }


def build_diagnostics(phases: list[dict]) -> dict:
    straight, rotate = phases
    straight_expected = straight["safe_command_median"]["linear_mps"] * straight["duration_s"]
    rotate_expected = rotate["safe_command_median"]["angular_rps"] * rotate["duration_s"]
    truth_straight = straight["delta"]["truth"]
    truth_rotate = rotate["delta"]["truth"]
    wheel_straight = straight["delta"]["wheel"]
    wheel_rotate = rotate["delta"]["wheel"]
    return {
        "straight_forward_ratio": (
            truth_straight["forward_m"] / straight_expected
            if abs(straight_expected) > 1e-6
            else None
        ),
        "straight_lateral_m": truth_straight["left_m"],
        "straight_yaw_rad": truth_straight["yaw_rad"],
        "straight_truth_to_wheel_ratio": (
            truth_straight["forward_m"] / wheel_straight["forward_m"]
            if abs(wheel_straight["forward_m"]) > 1e-6
            else None
        ),
        "rotate_yaw_ratio": (
            truth_rotate["yaw_rad"] / rotate_expected
            if abs(rotate_expected) > 1e-6
            else None
        ),
        "rotate_translation_m": math.hypot(
            truth_rotate["forward_m"], truth_rotate["left_m"]
        ),
        "rotate_truth_to_wheel_ratio": (
            truth_rotate["yaw_rad"] / wheel_rotate["yaw_rad"]
            if abs(wheel_rotate["yaw_rad"]) > 1e-6
            else None
        ),
        "wheel_truth_rotate_yaw_error_rad": wrap_angle(
            wheel_rotate["yaw_rad"] - truth_rotate["yaw_rad"]
        ),
        "vio_truth_rotate_yaw_error_rad": wrap_angle(
            rotate["delta"]["vio"]["yaw_rad"] - truth_rotate["yaw_rad"]
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--straight-seconds", type=float, default=2.0)
    parser.add_argument("--rotate-seconds", type=float, default=3.0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    rclpy.init()
    node = CalibrationNode()
    try:
        wait_for_inputs(node, 20.0)
        spin_for(node, 1.0)
        phases = [
            summarize_phase(node, "straight", args.straight_seconds, 0.10, 0.0),
            summarize_phase(node, "rotate", args.rotate_seconds, 0.0, 0.38),
        ]
        report = {"contract": "pulso.rover-calibration.v1", "phases": phases}
        report["diagnostics"] = build_diagnostics(phases)
        encoded = json.dumps(report, indent=2, sort_keys=True)
        if args.output:
            args.output.write_text(encoded + "\n", encoding="utf-8")
        print(encoded)
        return 0
    finally:
        node.command(0.0, 0.0)
        spin_for(node, 0.4)
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
