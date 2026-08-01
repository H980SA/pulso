#!/usr/bin/env python3
"""Inspect frontier feasibility from live normalized topics, never simulator truth."""

import json
import time

from nav_msgs.msg import OccupancyGrid
import numpy as np
import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from pulso_navigation.frontier import GridSpec, extract_frontiers, world_to_cell


class DiagnosticsNode(Node):
    def __init__(self) -> None:
        super().__init__("pulso_frontier_diagnostics")
        self.map_message: OccupancyGrid | None = None
        self.robot_xy: tuple[float, float] | None = None
        self.create_subscription(OccupancyGrid, "/map", self._on_map, 1)
        self.create_subscription(String, "/pulso/hil/observation", self._on_observation, 1)

    def _on_map(self, message: OccupancyGrid) -> None:
        self.map_message = message

    def _on_observation(self, message: String) -> None:
        try:
            payload = json.loads(message.data)
            position = payload["robot"]["pose"]["position_m"]
            self.robot_xy = float(position[0]), float(position[1])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return


def main() -> None:
    rclpy.init()
    node = DiagnosticsNode()
    deadline = time.monotonic() + 8.0
    while time.monotonic() < deadline and (
        node.map_message is None or node.robot_xy is None
    ):
        rclpy.spin_once(node, timeout_sec=0.2)
    message, robot_xy = node.map_message, node.robot_xy
    if message is None or robot_xy is None:
        raise SystemExit("Timed out waiting for /map and /pulso/hil/observation")
    occupancy = np.asarray(message.data, dtype=np.int16).reshape(
        (message.info.height, message.info.width)
    )
    spec = GridSpec(
        float(message.info.resolution),
        float(message.info.origin.position.x),
        float(message.info.origin.position.y),
    )
    robot_cell = world_to_cell(robot_xy[0], robot_xy[1], spec)
    result = {
        "shape": [int(message.info.height), int(message.info.width)],
        "resolution_m": spec.resolution,
        "robot_xy": [round(value, 3) for value in robot_xy],
        "robot_cell": list(robot_cell),
        "counts": {
            "unknown": int(np.count_nonzero(occupancy < 0)),
            "free": int(np.count_nonzero((occupancy >= 0) & (occupancy <= 20))),
            "occupied": int(np.count_nonzero(occupancy >= 65)),
        },
        "candidates_by_inflation": {},
    }
    for inflation in (0.0, 0.05, 0.08, 0.10, 0.12, 0.16):
        candidates = extract_frontiers(
            occupancy, spec, robot_xy, inflation_m=inflation
        )
        result["candidates_by_inflation"][f"{inflation:.2f}"] = [
            {
                "id": candidate.candidate_id,
                "path_m": round(candidate.path_length_m, 3),
                "risk": round(candidate.risk, 3),
                "cells": candidate.frontier_cells,
            }
            for candidate in candidates
        ]
    print(json.dumps(result, indent=2))
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
