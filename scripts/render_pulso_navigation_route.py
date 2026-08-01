"""Render an open-roof QA view with the verified A/B rover routes overlaid."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import bpy
from mathutils import Vector


PROJECT = Path(__file__).resolve().parents[1]
SCRIPT_ROOT = PROJECT / "scripts"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from pulso_navigation_geometry import look_at, render, require_object  # noqa: E402


REPORT = PROJECT / "art/current/ragdoll/navigable/navigation_report.json"
OUTPUT = (
    PROJECT
    / "art/current/ragdoll/navigable/renders/pulso_navigable_routes.png"
)
OVERLAY_Z = 3.25


def route_material(name: str, color: tuple[float, float, float, float]):
    material = bpy.data.materials.new(name)
    material.diffuse_color = color
    material.use_nodes = True
    shader = material.node_tree.nodes.get("Principled BSDF")
    if shader is not None:
        shader.inputs["Base Color"].default_value = color
        shader.inputs["Roughness"].default_value = 0.32
        emission = shader.inputs.get("Emission Color")
        if emission is not None:
            emission.default_value = color
        strength = shader.inputs.get("Emission Strength")
        if strength is not None:
            strength.default_value = 2.5
    return material


def add_route(
    name: str,
    points: list[list[float]],
    material: bpy.types.Material,
) -> None:
    curve = bpy.data.curves.new(f"{name}_DATA", "CURVE")
    curve.dimensions = "3D"
    curve.bevel_depth = 0.045
    curve.bevel_resolution = 4
    spline = curve.splines.new("POLY")
    spline.points.add(len(points) - 1)
    for point, coordinates in zip(spline.points, points):
        point.co = (coordinates[0], coordinates[1], OVERLAY_Z, 1.0)
    obj = bpy.data.objects.new(name, curve)
    bpy.context.scene.collection.objects.link(obj)
    curve.materials.append(material)

    for suffix, coordinates in (("START", points[0]), ("GOAL", points[-1])):
        bpy.ops.mesh.primitive_uv_sphere_add(
            segments=24,
            ring_count=12,
            radius=0.11 if suffix == "START" else 0.15,
            location=(coordinates[0], coordinates[1], OVERLAY_Z),
        )
        marker = bpy.context.object
        marker.name = f"{name}_{suffix}"
        marker.data.materials.append(material)


report = json.loads(REPORT.read_text())
material_a = route_material("MAT_NAV_ROUTE_A", (0.06, 0.85, 0.38, 1.0))
material_b = route_material("MAT_NAV_ROUTE_B", (1.0, 0.38, 0.04, 1.0))
add_route(
    "PULSO_NAV_ROUTE_A",
    report["victims"]["A"]["waypoints_xy_m"],
    material_a,
)
add_route(
    "PULSO_NAV_ROUTE_B",
    report["victims"]["B"]["waypoints_xy_m"],
    material_b,
)

hidden_states = {
    obj.name: obj.hide_render
    for obj in bpy.data.objects
    if (
        any(token in obj.name for token in ("CEIL_", "CEILING", "ROOF"))
        or obj.name.startswith("VIS_FX_")
    )
}
for name in hidden_states:
    require_object(name).hide_render = True

camera_data = bpy.data.cameras.new("PULSO_NAV_ROUTE_CAM_DATA")
camera = bpy.data.objects.new("PULSO_NAV_ROUTE_CAM", camera_data)
bpy.context.scene.collection.objects.link(camera)
camera.location = (2.0, 0.0, 17.5)
camera_data.type = "ORTHO"
camera_data.ortho_scale = 18.4
look_at(camera, Vector((2.0, 0.0, 0.0)))

light_data = bpy.data.lights.new("PULSO_NAV_ROUTE_LIGHT_DATA", "AREA")
light = bpy.data.objects.new("PULSO_NAV_ROUTE_LIGHT", light_data)
bpy.context.scene.collection.objects.link(light)
light.location = (2.0, 0.0, 9.0)
light_data.energy = 3100.0
light_data.shape = "RECTANGLE"
light_data.size = 12.0
light_data.size_y = 7.0
look_at(light, Vector((2.0, 0.0, 0.0)))

scene = bpy.context.scene
scene.render.engine = "BLENDER_EEVEE"
scene.render.resolution_x = 1280
scene.render.resolution_y = 720
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
render(camera, OUTPUT, exposure=-0.15)
print("PULSO_NAVIGATION_ROUTE_RENDER_OK", OUTPUT)
