"""Deterministically audit rover reachability in an open Pulso Blender scene.

The planner uses a 5 cm occupancy grid and inflates every blocking footprint by
the rover's conservative 21.5 cm swept radius.  The 15 cm room-B level change
can only be crossed through the authored south ramp; the corridor floor heave
can only be entered through its transition wedge.
"""

from __future__ import annotations

import heapq
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector


PROJECT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = (
    PROJECT / "art/current/ragdoll/navigable/navigation_report.json"
)

RESOLUTION_M = 0.05
ROVER_RADIUS_M = 0.215
ROVER_BODY_TOP_M = 0.22
WORLD = (-6.2, 10.0, -3.3, 3.4)

FLOORS = (
    (-6.2, -1.0, -3.2, 3.2),
    (-1.0, 5.2, -1.1, 1.1),
    (0.4, 5.2, -3.3, -1.1),
    (5.2, 7.0, -3.3, 3.4),
    (7.0, 10.0, -3.3, 3.4),
)

B_RAMP = (7.0, 8.30, -3.00, -2.42)
CORRIDOR_RAMP = (3.88, 4.565, -0.72, 0.02)

SURFACE_COLLIDERS = {
    "COL_ARCH_HEAVE_SLAB_COR",
    "COL_NAV_RAMP_CORRIDOR",
    "COL_NAV_RAMP_B_SOUTH",
}


def output_path() -> Path:
    if "--" not in sys.argv:
        return DEFAULT_OUTPUT
    arguments = sys.argv[sys.argv.index("--") + 1 :]
    for index, argument in enumerate(arguments):
        if argument == "--output" and index + 1 < len(arguments):
            return Path(arguments[index + 1]).expanduser().resolve()
    return DEFAULT_OUTPUT


def world_bounds(obj: bpy.types.Object) -> tuple[Vector, Vector]:
    points = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    low = Vector(tuple(min(point[axis] for point in points) for axis in range(3)))
    high = Vector(tuple(max(point[axis] for point in points) for axis in range(3)))
    return low, high


def evaluated_bounds(objects: list[bpy.types.Object]) -> tuple[Vector, Vector]:
    depsgraph = bpy.context.evaluated_depsgraph_get()
    low = Vector((math.inf, math.inf, math.inf))
    high = Vector((-math.inf, -math.inf, -math.inf))
    for obj in objects:
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        try:
            for vertex in mesh.vertices:
                world = evaluated.matrix_world @ vertex.co
                for axis in range(3):
                    low[axis] = min(low[axis], world[axis])
                    high[axis] = max(high[axis], world[axis])
        finally:
            evaluated.to_mesh_clear()
    return low, high


def victim_center(code: str) -> Vector:
    rig = bpy.data.objects[f"PULSO_SURVIVOR_{code}_RIG"]
    meshes = [
        obj
        for obj in bpy.data.objects
        if obj.type == "MESH"
        and obj.name.startswith(f"PULSO_SURVIVOR_{code}_")
        and (
            obj.parent == rig
            or any(
                modifier.type == "ARMATURE" and modifier.object == rig
                for modifier in obj.modifiers
            )
        )
    ]
    low, high = evaluated_bounds(meshes)
    return (low + high) * 0.5


def should_use_collision(obj: bpy.types.Object) -> bool:
    if obj.type != "MESH":
        return False
    if obj.name in SURFACE_COLLIDERS:
        return False
    if obj.name.startswith(
        (
            "COL_ARCH_FLOOR_",
            "COL_ARCH_SITE_BASE",
            "COL_ROVER_",
        )
    ):
        return False
    return obj.name.startswith("COL_")


def obstacle_rectangles() -> list[tuple[str, float, float, float, float]]:
    rectangles: list[tuple[str, float, float, float, float]] = []
    for obj in bpy.data.objects:
        use = should_use_collision(obj) or (
            obj.type == "MESH"
            and (
                "_DEBRIS_" in obj.name
                and obj.name.startswith("PULSO_RAGDOLL_")
            )
        )
        if not use:
            continue
        low, high = world_bounds(obj)
        if low.z > ROVER_BODY_TOP_M or high.z < -0.20:
            continue
        rectangles.append((obj.name, low.x, high.x, low.y, high.y))

    # A two-dimensional planner must not "teleport" over level changes.
    # These virtual barriers leave openings only at the validated ramps.
    rectangles.extend(
        (
            ("LEVEL_CHANGE_B_SOUTH", 6.975, 7.025, -3.3, B_RAMP[2]),
            ("LEVEL_CHANGE_B_NORTH", 6.975, 7.025, B_RAMP[3], 3.4),
            (
                "HEAVE_LIP_CORRIDOR_SOUTH",
                4.53,
                4.58,
                -0.9,
                CORRIDOR_RAMP[2],
            ),
            (
                "HEAVE_LIP_CORRIDOR_NORTH",
                4.53,
                4.58,
                CORRIDOR_RAMP[3],
                0.9,
            ),
        )
    )
    return rectangles


def inside_floor(x: float, y: float) -> bool:
    return any(x0 <= x <= x1 and y0 <= y <= y1 for x0, x1, y0, y1 in FLOORS)


def inflated_contains(
    rectangle: tuple[str, float, float, float, float],
    x: float,
    y: float,
) -> bool:
    _, x0, x1, y0, y1 = rectangle
    return (
        x0 - ROVER_RADIUS_M <= x <= x1 + ROVER_RADIUS_M
        and y0 - ROVER_RADIUS_M <= y <= y1 + ROVER_RADIUS_M
    )


def cell_xy(cell: tuple[int, int]) -> tuple[float, float]:
    return (
        WORLD[0] + cell[0] * RESOLUTION_M,
        WORLD[2] + cell[1] * RESOLUTION_M,
    )


def xy_cell(x: float, y: float) -> tuple[int, int]:
    return (
        round((x - WORLD[0]) / RESOLUTION_M),
        round((y - WORLD[2]) / RESOLUTION_M),
    )


def build_free_cells(
    rectangles: list[tuple[str, float, float, float, float]],
) -> set[tuple[int, int]]:
    width = round((WORLD[1] - WORLD[0]) / RESOLUTION_M)
    height = round((WORLD[3] - WORLD[2]) / RESOLUTION_M)
    free: set[tuple[int, int]] = set()
    for ix in range(width + 1):
        for iy in range(height + 1):
            x, y = cell_xy((ix, iy))
            if not inside_floor(x, y):
                continue
            if any(inflated_contains(rectangle, x, y) for rectangle in rectangles):
                continue
            free.add((ix, iy))
    return free


NEIGHBORS = (
    (-1, 0, 1.0),
    (1, 0, 1.0),
    (0, -1, 1.0),
    (0, 1, 1.0),
    (-1, -1, math.sqrt(2.0)),
    (-1, 1, math.sqrt(2.0)),
    (1, -1, math.sqrt(2.0)),
    (1, 1, math.sqrt(2.0)),
)


def astar(
    free: set[tuple[int, int]],
    start: tuple[int, int],
    goals: set[tuple[int, int]],
    cost_bias=None,
) -> list[tuple[int, int]]:
    if start not in free:
        raise RuntimeError("Rover spawn is not collision-free")
    if not goals:
        raise RuntimeError("No collision-free observation goals exist")

    goal_xy = [cell_xy(goal) for goal in goals]

    def heuristic(cell: tuple[int, int]) -> float:
        x, y = cell_xy(cell)
        return min(math.hypot(x - gx, y - gy) for gx, gy in goal_xy)

    queue: list[tuple[float, float, tuple[int, int]]] = [
        (heuristic(start), 0.0, start)
    ]
    cost = {start: 0.0}
    parent: dict[tuple[int, int], tuple[int, int]] = {}

    while queue:
        _, current_cost, current = heapq.heappop(queue)
        if current in goals:
            path = [current]
            while current in parent:
                current = parent[current]
                path.append(current)
            path.reverse()
            return path
        if current_cost > cost.get(current, math.inf):
            continue
        for dx, dy, step in NEIGHBORS:
            neighbor = (current[0] + dx, current[1] + dy)
            if neighbor not in free:
                continue
            if dx and dy:
                if (
                    (current[0] + dx, current[1]) not in free
                    or (current[0], current[1] + dy) not in free
                ):
                    continue
            candidate = (
                current_cost
                + step * RESOLUTION_M
                + (0.0 if cost_bias is None else cost_bias(neighbor))
            )
            if candidate >= cost.get(neighbor, math.inf):
                continue
            cost[neighbor] = candidate
            parent[neighbor] = current
            heapq.heappush(
                queue,
                (candidate + heuristic(neighbor), candidate, neighbor),
            )
    raise RuntimeError("No route exists to the requested observation zone")


def simplify(path: list[tuple[int, int]]) -> list[tuple[float, float]]:
    if len(path) <= 2:
        return [cell_xy(cell) for cell in path]
    result = [path[0]]
    previous_direction = (
        path[1][0] - path[0][0],
        path[1][1] - path[0][1],
    )
    for index in range(1, len(path) - 1):
        direction = (
            path[index + 1][0] - path[index][0],
            path[index + 1][1] - path[index][1],
        )
        if direction != previous_direction:
            result.append(path[index])
        previous_direction = direction
    result.append(path[-1])
    return [
        (round(x, 3), round(y, 3))
        for x, y in (cell_xy(cell) for cell in result)
    ]


def observation_goals(
    free: set[tuple[int, int]],
    victim: Vector,
    *,
    east_room_only: bool,
) -> set[tuple[int, int]]:
    goals = set()
    for cell in free:
        x, y = cell_xy(cell)
        distance = math.hypot(x - victim.x, y - victim.y)
        if (
            0.8 <= distance <= 2.2
            and (
                not east_room_only
                or x >= B_RAMP[1] + RESOLUTION_M
            )
        ):
            goals.add(cell)
    return goals


def path_length(path: list[tuple[int, int]]) -> float:
    return sum(
        math.hypot(
            cell_xy(current)[0] - cell_xy(previous)[0],
            cell_xy(current)[1] - cell_xy(previous)[1],
        )
        for previous, current in zip(path, path[1:])
    )


def b_route_bias(cell: tuple[int, int]) -> float:
    x, y = cell_xy(cell)
    if 6.80 <= x <= B_RAMP[1] + RESOLUTION_M:
        ramp_center_y = (B_RAMP[2] + B_RAMP[3]) * 0.5
        return abs(y - ramp_center_y) * 0.40
    return 0.0


rectangles = obstacle_rectangles()
free_cells = build_free_cells(rectangles)
rover = bpy.data.objects.get("ROVER_OPENBOT_ROOT")
if rover is None:
    raise RuntimeError("ROVER_OPENBOT_ROOT is missing")
start_xy = (rover.matrix_world.translation.x, rover.matrix_world.translation.y)
start_cell = xy_cell(*start_xy)

victims = {code: victim_center(code) for code in ("A", "B")}
paths = {
    "A": astar(
        free_cells,
        start_cell,
        observation_goals(free_cells, victims["A"], east_room_only=False),
    ),
    "B": astar(
        free_cells,
        start_cell,
        observation_goals(free_cells, victims["B"], east_room_only=True),
        cost_bias=b_route_bias,
    ),
}

b_crossings = [
    cell_xy(cell)
    for cell in paths["B"]
    if 6.95 <= cell_xy(cell)[0] <= 7.10
]
if not b_crossings or not all(
    B_RAMP[2] + ROVER_RADIUS_M
    <= y
    <= B_RAMP[3] - ROVER_RADIUS_M
    for _, y in b_crossings
):
    raise RuntimeError("B route did not cross the level change inside the ramp")
if max(cell_xy(cell)[0] for cell in paths["B"]) < B_RAMP[1] + RESOLUTION_M:
    raise RuntimeError("B route entered the ramp but did not reach the lower floor")

report = {
    "status": "passed",
    "blend": bpy.data.filepath,
    "grid_resolution_m": RESOLUTION_M,
    "rover_swept_radius_m": ROVER_RADIUS_M,
    "rover_swept_diameter_m": ROVER_RADIUS_M * 2.0,
    "spawn_xy_m": [round(value, 3) for value in start_xy],
    "spawn_collision_free": start_cell in free_cells,
    "obstacle_rectangles": len(rectangles),
    "free_grid_cells": len(free_cells),
    "ramp_B": {
        "width_m": B_RAMP[3] - B_RAMP[2],
        "run_m": B_RAMP[1] - B_RAMP[0],
        "drop_m": 0.15,
        "grade_percent": 0.15 / (B_RAMP[1] - B_RAMP[0]) * 100.0,
        "angle_degrees": math.degrees(
            math.atan2(0.15, B_RAMP[1] - B_RAMP[0])
        ),
        "vertical_lip_m": 0.0,
    },
    "victims": {},
}
for code, path in paths.items():
    endpoint = cell_xy(path[-1])
    report["victims"][code] = {
        "reachable": True,
        "path_length_m": round(path_length(path), 3),
        "observation_standoff_m": round(
            math.hypot(
                endpoint[0] - victims[code].x,
                endpoint[1] - victims[code].y,
            ),
            3,
        ),
        "endpoint_xy_m": [round(value, 3) for value in endpoint],
        "waypoints_xy_m": simplify(path),
    }

destination = output_path()
destination.parent.mkdir(parents=True, exist_ok=True)
destination.write_text(json.dumps(report, indent=2) + "\n")
print("PULSO_NAVIGATION_AUDIT_OK", json.dumps(report, separators=(",", ":")))
