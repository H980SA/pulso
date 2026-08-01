"""Smoke-test official CC0 MakeHuman clothes on two MPFB bodies."""

from pathlib import Path

import bpy
from mathutils import Vector
from bl_ext.user_default.mpfb.services import HumanService


PROJECT = Path(__file__).resolve().parents[1]
ASSETS = PROJECT / ".tools/vendor/makehuman_assets/cc0/clothes"
OUTPUT = PROJECT / "art/claude_workspace/renders/survivors/mpfb_clothes_smoke.png"
OUTPUT.parent.mkdir(parents=True, exist_ok=True)


def look_at(obj: bpy.types.Object, target: Vector) -> None:
    obj.rotation_euler = (target - obj.location).to_track_quat("-Z", "Y").to_euler()


def create_character(
    name: str,
    gender: str,
    x: float,
    clothes: list[Path],
    bodyparts: list[tuple[str, Path]],
) -> None:
    scene = bpy.context.scene
    scene.MPFB_NH_add_phenotype = True
    scene.MPFB_NH_phenotype_gender = gender
    scene.MPFB_NH_phenotype_age = "young"
    scene.MPFB_NH_phenotype_muscle = "averagemuscle"
    scene.MPFB_NH_phenotype_weight = "averageweight"
    scene.MPFB_NH_phenotype_height = "average"
    scene.MPFB_NH_phenotype_proportions = "average"
    scene.MPFB_NH_phenotype_race = "universal"
    scene.MPFB_NH_phenotype_influence = 0.7

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

    for mhclo in clothes:
        bpy.ops.object.select_all(action="DESELECT")
        body.select_set(True)
        bpy.context.view_layer.objects.active = body
        garment = HumanService.add_mhclo_asset(
            str(mhclo),
            body,
            asset_type="Clothes",
            subdiv_levels=1,
            material_type="GAMEENGINE",
            set_up_rigging=True,
            interpolate_weights=True,
            import_subrig=True,
            import_weights=True,
        )
        garment.name = f"{name}_{mhclo.parent.name.upper()}"

    for asset_type, mhclo in bodyparts:
        bpy.ops.object.select_all(action="DESELECT")
        body.select_set(True)
        bpy.context.view_layer.objects.active = body
        asset = HumanService.add_mhclo_asset(
            str(mhclo),
            body,
            asset_type=asset_type,
            subdiv_levels=1,
            material_type="GAMEENGINE",
            set_up_rigging=True,
            interpolate_weights=True,
            import_subrig=True,
            import_weights=True,
        )
        asset.name = f"{name}_{asset_type.upper()}"

    rig.location.x = x


bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)

create_character(
    "CLOTHES_F",
    "female",
    -0.9,
    [
        ASSETS / "joepal_crude_t-shirt_female/joepal_crude_t-shirt_female.mhclo",
        ASSETS / "cortu_cargo_pants/cortu_cargo_pants.mhclo",
        ASSETS / "toigo_ankle_boots_female/toigo_ankle_boots_female.mhclo",
    ],
    [
        ("Eyes", PROJECT / ".tools/vendor/makehuman_assets/cc0/eyes/high-poly/high-poly.mhclo"),
        ("Eyebrows", PROJECT / ".tools/vendor/makehuman_assets/cc0/eyebrows/eyebrow003/eyebrow003.mhclo"),
        ("Eyelashes", PROJECT / ".tools/vendor/makehuman_assets/cc0/eyelashes/eyelashes01/eyelashes01.mhclo"),
        ("Hair", PROJECT / ".tools/vendor/makehuman_assets/cc0/hair/short03/short03.mhclo"),
    ],
)
create_character(
    "CLOTHES_M",
    "male",
    0.9,
    [
        ASSETS / "namuhekam_male_polo_shirt/namuhekam_male_polo_shirt.mhclo",
        ASSETS / "toigo_wool_pants/toigo_wool_pants.mhclo",
        ASSETS / "toigo_ankle_boots_male/toigo_ankle_boots_male.mhclo",
    ],
    [
        ("Eyes", PROJECT / ".tools/vendor/makehuman_assets/cc0/eyes/high-poly/high-poly.mhclo"),
        ("Eyebrows", PROJECT / ".tools/vendor/makehuman_assets/cc0/eyebrows/eyebrow001/eyebrow001.mhclo"),
        ("Eyelashes", PROJECT / ".tools/vendor/makehuman_assets/cc0/eyelashes/eyelashes02/eyelashes02.mhclo"),
        ("Hair", PROJECT / ".tools/vendor/makehuman_assets/cc0/hair/short01/short01.mhclo"),
    ],
)

for body_name, color in (
    ("CLOTHES_F_BODY", (0.18, 0.055, 0.022, 1.0)),
    ("CLOTHES_M_BODY", (0.12, 0.035, 0.014, 1.0)),
):
    body = bpy.data.objects[body_name]
    material = bpy.data.materials.new(f"{body_name}_SKIN")
    material.diffuse_color = color
    material.use_nodes = True
    material.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = color
    material.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.5
    body.data.materials.clear()
    body.data.materials.append(material)

bpy.ops.mesh.primitive_plane_add(size=8.0, location=(0.0, 0.0, -0.005))
ground = bpy.context.object
ground_material = bpy.data.materials.new("CLOTHES_SMOKE_GROUND")
ground_material.diffuse_color = (0.025, 0.03, 0.035, 1.0)
ground.data.materials.append(ground_material)

bpy.ops.object.camera_add(location=(0.0, -5.0, 1.1))
camera = bpy.context.object
camera.data.lens = 62.0
look_at(camera, Vector((0.0, 0.0, 0.86)))
bpy.context.scene.camera = camera

bpy.ops.object.light_add(type="AREA", location=(-2.5, -3.0, 4.0))
key = bpy.context.object
key.data.energy = 1150.0
key.data.size = 3.5
look_at(key, Vector((0.0, 0.0, 0.95)))

bpy.ops.object.light_add(type="AREA", location=(2.4, 1.2, 2.4))
rim = bpy.context.object
rim.data.energy = 650.0
rim.data.color = (0.3, 0.48, 1.0)
rim.data.size = 2.2
look_at(rim, Vector((0.0, 0.0, 1.0)))

scene = bpy.context.scene
scene.render.engine = "BLENDER_EEVEE"
scene.render.resolution_x = 1000
scene.render.resolution_y = 800
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.filepath = str(OUTPUT)
scene.view_settings.look = "AgX - Medium High Contrast"
scene.world.color = (0.006, 0.008, 0.012)
bpy.ops.render.render(write_still=True)
print("MPFB_CLOTHES_SMOKE_OK", OUTPUT)
