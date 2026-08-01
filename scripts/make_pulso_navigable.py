"""Build a reversible, rover-navigable variant of the accepted Pulso scene.

Run with Blender:

    blender -b art/current/ragdoll/canonical/pulso_ragdoll_canonical.blend \
      --python scripts/make_pulso_navigable.py

The canonical checkpoint is never modified.  The pass relocates only loose,
non-entrapment rubble, adds exact collision ramps, fixes survivor B's localized
polo/pants intersection, and writes review renders plus a new static blend.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector


PROJECT = Path(__file__).resolve().parents[1]
SCRIPT_ROOT = PROJECT / "scripts"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from pulso_navigation_geometry import (  # noqa: E402
    create_wedge,
    ensure_collection,
    look_at,
    place_center,
    protected_objects,
    remove_existing_navigation_pass,
    render,
    require_object,
    signature,
    translate,
)
from pulso_survivor_clothing import (  # noqa: E402
    CLEARANCE_OFFSET_M,
    correct_survivor_b_clothing,
    pose_matrices,
)


OUTPUT_ROOT = PROJECT / "art/current/ragdoll/navigable"
RENDER_ROOT = OUTPUT_ROOT / "renders"
OUTPUT_BLEND = OUTPUT_ROOT / "pulso_ragdoll_navigable.blend"

ROVER_SWEPT_DIAMETER_M = 0.43
MIN_ROUTE_WIDTH_M = 0.58
CORRIDOR_RAMP = {
    "x0": 3.88,
    "x1": 4.565,
    "y0": -0.72,
    "y1": 0.02,
    "z0": 0.0,
    "z1": 0.059,
    "bottom": -0.07,
}
B_RAMP = {
    "x0": 7.0,
    "x1": 8.30,
    "y0": -3.00,
    "y1": -2.42,
    "z0": 0.0,
    "z1": -0.15,
    "bottom": -0.27,
}


def render_review_views() -> None:
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.color_depth = "8"

    camera_a = require_object("PULSO_RAGDOLL_CAM_A")
    camera_b = require_object("PULSO_RAGDOLL_CAM_B")
    light_a = require_object("PULSO_RAGDOLL_LIGHT_A")
    light_b = require_object("PULSO_RAGDOLL_LIGHT_B")
    light_a.hide_render = False
    light_b.hide_render = True
    render(camera_a, RENDER_ROOT / "pulso_navigable_A.png", exposure=-0.45)
    light_a.hide_render = True
    light_b.hide_render = False
    render(camera_b, RENDER_ROOT / "pulso_navigable_B.png", exposure=-1.25)
    light_a.hide_render = True
    light_b.hide_render = True

    ceiling_states = {
        obj.name: obj.hide_render
        for obj in bpy.data.objects
        if any(token in obj.name for token in ("CEIL_", "CEILING", "ROOF"))
    }
    fx_states = {
        obj.name: obj.hide_render
        for obj in bpy.data.objects
        if obj.name.startswith("VIS_FX_")
    }
    for name in (*ceiling_states, *fx_states):
        require_object(name).hide_render = True

    camera_data = bpy.data.cameras.new("PULSO_NAV_CAM_TOP_DATA")
    camera = bpy.data.objects.new("PULSO_NAV_CAM_TOP", camera_data)
    scene.collection.objects.link(camera)
    camera.location = (2.0, 0.0, 17.5)
    camera_data.type = "ORTHO"
    camera_data.ortho_scale = 18.4
    look_at(camera, Vector((2.0, 0.0, 0.0)))

    light_data = bpy.data.lights.new("PULSO_NAV_TOP_LIGHT_DATA", "AREA")
    light = bpy.data.objects.new("PULSO_NAV_TOP_LIGHT", light_data)
    scene.collection.objects.link(light)
    light.location = (2.0, 0.0, 9.0)
    light_data.energy = 3100.0
    light_data.shape = "RECTANGLE"
    light_data.size = 12.0
    light_data.size_y = 7.0
    look_at(light, Vector((2.0, 0.0, 0.0)))
    render(camera, RENDER_ROOT / "pulso_navigable_top.png", exposure=-0.15)

    bpy.data.objects.remove(camera, do_unlink=True)
    bpy.data.cameras.remove(camera_data)
    bpy.data.objects.remove(light, do_unlink=True)
    bpy.data.lights.remove(light_data)
    for name, hidden in {**ceiling_states, **fx_states}.items():
        require_object(name).hide_render = hidden


def relocate_loose_debris() -> None:
    # North-bank the pieces blocking the spawn/corridor without deleting them.
    translate(
        ("VIS_DYN_DEB_BRICK_02", "COL_DYN_DEB_BRICK_02"),
        (0.0, 1.15, 0.0),
    )
    translate(
        ("VIS_DEB_FLOORFRAG_RAMP", "COL_DEB_FLOORFRAG_RAMP"),
        (0.0, 0.78, 0.0),
    )
    translate(
        ("VIS_DEB_PLASTERSHEET_COR_04", "COL_DEB_PLASTERSHEET_COR_04"),
        (0.0, 0.95, 0.0),
    )

    for name in ("VIS_DEB_PLASTERSHEET_B_03", "COL_DEB_PLASTERSHEET_B_03"):
        place_center(name, (5.85, 2.30), target_low_z=0.0)
    for name in ("VIS_DEB_PLASTERSHEET_B_01", "COL_DEB_PLASTERSHEET_B_01"):
        place_center(name, (8.45, 2.55), target_low_z=-0.15)
    place_center(
        "PULSO_RAGDOLL_B_DEBRIS_CHUNK_03",
        (7.70, 2.55),
        target_low_z=-0.15,
    )
    place_center(
        "PULSO_RAGDOLL_B_DEBRIS_CHUNK_09",
        (9.05, 2.60),
        target_low_z=-0.15,
    )


def add_navigation_ramps() -> None:
    visual_collection = ensure_collection(
        "VISUAL_NAVIGATION",
        "Accidental rubble surfaces retained for rover navigation",
    )
    collision_collection = ensure_collection(
        "COLLISION_NAVIGATION",
        "Exact collision wedges for the Pulso navigation pass",
    )
    visual_material = require_object(
        "VIS_DEB_STEP_BRIDGE_B"
    ).data.materials[0]
    collision_material = require_object(
        "COL_DEB_STEP_BRIDGE_B"
    ).data.materials[0]
    for collection, prefix, material, collision in (
        (visual_collection, "VIS", visual_material, False),
        (collision_collection, "COL", collision_material, True),
    ):
        create_wedge(
            collection,
            f"{prefix}_NAV_RAMP_CORRIDOR",
            CORRIDOR_RAMP,
            material,
            collision=collision,
        )
        create_wedge(
            collection,
            f"{prefix}_NAV_RAMP_B_SOUTH",
            B_RAMP,
            material,
            collision=collision,
        )


OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
RENDER_ROOT.mkdir(parents=True, exist_ok=True)
remove_existing_navigation_pass()

protected_before = {
    obj.name: signature(obj)
    for obj in protected_objects()
}
rig_b = require_object("PULSO_SURVIVOR_B_RIG")
pose_before = pose_matrices(rig_b)

relocate_loose_debris()
clothing_report = correct_survivor_b_clothing()
add_navigation_ramps()

scene = bpy.context.scene
scene["pulso_navigation_pass"] = "B_south_corridor_v1"
scene["pulso_navigation_source"] = (
    "ragdoll/canonical/pulso_ragdoll_canonical.blend"
)
scene["pulso_rover_swept_diameter_m"] = ROVER_SWEPT_DIAMETER_M
scene["pulso_navigation_min_route_width_m"] = MIN_ROUTE_WIDTH_M
scene["pulso_navigation_ramp_B_grade_percent"] = (
    abs(B_RAMP["z1"] - B_RAMP["z0"])
    / (B_RAMP["x1"] - B_RAMP["x0"])
    * 100.0
)
scene["pulso_navigation_ramp_B_lip_m"] = 0.0
scene["pulso_navigation_critical_entrapment_unchanged"] = True
scene["pulso_survivor_B_clothing_correction"] = (
    "localized_polo_clearance_over_pants"
)
scene["pulso_survivor_B_clothing_offset_m"] = CLEARANCE_OFFSET_M

protected_after = {
    obj.name: signature(obj)
    for obj in protected_objects()
}
if protected_before != protected_after:
    changed = sorted(
        name
        for name in set(protected_before) | set(protected_after)
        if protected_before.get(name) != protected_after.get(name)
    )
    raise RuntimeError(f"Protected scene content changed: {changed}")

pose_after = pose_matrices(rig_b)
unexpected_pose_changes = sorted(
    name
    for name in pose_before
    if pose_before[name] != pose_after[name]
)
if unexpected_pose_changes:
    raise RuntimeError(
        "Clothing correction changed protected pose bones: "
        f"{unexpected_pose_changes}"
    )

bpy.ops.file.pack_all()
bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT_BLEND))
render_review_views()
bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT_BLEND))
blend_backup = Path(f"{OUTPUT_BLEND}1")
if blend_backup.exists():
    blend_backup.unlink()

print(
    "PULSO_NAVIGATION_BUILD_OK",
    {
        "blend": str(OUTPUT_BLEND),
        "ramp_B_width_m": B_RAMP["y1"] - B_RAMP["y0"],
        "ramp_B_run_m": B_RAMP["x1"] - B_RAMP["x0"],
        "ramp_B_drop_m": abs(B_RAMP["z1"] - B_RAMP["z0"]),
        "ramp_B_grade_percent": round(
            abs(B_RAMP["z1"] - B_RAMP["z0"])
            / (B_RAMP["x1"] - B_RAMP["x0"])
            * 100.0,
            3,
        ),
        "ramp_B_angle_deg": round(
            math.degrees(
                math.atan2(
                    abs(B_RAMP["z1"] - B_RAMP["z0"]),
                    B_RAMP["x1"] - B_RAMP["x0"],
                )
            ),
            3,
        ),
        "survivor_B_clothing": clothing_report,
        "survivor_B_pose_bones_changed": unexpected_pose_changes,
        "protected_objects": len(protected_after),
    },
)
