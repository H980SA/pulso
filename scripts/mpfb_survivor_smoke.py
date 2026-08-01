"""Disposable MPFB2 smoke test for the Pulso survivor pass."""

from pathlib import Path

import bpy
from mathutils import Vector


PROJECT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT / "art/claude_workspace/renders/survivors"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def look_at(obj: bpy.types.Object, target: Vector) -> None:
    direction = target - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)

bpy.ops.mpfb.create_human()
human = bpy.context.object
human.name = "SURVIVOR_SMOKE_BODY"

bpy.ops.mpfb.add_standard_rig()
rig = next(obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE")
rig.name = "SURVIVOR_SMOKE_RIG"

bpy.ops.object.select_all(action="DESELECT")
human.select_set(True)
bpy.context.view_layer.objects.active = human
bpy.ops.mpfb.create_v2_skin()

bpy.ops.mesh.primitive_plane_add(size=8.0, location=(0.0, 0.0, -0.005))
ground = bpy.context.object
ground.name = "SMOKE_GROUND"
ground_material = bpy.data.materials.new("SMOKE_GROUND_MAT")
ground_material.diffuse_color = (0.04, 0.045, 0.05, 1.0)
ground.data.materials.append(ground_material)

bpy.ops.object.camera_add(location=(0.0, -3.4, 1.05))
camera = bpy.context.object
camera.name = "SMOKE_CAMERA"
camera.data.lens = 55.0
look_at(camera, Vector((0.0, 0.0, 0.86)))
bpy.context.scene.camera = camera

bpy.ops.object.light_add(type="AREA", location=(-1.3, -1.8, 2.7))
key = bpy.context.object
key.name = "SMOKE_KEY"
key.data.energy = 900.0
key.data.shape = "DISK"
key.data.size = 2.0
look_at(key, Vector((0.0, 0.0, 0.9)))

bpy.ops.object.light_add(type="AREA", location=(1.8, 0.8, 1.7))
rim = bpy.context.object
rim.name = "SMOKE_RIM"
rim.data.energy = 650.0
rim.data.color = (0.35, 0.55, 1.0)
rim.data.size = 1.5
look_at(rim, Vector((0.0, 0.0, 1.0)))

scene = bpy.context.scene
scene.render.engine = "BLENDER_EEVEE"
scene.render.resolution_x = 640
scene.render.resolution_y = 640
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.filepath = str(OUTPUT_DIR / "mpfb_smoke_front.png")
scene.render.film_transparent = False
scene.world.color = (0.008, 0.01, 0.015)

bpy.ops.wm.save_as_mainfile(
    filepath=str(PROJECT / "art/claude_workspace/mpfb_survivor_smoke.blend")
)
bpy.ops.render.render(write_still=True)

print(
    "MPFB_SMOKE_OK",
    {
        "human_dimensions_m": tuple(round(value, 4) for value in human.dimensions),
        "materials": [material.name for material in human.data.materials],
        "rig_bones": len(rig.data.bones),
        "render": scene.render.filepath,
    },
)
