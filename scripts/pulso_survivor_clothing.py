"""Localized garment-intersection correction and proof for survivor B."""

from __future__ import annotations

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from pulso_navigation_geometry import require_object


CLEARANCE_CENTER = Vector((8.8013, -0.9610, 0.1332))
INNER_RADIUS_M = 0.07
OUTER_RADIUS_M = 0.24
CLEARANCE_OFFSET_M = 0.012
CLEARANCE_TEST_PIXEL = (760, 500)


def pose_matrices(
    rig: bpy.types.Object,
) -> dict[str, tuple[float, ...]]:
    return {
        bone.name: tuple(
            round(value, 9)
            for row in bone.matrix
            for value in row
        )
        for bone in rig.pose.bones
    }


def camera_ray(
    camera: bpy.types.Object,
    pixel: tuple[int, int],
    resolution: tuple[int, int],
) -> tuple[Vector, Vector]:
    frame = camera.data.view_frame(scene=bpy.context.scene)
    u = pixel[0] / resolution[0]
    v = 1.0 - pixel[1] / resolution[1]
    bottom = frame[2].lerp(frame[1], u)
    top = frame[3].lerp(frame[0], u)
    camera_point = bottom.lerp(top, v)
    origin = camera.matrix_world.translation.copy()
    direction = (
        camera.matrix_world.to_quaternion() @ camera_point
    ).normalized()
    return origin, direction


def ray_hit_distance(
    obj: bpy.types.Object,
    origin_world: Vector,
    direction_world: Vector,
) -> float | None:
    inverse = obj.matrix_world.inverted()
    origin_local = inverse @ origin_world
    direction_local = (inverse.to_3x3() @ direction_world).normalized()
    hit = BVHTree.FromObject(
        obj,
        bpy.context.evaluated_depsgraph_get(),
    ).ray_cast(origin_local, direction_local)
    return None if hit[0] is None else float(hit[3])


def correct_survivor_b_clothing() -> dict[str, float | int | None]:
    polo = require_object("PULSO_SURVIVOR_B_POLO")
    pants = require_object("PULSO_SURVIVOR_B_WOOL_PANTS")
    camera = require_object("PULSO_RAGDOLL_CAM_B")
    origin, direction = camera_ray(
        camera,
        CLEARANCE_TEST_PIXEL,
        (1280, 720),
    )
    before_polo = ray_hit_distance(polo, origin, direction)
    pants_distance = ray_hit_distance(pants, origin, direction)
    if pants_distance is None:
        raise RuntimeError("Clothing QA ray no longer intersects survivor B pants")

    old_modifier = polo.modifiers.get("PULSO_HIP_CLEARANCE")
    if old_modifier is not None:
        polo.modifiers.remove(old_modifier)
    old_group = polo.vertex_groups.get("PULSO_HIP_CLEARANCE")
    if old_group is not None:
        polo.vertex_groups.remove(old_group)

    subdivision = next(
        (modifier for modifier in polo.modifiers if modifier.type == "SUBSURF"),
        None,
    )
    previous_viewport = subdivision.show_viewport if subdivision else None
    previous_render = subdivision.show_render if subdivision else None
    if subdivision is not None:
        subdivision.show_viewport = False
        subdivision.show_render = False
    bpy.context.view_layer.update()

    evaluated = polo.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh = evaluated.to_mesh()
    group = polo.vertex_groups.new(name="PULSO_HIP_CLEARANCE")
    selected = 0
    try:
        for vertex in mesh.vertices:
            world = evaluated.matrix_world @ vertex.co
            distance = (world - CLEARANCE_CENTER).length
            if distance >= OUTER_RADIUS_M:
                continue
            ratio = max(
                0.0,
                min(
                    1.0,
                    (OUTER_RADIUS_M - distance)
                    / (OUTER_RADIUS_M - INNER_RADIUS_M),
                ),
            )
            weight = ratio * ratio * (3.0 - 2.0 * ratio)
            group.add([vertex.index], weight, "REPLACE")
            selected += 1
    finally:
        evaluated.to_mesh_clear()
        if subdivision is not None:
            subdivision.show_viewport = bool(previous_viewport)
            subdivision.show_render = bool(previous_render)
    if selected < 8:
        raise RuntimeError(
            f"Too few polo vertices selected for clearance: {selected}"
        )

    displacement = polo.modifiers.new("PULSO_HIP_CLEARANCE", "DISPLACE")
    displacement.direction = "NORMAL"
    displacement.mid_level = 0.0
    displacement.strength = CLEARANCE_OFFSET_M
    displacement.vertex_group = group.name
    bpy.context.view_layer.update()

    after_polo = ray_hit_distance(polo, origin, direction)
    if after_polo is None or after_polo >= pants_distance:
        raise RuntimeError(
            "Localized polo correction did not cover the pants intersection"
        )
    return {
        "selected_vertices": selected,
        "offset_m": CLEARANCE_OFFSET_M,
        "polo_ray_before_m": before_polo,
        "polo_ray_after_m": after_polo,
        "pants_ray_m": pants_distance,
    }
