"""Regenerate only the open-roof overview on an already built survivor scene."""

from pathlib import Path

import bpy
from mathutils import Vector


PROJECT = Path(__file__).resolve().parents[1]
OUTPUT = PROJECT / "art/current/renders/pulso_survivors_overview.png"
PREFIX = "PULSO_SURVIVOR_"


def look_at(obj: bpy.types.Object, target: Vector) -> None:
    obj.rotation_euler = (target - obj.location).to_track_quat("-Z", "Y").to_euler()


collection = bpy.data.collections["VISUAL_SURVIVORS"]
camera = bpy.data.objects[f"{PREFIX}CAM_TOP_OVERVIEW"]
light = bpy.data.objects.get(f"{PREFIX}LIGHT_TOP_OVERVIEW")
if light is None:
    data = bpy.data.lights.new(f"{PREFIX}LIGHT_TOP_OVERVIEW_DATA", "AREA")
    light = bpy.data.objects.new(f"{PREFIX}LIGHT_TOP_OVERVIEW", data)
    collection.objects.link(light)
    light.location = (1.9, 0.0, 15.0)
    data.energy = 3600.0
    data.shape = "DISK"
    data.size = 11.0
    data.color = (0.82, 0.90, 1.0)
    look_at(light, Vector((1.9, 0.0, 0.0)))

architecture = bpy.data.collections["VISUAL_ARCH"]
ceilings = [obj for obj in architecture.objects if "CEIL_" in obj.name]
states = {obj.name: obj.hide_render for obj in ceilings}
for obj in ceilings:
    obj.hide_render = True

light.hide_render = False
scene = bpy.context.scene
scene.camera = camera
scene.view_settings.look = "AgX - Medium High Contrast"
scene.view_settings.exposure = -0.2
scene.render.filepath = str(OUTPUT)
bpy.ops.render.render(write_still=True)

for obj in ceilings:
    obj.hide_render = states[obj.name]
light.hide_render = True
bpy.ops.wm.save_as_mainfile(filepath=bpy.data.filepath)
print("PULSO_OPEN_ROOF_OVERVIEW_OK", OUTPUT)
