"""Build the two-survivor pass for the Pulso disaster environment.

The script is intentionally deterministic and works only on the writable
derivative of the approved pre-survivor checkpoint.  It never edits any
COLLISION_* collection.
"""

from __future__ import annotations

import math
import random
from pathlib import Path
from typing import Callable

import bmesh
import bpy
from mathutils import Quaternion, Vector
from bl_ext.user_default.mpfb.services import HumanService


PROJECT = Path(__file__).resolve().parents[1]
WORKING_BLEND = PROJECT / "art/current/pulso_disaster_world_current.blend"
RENDER_DIR = PROJECT / "art/current/renders"
RENDER_DIR.mkdir(parents=True, exist_ok=True)
EXPORT_DIR = PROJECT / "art/current/exports/survivors"
EXPORT_DIR.mkdir(parents=True, exist_ok=True)
ASSET_ROOT = PROJECT / ".tools/vendor/makehuman_assets/cc0"

PREFIX = "PULSO_SURVIVOR_"
COLLECTION_NAME = "VISUAL_SURVIVORS"
RNG = random.Random(20260730)


def activate(obj: bpy.types.Object) -> None:
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def move_to_collection(obj: bpy.types.Object, collection: bpy.types.Collection) -> None:
    for current in list(obj.users_collection):
        current.objects.unlink(obj)
    collection.objects.link(obj)


def remove_previous_pass() -> None:
    for obj in list(bpy.data.objects):
        if obj.name.startswith(PREFIX):
            bpy.data.objects.remove(obj, do_unlink=True)

    previous = bpy.data.collections.get(COLLECTION_NAME)
    if previous is not None:
        bpy.data.collections.remove(previous)

    for datablocks in (
        bpy.data.meshes,
        bpy.data.armatures,
        bpy.data.cameras,
        bpy.data.lights,
        bpy.data.materials,
    ):
        for datablock in list(datablocks):
            if datablock.name.startswith(PREFIX):
                datablocks.remove(datablock)


def new_collection() -> bpy.types.Collection:
    collection = bpy.data.collections.new(COLLECTION_NAME)
    bpy.context.scene.collection.children.link(collection)
    collection["purpose"] = "Visual-only trapped-survivor benchmark layer"
    collection["collision_contract"] = "No objects in this collection are collision geometry"
    collection["checkpoint_source"] = "pre_fable_20260730_230714"
    return collection


def set_principled_input(node: bpy.types.ShaderNodeBsdfPrincipled, name: str, value) -> None:
    socket = node.inputs.get(name)
    if socket is not None:
        socket.default_value = value


def make_skin_material(name: str, dark: tuple[float, float, float], light: tuple[float, float, float]):
    material = bpy.data.materials.new(name)
    material.use_fake_user = True
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()

    output = nodes.new("ShaderNodeOutputMaterial")
    shader = nodes.new("ShaderNodeBsdfPrincipled")
    noise = nodes.new("ShaderNodeTexNoise")
    ramp = nodes.new("ShaderNodeValToRGB")
    bump_noise = nodes.new("ShaderNodeTexNoise")
    bump = nodes.new("ShaderNodeBump")

    noise.inputs["Scale"].default_value = 7.0
    noise.inputs["Detail"].default_value = 3.0
    noise.inputs["Roughness"].default_value = 0.58
    ramp.color_ramp.elements[0].color = (*dark, 1.0)
    ramp.color_ramp.elements[1].color = (*light, 1.0)
    ramp.color_ramp.elements[0].position = 0.27
    ramp.color_ramp.elements[1].position = 0.76

    bump_noise.inputs["Scale"].default_value = 115.0
    bump_noise.inputs["Detail"].default_value = 2.0
    bump.inputs["Strength"].default_value = 0.075
    bump.inputs["Distance"].default_value = 0.0012

    set_principled_input(shader, "Roughness", 0.5)
    set_principled_input(shader, "IOR", 1.42)
    set_principled_input(shader, "Subsurface Weight", 0.055)
    set_principled_input(shader, "Subsurface Scale", 0.035)

    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], shader.inputs["Base Color"])
    links.new(bump_noise.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], shader.inputs["Normal"])
    links.new(shader.outputs["BSDF"], output.inputs["Surface"])
    return material


def make_fabric_material(
    name: str,
    base: tuple[float, float, float],
    dust: tuple[float, float, float] = (0.29, 0.24, 0.19),
    roughness: float = 0.72,
):
    material = bpy.data.materials.new(name)
    material.use_fake_user = True
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()

    output = nodes.new("ShaderNodeOutputMaterial")
    shader = nodes.new("ShaderNodeBsdfPrincipled")
    noise = nodes.new("ShaderNodeTexNoise")
    ramp = nodes.new("ShaderNodeValToRGB")
    weave = nodes.new("ShaderNodeTexNoise")
    bump = nodes.new("ShaderNodeBump")

    noise.inputs["Scale"].default_value = 4.8
    noise.inputs["Detail"].default_value = 4.0
    noise.inputs["Roughness"].default_value = 0.7
    ramp.color_ramp.elements[0].color = (*base, 1.0)
    ramp.color_ramp.elements[1].color = (*dust, 1.0)
    ramp.color_ramp.elements[0].position = 0.32
    ramp.color_ramp.elements[1].position = 0.72

    weave.inputs["Scale"].default_value = 185.0
    weave.inputs["Detail"].default_value = 1.5
    bump.inputs["Strength"].default_value = 0.12
    bump.inputs["Distance"].default_value = 0.001

    set_principled_input(shader, "Roughness", roughness)
    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], shader.inputs["Base Color"])
    links.new(weave.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], shader.inputs["Normal"])
    links.new(shader.outputs["BSDF"], output.inputs["Surface"])
    return material


def make_simple_material(name: str, color: tuple[float, float, float], roughness: float = 0.65):
    material = bpy.data.materials.new(name)
    material.use_fake_user = True
    material.use_nodes = True
    shader = material.node_tree.nodes.get("Principled BSDF")
    set_principled_input(shader, "Base Color", (*color, 1.0))
    set_principled_input(shader, "Roughness", roughness)
    return material


def set_body_material(body: bpy.types.Object, material: bpy.types.Material) -> None:
    body.data.materials.clear()
    body.data.materials.append(material)


def tint_materials(obj: bpy.types.Object, tint: tuple[float, float, float]) -> None:
    """Multiply an imported PBR texture by a deterministic garment tint."""
    for material in obj.data.materials:
        if material is None:
            continue
        material.use_fake_user = True
        material.diffuse_color = (*tint, 1.0)
        if not material.use_nodes:
            continue
        nodes = material.node_tree.nodes
        links = material.node_tree.links
        shader = next((node for node in nodes if node.type == "BSDF_PRINCIPLED"), None)
        if shader is None:
            continue
        base = shader.inputs.get("Base Color")
        if base is None:
            continue
        if base.is_linked:
            source = base.links[0].from_socket
            links.remove(base.links[0])
            multiply = nodes.new("ShaderNodeMixRGB")
            multiply.name = f"{PREFIX}GARMENT_TINT"
            multiply.blend_type = "MULTIPLY"
            multiply.inputs[0].default_value = 1.0
            multiply.inputs[2].default_value = (*tint, 1.0)
            links.new(source, multiply.inputs[1])
            links.new(multiply.outputs[0], base)
        else:
            base.default_value = (*tint, 1.0)


def add_official_asset(
    body: bpy.types.Object,
    code: str,
    collection: bpy.types.Collection,
    asset_type: str,
    relative_path: str,
    label: str,
    tint: tuple[float, float, float] | None = None,
    mask_body: bool = False,
) -> bpy.types.Object:
    """Attach a CC0 MakeHuman mesh to the character and its standard rig."""
    mhclo = ASSET_ROOT / relative_path
    if not mhclo.exists():
        raise FileNotFoundError(mhclo)

    activate(body)
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
    asset.name = f"{PREFIX}{code}_{label}"
    asset.data.name = f"{PREFIX}{code}_{label}_MESH"
    move_to_collection(asset, collection)
    asset["asset_source"] = str(mhclo.relative_to(PROJECT))
    asset["license"] = "CC0-1.0"
    asset["actor_id"] = code
    asset["simulation_role"] = "visual_mesh"

    if tint is not None:
        tint_materials(asset, tint)

    if mask_body and asset_type.lower() == "clothes":
        group_name = f"Delete.{mhclo.stem}"
        if body.vertex_groups.get(group_name) is not None:
            modifier = body.modifiers.new(f"Hide body under {label}", "MASK")
            modifier.vertex_group = group_name
            modifier.invert_vertex_group = True

    return asset


def create_surface_garment(
    body: bpy.types.Object,
    name: str,
    collection: bpy.types.Collection,
    keep: Callable[[Vector], bool],
    material: bpy.types.Material,
    offset: float,
    thickness: float,
) -> bpy.types.Object:
    garment = body.copy()
    garment.data = body.data.copy()
    garment.name = name
    garment.data.name = f"{name}_MESH"
    collection.objects.link(garment)

    activate(garment)
    if garment.data.shape_keys is not None:
        bpy.ops.object.shape_key_remove(all=True, apply_mix=True)

    mesh = garment.data
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.verts.ensure_lookup_table()
    to_delete = [vertex for vertex in bm.verts if not keep(vertex.co)]
    bmesh.ops.delete(bm, geom=to_delete, context="VERTS")
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()

    for vertex in mesh.vertices:
        vertex.co += vertex.normal * offset
    mesh.materials.clear()
    mesh.materials.append(material)

    solidify = garment.modifiers.new("Fabric thickness", "SOLIDIFY")
    solidify.thickness = thickness
    solidify.offset = 0.15
    bevel = garment.modifiers.new("Soft garment edges", "BEVEL")
    bevel.width = 0.0025
    bevel.segments = 2

    garment["visual_role"] = "clothing"
    return garment


def configure_phenotype(
    gender: str,
    influence: float,
    weight: str = "averageweight",
    muscle: str = "averagemuscle",
) -> None:
    scene = bpy.context.scene
    scene.MPFB_NH_add_phenotype = True
    scene.MPFB_NH_phenotype_gender = gender
    scene.MPFB_NH_phenotype_age = "young"
    scene.MPFB_NH_phenotype_muscle = muscle
    scene.MPFB_NH_phenotype_weight = weight
    scene.MPFB_NH_phenotype_height = "average"
    scene.MPFB_NH_phenotype_proportions = "average"
    scene.MPFB_NH_phenotype_race = "universal"
    scene.MPFB_NH_phenotype_influence = influence


def create_human(
    code: str,
    collection: bpy.types.Collection,
    gender: str,
    influence: float,
    skin_material: bpy.types.Material,
) -> tuple[bpy.types.Object, bpy.types.Object]:
    configure_phenotype(gender, influence)
    bpy.ops.mpfb.create_human()
    body = bpy.context.object
    body.name = f"{PREFIX}{code}_BODY"
    body.data.name = f"{PREFIX}{code}_BODY_MESH"

    before_rigs = {obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE"}
    bpy.ops.mpfb.add_standard_rig()
    rig = next(
        obj
        for obj in bpy.context.scene.objects
        if obj.type == "ARMATURE" and obj not in before_rigs
    )
    rig.name = f"{PREFIX}{code}_RIG"
    rig.data.name = f"{PREFIX}{code}_RIG_DATA"

    activate(body)
    bpy.ops.mpfb.create_v2_skin()
    set_body_material(body, skin_material)

    move_to_collection(body, collection)
    move_to_collection(rig, collection)
    body["semantic_class"] = "person"
    body["survivor_id"] = code
    rig["survivor_id"] = code
    return body, rig


def set_bone_rotation(
    rig: bpy.types.Object,
    bone_name: str,
    xyz_degrees: tuple[float, float, float],
) -> None:
    bone = rig.pose.bones.get(bone_name)
    if bone is None:
        raise RuntimeError(f"Missing standard-rig bone: {bone_name}")
    bone.rotation_mode = "XYZ"
    bone.rotation_euler = tuple(math.radians(value) for value in xyz_degrees)


def set_lie_transform(
    rig: bpy.types.Object,
    feet_location: tuple[float, float, float],
    yaw_degrees: float,
    roll_degrees: float,
) -> None:
    lie = Quaternion((1.0, 0.0, 0.0), math.radians(-90.0))
    yaw = Quaternion((0.0, 0.0, 1.0), math.radians(yaw_degrees))
    base = yaw @ lie
    body_axis = base @ Vector((0.0, 0.0, 1.0))
    roll = Quaternion(body_axis.normalized(), math.radians(roll_degrees))
    rig.rotation_mode = "QUATERNION"
    rig.rotation_quaternion = roll @ base
    rig.location = feet_location


def evaluated_min_z(obj: bpy.types.Object) -> float:
    depsgraph = bpy.context.evaluated_depsgraph_get()
    bpy.context.view_layer.update()
    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    try:
        return min((evaluated.matrix_world @ vertex.co).z for vertex in mesh.vertices)
    finally:
        evaluated.to_mesh_clear()


def ground_body(body: bpy.types.Object, rig: bpy.types.Object, floor_z: float, clearance: float = 0.012) -> None:
    min_z = evaluated_min_z(body)
    rig.location.z += floor_z + clearance - min_z
    bpy.context.view_layer.update()


def ground_actor(
    actor_meshes: list[bpy.types.Object],
    rig: bpy.types.Object,
    floor_z: float,
    clearance: float = 0.012,
) -> None:
    min_z = min(evaluated_min_z(obj) for obj in actor_meshes if obj.type == "MESH")
    rig.location.z += floor_z + clearance - min_z
    bpy.context.view_layer.update()


def max_actor_z_in_footprint(
    actor_meshes: list[bpy.types.Object],
    center_x: float,
    center_y: float,
    size_x: float,
    size_y: float,
) -> float:
    """Return the evaluated actor surface height under a horizontal debris slab."""
    depsgraph = bpy.context.evaluated_depsgraph_get()
    bpy.context.view_layer.update()
    half_x = size_x * 0.5
    half_y = size_y * 0.5
    heights: list[float] = []

    for obj in actor_meshes:
        if obj.type != "MESH":
            continue
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        try:
            for vertex in mesh.vertices:
                world = evaluated.matrix_world @ vertex.co
                if (
                    abs(world.x - center_x) <= half_x
                    and abs(world.y - center_y) <= half_y
                ):
                    heights.append(world.z)
        finally:
            evaluated.to_mesh_clear()

    if not heights:
        raise RuntimeError(
            "No evaluated actor surface found below supported debris footprint "
            f"at ({center_x:.3f}, {center_y:.3f})"
        )
    return max(heights)


def world_bounds(obj: bpy.types.Object) -> tuple[Vector, Vector]:
    corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    low = Vector(tuple(min(corner[index] for corner in corners) for index in range(3)))
    high = Vector(tuple(max(corner[index] for corner in corners) for index in range(3)))
    return low, high


def bounds_overlap(
    first: tuple[Vector, Vector],
    second: tuple[Vector, Vector],
    margin: float = 0.015,
) -> bool:
    first_low, first_high = first
    second_low, second_high = second
    return all(
        first_low[axis] < second_high[axis] - margin
        and first_high[axis] > second_low[axis] + margin
        for axis in range(3)
    )


def architecture_overlap_report(
    code: str,
    actor_meshes: list[bpy.types.Object],
) -> list[str]:
    """Broad-phase guard against putting an actor through walls or ceilings."""
    obstacles: list[bpy.types.Object] = []
    for collection_name in ("VISUAL_ARCH",):
        collection = bpy.data.collections.get(collection_name)
        if collection is None:
            continue
        obstacles.extend(
            obj
            for obj in collection.objects
            if obj.type == "MESH" and "FLOOR" not in obj.name
        )

    violations: set[str] = set()
    for actor in actor_meshes:
        actor_bounds = world_bounds(actor)
        for obstacle in obstacles:
            if bounds_overlap(actor_bounds, world_bounds(obstacle)):
                violations.add(obstacle.name)

    report = sorted(violations)
    print(f"ARCHITECTURE_CLEARANCE_{code}", "OK" if not report else report)
    return report


def add_semantic_anchor(
    collection: bpy.types.Collection,
    code: str,
    location: tuple[float, float, float],
    condition: str,
    visibility: float,
    response: str,
) -> bpy.types.Object:
    empty = bpy.data.objects.new(f"{PREFIX}{code}_SEMANTIC_ANCHOR", None)
    collection.objects.link(empty)
    empty.empty_display_type = "SPHERE"
    empty.empty_display_size = 0.12
    empty.location = location
    empty.hide_render = True
    empty["semantic_class"] = "person"
    empty["scenario_role"] = "trapped_survivor"
    empty["condition"] = condition
    empty["estimated_visible_fraction"] = visibility
    empty["expected_interaction"] = response
    empty["benchmark_positive"] = True
    return empty


def add_debris_piece(
    collection: bpy.types.Collection,
    name: str,
    location: tuple[float, float, float],
    dimensions: tuple[float, float, float],
    rotation: tuple[float, float, float],
    material: bpy.types.Material,
    bevel: float = 0.025,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=location, rotation=rotation)
    piece = bpy.context.object
    piece.name = name
    piece.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    move_to_collection(piece, collection)
    piece.data.materials.append(material)
    modifier = piece.modifiers.new("Broken edges", "BEVEL")
    modifier.width = bevel
    modifier.segments = 2
    piece["visual_role"] = "survivor_entrapment_debris"
    piece["collision"] = False
    return piece


def add_supported_debris_piece(
    collection: bpy.types.Collection,
    name: str,
    actor_meshes: list[bpy.types.Object],
    center_xy: tuple[float, float],
    dimensions: tuple[float, float, float],
    z_rotation_degrees: float,
    material: bpy.types.Material,
    clearance: float = 0.004,
    bevel: float = 0.025,
) -> bpy.types.Object:
    """Place a level slab immediately above the highest actor surface below it."""
    center_x, center_y = center_xy
    support_z = max_actor_z_in_footprint(
        actor_meshes,
        center_x,
        center_y,
        dimensions[0],
        dimensions[1],
    )
    bottom_z = support_z + clearance
    piece = add_debris_piece(
        collection,
        name,
        (center_x, center_y, bottom_z + dimensions[2] * 0.5),
        dimensions,
        (0.0, 0.0, math.radians(z_rotation_degrees)),
        material,
        bevel=bevel,
    )
    actual_bottom_z = piece.location.z - piece.dimensions.z * 0.5
    actual_clearance = actual_bottom_z - support_z
    piece["contact_mode"] = "supported_on_evaluated_actor_surface"
    piece["support_surface_z_m"] = support_z
    piece["contact_clearance_m"] = actual_clearance
    print(
        f"SLAB_CONTACT_{name}",
        {
            "support_z": round(support_z, 5),
            "bottom_z": round(actual_bottom_z, 5),
            "clearance": round(actual_clearance, 5),
        },
    )
    if actual_clearance < 0.002:
        raise RuntimeError(
            f"{name} penetrates its actor support surface: {actual_clearance:.6f} m"
        )
    return piece


def add_rigid_body(
    obj: bpy.types.Object,
    body_type: str,
    collision_shape: str,
    mass: float = 1.0,
    friction: float = 0.88,
) -> None:
    activate(obj)
    bpy.ops.rigidbody.object_add()
    rigid_body = obj.rigid_body
    rigid_body.type = body_type
    rigid_body.collision_shape = collision_shape
    rigid_body.friction = friction
    rigid_body.restitution = 0.015
    rigid_body.use_margin = True
    rigid_body.collision_margin = 0.004
    if body_type == "ACTIVE":
        rigid_body.mass = mass
        rigid_body.linear_damping = 0.62
        rigid_body.angular_damping = 0.78
        rigid_body.use_deactivation = False


def bone_world_segment(
    rig: bpy.types.Object,
    bone_name: str,
) -> tuple[Vector, Vector]:
    bone = rig.pose.bones.get(bone_name)
    if bone is None:
        raise RuntimeError(f"Missing physics-proxy bone: {bone_name}")
    return rig.matrix_world @ bone.head, rig.matrix_world @ bone.tail


def lower_leg_contact_center(rig: bpy.types.Object) -> tuple[float, float]:
    points: list[Vector] = []
    for side in ("L", "R"):
        first_head, first_tail = bone_world_segment(rig, f"lowerleg01.{side}")
        second_head, second_tail = bone_world_segment(rig, f"lowerleg02.{side}")
        points.extend((first_head, first_tail, second_head, second_tail))
    return (
        sum(point.x for point in points) / len(points),
        sum(point.y for point in points) / len(points),
    )


def add_capsule_proxy(
    collection: bpy.types.Collection,
    name: str,
    start: Vector,
    end: Vector,
    radius: float,
) -> bpy.types.Object:
    direction = end - start
    length = direction.length
    if length <= 0.001:
        raise RuntimeError(f"Degenerate capsule proxy: {name}")
    midpoint = (start + end) * 0.5
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=midpoint)
    proxy = bpy.context.object
    proxy.name = name
    proxy.rotation_mode = "QUATERNION"
    proxy.rotation_quaternion = direction.to_track_quat("Z", "Y")
    proxy.dimensions = (radius * 2.0, radius * 2.0, length + radius * 2.0)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    move_to_collection(proxy, collection)
    proxy.display_type = "WIRE"
    proxy.hide_render = True
    proxy["physics_role"] = "passive_human_collision_proxy"
    add_rigid_body(proxy, "PASSIVE", "CAPSULE")
    return proxy


def add_leg_physics_proxies(
    collection: bpy.types.Collection,
    code: str,
    rig: bpy.types.Object,
) -> list[bpy.types.Object]:
    proxies: list[bpy.types.Object] = []
    for side in ("L", "R"):
        for segment in ("lowerleg01", "lowerleg02"):
            start, end = bone_world_segment(rig, f"{segment}.{side}")
            proxies.append(
                add_capsule_proxy(
                    collection,
                    f"{PREFIX}{code}_PHYS_{segment.upper()}_{side}",
                    start,
                    end,
                    radius=0.115,
                )
            )
    return proxies


def add_contact_proxy(
    collection: bpy.types.Collection,
    code: str,
    actor_meshes: list[bpy.types.Object],
    center_xy: tuple[float, float],
    footprint: tuple[float, float],
    floor_z: float,
) -> tuple[bpy.types.Object, float]:
    center_x, center_y = center_xy
    support_z = max_actor_z_in_footprint(
        actor_meshes,
        center_x,
        center_y,
        footprint[0],
        footprint[1],
    )
    height = max(0.04, support_z - floor_z)
    bpy.ops.mesh.primitive_cube_add(
        size=1.0,
        location=(center_x, center_y, floor_z + height * 0.5),
    )
    proxy = bpy.context.object
    proxy.name = f"{PREFIX}{code}_PHYS_CONTACT_PROXY"
    proxy.dimensions = (footprint[0] * 0.78, footprint[1] * 0.72, height)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    move_to_collection(proxy, collection)
    proxy.display_type = "WIRE"
    proxy.hide_render = True
    proxy["physics_role"] = "passive_actor_surface_proxy"
    proxy["support_surface_z_m"] = support_z
    add_rigid_body(proxy, "PASSIVE", "BOX")
    return proxy, support_z


def add_floor_physics_proxy(
    collection: bpy.types.Collection,
    code: str,
    center_xy: tuple[float, float],
    floor_z: float,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cube_add(
        size=1.0,
        location=(center_xy[0], center_xy[1], floor_z - 0.045),
    )
    proxy = bpy.context.object
    proxy.name = f"{PREFIX}{code}_PHYS_FLOOR_PROXY"
    proxy.dimensions = (6.0, 6.0, 0.09)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    move_to_collection(proxy, collection)
    proxy.display_type = "WIRE"
    proxy.hide_render = True
    proxy["physics_role"] = "passive_local_floor_proxy"
    add_rigid_body(proxy, "PASSIVE", "BOX")
    return proxy


def add_slab_guide_proxies(
    collection: bpy.types.Collection,
    code: str,
    center_xy: tuple[float, float],
    slab_dimensions: tuple[float, float, float],
    floor_z: float,
    support_z: float,
) -> list[bpy.types.Object]:
    """Create temporary invisible rails that permit falling but prevent escape."""
    center_x, center_y = center_xy
    size_x, size_y, _ = slab_dimensions
    rail_height = max(0.9, support_z - floor_z + 0.72)
    rail_z = floor_z + rail_height * 0.5
    thickness = 0.045
    clearance = 0.085
    specs = (
        (
            "X_NEG",
            (center_x - size_x * 0.5 - clearance, center_y, rail_z),
            (thickness, size_y + 0.34, rail_height),
        ),
        (
            "X_POS",
            (center_x + size_x * 0.5 + clearance, center_y, rail_z),
            (thickness, size_y + 0.34, rail_height),
        ),
        (
            "Y_NEG",
            (center_x, center_y - size_y * 0.5 - clearance, rail_z),
            (size_x + 0.34, thickness, rail_height),
        ),
        (
            "Y_POS",
            (center_x, center_y + size_y * 0.5 + clearance, rail_z),
            (size_x + 0.34, thickness, rail_height),
        ),
    )
    rails: list[bpy.types.Object] = []
    for suffix, location, dimensions in specs:
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=location)
        rail = bpy.context.object
        rail.name = f"{PREFIX}{code}_PHYS_GUIDE_{suffix}"
        rail.dimensions = dimensions
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        move_to_collection(rail, collection)
        rail.display_type = "WIRE"
        rail.hide_render = True
        rail["physics_role"] = "passive_temporary_slab_guide"
        add_rigid_body(rail, "PASSIVE", "BOX")
        rails.append(rail)
    return rails


def add_falling_slab(
    collection: bpy.types.Collection,
    code: str,
    center_xy: tuple[float, float],
    dimensions: tuple[float, float, float],
    z_rotation_degrees: float,
    support_z: float,
    material: bpy.types.Material,
) -> bpy.types.Object:
    piece = add_debris_piece(
        collection,
        f"{PREFIX}{code}_PINNING_SLAB",
        (center_xy[0], center_xy[1], support_z + 0.34),
        dimensions,
        (0.0, 0.0, math.radians(z_rotation_degrees)),
        material,
        bevel=0.032,
    )
    piece["physics_role"] = "active_guided_collapse_slab"
    piece["support_surface_z_m"] = support_z
    add_rigid_body(piece, "ACTIVE", "BOX", mass=22.0, friction=0.98)
    return piece


def add_falling_rubble_cluster(
    collection: bpy.types.Collection,
    code: str,
    center_xy: tuple[float, float],
    support_z: float,
    material: bpy.types.Material,
    count: int,
    spread: tuple[float, float],
) -> list[bpy.types.Object]:
    pieces: list[bpy.types.Object] = []
    for index in range(count):
        sx = RNG.uniform(0.11, 0.29)
        sy = RNG.uniform(0.09, 0.24)
        sz = RNG.uniform(0.055, 0.14)
        side = -1.0 if index % 2 == 0 else 1.0
        x = center_xy[0] + side * RNG.uniform(spread[0] * 0.84, spread[0])
        y = center_xy[1] + RNG.uniform(-spread[1], spread[1])
        z = support_z + 0.48 + index * 0.075
        rotations = tuple(RNG.uniform(-0.28, 0.28) for _ in range(3))
        piece = add_debris_piece(
            collection,
            f"{PREFIX}{code}_RUBBLE_{index:02d}",
            (x, y, z),
            (sx, sy, sz),
            rotations,
            material,
            bevel=min(sx, sy, sz) * 0.12,
        )
        piece["physics_role"] = "active_guided_collapse_rubble"
        add_rigid_body(
            piece,
            "ACTIVE",
            "BOX",
            mass=max(0.8, sx * sy * sz * 900.0),
            friction=0.9,
        )
        pieces.append(piece)
    return pieces


def simulate_and_freeze_collapse(
    dynamic_objects: list[bpy.types.Object],
    proxy_objects: list[bpy.types.Object],
    end_frame: int = 300,
) -> dict[str, object]:
    scene = bpy.context.scene
    if scene.rigidbody_world is None:
        bpy.ops.rigidbody.world_add()
    world = scene.rigidbody_world
    world.substeps_per_frame = 12
    world.solver_iterations = 24
    world.time_scale = 1.0
    world.point_cache.frame_start = 1
    world.point_cache.frame_end = end_frame
    scene.frame_start = 1
    scene.frame_end = end_frame
    scene.frame_set(1)

    previous_positions: dict[str, Vector] = {}
    max_late_step = 0.0
    max_late_by_object: dict[str, float] = {obj.name: 0.0 for obj in dynamic_objects}
    for frame in range(1, end_frame + 1):
        scene.frame_set(frame)
        if frame >= end_frame - 20:
            for obj in dynamic_objects:
                current = obj.matrix_world.translation.copy()
                previous = previous_positions.get(obj.name)
                if previous is not None:
                    step = (current - previous).length
                    max_late_step = max(max_late_step, step)
                    max_late_by_object[obj.name] = max(max_late_by_object[obj.name], step)
                previous_positions[obj.name] = current

    final_matrices = {obj.name: obj.matrix_world.copy() for obj in dynamic_objects}
    unstable_objects = {
        name: step for name, step in max_late_by_object.items() if step > 0.003
    }
    for obj in dynamic_objects:
        activate(obj)
        if obj.rigid_body is not None:
            bpy.ops.rigidbody.object_remove()
        obj.matrix_world = final_matrices[obj.name]
        obj["physics_frozen_frame"] = end_frame
        obj["physics_baked_static"] = True

    for proxy in proxy_objects:
        if proxy.name in bpy.data.objects:
            bpy.data.objects.remove(proxy, do_unlink=True)

    if scene.rigidbody_world is not None:
        bpy.ops.rigidbody.world_remove()
    scene.frame_set(end_frame)
    print(
        "PHYSICS_SETTLE",
        {
            "frame": end_frame,
            "dynamic_count": len(dynamic_objects),
            "max_late_step_m": round(max_late_step, 6),
            "unstable_objects": {
                name: round(step, 6) for name, step in unstable_objects.items()
            },
        },
    )
    return {
        "max_late_step_m": max_late_step,
        "frame": float(end_frame),
        "unstable_objects": unstable_objects,
    }


def enforce_settled_slab_clearance(
    code: str,
    slab: bpy.types.Object,
    contact_center: tuple[float, float],
    support_z: float,
    clearance: float = 0.004,
) -> dict[str, float]:
    """Apply a millimetric safety lift after physics and validate lateral drift."""
    low, _ = world_bounds(slab)
    lift = max(0.0, support_z + clearance - low.z)
    slab.location.z += lift
    bpy.context.view_layer.update()
    final_low, _ = world_bounds(slab)
    drift = math.hypot(
        slab.matrix_world.translation.x - contact_center[0],
        slab.matrix_world.translation.y - contact_center[1],
    )
    final_clearance = final_low.z - support_z
    slab["post_settle_safety_lift_m"] = lift
    slab["final_contact_clearance_m"] = final_clearance
    slab["final_lateral_drift_m"] = drift
    report = {
        "lift_m": lift,
        "clearance_m": final_clearance,
        "lateral_drift_m": drift,
    }
    print(
        f"SETTLED_SLAB_CLEARANCE_{code}",
        {key: round(value, 6) for key, value in report.items()},
    )
    if final_clearance < 0.0035 or drift > 0.10:
        raise RuntimeError(f"Invalid settled slab contact {code}: {report}")
    return report


def add_rubble_cluster(
    collection: bpy.types.Collection,
    code: str,
    center: tuple[float, float, float],
    floor_z: float,
    material: bpy.types.Material,
    count: int,
    spread: tuple[float, float],
) -> None:
    cx, cy, _ = center
    for index in range(count):
        sx = RNG.uniform(0.11, 0.34)
        sy = RNG.uniform(0.09, 0.29)
        sz = RNG.uniform(0.055, 0.16)
        x = cx + RNG.uniform(-spread[0], spread[0])
        y = cy + RNG.uniform(-spread[1], spread[1])
        z = floor_z + sz * 0.5 + RNG.uniform(0.0, 0.045)
        rotations = tuple(RNG.uniform(-0.32, 0.32) for _ in range(3))
        add_debris_piece(
            collection,
            f"{PREFIX}{code}_RUBBLE_{index:02d}",
            (x, y, z),
            (sx, sy, sz),
            rotations,
            material,
            bevel=min(sx, sy, sz) * 0.12,
        )


def look_at(obj: bpy.types.Object, target: tuple[float, float, float] | Vector) -> None:
    target_vector = Vector(target)
    obj.rotation_euler = (target_vector - obj.location).to_track_quat("-Z", "Y").to_euler()


def add_camera(
    collection: bpy.types.Collection,
    name: str,
    location: tuple[float, float, float],
    target: tuple[float, float, float],
    lens: float,
) -> bpy.types.Object:
    camera_data = bpy.data.cameras.new(f"{name}_DATA")
    camera = bpy.data.objects.new(name, camera_data)
    collection.objects.link(camera)
    camera.location = location
    camera.data.lens = lens
    camera.data.sensor_width = 32.0
    camera.data.dof.use_dof = True
    camera.data.dof.focus_distance = (Vector(location) - Vector(target)).length
    camera.data.dof.aperture_fstop = 4.8
    look_at(camera, target)
    return camera


def add_area_light(
    collection: bpy.types.Collection,
    name: str,
    location: tuple[float, float, float],
    target: tuple[float, float, float],
    energy: float,
    size: float,
    color: tuple[float, float, float],
) -> bpy.types.Object:
    data = bpy.data.lights.new(f"{name}_DATA", "AREA")
    light = bpy.data.objects.new(name, data)
    collection.objects.link(light)
    light.location = location
    data.energy = energy
    data.shape = "DISK"
    data.size = size
    data.color = color
    look_at(light, target)
    return light


def add_spot_light(
    collection: bpy.types.Collection,
    name: str,
    location: tuple[float, float, float],
    target: tuple[float, float, float],
    energy: float,
    color: tuple[float, float, float],
) -> bpy.types.Object:
    data = bpy.data.lights.new(f"{name}_DATA", "SPOT")
    light = bpy.data.objects.new(name, data)
    collection.objects.link(light)
    light.location = location
    data.energy = energy
    data.color = color
    data.spot_size = math.radians(52.0)
    data.spot_blend = 0.56
    data.shadow_soft_size = 0.09
    look_at(light, target)
    return light


def render(camera: bpy.types.Object, filename: str, exposure: float = 0.0) -> None:
    scene = bpy.context.scene
    scene.camera = camera
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = exposure
    scene.render.filepath = str(RENDER_DIR / filename)
    bpy.ops.render.render(write_still=True)


def render_open_roof_overview(
    camera: bpy.types.Object,
    filename: str,
    exposure: float = 0.0,
) -> None:
    architecture = bpy.data.collections.get("VISUAL_ARCH")
    ceilings = (
        [obj for obj in architecture.objects if "CEIL_" in obj.name]
        if architecture is not None
        else []
    )
    previous_states = {obj.name: obj.hide_render for obj in ceilings}
    try:
        for ceiling in ceilings:
            ceiling.hide_render = True
        render(camera, filename, exposure)
    finally:
        for ceiling in ceilings:
            ceiling.hide_render = previous_states[ceiling.name]


def export_actor_glb(
    code: str,
    rig: bpy.types.Object,
    meshes: list[bpy.types.Object],
) -> Path:
    bpy.ops.object.select_all(action="DESELECT")
    rig.select_set(True)
    for obj in meshes:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = rig
    destination = EXPORT_DIR / f"pulso_survivor_{code}.glb"
    bpy.ops.export_scene.gltf(
        filepath=str(destination),
        export_format="GLB",
        use_selection=True,
        export_extras=True,
        export_animations=True,
        export_frame_range=False,
        export_apply=False,
    )
    return destination


remove_previous_pass()
survivor_collection = new_collection()

skin_a = make_skin_material(
    f"{PREFIX}A_SKIN",
    (0.052, 0.014, 0.006),
    (0.18, 0.052, 0.019),
)
skin_b = make_skin_material(
    f"{PREFIX}B_SKIN",
    (0.035, 0.008, 0.003),
    (0.125, 0.031, 0.011),
)

rubble_material = bpy.data.materials.get("MAT_BLOCK_FRAGMENT")
if rubble_material is None:
    rubble_material = make_fabric_material(
        f"{PREFIX}RUBBLE_MAT",
        (0.21, 0.19, 0.17),
        (0.37, 0.34, 0.29),
        roughness=0.9,
    )

physics_dynamic: list[bpy.types.Object] = []
physics_proxies: list[bpy.types.Object] = []


# Survivor A: conscious and signaling; calves pinned at the edge of Room A's talus.
body_a, rig_a = create_human("A", survivor_collection, "female", 0.72, skin_a)
actor_a_meshes = [body_a]
actor_a_meshes.extend(
    [
        add_official_asset(
            body_a,
            "A",
            survivor_collection,
            "Clothes",
            "clothes/joepal_crude_t-shirt_female/joepal_crude_t-shirt_female.mhclo",
            "TSHIRT",
            tint=(0.34, 0.045, 0.008),
            mask_body=True,
        ),
        add_official_asset(
            body_a,
            "A",
            survivor_collection,
            "Clothes",
            "clothes/cortu_cargo_pants/cortu_cargo_pants.mhclo",
            "CARGO_PANTS",
            tint=(0.065, 0.075, 0.09),
            mask_body=True,
        ),
        add_official_asset(
            body_a,
            "A",
            survivor_collection,
            "Clothes",
            "clothes/toigo_ankle_boots_female/toigo_ankle_boots_female.mhclo",
            "BOOTS",
            tint=(0.055, 0.035, 0.02),
            mask_body=True,
        ),
        add_official_asset(
            body_a,
            "A",
            survivor_collection,
            "Eyes",
            "eyes/high-poly/high-poly.mhclo",
            "EYES",
        ),
        add_official_asset(
            body_a,
            "A",
            survivor_collection,
            "Eyebrows",
            "eyebrows/eyebrow003/eyebrow003.mhclo",
            "EYEBROWS",
        ),
        add_official_asset(
            body_a,
            "A",
            survivor_collection,
            "Eyelashes",
            "eyelashes/eyelashes01/eyelashes01.mhclo",
            "EYELASHES",
        ),
        add_official_asset(
            body_a,
            "A",
            survivor_collection,
            "Hair",
            "hair/short03/short03.mhclo",
            "HAIR",
            tint=(0.075, 0.026, 0.012),
        ),
    ]
)

set_bone_rotation(rig_a, "upperarm01.L", (0.0, 0.0, 46.0))
set_bone_rotation(rig_a, "upperarm02.L", (0.0, 0.0, 10.0))
set_bone_rotation(rig_a, "lowerarm01.L", (4.0, 0.0, 76.0))
set_bone_rotation(rig_a, "wrist.L", (0.0, -8.0, 12.0))
set_bone_rotation(rig_a, "upperarm01.R", (-5.0, 0.0, -29.0))
set_bone_rotation(rig_a, "lowerarm01.R", (-8.0, 0.0, -61.0))
set_bone_rotation(rig_a, "upperleg01.L", (9.0, 0.0, 5.0))
set_bone_rotation(rig_a, "lowerleg01.L", (-27.0, 0.0, -2.0))
set_bone_rotation(rig_a, "upperleg01.R", (2.0, 0.0, -4.0))
set_bone_rotation(rig_a, "head", (0.0, 14.0, 18.0))
set_bone_rotation(rig_a, "neck01", (0.0, 6.0, 8.0))
set_lie_transform(rig_a, (-5.12, 0.74, 0.12), yaw_degrees=180.0, roll_degrees=5.0)
ground_actor(actor_a_meshes, rig_a, floor_z=0.0)

body_a["condition"] = "conscious_partial_lower_body_entrapment"
body_a["expected_response"] = "voice_and_hand_signal"
body_a["priority"] = "P1"
body_a["actor_export"] = "pulso_survivor_A.glb"

contact_center_a = lower_leg_contact_center(rig_a)
physics_proxies.extend(add_leg_physics_proxies(survivor_collection, "A", rig_a))
contact_proxy_a, support_z_a = add_contact_proxy(
    survivor_collection,
    "A",
    actor_a_meshes,
    contact_center_a,
    (1.02, 0.42),
    floor_z=0.0,
)
physics_proxies.extend(
    (
        contact_proxy_a,
        add_floor_physics_proxy(
            survivor_collection,
            "A",
            contact_center_a,
            floor_z=0.0,
        ),
    )
)
physics_proxies.extend(
    add_slab_guide_proxies(
        survivor_collection,
        "A",
        contact_center_a,
        (1.02, 0.42, 0.16),
        floor_z=0.0,
        support_z=support_z_a,
    )
)
slab_a = add_falling_slab(
    survivor_collection,
    "A",
    contact_center_a,
    (1.02, 0.42, 0.16),
    7.0,
    support_z_a,
    rubble_material,
)
physics_dynamic.append(slab_a)
add_semantic_anchor(
    survivor_collection,
    "A",
    (-5.12, -0.66, 0.22),
    "conscious_partial_lower_body_entrapment",
    visibility=0.62,
    response="answers_voice_and_raises_left_hand",
)


# Survivor B: side-lying, face toward the rover, lower legs under a dedicated slab.
body_b, rig_b = create_human("B", survivor_collection, "male", 0.70, skin_b)
actor_b_meshes = [body_b]
actor_b_meshes.extend(
    [
        add_official_asset(
            body_b,
            "B",
            survivor_collection,
            "Clothes",
            "clothes/namuhekam_male_polo_shirt/namuhekam_male_polo_shirt.mhclo",
            "POLO",
            tint=(0.012, 0.13, 0.19),
            mask_body=True,
        ),
        add_official_asset(
            body_b,
            "B",
            survivor_collection,
            "Clothes",
            "clothes/toigo_wool_pants/toigo_wool_pants.mhclo",
            "WOOL_PANTS",
            tint=(0.045, 0.06, 0.095),
            mask_body=True,
        ),
        add_official_asset(
            body_b,
            "B",
            survivor_collection,
            "Clothes",
            "clothes/toigo_ankle_boots_male/toigo_ankle_boots_male.mhclo",
            "BOOTS",
            tint=(0.055, 0.035, 0.02),
            mask_body=True,
        ),
        add_official_asset(
            body_b,
            "B",
            survivor_collection,
            "Eyes",
            "eyes/high-poly/high-poly.mhclo",
            "EYES",
        ),
        add_official_asset(
            body_b,
            "B",
            survivor_collection,
            "Eyebrows",
            "eyebrows/eyebrow001/eyebrow001.mhclo",
            "EYEBROWS",
        ),
        add_official_asset(
            body_b,
            "B",
            survivor_collection,
            "Eyelashes",
            "eyelashes/eyelashes02/eyelashes02.mhclo",
            "EYELASHES",
        ),
        add_official_asset(
            body_b,
            "B",
            survivor_collection,
            "Hair",
            "hair/short01/short01.mhclo",
            "HAIR",
            tint=(0.035, 0.012, 0.006),
        ),
    ]
)

set_bone_rotation(rig_b, "upperarm01.L", (3.0, 0.0, 45.0))
set_bone_rotation(rig_b, "lowerarm01.L", (-6.0, 0.0, 105.0))
set_bone_rotation(rig_b, "wrist.L", (0.0, 8.0, -8.0))
set_bone_rotation(rig_b, "upperarm01.R", (-4.0, 0.0, -18.0))
set_bone_rotation(rig_b, "lowerarm01.R", (4.0, 0.0, -95.0))
set_bone_rotation(rig_b, "upperleg01.L", (25.0, 0.0, 12.0))
set_bone_rotation(rig_b, "lowerleg01.L", (-65.0, 0.0, -5.0))
set_bone_rotation(rig_b, "upperleg01.R", (12.0, 0.0, -10.0))
set_bone_rotation(rig_b, "lowerleg01.R", (-45.0, 0.0, 5.0))
set_bone_rotation(rig_b, "head", (0.0, 9.0, 12.0))
set_bone_rotation(rig_b, "neck01", (0.0, 4.0, 5.0))
set_lie_transform(rig_b, (8.40, -2.60, -0.04), yaw_degrees=0.0, roll_degrees=65.0)
ground_actor(actor_b_meshes, rig_b, floor_z=-0.15)

body_b["condition"] = "conscious_weak_lower_body_entrapment"
body_b["expected_response"] = "weak_voice_and_small_left_arm_movement"
body_b["priority"] = "P1"
body_b["actor_export"] = "pulso_survivor_B.glb"

contact_center_b = lower_leg_contact_center(rig_b)
physics_proxies.extend(add_leg_physics_proxies(survivor_collection, "B", rig_b))
contact_proxy_b, support_z_b = add_contact_proxy(
    survivor_collection,
    "B",
    actor_b_meshes,
    contact_center_b,
    (1.05, 0.42),
    floor_z=-0.15,
)
physics_proxies.extend(
    (
        contact_proxy_b,
        add_floor_physics_proxy(
            survivor_collection,
            "B",
            contact_center_b,
            floor_z=-0.15,
        ),
    )
)
physics_proxies.extend(
    add_slab_guide_proxies(
        survivor_collection,
        "B",
        contact_center_b,
        (1.05, 0.42, 0.17),
        floor_z=-0.15,
        support_z=support_z_b,
    )
)
slab_b = add_falling_slab(
    survivor_collection,
    "B",
    contact_center_b,
    (1.05, 0.42, 0.17),
    -6.0,
    support_z_b,
    rubble_material,
)
physics_dynamic.append(slab_b)
add_semantic_anchor(
    survivor_collection,
    "B",
    (8.40, -0.97, 0.06),
    "conscious_weak_lower_body_entrapment",
    visibility=0.52,
    response="weak_voice_after_prompt_and_small_left_arm_movement",
)

wall_violations_a = architecture_overlap_report("A", actor_a_meshes)
wall_violations_b = architecture_overlap_report("B", actor_b_meshes)
if wall_violations_a or wall_violations_b:
    raise RuntimeError(
        f"Survivor architecture overlap: A={wall_violations_a}, B={wall_violations_b}"
    )

physics_settle = simulate_and_freeze_collapse(
    physics_dynamic,
    physics_proxies,
    end_frame=300,
)
if physics_settle["max_late_step_m"] > 0.003:
    raise RuntimeError(f"Rigid-body collapse did not settle: {physics_settle}")
slab_contact_a = enforce_settled_slab_clearance(
    "A",
    slab_a,
    contact_center_a,
    support_z_a,
)
slab_contact_b = enforce_settled_slab_clearance(
    "B",
    slab_b,
    contact_center_b,
    support_z_b,
)

camera_a = add_camera(
    survivor_collection,
    f"{PREFIX}CAM_A_DETECTION",
    (-5.92, -2.74, 0.72),
    (-5.10, -0.28, 0.19),
    lens=55.0,
)
camera_b = add_camera(
    survivor_collection,
    f"{PREFIX}CAM_B_DETECTION",
    (9.50, -0.22, 1.55),
    (8.40, -1.78, 0.14),
    lens=30.0,
)
camera_overview = add_camera(
    survivor_collection,
    f"{PREFIX}CAM_TOP_OVERVIEW",
    (1.90, 0.0, 19.0),
    (1.90, 0.0, 0.0),
    lens=36.0,
)

light_a_flash = add_spot_light(
    survivor_collection,
    f"{PREFIX}LIGHT_A_ROVER_FLASH",
    (-5.72, -1.72, 0.40),
    (-5.10, -0.30, 0.18),
    energy=285.0,
    color=(1.0, 0.80, 0.57),
)
light_a_bounce = add_area_light(
    survivor_collection,
    f"{PREFIX}LIGHT_A_BOUNCE",
    (-4.20, -0.92, 2.20),
    (-5.10, -0.22, 0.20),
    energy=165.0,
    size=2.0,
    color=(0.42, 0.58, 1.0),
)
light_b_flash = add_spot_light(
    survivor_collection,
    f"{PREFIX}LIGHT_B_ROVER_FLASH",
    (9.34, -0.62, 0.55),
    (8.40, -1.70, 0.08),
    energy=45.0,
    color=(1.0, 0.79, 0.55),
)
light_b_bounce = add_area_light(
    survivor_collection,
    f"{PREFIX}LIGHT_B_BOUNCE",
    (7.42, -0.82, 2.35),
    (8.40, -1.70, 0.06),
    energy=25.0,
    size=2.3,
    color=(0.39, 0.53, 1.0),
)
light_overview = add_area_light(
    survivor_collection,
    f"{PREFIX}LIGHT_TOP_OVERVIEW",
    (1.90, 0.0, 15.0),
    (1.90, 0.0, 0.0),
    energy=3600.0,
    size=11.0,
    color=(0.82, 0.90, 1.0),
)


scene = bpy.context.scene
scene.render.engine = "BLENDER_EEVEE"
scene.render.resolution_x = 1280
scene.render.resolution_y = 720
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGBA"
scene.render.film_transparent = False
scene.render.use_file_extension = True
scene.render.image_settings.color_depth = "8"
scene.world.color = (0.006, 0.007, 0.01)

scene["pulso_survivor_pass"] = "v002_physics_settled"
scene["survivor_count"] = 2
scene["semantic_contract"] = "Bodies and anchors carry person/condition/response properties"
scene["collision_unchanged"] = True
scene["source_checkpoint"] = "pre_fable_20260730_230714"
scene["actor_visual_format"] = "glTF Binary (GLB)"
scene["actor_collision_strategy"] = "Use simple Gazebo/ROS proxy colliders, not visual meshes"
scene["collapse_layout_method"] = "guided Blender rigid-body settle frozen at frame 300"
scene["collapse_settle_max_late_step_m"] = physics_settle["max_late_step_m"]
scene["slab_contact_clearance_A_m"] = slab_contact_a["clearance_m"]
scene["slab_contact_clearance_B_m"] = slab_contact_b["clearance_m"]

bpy.ops.file.pack_all()
bpy.ops.wm.save_as_mainfile(filepath=str(WORKING_BLEND))
export_a = export_actor_glb("A", rig_a, actor_a_meshes)
export_b = export_actor_glb("B", rig_b, actor_b_meshes)
light_a_flash.hide_render = False
light_a_bounce.hide_render = False
light_b_flash.hide_render = True
light_b_bounce.hide_render = True
light_overview.hide_render = True
render(camera_a, "pulso_survivor_A_detection.png", exposure=-0.35)

light_a_flash.hide_render = True
light_a_bounce.hide_render = True
light_b_flash.hide_render = False
light_b_bounce.hide_render = False
light_overview.hide_render = True
render(camera_b, "pulso_survivor_B_detection.png", exposure=-1.4)

light_a_flash.hide_render = True
light_a_bounce.hide_render = True
light_b_flash.hide_render = True
light_b_bounce.hide_render = True
light_overview.hide_render = False
render_open_roof_overview(camera_overview, "pulso_survivors_overview.png", exposure=-0.2)
light_overview.hide_render = True
bpy.ops.wm.save_as_mainfile(filepath=str(WORKING_BLEND))

print(
    "PULSO_SURVIVOR_BUILD_OK",
    {
        "blend": str(WORKING_BLEND),
        "collection_objects": len(survivor_collection.objects),
        "survivors": [body_a.name, body_b.name],
        "physics_settle": physics_settle,
        "slab_contacts": {"A": slab_contact_a, "B": slab_contact_b},
        "exports": [str(export_a), str(export_b)],
        "renders": [
            str(RENDER_DIR / "pulso_survivor_A_detection.png"),
            str(RENDER_DIR / "pulso_survivor_B_detection.png"),
            str(RENDER_DIR / "pulso_survivors_overview.png"),
        ],
    },
)
