"""Render three local-axis pose probes for the MPFB standard rig."""

from math import radians
from pathlib import Path

import bpy
from mathutils import Vector


PROJECT = Path(__file__).resolve().parents[1]
OUTPUT = PROJECT / "art/claude_workspace/renders/survivors/mpfb_pose_probe.png"
OUTPUT.parent.mkdir(parents=True, exist_ok=True)


def look_at(obj: bpy.types.Object, target: Vector) -> None:
    obj.rotation_euler = (target - obj.location).to_track_quat("-Z", "Y").to_euler()


def set_rotation(rig: bpy.types.Object, bone: str, xyz_deg: tuple[float, float, float]) -> None:
    pose_bone = rig.pose.bones[bone]
    pose_bone.rotation_mode = "XYZ"
    pose_bone.rotation_euler = tuple(radians(value) for value in xyz_deg)


def create_probe(name: str, x: float, axis: str) -> None:
    bpy.ops.mpfb.create_human()
    body = bpy.context.object
    body.name = f"{name}_BODY"
    bpy.ops.mpfb.add_standard_rig()
    rig = bpy.context.object
    rig.name = f"{name}_RIG"

    bpy.ops.object.select_all(action="DESELECT")
    body.select_set(True)
    bpy.context.view_layer.objects.active = body
    bpy.ops.mpfb.create_v2_skin()

    rig.location.x = x
    if axis == "X":
        set_rotation(rig, "upperarm01.L", (45, 0, 0))
        set_rotation(rig, "lowerarm01.L", (85, 0, 0))
        set_rotation(rig, "upperleg01.L", (35, 0, 0))
        set_rotation(rig, "lowerleg01.L", (-80, 0, 0))
    elif axis == "Y":
        set_rotation(rig, "upperarm01.L", (0, 45, 0))
        set_rotation(rig, "lowerarm01.L", (0, 85, 0))
        set_rotation(rig, "upperleg01.L", (0, 35, 0))
        set_rotation(rig, "lowerleg01.L", (0, -80, 0))
    else:
        set_rotation(rig, "upperarm01.L", (0, 0, 45))
        set_rotation(rig, "lowerarm01.L", (0, 0, 85))
        set_rotation(rig, "upperleg01.L", (0, 0, 35))
        set_rotation(rig, "lowerleg01.L", (0, 0, -80))


bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)

create_probe("PROBE_X", -2.0, "X")
create_probe("PROBE_Y", 0.0, "Y")
create_probe("PROBE_Z", 2.0, "Z")

bpy.ops.mesh.primitive_plane_add(size=10.0, location=(0.0, 0.0, -0.005))
ground = bpy.context.object
ground_material = bpy.data.materials.new("PROBE_GROUND_MAT")
ground_material.diffuse_color = (0.04, 0.045, 0.05, 1.0)
ground.data.materials.append(ground_material)

bpy.ops.object.camera_add(location=(0.0, -8.6, 1.4))
camera = bpy.context.object
camera.data.lens = 58.0
look_at(camera, Vector((0.0, 0.0, 0.82)))
bpy.context.scene.camera = camera

bpy.ops.object.light_add(type="AREA", location=(-2.5, -3.5, 4.0))
key = bpy.context.object
key.data.energy = 1800
key.data.size = 4.0
look_at(key, Vector((0.0, 0.0, 0.9)))

bpy.ops.object.light_add(type="AREA", location=(3.0, 1.0, 2.8))
rim = bpy.context.object
rim.data.energy = 900
rim.data.color = (0.35, 0.5, 1.0)
rim.data.size = 3.0
look_at(rim, Vector((0.0, 0.0, 1.0)))

scene = bpy.context.scene
scene.render.engine = "BLENDER_EEVEE"
scene.render.resolution_x = 1200
scene.render.resolution_y = 700
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.filepath = str(OUTPUT)
scene.world.color = (0.01, 0.012, 0.018)
bpy.ops.render.render(write_still=True)
print("POSE_PROBE_OK", OUTPUT)
