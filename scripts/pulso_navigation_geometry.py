"""Blender geometry helpers owned by the Pulso navigation pass."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterable

import bpy
from mathutils import Vector


def world_bounds(obj: bpy.types.Object) -> tuple[Vector, Vector]:
    points = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    low = Vector(tuple(min(point[axis] for point in points) for axis in range(3)))
    high = Vector(tuple(max(point[axis] for point in points) for axis in range(3)))
    return low, high


def signature(obj: bpy.types.Object) -> str:
    digest = hashlib.sha256()
    digest.update(obj.name.encode())
    for row in obj.matrix_world:
        digest.update(",".join(f"{value:.9f}" for value in row).encode())
    if obj.type == "MESH":
        for vertex in obj.data.vertices:
            digest.update(
                f"{vertex.co.x:.9f},{vertex.co.y:.9f},{vertex.co.z:.9f}".encode()
            )
    elif obj.type == "CAMERA":
        digest.update(
            f"{obj.data.lens:.9f},{obj.data.sensor_width:.9f}".encode()
        )
    elif obj.type == "LIGHT":
        digest.update(
            f"{obj.data.energy:.9f},{obj.data.color[:]}".encode()
        )
    return digest.hexdigest()


def protected_objects() -> list[bpy.types.Object]:
    exact_names = {
        "PULSO_RAGDOLL_A_DEBRIS_PRIMARY_SLAB",
        "PULSO_RAGDOLL_A_DEBRIS_SECONDARY_SLAB",
        "PULSO_RAGDOLL_A_DEBRIS_BEAM",
        "PULSO_RAGDOLL_B_DEBRIS_PRIMARY_SLAB",
        "PULSO_RAGDOLL_B_DEBRIS_SECONDARY_SLAB",
        "PULSO_RAGDOLL_B_DEBRIS_BEAM",
    }
    return [
        obj
        for obj in bpy.data.objects
        if (
            obj.name.startswith("PULSO_SURVIVOR_")
            or obj.name.startswith("PULSO_RAGDOLL_CAM_")
            or obj.name.startswith("PULSO_RAGDOLL_LIGHT_")
            or obj.name in exact_names
            or "BLOOD_STAIN" in obj.name
            or "BLOOD_TRAIL" in obj.name
        )
    ]


def require_object(name: str) -> bpy.types.Object:
    obj = bpy.data.objects.get(name)
    if obj is None:
        raise RuntimeError(f"Required scene object is missing: {name}")
    return obj


def translate(names: Iterable[str], offset: tuple[float, float, float]) -> None:
    movement = Vector(offset)
    for name in names:
        require_object(name).location += movement


def place_center(
    name: str,
    target_xy: tuple[float, float],
    target_low_z: float,
) -> None:
    obj = require_object(name)
    low, high = world_bounds(obj)
    center = (low + high) * 0.5
    obj.location += Vector(
        (
            target_xy[0] - center.x,
            target_xy[1] - center.y,
            target_low_z - low.z,
        )
    )


def ensure_collection(name: str, purpose: str) -> bpy.types.Collection:
    collection = bpy.data.collections.get(name)
    if collection is None:
        collection = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(collection)
    collection["purpose"] = purpose
    return collection


def remove_existing_navigation_pass() -> None:
    for obj in list(bpy.data.objects):
        if obj.name.startswith(("VIS_NAV_", "COL_NAV_", "PULSO_NAV_CAM_")):
            bpy.data.objects.remove(obj, do_unlink=True)
    for name in ("VISUAL_NAVIGATION", "COLLISION_NAVIGATION"):
        collection = bpy.data.collections.get(name)
        if collection is not None and not collection.objects:
            bpy.data.collections.remove(collection)


def wedge_vertices(spec: dict[str, float]) -> list[tuple[float, float, float]]:
    return [
        (spec["x0"], spec["y0"], spec["bottom"]),
        (spec["x0"], spec["y1"], spec["bottom"]),
        (spec["x1"], spec["y0"], spec["bottom"]),
        (spec["x1"], spec["y1"], spec["bottom"]),
        (spec["x0"], spec["y0"], spec["z0"]),
        (spec["x0"], spec["y1"], spec["z0"]),
        (spec["x1"], spec["y0"], spec["z1"]),
        (spec["x1"], spec["y1"], spec["z1"]),
    ]


def create_wedge(
    collection: bpy.types.Collection,
    name: str,
    spec: dict[str, float],
    material: bpy.types.Material,
    *,
    collision: bool,
) -> bpy.types.Object:
    mesh = bpy.data.meshes.new(f"{name}_MESH")
    mesh.from_pydata(
        wedge_vertices(spec),
        [],
        [
            (0, 2, 3, 1),
            (0, 4, 6, 2),
            (1, 3, 7, 5),
            (0, 1, 5, 4),
            (2, 6, 7, 3),
            (4, 5, 7, 6),
        ],
    )
    mesh.materials.append(material)
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    obj["navigation_surface"] = True
    obj["minimum_width_m"] = spec["y1"] - spec["y0"]
    obj["run_m"] = spec["x1"] - spec["x0"]
    obj["rise_m"] = spec["z1"] - spec["z0"]
    obj["grade_percent"] = (
        abs(spec["z1"] - spec["z0"])
        / (spec["x1"] - spec["x0"])
        * 100.0
    )
    obj["maximum_vertical_lip_m"] = 0.0
    if collision:
        obj.hide_render = True
        obj.display_type = "WIRE"
    else:
        bevel = obj.modifiers.new("NAV_RAMP_EDGE_SOFTEN", "BEVEL")
        bevel.width = 0.006
        bevel.segments = 2
        bevel.affect = "EDGES"
    return obj


def look_at(obj: bpy.types.Object, target: Vector) -> None:
    obj.rotation_euler = (target - obj.location).to_track_quat("-Z", "Y").to_euler()


def render(
    camera: bpy.types.Object,
    path: Path,
    exposure: float,
) -> None:
    scene = bpy.context.scene
    scene.camera = camera
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = exposure
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
