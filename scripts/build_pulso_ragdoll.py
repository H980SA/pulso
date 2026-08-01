"""Generate a physics-first Pulso collapse scenario with articulated ragdolls.

Run this script from Blender against the current packed Pulso scene.  Human
poses and entrapment debris are outcomes of rigid-body simulation rather than
hand-authored final poses.  The stable frame is transferred back to the MPFB
armatures, physics helpers are removed, and a static scenario is saved for
Gazebo/Unity ingestion.
"""

from __future__ import annotations

import math
import random
import sys
from pathlib import Path
from typing import Any

import bpy
from mathutils import Matrix, Quaternion, Vector


PROJECT = Path(__file__).resolve().parents[1]
DEFAULT_SEED = 20260731
RAGDOLL_PREFIX = "PULSO_RAGDOLL_"
SURVIVOR_PREFIX = "PULSO_SURVIVOR_"
PROXY_COLLISION_LAYERS = {
    "pelvis": 0,
    "chest": 1,
    "neck": 2,
    "head": 3,
    "upperarm_L": 4,
    "lowerarm_L": 5,
    "hand_L": 6,
    "upperarm_R": 7,
    "lowerarm_R": 8,
    "hand_R": 9,
    "thigh_L": 10,
    "shin_L": 11,
    "foot_L": 12,
    "thigh_R": 13,
    "shin_R": 14,
    "foot_R": 15,
}
SCENARIO_COLLISION_LAYERS = set(range(16))


def parse_seed() -> int:
    if "--" not in sys.argv:
        return DEFAULT_SEED
    arguments = sys.argv[sys.argv.index("--") + 1 :]
    for index, argument in enumerate(arguments):
        if argument == "--seed" and index + 1 < len(arguments):
            return int(arguments[index + 1])
    return DEFAULT_SEED


SEED = parse_seed()
RNG = random.Random(SEED)
OUTPUT_ROOT = PROJECT / "art/current/ragdoll" / f"seed_{SEED}"
RENDER_DIR = OUTPUT_ROOT / "renders"
RENDER_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_BLEND = OUTPUT_ROOT / f"pulso_ragdoll_seed_{SEED}.blend"
SIMULATION_BLEND = OUTPUT_ROOT / f"pulso_ragdoll_seed_{SEED}_simulation.blend"


def activate(obj: bpy.types.Object) -> None:
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def move_to_collection(obj: bpy.types.Object, collection: bpy.types.Collection) -> None:
    for current in list(obj.users_collection):
        current.objects.unlink(obj)
    collection.objects.link(obj)


def remove_object(obj: bpy.types.Object) -> None:
    if obj.name in bpy.data.objects:
        bpy.data.objects.remove(obj, do_unlink=True)


def clean_previous_ragdoll_pass() -> None:
    for obj in list(bpy.data.objects):
        if obj.name.startswith(RAGDOLL_PREFIX):
            remove_object(obj)
        elif obj.name.startswith(SURVIVOR_PREFIX) and any(
            marker in obj.name
            for marker in ("PINNING_SLAB", "CAM_", "LIGHT_", "_RUBBLE_")
        ):
            remove_object(obj)

    for collection_name in ("VISUAL_RAGDOLL", "PHYSICS_RAGDOLL"):
        collection = bpy.data.collections.get(collection_name)
        if collection is not None:
            bpy.data.collections.remove(collection)

    if bpy.context.scene.rigidbody_world is not None:
        for obj in bpy.data.objects:
            if obj.rigid_body is not None:
                activate(obj)
                bpy.ops.rigidbody.object_remove()
        bpy.ops.rigidbody.world_remove()


def new_collection(name: str, purpose: str) -> bpy.types.Collection:
    collection = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(collection)
    collection["purpose"] = purpose
    collection["scenario_seed"] = SEED
    return collection


def actor_rig(code: str) -> bpy.types.Object:
    return bpy.data.objects[f"{SURVIVOR_PREFIX}{code}_RIG"]


def actor_meshes(code: str, rig: bpy.types.Object) -> list[bpy.types.Object]:
    meshes: list[bpy.types.Object] = []
    for obj in bpy.data.objects:
        if obj.type != "MESH" or not obj.name.startswith(f"{SURVIVOR_PREFIX}{code}_"):
            continue
        if obj.parent == rig or any(
            modifier.type == "ARMATURE" and modifier.object == rig
            for modifier in obj.modifiers
        ):
            meshes.append(obj)
    if not meshes:
        raise RuntimeError(f"No actor meshes found for survivor {code}")
    return meshes


def evaluated_min_z(objects: list[bpy.types.Object]) -> float:
    depsgraph = bpy.context.evaluated_depsgraph_get()
    bpy.context.view_layer.update()
    minimum = math.inf
    for obj in objects:
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        try:
            minimum = min(
                minimum,
                min(
                    (evaluated.matrix_world @ vertex.co).z
                    for vertex in mesh.vertices
                ),
            )
        finally:
            evaluated.to_mesh_clear()
    return minimum


def evaluated_bounds(objects: list[bpy.types.Object]) -> tuple[Vector, Vector]:
    depsgraph = bpy.context.evaluated_depsgraph_get()
    bpy.context.view_layer.update()
    lows = Vector((math.inf, math.inf, math.inf))
    highs = Vector((-math.inf, -math.inf, -math.inf))
    for obj in objects:
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        try:
            for vertex in mesh.vertices:
                world = evaluated.matrix_world @ vertex.co
                for axis in range(3):
                    lows[axis] = min(lows[axis], world[axis])
                    highs[axis] = max(highs[axis], world[axis])
        finally:
            evaluated.to_mesh_clear()
    return lows, highs


def reset_actor_for_drop(
    code: str,
    rig: bpy.types.Object,
    meshes: list[bpy.types.Object],
    location_xy: tuple[float, float],
    floor_z: float,
    yaw_degrees: float,
    tilt_degrees: tuple[float, float],
    drop_height: float,
) -> None:
    rig.animation_data_clear()
    for bone in rig.pose.bones:
        bone.matrix_basis = Matrix.Identity(4)

    rig.rotation_mode = "XYZ"
    rig.rotation_euler = (
        math.radians(tilt_degrees[0]),
        math.radians(tilt_degrees[1]),
        math.radians(yaw_degrees),
    )
    rig.location = (location_xy[0], location_xy[1], floor_z)
    bpy.context.view_layer.update()
    rig.location.z += floor_z + drop_height - evaluated_min_z(meshes)
    bpy.context.view_layer.update()
    rig["ragdoll_seed"] = SEED
    rig["ragdoll_initial_state"] = "lateral_collapse_drop_with_random_tilt"
    print(
        f"RAGDOLL_INITIAL_{code}",
        {
            "location": tuple(round(value, 4) for value in rig.location),
            "rotation_deg": (
                round(tilt_degrees[0], 2),
                round(tilt_degrees[1], 2),
                round(yaw_degrees, 2),
            ),
            "drop_height_m": drop_height,
        },
    )


def random_lateral_collapse_tilt() -> tuple[float, float]:
    # Start from a physically plausible knocked-off-balance state, not a
    # mannequin standing under a slab.  The final pose still comes exclusively
    # from Bullet and varies with the scenario seed.
    major = RNG.choice((-1.0, 1.0)) * RNG.uniform(62.0, 84.0)
    minor = RNG.uniform(-16.0, 16.0)
    return (major, minor) if RNG.random() < 0.5 else (minor, major)


def bone_world_point(
    rig: bpy.types.Object,
    bone_name: str,
    endpoint: str,
) -> Vector:
    bone = rig.pose.bones.get(bone_name)
    if bone is None:
        raise RuntimeError(f"Missing ragdoll bone: {bone_name}")
    point = bone.head if endpoint == "head" else bone.tail
    return rig.matrix_world @ point


def bone_world_matrix(rig: bpy.types.Object, bone_name: str) -> Matrix:
    bone = rig.pose.bones.get(bone_name)
    if bone is None:
        raise RuntimeError(f"Missing ragdoll driver bone: {bone_name}")
    return rig.matrix_world @ bone.matrix


def add_rigid_body(
    obj: bpy.types.Object,
    body_type: str,
    collision_shape: str,
    mass: float = 1.0,
    friction: float = 0.82,
    linear_damping: float = 0.36,
    angular_damping: float = 0.55,
    collision_layers: set[int] | None = None,
) -> None:
    activate(obj)
    bpy.ops.rigidbody.object_add()
    rigid_body = obj.rigid_body
    rigid_body.type = body_type
    rigid_body.collision_shape = collision_shape
    rigid_body.friction = friction
    rigid_body.restitution = 0.01
    rigid_body.use_margin = True
    rigid_body.collision_margin = 0.004
    if collision_layers is not None:
        for index in range(20):
            rigid_body.collision_collections[index] = index in collision_layers
    if body_type == "ACTIVE":
        rigid_body.mass = mass
        rigid_body.linear_damping = linear_damping
        rigid_body.angular_damping = angular_damping
        rigid_body.use_deactivation = False
        if hasattr(rigid_body, "use_ccd"):
            rigid_body.use_ccd = True


def aligned_quaternion(start: Vector, end: Vector) -> Quaternion:
    direction = end - start
    if direction.length <= 0.001:
        raise RuntimeError("Cannot align a zero-length ragdoll segment")
    return direction.to_track_quat("Z", "Y")


def create_segment_proxy(
    collection: bpy.types.Collection,
    code: str,
    name: str,
    rig: bpy.types.Object,
    driver_bone: str,
    start: Vector,
    end: Vector,
    radius: float,
    mass: float,
    collision_shape: str = "CAPSULE",
    box_dimensions: tuple[float, float, float] | None = None,
) -> dict[str, Any]:
    midpoint = (start + end) * 0.5
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=midpoint)
    proxy = bpy.context.object
    proxy.name = f"{RAGDOLL_PREFIX}{code}_{name.upper()}"
    proxy.rotation_mode = "QUATERNION"
    proxy.rotation_quaternion = aligned_quaternion(start, end)
    if box_dimensions is None:
        proxy.dimensions = (
            radius * 2.0,
            radius * 2.0,
            (end - start).length + radius * 2.0,
        )
    else:
        proxy.dimensions = box_dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    move_to_collection(proxy, collection)
    proxy.display_type = "WIRE"
    proxy.hide_render = True
    proxy["physics_role"] = "articulated_human_segment"
    proxy["survivor_id"] = code
    proxy["driver_bone"] = driver_bone
    add_rigid_body(
        proxy,
        "ACTIVE",
        collision_shape,
        mass=mass,
        friction=0.78,
        linear_damping=0.42,
        angular_damping=0.64,
        collision_layers={PROXY_COLLISION_LAYERS[name]},
    )
    driver_offset = proxy.matrix_world.inverted() @ bone_world_matrix(rig, driver_bone)
    return {
        "name": name,
        "object": proxy,
        "driver_bone": driver_bone,
        "driver_offset": driver_offset,
        "start": start.copy(),
        "end": end.copy(),
    }


def make_actor_ragdoll(
    code: str,
    rig: bpy.types.Object,
    collection: bpy.types.Collection,
) -> dict[str, dict[str, Any]]:
    segments: dict[str, dict[str, Any]] = {}

    # Keep the pelvis and rib cage independent.  A single rigid torso made the
    # victims read as mannequins and provided too little collision coverage for
    # debris loading.
    pelvis_start = bone_world_point(rig, "pelvis.R", "tail")
    pelvis_end = bone_world_point(rig, "pelvis.L", "tail")
    segments["pelvis"] = create_segment_proxy(
        collection,
        code,
        "pelvis",
        rig,
        "root",
        pelvis_start,
        pelvis_end,
        radius=0.15,
        mass=19.0,
        collision_shape="BOX",
        box_dimensions=(0.24, 0.22, (pelvis_end - pelvis_start).length + 0.10),
    )

    chest_start = bone_world_point(rig, "spine05", "head")
    chest_end = bone_world_point(rig, "spine01", "tail")
    chest_length = (chest_end - chest_start).length
    segments["chest"] = create_segment_proxy(
        collection,
        code,
        "chest",
        rig,
        "spine05",
        chest_start,
        chest_end,
        radius=0.16,
        mass=25.0,
        collision_shape="BOX",
        box_dimensions=(0.36, 0.25, chest_length + 0.07),
    )

    neck_start = bone_world_point(rig, "neck01", "head")
    neck_end = bone_world_point(rig, "head", "head")
    segments["neck"] = create_segment_proxy(
        collection,
        code,
        "neck",
        rig,
        "neck01",
        neck_start,
        neck_end,
        radius=0.073,
        mass=1.25,
    )

    head_start = bone_world_point(rig, "head", "head")
    head_end = bone_world_point(rig, "head", "tail")
    segments["head"] = create_segment_proxy(
        collection,
        code,
        "head",
        rig,
        "head",
        head_start,
        head_end,
        radius=0.115,
        mass=5.0,
    )

    for side in ("L", "R"):
        upper_arm_start = bone_world_point(rig, f"upperarm01.{side}", "head")
        upper_arm_end = bone_world_point(rig, f"upperarm02.{side}", "tail")
        segments[f"upperarm.{side}"] = create_segment_proxy(
            collection,
            code,
            f"upperarm_{side}",
            rig,
            f"upperarm01.{side}",
            upper_arm_start,
            upper_arm_end,
            radius=0.072,
            mass=2.2,
        )

        lower_arm_start = bone_world_point(rig, f"lowerarm01.{side}", "head")
        lower_arm_end = bone_world_point(rig, f"lowerarm02.{side}", "tail")
        segments[f"lowerarm.{side}"] = create_segment_proxy(
            collection,
            code,
            f"lowerarm_{side}",
            rig,
            f"lowerarm01.{side}",
            lower_arm_start,
            lower_arm_end,
            radius=0.062,
            mass=1.6,
        )

        hand_start = bone_world_point(rig, f"wrist.{side}", "head")
        hand_end = bone_world_point(rig, f"finger3-3.{side}", "tail")
        segments[f"hand.{side}"] = create_segment_proxy(
            collection,
            code,
            f"hand_{side}",
            rig,
            f"wrist.{side}",
            hand_start,
            hand_end,
            radius=0.058,
            mass=0.65,
        )

        thigh_start = bone_world_point(rig, f"upperleg01.{side}", "head")
        thigh_end = bone_world_point(rig, f"upperleg02.{side}", "tail")
        segments[f"thigh.{side}"] = create_segment_proxy(
            collection,
            code,
            f"thigh_{side}",
            rig,
            f"upperleg01.{side}",
            thigh_start,
            thigh_end,
            radius=0.105,
            mass=8.4,
        )

        shin_start = bone_world_point(rig, f"lowerleg01.{side}", "head")
        shin_end = bone_world_point(rig, f"lowerleg02.{side}", "tail")
        segments[f"shin.{side}"] = create_segment_proxy(
            collection,
            code,
            f"shin_{side}",
            rig,
            f"lowerleg01.{side}",
            shin_start,
            shin_end,
            radius=0.084,
            mass=4.2,
        )

        foot_start = bone_world_point(rig, f"foot.{side}", "head")
        foot_end = bone_world_point(rig, f"toe1-1.{side}", "tail")
        segments[f"foot.{side}"] = create_segment_proxy(
            collection,
            code,
            f"foot_{side}",
            rig,
            f"foot.{side}",
            foot_start,
            foot_end,
            radius=0.068,
            mass=1.1,
        )

    return segments


def joint_frame_quaternion(
    parent_proxy: bpy.types.Object,
    child_proxy: bpy.types.Object,
    hinge_reference: Vector | None = None,
) -> Quaternion:
    if hinge_reference is None:
        return parent_proxy.matrix_world.to_quaternion()

    parent_axis = parent_proxy.matrix_world.to_quaternion() @ Vector((0.0, 0.0, 1.0))
    child_axis = child_proxy.matrix_world.to_quaternion() @ Vector((0.0, 0.0, 1.0))
    hinge_axis = parent_axis.cross(child_axis)
    if hinge_axis.length < 0.04:
        hinge_axis = hinge_reference.copy()
    hinge_axis.normalize()
    z_axis = (parent_axis + child_axis).normalized()
    if abs(hinge_axis.dot(z_axis)) > 0.92:
        z_axis = parent_axis.normalized()
    y_axis = z_axis.cross(hinge_axis).normalized()
    z_axis = hinge_axis.cross(y_axis).normalized()
    # Matrix expects rows, while these vectors describe the desired world-space
    # basis columns for the Bullet constraint.  The previous non-transposed
    # matrix skewed elbow and knee axes.
    rotation = Matrix(
        (
            (hinge_axis.x, y_axis.x, z_axis.x),
            (hinge_axis.y, y_axis.y, z_axis.y),
            (hinge_axis.z, y_axis.z, z_axis.z),
        )
    ).transposed()
    return rotation.to_quaternion()


def add_generic_joint(
    collection: bpy.types.Collection,
    code: str,
    name: str,
    parent_proxy: bpy.types.Object,
    child_proxy: bpy.types.Object,
    location: Vector,
    angular_limits_degrees: tuple[
        tuple[float, float],
        tuple[float, float],
        tuple[float, float],
    ],
    hinge_reference: Vector | None = None,
    frame_quaternion: Quaternion | None = None,
) -> bpy.types.Object:
    bpy.ops.object.empty_add(type="PLAIN_AXES", location=location)
    joint = bpy.context.object
    joint.name = f"{RAGDOLL_PREFIX}{code}_JOINT_{name.upper()}"
    move_to_collection(joint, collection)
    joint.rotation_mode = "QUATERNION"
    joint.rotation_quaternion = (
        frame_quaternion
        if frame_quaternion is not None
        else joint_frame_quaternion(
            parent_proxy,
            child_proxy,
            hinge_reference=hinge_reference,
        )
    )
    activate(joint)
    bpy.ops.rigidbody.constraint_add()
    constraint = joint.rigid_body_constraint
    constraint.type = "GENERIC"
    constraint.object1 = parent_proxy
    constraint.object2 = child_proxy
    constraint.disable_collisions = True

    for axis in ("x", "y", "z"):
        setattr(constraint, f"use_limit_lin_{axis}", True)
        setattr(constraint, f"limit_lin_{axis}_lower", 0.0)
        setattr(constraint, f"limit_lin_{axis}_upper", 0.0)

    for axis, limits in zip(("x", "y", "z"), angular_limits_degrees):
        setattr(constraint, f"use_limit_ang_{axis}", True)
        setattr(constraint, f"limit_ang_{axis}_lower", math.radians(limits[0]))
        setattr(constraint, f"limit_ang_{axis}_upper", math.radians(limits[1]))

    joint.hide_render = True
    joint["physics_role"] = "anatomical_ragdoll_joint"
    joint["survivor_id"] = code
    return joint


def add_actor_joints(
    code: str,
    rig: bpy.types.Object,
    segments: dict[str, dict[str, Any]],
    collection: bpy.types.Collection,
) -> list[bpy.types.Object]:
    joints: list[bpy.types.Object] = []
    pelvis = segments["pelvis"]["object"]
    chest = segments["chest"]["object"]
    neck = segments["neck"]["object"]
    head = segments["head"]["object"]
    joints.append(
        add_generic_joint(
            collection,
            code,
            "spine",
            pelvis,
            chest,
            bone_world_point(rig, "spine05", "head"),
            ((-24.0, 24.0), (-18.0, 18.0), (-16.0, 16.0)),
            frame_quaternion=bone_world_matrix(rig, "spine05").to_quaternion(),
        )
    )
    joints.append(
        add_generic_joint(
            collection,
            code,
            "neck_base",
            chest,
            neck,
            bone_world_point(rig, "neck01", "head"),
            ((-15.0, 15.0), (-13.0, 13.0), (-16.0, 16.0)),
            frame_quaternion=bone_world_matrix(rig, "neck01").to_quaternion(),
        )
    )
    joints.append(
        add_generic_joint(
            collection,
            code,
            "head",
            neck,
            head,
            bone_world_point(rig, "head", "head"),
            ((-20.0, 20.0), (-18.0, 18.0), (-22.0, 22.0)),
            frame_quaternion=bone_world_matrix(rig, "head").to_quaternion(),
        )
    )

    rig_quaternion = rig.matrix_world.to_quaternion()
    arm_hinge = rig_quaternion @ Vector((0.0, 1.0, 0.0))
    knee_hinge = rig_quaternion @ Vector((1.0, 0.0, 0.0))

    for side in ("L", "R"):
        upper_arm = segments[f"upperarm.{side}"]["object"]
        lower_arm = segments[f"lowerarm.{side}"]["object"]
        hand = segments[f"hand.{side}"]["object"]
        thigh = segments[f"thigh.{side}"]["object"]
        shin = segments[f"shin.{side}"]["object"]
        foot = segments[f"foot.{side}"]["object"]

        joints.append(
            add_generic_joint(
                collection,
                code,
                f"shoulder_{side}",
                chest,
                upper_arm,
                bone_world_point(rig, f"upperarm01.{side}", "head"),
                ((-58.0, 58.0), (-48.0, 48.0), (-42.0, 42.0)),
                frame_quaternion=bone_world_matrix(
                    rig, f"upperarm01.{side}"
                ).to_quaternion(),
            )
        )
        joints.append(
            add_generic_joint(
                collection,
                code,
                f"elbow_{side}",
                upper_arm,
                lower_arm,
                bone_world_point(rig, f"lowerarm01.{side}", "head"),
                ((-8.0, 132.0), (-7.0, 7.0), (-8.0, 8.0)),
                hinge_reference=arm_hinge if side == "L" else -arm_hinge,
            )
        )
        joints.append(
            add_generic_joint(
                collection,
                code,
                f"wrist_{side}",
                lower_arm,
                hand,
                bone_world_point(rig, f"wrist.{side}", "head"),
                ((-28.0, 28.0), (-22.0, 22.0), (-24.0, 24.0)),
                frame_quaternion=bone_world_matrix(
                    rig, f"wrist.{side}"
                ).to_quaternion(),
            )
        )
        joints.append(
            add_generic_joint(
                collection,
                code,
                f"hip_{side}",
                pelvis,
                thigh,
                bone_world_point(rig, f"upperleg01.{side}", "head"),
                ((-62.0, 62.0), (-43.0, 43.0), (-42.0, 42.0)),
                frame_quaternion=bone_world_matrix(
                    rig, f"upperleg01.{side}"
                ).to_quaternion(),
            )
        )
        joints.append(
            add_generic_joint(
                collection,
                code,
                f"knee_{side}",
                thigh,
                shin,
                bone_world_point(rig, f"lowerleg01.{side}", "head"),
                ((-7.0, 142.0), (-7.0, 7.0), (-7.0, 7.0)),
                hinge_reference=knee_hinge,
            )
        )
        joints.append(
            add_generic_joint(
                collection,
                code,
                f"ankle_{side}",
                shin,
                foot,
                bone_world_point(rig, f"foot.{side}", "head"),
                ((-27.0, 27.0), (-18.0, 18.0), (-18.0, 18.0)),
                frame_quaternion=bone_world_matrix(
                    rig, f"foot.{side}"
                ).to_quaternion(),
            )
        )
    return joints


def add_environment_passive_bodies() -> list[bpy.types.Object]:
    passive_objects: list[bpy.types.Object] = []
    for collection_name in ("COLLISION_ARCH", "COLLISION_DEBRIS_STATIC"):
        collection = bpy.data.collections.get(collection_name)
        if collection is None:
            continue
        for obj in collection.objects:
            if obj.type != "MESH":
                continue
            add_rigid_body(
                obj,
                "PASSIVE",
                "MESH",
                friction=0.88,
                collision_layers=SCENARIO_COLLISION_LAYERS,
            )
            passive_objects.append(obj)
    print("PASSIVE_ENVIRONMENT_BODIES", len(passive_objects))
    return passive_objects


def add_debris_piece(
    collection: bpy.types.Collection,
    code: str,
    name: str,
    location: tuple[float, float, float],
    dimensions: tuple[float, float, float],
    rotation_degrees: tuple[float, float, float],
    material: bpy.types.Material,
    mass: float,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cube_add(
        size=1.0,
        location=location,
        rotation=tuple(math.radians(value) for value in rotation_degrees),
    )
    piece = bpy.context.object
    piece.name = f"{RAGDOLL_PREFIX}{code}_DEBRIS_{name}"
    piece.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    # Break the perfect cuboid silhouette before Bullet sees it.  With small,
    # independent corner offsets the mesh stays convex, looks chipped, and can
    # use the real hull instead of a school-project BOX collider.
    for vertex in piece.data.vertices:
        vertex.co.x *= RNG.uniform(0.86, 1.07)
        vertex.co.y *= RNG.uniform(0.84, 1.08)
        vertex.co.z *= RNG.uniform(0.80, 1.10)
    piece.data.update()
    move_to_collection(piece, collection)
    piece.data.materials.append(material)
    bevel = piece.modifiers.new("Impact-chipped edges", "BEVEL")
    bevel.width = min(dimensions) * RNG.uniform(0.045, 0.09)
    bevel.segments = 1
    piece["physics_role"] = "active_collapse_debris"
    piece["survivor_id"] = code
    piece["scenario_seed"] = SEED
    piece["debris_mass_kg"] = mass
    piece["spawn_height_m"] = location[2]
    add_rigid_body(
        piece,
        "ACTIVE",
        "CONVEX_HULL",
        mass=mass,
        friction=0.86,
        linear_damping=0.28,
        angular_damping=0.42,
        collision_layers=SCENARIO_COLLISION_LAYERS,
    )
    return piece


def create_collapse_debris(
    code: str,
    center_xy: tuple[float, float],
    floor_z: float,
    collection: bpy.types.Collection,
    material: bpy.types.Material,
) -> list[bpy.types.Object]:
    pieces: list[bpy.types.Object] = []
    primary_yaw = RNG.uniform(-18.0, 18.0)
    pieces.append(
        add_debris_piece(
            collection,
            code,
            "PRIMARY_SLAB",
            (
                center_xy[0] + RNG.uniform(-0.09, 0.09),
                center_xy[1] + RNG.uniform(-0.09, 0.09),
                floor_z + RNG.uniform(1.58, 1.76),
            ),
            (RNG.uniform(1.68, 1.92), RNG.uniform(0.52, 0.66), 0.18),
            (RNG.uniform(-8.0, 8.0), RNG.uniform(-8.0, 8.0), primary_yaw),
            material,
            mass=29.0,
        )
    )
    pieces.append(
        add_debris_piece(
            collection,
            code,
            "SECONDARY_SLAB",
            (
                center_xy[0] + RNG.uniform(-0.12, 0.12),
                center_xy[1] + RNG.uniform(-0.12, 0.12),
                floor_z + RNG.uniform(1.86, 2.04),
            ),
            (RNG.uniform(1.48, 1.72), RNG.uniform(0.48, 0.60), 0.16),
            (
                RNG.uniform(-10.0, 10.0),
                RNG.uniform(-10.0, 10.0),
                primary_yaw + RNG.uniform(72.0, 98.0),
            ),
            material,
            mass=24.0,
        )
    )
    pieces.append(
        add_debris_piece(
            collection,
            code,
            "BEAM",
            (
                center_xy[0] + RNG.uniform(-0.30, 0.30),
                center_xy[1] + RNG.uniform(-0.30, 0.30),
                floor_z + RNG.uniform(2.14, 2.34),
            ),
            (RNG.uniform(1.52, 1.82), 0.22, 0.20),
            (RNG.uniform(-14.0, 14.0), RNG.uniform(-12.0, 12.0), RNG.uniform(-40.0, 40.0)),
            material,
            mass=21.0,
        )
    )
    for index in range(10):
        size_x = RNG.uniform(0.18, 0.48)
        size_y = RNG.uniform(0.15, 0.42)
        size_z = RNG.uniform(0.10, 0.25)
        pieces.append(
            add_debris_piece(
                collection,
                code,
                f"CHUNK_{index:02d}",
                (
                    center_xy[0] + RNG.uniform(-0.78, 0.78),
                    center_xy[1] + RNG.uniform(-0.72, 0.72),
                    floor_z + 1.48 + index * 0.085 + RNG.uniform(0.0, 0.16),
                ),
                (size_x, size_y, size_z),
                (
                    RNG.uniform(-32.0, 32.0),
                    RNG.uniform(-32.0, 32.0),
                    RNG.uniform(-90.0, 90.0),
                ),
                material,
                mass=max(1.3, min(8.0, size_x * size_y * size_z * 1150.0)),
            )
        )
    return pieces


def object_world_bounds(obj: bpy.types.Object) -> tuple[Vector, Vector]:
    corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    low = Vector(
        (
            min(point.x for point in corners),
            min(point.y for point in corners),
            min(point.z for point in corners),
        )
    )
    high = Vector(
        (
            max(point.x for point in corners),
            max(point.y for point in corners),
            max(point.z for point in corners),
        )
    )
    return low, high


def validate_entrapment(
    code: str,
    segments: dict[str, dict[str, Any]],
    debris: list[bpy.types.Object],
) -> dict[str, Any]:
    # This is deliberately an acceptance gate, not an art-direction step.  It
    # reads the final Bullet state and rejects seeds whose rubble merely lands
    # around a victim.
    load_bearing_segments = {
        "pelvis",
        "chest",
        "thigh.L",
        "thigh.R",
        "shin.L",
        "shin.R",
        "upperarm.L",
        "upperarm.R",
    }
    contacts: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    for piece in debris:
        mass = float(piece.get("debris_mass_kg", 0.0))
        if mass < 12.0:
            continue
        debris_low, debris_high = object_world_bounds(piece)
        debris_center = (debris_low + debris_high) * 0.5
        for segment_name in load_bearing_segments:
            proxy = segments[segment_name]["object"]
            body_low, body_high = object_world_bounds(proxy)
            body_center = (body_low + body_high) * 0.5
            overlap_x = min(debris_high.x, body_high.x) - max(
                debris_low.x, body_low.x
            )
            overlap_y = min(debris_high.y, body_high.y) - max(
                debris_low.y, body_low.y
            )
            vertical_gap = debris_low.z - body_high.z
            separation_x = max(
                body_low.x - debris_high.x,
                debris_low.x - body_high.x,
                0.0,
            )
            separation_y = max(
                body_low.y - debris_high.y,
                debris_low.y - body_high.y,
                0.0,
            )
            candidates.append(
                {
                    "piece": piece.name,
                    "segment": segment_name,
                    "horizontal_separation_m": round(
                        math.hypot(separation_x, separation_y), 3
                    ),
                    "vertical_gap_m": round(vertical_gap, 3),
                    "piece_center": tuple(
                        round(value, 3) for value in debris_center
                    ),
                    "body_center": tuple(
                        round(value, 3) for value in body_center
                    ),
                }
            )
            if (
                overlap_x >= 0.045
                and overlap_y >= 0.045
                # Rotated convex slabs have conservative world AABBs.  Bullet
                # already prevents hull penetration, so projected overlap plus
                # a materially higher center is the reliable "under load"
                # signal even when the AABB vertical overlap looks deep.
                and vertical_gap <= 0.11
                and debris_center.z >= body_center.z + 0.06
            ):
                contacts.append(
                    {
                        "piece": piece.name,
                        "mass_kg": round(mass, 2),
                        "segment": segment_name,
                        "overlap_xy_m": (
                            round(overlap_x, 3),
                            round(overlap_y, 3),
                        ),
                        "vertical_gap_m": round(vertical_gap, 3),
                    }
                )

    heavy_pieces = sorted({contact["piece"] for contact in contacts})
    report = {
        "survivor": code,
        "passed": bool(contacts),
        "heavy_piece_count": len(heavy_pieces),
        "heavy_pieces": heavy_pieces,
        "contacts": contacts,
        "nearest_candidates": sorted(
            candidates,
            key=lambda candidate: (
                candidate["horizontal_separation_m"]
                + abs(candidate["vertical_gap_m"])
            ),
        )[:6],
    }
    print(f"RAGDOLL_ENTRAPMENT_{code}", report)
    return report


def head_occlusion_score(
    head_proxy: bpy.types.Object,
    debris: list[bpy.types.Object],
) -> float:
    head_low, head_high = object_world_bounds(head_proxy)
    head_center = (head_low + head_high) * 0.5
    score = 0.0
    for piece in debris:
        piece_low, piece_high = object_world_bounds(piece)
        piece_center = (piece_low + piece_high) * 0.5
        if piece_center.z <= head_center.z:
            continue
        overlap_x = max(
            0.0, min(piece_high.x, head_high.x) - max(piece_low.x, head_low.x)
        )
        overlap_y = max(
            0.0, min(piece_high.y, head_high.y) - max(piece_low.y, head_low.y)
        )
        score += overlap_x * overlap_y
    return score


def simulate_until_stable(
    active_objects: list[bpy.types.Object],
    animation_actors: list[
        tuple[str, bpy.types.Object, dict[str, dict[str, Any]]]
    ],
    end_frame: int = 720,
    sample_window: int = 60,
) -> dict[str, Any]:
    scene = bpy.context.scene
    if scene.rigidbody_world is None:
        bpy.ops.rigidbody.world_add()
    world = scene.rigidbody_world
    world.substeps_per_frame = 20
    world.solver_iterations = 40
    world.time_scale = 1.0
    world.point_cache.frame_start = 1
    world.point_cache.frame_end = end_frame
    scene.frame_start = 1
    scene.frame_end = end_frame

    previous: dict[str, Vector] = {}
    previous_rotation: dict[str, Quaternion] = {}
    movement: dict[str, float] = {obj.name: 0.0 for obj in active_objects}
    angular_movement: dict[str, float] = {
        obj.name: 0.0 for obj in active_objects
    }
    final_steps: dict[str, list[float]] = {obj.name: [] for obj in active_objects}
    final_angular_steps: dict[str, list[float]] = {
        obj.name: [] for obj in active_objects
    }
    scene.frame_set(1)
    for frame in range(1, end_frame + 1):
        if frame == end_frame - 240:
            # Bodies begin fully awake so gravity always acts.  Once the
            # collapse has run long enough, allow Bullet to sleep contact
            # stacks that would otherwise jitter indefinitely under debris.
            for obj in active_objects:
                rigid_body = obj.rigid_body
                if rigid_body is None:
                    continue
                rigid_body.linear_damping = 0.985
                rigid_body.angular_damping = 0.985
                rigid_body.use_deactivation = True
                rigid_body.deactivate_linear_velocity = 0.12
                rigid_body.deactivate_angular_velocity = 0.18
        scene.frame_set(frame)
        if frame == 1 or frame == end_frame or frame % 4 == 0:
            for code, rig, segments in animation_actors:
                apply_ragdoll_to_armature(
                    code,
                    rig,
                    segments,
                    log=False,
                )
                keyframe_ragdoll_pose(rig, segments, frame)
        if frame >= end_frame - sample_window:
            for obj in active_objects:
                location = obj.matrix_world.translation.copy()
                rotation = obj.matrix_world.to_quaternion().normalized()
                if obj.name in previous:
                    step = (location - previous[obj.name]).length
                    angular_step = previous_rotation[obj.name].rotation_difference(
                        rotation
                    ).angle
                    angular_step = min(angular_step, math.tau - angular_step)
                    movement[obj.name] = max(movement[obj.name], step)
                    angular_movement[obj.name] = max(
                        angular_movement[obj.name], angular_step
                    )
                    if frame >= end_frame - 8:
                        final_steps[obj.name].append(step)
                        final_angular_steps[obj.name].append(angular_step)
                previous[obj.name] = location
                previous_rotation[obj.name] = rotation

    max_window_step = max(movement.values(), default=0.0)
    max_window_angular_step = max(angular_movement.values(), default=0.0)
    final_movement = {
        name: max(steps, default=0.0) for name, steps in final_steps.items()
    }
    final_angular_movement = {
        name: max(steps, default=0.0)
        for name, steps in final_angular_steps.items()
    }
    max_step = max(final_movement.values(), default=0.0)
    max_angular_step = max(final_angular_movement.values(), default=0.0)
    unstable = {
        name: {
            "translation_m": final_movement[name],
            "rotation_rad": final_angular_movement[name],
        }
        for name in final_movement
        if final_movement[name] > 0.003
        or final_angular_movement[name] > 0.012
    }
    final_locations = {
        obj.name: tuple(float(value) for value in obj.matrix_world.translation)
        for obj in active_objects
        if obj.name in unstable
    }
    report = {
        "frame": end_frame,
        "max_late_step_m": max_step,
        "max_late_rotation_rad": max_angular_step,
        "max_window_step_m": max_window_step,
        "max_window_rotation_rad": max_window_angular_step,
        "unstable_objects": unstable,
        "unstable_final_locations": final_locations,
        "active_count": len(active_objects),
    }
    print(
        "RAGDOLL_PHYSICS_SETTLE",
        {
            **report,
            "max_late_step_m": round(max_step, 6),
            "max_late_rotation_rad": round(max_angular_step, 6),
            "max_window_step_m": round(max_window_step, 6),
            "max_window_rotation_rad": round(max_window_angular_step, 6),
            "unstable_objects": {
                name: {
                    "translation_m": round(value["translation_m"], 6),
                    "rotation_rad": round(value["rotation_rad"], 6),
                }
                for name, value in unstable.items()
            },
            "unstable_final_locations": {
                name: tuple(round(value, 3) for value in location)
                for name, location in final_locations.items()
            },
        },
    )
    escaped = {
        obj.name: tuple(float(value) for value in obj.matrix_world.translation)
        for obj in active_objects
        if obj.matrix_world.translation.z < -1.0
        or obj.matrix_world.translation.z > 4.0
    }
    report["contact_jitter_baked"] = bool(unstable)
    report["escaped_objects"] = escaped
    if max_step > 0.012 or max_angular_step > 0.035 or escaped:
        raise RuntimeError(f"Ragdoll scenario is not bakeable: {report}")
    return report


def apply_ragdoll_to_armature(
    code: str,
    rig: bpy.types.Object,
    segments: dict[str, dict[str, Any]],
    log: bool = True,
) -> float:
    order = (
        "pelvis",
        "chest",
        "thigh.L",
        "shin.L",
        "foot.L",
        "thigh.R",
        "shin.R",
        "foot.R",
        "upperarm.L",
        "lowerarm.L",
        "hand.L",
        "upperarm.R",
        "lowerarm.R",
        "hand.R",
        "neck",
        "head",
    )
    max_matrix_error = 0.0
    for name in order:
        segment = segments[name]
        desired_world = segment["object"].matrix_world @ segment["driver_offset"]
        bone = rig.pose.bones[segment["driver_bone"]]
        bone.matrix = rig.matrix_world.inverted() @ desired_world
        bpy.context.view_layer.update()
        actual_world = rig.matrix_world @ bone.matrix
        error = sum(
            abs(actual_world[row][column] - desired_world[row][column])
            for row in range(4)
            for column in range(4)
        )
        max_matrix_error = max(max_matrix_error, error)

    rig["ragdoll_baked"] = True
    rig["ragdoll_baked_frame"] = bpy.context.scene.frame_current
    rig["ragdoll_transfer_max_matrix_error"] = max_matrix_error
    if log:
        print(f"RAGDOLL_TRANSFER_{code}", round(max_matrix_error, 8))
    return max_matrix_error


def keyframe_ragdoll_pose(
    rig: bpy.types.Object,
    segments: dict[str, dict[str, Any]],
    frame: int,
) -> None:
    keyed_bones = {
        segment["driver_bone"] for segment in segments.values()
    }
    for bone_name in keyed_bones:
        bone = rig.pose.bones[bone_name]
        bone.rotation_mode = "QUATERNION"
        bone.keyframe_insert(data_path="location", frame=frame, group="Ragdoll")
        bone.keyframe_insert(
            data_path="rotation_quaternion",
            frame=frame,
            group="Ragdoll",
        )
        bone.keyframe_insert(data_path="scale", frame=frame, group="Ragdoll")


def freeze_object(obj: bpy.types.Object) -> None:
    matrix = obj.matrix_world.copy()
    activate(obj)
    if obj.rigid_body is not None:
        bpy.ops.rigidbody.object_remove()
    obj.matrix_world = matrix
    obj["physics_baked_static"] = True
    obj["physics_baked_frame"] = bpy.context.scene.frame_current


def remove_physics(
    proxy_segments: list[bpy.types.Object],
    joints: list[bpy.types.Object],
    debris: list[bpy.types.Object],
    passive_environment: list[bpy.types.Object],
) -> None:
    for piece in debris:
        freeze_object(piece)
    for obj in proxy_segments:
        if obj.rigid_body is not None:
            activate(obj)
            bpy.ops.rigidbody.object_remove()
    for obj in passive_environment:
        if obj.rigid_body is not None:
            activate(obj)
            bpy.ops.rigidbody.object_remove()
    for joint in joints:
        remove_object(joint)
    for proxy in proxy_segments:
        remove_object(proxy)
    if bpy.context.scene.rigidbody_world is not None:
        bpy.ops.rigidbody.world_remove()


def look_at(obj: bpy.types.Object, target: Vector) -> None:
    obj.rotation_euler = (target - obj.location).to_track_quat("-Z", "Y").to_euler()


def add_camera(
    collection: bpy.types.Collection,
    name: str,
    location: tuple[float, float, float],
    target: Vector,
    lens: float,
) -> bpy.types.Object:
    data = bpy.data.cameras.new(f"{name}_DATA")
    camera = bpy.data.objects.new(name, data)
    collection.objects.link(camera)
    camera.location = location
    data.lens = lens
    data.sensor_width = 32.0
    look_at(camera, target)
    return camera


def add_spot_light(
    collection: bpy.types.Collection,
    name: str,
    location: tuple[float, float, float],
    target: Vector,
    energy: float,
) -> bpy.types.Object:
    data = bpy.data.lights.new(f"{name}_DATA", "SPOT")
    light = bpy.data.objects.new(name, data)
    collection.objects.link(light)
    light.location = location
    data.energy = energy
    data.color = (1.0, 0.79, 0.56)
    data.spot_size = math.radians(58.0)
    data.spot_blend = 0.58
    data.shadow_soft_size = 0.11
    look_at(light, target)
    return light


def injury_material() -> bpy.types.Material:
    material = bpy.data.materials.get("MAT_PULSO_NON_GRAPHIC_BLOOD")
    if material is None:
        material = bpy.data.materials.new("MAT_PULSO_NON_GRAPHIC_BLOOD")
        material.diffuse_color = (0.19, 0.006, 0.008, 1.0)
        material.use_nodes = True
        principled = material.node_tree.nodes.get("Principled BSDF")
        if principled is not None:
            principled.inputs["Base Color"].default_value = (
                0.19,
                0.006,
                0.008,
                1.0,
            )
            principled.inputs["Roughness"].default_value = 0.58
    return material


def add_irregular_disc(
    collection: bpy.types.Collection,
    name: str,
    center: Vector,
    normal: Vector,
    radius: float,
    material: bpy.types.Material,
    vertex_count: int = 13,
) -> bpy.types.Object:
    normal = normal.normalized()
    reference = (
        Vector((0.0, 0.0, 1.0))
        if abs(normal.z) < 0.86
        else Vector((1.0, 0.0, 0.0))
    )
    tangent = normal.cross(reference).normalized()
    bitangent = normal.cross(tangent).normalized()
    vertices = [center + normal * 0.002]
    for index in range(vertex_count):
        angle = math.tau * index / vertex_count
        local_radius = radius * RNG.uniform(0.72, 1.12)
        vertices.append(
            center
            + tangent * math.cos(angle) * local_radius
            + bitangent * math.sin(angle) * local_radius
            + normal * 0.002
        )
    faces = [
        (0, index + 1, ((index + 1) % vertex_count) + 1)
        for index in range(vertex_count)
    ]
    mesh = bpy.data.meshes.new(f"{name}_MESH")
    mesh.from_pydata(vertices, [], faces)
    mesh.materials.append(material)
    marker = bpy.data.objects.new(name, mesh)
    collection.objects.link(marker)
    marker["clinical_cue"] = "non_graphic_blood_evidence_near_head"
    marker["scenario_seed"] = SEED
    return marker


def add_head_injury(
    collection: bpy.types.Collection,
    code: str,
    head_proxy: bpy.types.Object,
    camera_location: tuple[float, float, float],
    floor_z: float,
) -> list[bpy.types.Object]:
    material = injury_material()
    head_center = head_proxy.matrix_world.translation.copy()
    camera_direction = Vector(camera_location) - head_center
    camera_direction.z = 0.0
    if camera_direction.length < 0.001:
        camera_direction = Vector((1.0, 0.0, 0.0))
    camera_direction.normalize()
    pool_center = Vector(
        (
            head_center.x + RNG.uniform(-0.025, 0.025),
            head_center.y + RNG.uniform(-0.025, 0.025),
            floor_z + 0.004,
        )
    )
    pool = add_irregular_disc(
        collection,
        f"{RAGDOLL_PREFIX}{code}_HEAD_BLOOD_STAIN",
        pool_center,
        Vector((0.0, 0.0, 1.0)),
        radius=0.105,
        material=material,
        vertex_count=17,
    )
    trail = add_irregular_disc(
        collection,
        f"{RAGDOLL_PREFIX}{code}_BLOOD_TRAIL",
        pool_center + camera_direction * 0.085 + Vector((0.0, 0.0, 0.0005)),
        Vector((0.0, 0.0, 1.0)),
        radius=0.045,
        material=material,
        vertex_count=11,
    )
    return [pool, trail]


def render(camera: bpy.types.Object, filename: str, exposure: float) -> None:
    scene = bpy.context.scene
    scene.camera = camera
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = exposure
    scene.render.filepath = str(RENDER_DIR / filename)
    bpy.ops.render.render(write_still=True)


def body_center(meshes: list[bpy.types.Object]) -> Vector:
    low, high = evaluated_bounds(meshes)
    return (low + high) * 0.5


clean_previous_ragdoll_pass()
visual_collection = new_collection(
    "VISUAL_RAGDOLL",
    "Physics-first victims and collapse debris retained in the final scenario",
)
physics_collection = new_collection(
    "PHYSICS_RAGDOLL",
    "Temporary articulated proxies and anatomical joints removed after baking",
)

rig_a = actor_rig("A")
rig_b = actor_rig("B")
meshes_a = actor_meshes("A", rig_a)
meshes_b = actor_meshes("B", rig_b)

reset_actor_for_drop(
    "A",
    rig_a,
    meshes_a,
    location_xy=(-4.62, -1.18),
    floor_z=0.0,
    yaw_degrees=RNG.uniform(-35.0, 35.0),
    tilt_degrees=random_lateral_collapse_tilt(),
    drop_height=0.28,
)
reset_actor_for_drop(
    "B",
    rig_b,
    meshes_b,
    location_xy=(8.25, -1.63),
    floor_z=-0.15,
    yaw_degrees=RNG.uniform(-45.0, 45.0),
    tilt_degrees=random_lateral_collapse_tilt(),
    drop_height=0.32,
)

segments_a = make_actor_ragdoll("A", rig_a, physics_collection)
segments_b = make_actor_ragdoll("B", rig_b, physics_collection)
joints_a = add_actor_joints("A", rig_a, segments_a, physics_collection)
joints_b = add_actor_joints("B", rig_b, segments_b, physics_collection)

rubble_material = bpy.data.materials.get("MAT_BLOCK_FRAGMENT")
if rubble_material is None:
    raise RuntimeError("Expected packed rubble material MAT_BLOCK_FRAGMENT")

debris_a = create_collapse_debris(
    "A",
    (-4.62, -1.18),
    floor_z=0.0,
    collection=visual_collection,
    material=rubble_material,
)
debris_b = create_collapse_debris(
    "B",
    (8.25, -1.63),
    floor_z=-0.15,
    collection=visual_collection,
    material=rubble_material,
)
passive_environment = add_environment_passive_bodies()

proxy_objects = [
    segment["object"] for segment in (*segments_a.values(), *segments_b.values())
]
debris_objects = debris_a + debris_b
physics_report = simulate_until_stable(
    proxy_objects + debris_objects,
    animation_actors=[
        ("A", rig_a, segments_a),
        ("B", rig_b, segments_b),
    ],
    end_frame=720,
)
entrapment_a = validate_entrapment("A", segments_a, debris_a)
entrapment_b = validate_entrapment("B", segments_b, debris_b)
if not entrapment_a["passed"] or not entrapment_b["passed"]:
    raise RuntimeError(
        f"Seed {SEED} rejected: entrapment A={entrapment_a['passed']} "
        f"B={entrapment_b['passed']}"
    )

transfer_error_a = apply_ragdoll_to_armature("A", rig_a, segments_a)
transfer_error_b = apply_ragdoll_to_armature("B", rig_b, segments_b)
if max(transfer_error_a, transfer_error_b) > 0.001:
    raise RuntimeError(
        f"Ragdoll-to-armature transfer error: A={transfer_error_a}, B={transfer_error_b}"
    )

low_a, high_a = evaluated_bounds(meshes_a)
low_b, high_b = evaluated_bounds(meshes_b)
center_a = (low_a + high_a) * 0.5
center_b = (low_b + high_b) * 0.5
print(
    "RAGDOLL_FINAL_BOUNDS",
    {
        "A": {
            "min": tuple(round(value, 4) for value in low_a),
            "max": tuple(round(value, 4) for value in high_a),
        },
        "B": {
            "min": tuple(round(value, 4) for value in low_b),
            "max": tuple(round(value, 4) for value in high_b),
        },
    },
)
if low_a.z < -0.025 or low_b.z < -0.175:
    raise RuntimeError(f"Ragdoll body penetrated floor: A={low_a.z}, B={low_b.z}")

neck_gap_a = (
    bone_world_point(rig_a, "neck03", "tail")
    - bone_world_point(rig_a, "head", "head")
).length
neck_gap_b = (
    bone_world_point(rig_b, "neck03", "tail")
    - bone_world_point(rig_b, "head", "head")
).length
print(
    "RAGDOLL_NECK_CONTINUITY",
    {"A_m": round(neck_gap_a, 6), "B_m": round(neck_gap_b, 6)},
)
if max(neck_gap_a, neck_gap_b) > 0.02:
    raise RuntimeError(
        f"Ragdoll neck discontinuity: A={neck_gap_a}, B={neck_gap_b}"
    )

camera_a_position = (-5.63, -2.77, 1.43)
camera_b_position = tuple(center_b + Vector((1.55, 1.75, 1.50)))
camera_a = add_camera(
    visual_collection,
    f"{RAGDOLL_PREFIX}CAM_A",
    camera_a_position,
    center_a,
    lens=28.0,
)
camera_b = add_camera(
    visual_collection,
    f"{RAGDOLL_PREFIX}CAM_B",
    camera_b_position,
    center_b,
    lens=31.0,
)
light_a = add_spot_light(
    visual_collection,
    f"{RAGDOLL_PREFIX}LIGHT_A",
    (-5.52, -2.45, 1.20),
    center_a,
    energy=240.0,
)
light_b = add_spot_light(
    visual_collection,
    f"{RAGDOLL_PREFIX}LIGHT_B",
    (9.32, -0.62, 1.18),
    center_b,
    energy=175.0,
)

injury_code = min(
    ("A", "B"),
    key=lambda code: head_occlusion_score(
        segments_a["head"]["object"] if code == "A" else segments_b["head"]["object"],
        debris_a if code == "A" else debris_b,
    ),
)

scene = bpy.context.scene
scene.render.engine = "BLENDER_EEVEE"
scene.render.resolution_x = 1280
scene.render.resolution_y = 720
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGBA"
scene.render.image_settings.color_depth = "8"
scene.render.film_transparent = False
scene.world.color = (0.005, 0.006, 0.009)
scene.frame_set(int(physics_report["frame"]))
scene["pulso_scenario_type"] = "physics_first_articulated_ragdoll"
scene["pulso_scenario_seed"] = SEED
scene["pulso_final_frame"] = int(physics_report["frame"])
scene["pulso_pose_authorship"] = "physics_outcome_not_hand_authored"
scene["pulso_ragdoll_transfer_error_A"] = transfer_error_a
scene["pulso_ragdoll_transfer_error_B"] = transfer_error_b
scene["pulso_physics_settle_max_step_m"] = physics_report["max_late_step_m"]
scene["pulso_physics_settle_max_rotation_rad"] = physics_report[
    "max_late_rotation_rad"
]
scene["pulso_entrapment_heavy_pieces_A"] = entrapment_a["heavy_piece_count"]
scene["pulso_entrapment_heavy_pieces_B"] = entrapment_b["heavy_piece_count"]
scene["pulso_injury_case"] = (
    f"{injury_code}_non_graphic_head_blood_cue"
)

# Preserve the actual falling-rubble run with articulated human keyframes.  The
# companion final file below is intentionally static for simulator ingestion.
bpy.ops.file.pack_all()
bpy.ops.wm.save_as_mainfile(filepath=str(SIMULATION_BLEND))

# Convert the accepted final physics frame into a clean static deliverable.
rig_a.animation_data_clear()
rig_b.animation_data_clear()
transfer_error_a = apply_ragdoll_to_armature("A", rig_a, segments_a)
transfer_error_b = apply_ragdoll_to_armature("B", rig_b, segments_b)
injury_markers = add_head_injury(
    visual_collection,
    injury_code,
    (
        segments_a["head"]["object"]
        if injury_code == "A"
        else segments_b["head"]["object"]
    ),
    tuple(camera_a.location if injury_code == "A" else camera_b.location),
    floor_z=0.0 if injury_code == "A" else -0.15,
)
remove_physics(
    proxy_objects,
    joints_a + joints_b,
    debris_objects,
    passive_environment,
)

bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT_BLEND))

light_a.hide_render = False
light_b.hide_render = True
render(camera_a, f"pulso_ragdoll_seed_{SEED}_A.png", exposure=-0.45)
light_a.hide_render = True
light_b.hide_render = False
render(camera_b, f"pulso_ragdoll_seed_{SEED}_B.png", exposure=-1.25)
light_a.hide_render = True
light_b.hide_render = True
bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT_BLEND))

print(
    "PULSO_RAGDOLL_BUILD_OK",
    {
        "seed": SEED,
        "blend": str(OUTPUT_BLEND),
        "simulation_blend": str(SIMULATION_BLEND),
        "renders": [
            str(RENDER_DIR / f"pulso_ragdoll_seed_{SEED}_A.png"),
            str(RENDER_DIR / f"pulso_ragdoll_seed_{SEED}_B.png"),
        ],
        "physics": physics_report,
        "entrapment": {"A": entrapment_a, "B": entrapment_b},
        "transfer_error": {"A": transfer_error_a, "B": transfer_error_b},
        "debris_count": len(debris_objects),
        "injury_markers": [marker.name for marker in injury_markers],
        "injury_survivor": injury_code,
    },
)
