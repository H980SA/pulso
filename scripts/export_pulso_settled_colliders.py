"""Export the accepted settled survivors and collapse debris for Gazebo.

Blender opens the source checkpoints itself, so the accepted files remain
read-only inputs and this command works from a factory-startup process.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path

import bpy
from mathutils import Matrix


PROJECT = Path(__file__).resolve().parents[1]
DEFAULT_SIMULATION = (
    PROJECT / "art/current/ragdoll/canonical/pulso_ragdoll_canonical_simulation.blend"
)
DEFAULT_CANONICAL = PROJECT / "art/current/ragdoll/canonical/pulso_ragdoll_canonical.blend"
DEFAULT_NAVIGABLE = PROJECT / "art/current/ragdoll/navigable/pulso_ragdoll_navigable.blend"
DEFAULT_OUTPUT = (
    PROJECT / "sim/ros2_ws/src/pulso_gazebo/models/pulso_settled_occupants"
)


PROXY_PATTERN = re.compile(r"^PULSO_RAGDOLL_([AB])_(?!DEBRIS_)(?!JOINT_).+$")
DEBRIS_PATTERN = re.compile(
    r"^PULSO_RAGDOLL_([AB])_DEBRIS_"
    r"(?:BEAM|PRIMARY_SLAB|SECONDARY_SLAB|CHUNK_[0-9]{2})$"
)


def parse_args() -> argparse.Namespace:
    raw = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--simulation", type=Path, default=DEFAULT_SIMULATION)
    parser.add_argument("--canonical", type=Path, default=DEFAULT_CANONICAL)
    parser.add_argument("--navigable", type=Path, default=DEFAULT_NAVIGABLE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args(raw)


def rounded(values, digits: int = 8) -> list[float]:
    return [round(float(value), digits) for value in values]


def matrix_values(matrix: Matrix) -> list[list[float]]:
    return [rounded(row) for row in matrix]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def project_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(PROJECT))
    except ValueError:
        return str(resolved)


def open_blend(path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(path)
    bpy.ops.wm.open_mainfile(filepath=str(path.resolve()))
    bpy.context.view_layer.update()


def bone_world_matrix(rig: bpy.types.Object, bone_name: str) -> Matrix:
    return rig.matrix_world @ rig.pose.bones[bone_name].matrix


def quaternion_to_rpy(quaternion) -> tuple[float, float, float]:
    w, x, y, z = (float(value) for value in quaternion)
    roll = math.atan2(2.0 * (w * x + y * z), 1.0 - 2.0 * (x * x + y * y))
    pitch_term = max(-1.0, min(1.0, 2.0 * (w * y - z * x)))
    pitch = math.asin(pitch_term)
    yaw = math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))
    return roll, pitch, yaw


def pose_record(matrix: Matrix) -> dict:
    location, rotation, scale = matrix.decompose()
    return {
        "xyz_m": rounded(location),
        "quaternion_wxyz": rounded(rotation),
        "rpy_rad": rounded(quaternion_to_rpy(rotation)),
        "scale": rounded(scale),
        "matrix": matrix_values(matrix),
    }


def sdf_pose(matrix: Matrix) -> str:
    record = pose_record(matrix)
    values = [*record["xyz_m"], *record["rpy_rad"]]
    return " ".join(f"{value:.9g}" for value in values)


def recover_survivor_proxies(simulation: Path) -> tuple[list[dict], dict[str, Matrix]]:
    open_blend(simulation)
    scene = bpy.context.scene
    final_frame = int(scene.get("pulso_final_frame", scene.frame_end))
    scene.frame_set(scene.frame_start)
    bpy.context.view_layer.update()

    offsets = {}
    dimensions = {}
    physics = {}
    for obj in sorted(bpy.data.objects, key=lambda item: item.name):
        match = PROXY_PATTERN.match(obj.name)
        if not match or obj.type != "MESH" or obj.rigid_body is None:
            continue
        survivor = match.group(1)
        driver_bone = str(obj.get("driver_bone", ""))
        if not driver_bone:
            raise RuntimeError(f"Missing driver bone on {obj.name}")
        rig = bpy.data.objects[f"PULSO_SURVIVOR_{survivor}_RIG"]
        offsets[obj.name] = obj.matrix_world.inverted() @ bone_world_matrix(rig, driver_bone)
        dimensions[obj.name] = tuple(float(value) for value in obj.dimensions)
        physics[obj.name] = {
            "survivor_id": survivor,
            "driver_bone": driver_bone,
            "shape": obj.rigid_body.collision_shape,
            "mass_kg": float(obj.rigid_body.mass),
            "friction": float(obj.rigid_body.friction),
            "restitution": float(obj.rigid_body.restitution),
            "linear_damping": float(obj.rigid_body.linear_damping),
            "angular_damping": float(obj.rigid_body.angular_damping),
        }

    scene.frame_set(final_frame)
    bpy.context.view_layer.update()
    proxies = []
    final_bones = {}
    for name in sorted(offsets):
        item = physics[name]
        rig = bpy.data.objects[f"PULSO_SURVIVOR_{item['survivor_id']}_RIG"]
        final_bone = bone_world_matrix(rig, item["driver_bone"])
        final_matrix = final_bone @ offsets[name].inverted()
        final_bones[name] = final_bone.copy()
        size_x, size_y, size_z = dimensions[name]
        if item["shape"] == "CAPSULE":
            radius = (size_x + size_y) * 0.25
            geometry = {
                "type": "capsule",
                "radius_m": round(radius, 8),
                "cylinder_length_m": round(max(0.0, size_z - 2.0 * radius), 8),
                "overall_dimensions_m": rounded(dimensions[name]),
            }
        elif item["shape"] == "BOX":
            geometry = {"type": "box", "size_m": rounded(dimensions[name])}
        else:
            raise RuntimeError(f"Unsupported survivor proxy shape {item['shape']} on {name}")
        proxies.append(
            {
                "name": name,
                **item,
                "geometry": geometry,
                "pose": pose_record(final_matrix),
            }
        )
    if len(proxies) != 32:
        raise RuntimeError(f"Expected 32 survivor segments, recovered {len(proxies)}")
    return proxies, final_bones


def debris_transform_map(blend: Path) -> dict[str, Matrix]:
    open_blend(blend)
    return {
        obj.name: obj.matrix_world.copy()
        for obj in bpy.data.objects
        if obj.type == "MESH" and DEBRIS_PATTERN.match(obj.name)
    }


def recover_debris_mass(simulation: Path) -> dict[str, dict]:
    open_blend(simulation)
    result = {}
    for obj in bpy.data.objects:
        if obj.type != "MESH" or not DEBRIS_PATTERN.match(obj.name):
            continue
        if obj.rigid_body is None:
            raise RuntimeError(f"Missing simulation rigid body on {obj.name}")
        result[obj.name] = {
            "mass_kg": round(float(obj.rigid_body.mass), 8),
            "friction": round(float(obj.rigid_body.friction), 8),
            "restitution": round(float(obj.rigid_body.restitution), 8),
            "source_collision_shape": obj.rigid_body.collision_shape,
        }
    return result


def write_local_obj(obj: bpy.types.Object, path: Path) -> dict:
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    try:
        mesh.calc_loop_triangles()
        lines = [f"o {obj.name}"]
        for vertex in mesh.vertices:
            lines.append("v " + " ".join(f"{value:.9g}" for value in vertex.co))
        # DART's ODE mesh adapter rejects (and in Fortress 6.18 can crash on)
        # an OBJ whose imported vertex count has no matching normals. Emit one
        # local-space normal per source vertex and bind it explicitly.
        for vertex in mesh.vertices:
            lines.append("vn " + " ".join(f"{value:.9g}" for value in vertex.normal))
        for triangle in mesh.loop_triangles:
            indices = [index + 1 for index in triangle.vertices]
            lines.append("f " + " ".join(f"{index}//{index}" for index in indices))
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        bounds_min = [min(vertex.co[axis] for vertex in mesh.vertices) for axis in range(3)]
        bounds_max = [max(vertex.co[axis] for vertex in mesh.vertices) for axis in range(3)]
        return {
            "vertices": len(mesh.vertices),
            "triangles": len(mesh.loop_triangles),
            "local_bounds_min_m": rounded(bounds_min),
            "local_bounds_max_m": rounded(bounds_max),
        }
    finally:
        evaluated.to_mesh_clear()


def validate_survivor_pose(
    proxies: list[dict], final_bones: dict[str, Matrix]
) -> dict:
    errors = {}
    for proxy in proxies:
        name = proxy["name"]
        rig = bpy.data.objects[f"PULSO_SURVIVOR_{proxy['survivor_id']}_RIG"]
        actual = bone_world_matrix(rig, proxy["driver_bone"])
        expected = final_bones[name]
        errors[name] = max(
            abs(float(actual[row][column] - expected[row][column]))
            for row in range(4)
            for column in range(4)
        )
    return {
        "max_bone_matrix_error": max(errors.values()),
        "per_proxy_max_error": {name: round(value, 12) for name, value in errors.items()},
    }


def safe_name(name: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", name.lower()).strip("_")


def collision_xml(name: str, pose: str, geometry: str, friction: float) -> str:
    return f"""      <collision name='{safe_name(name)}'>
        <pose>{pose}</pose>
        <geometry>{geometry}</geometry>
        <surface><friction><ode><mu>{friction:.6g}</mu><mu2>{friction:.6g}</mu2></ode></friction></surface>
      </collision>"""


def write_sdf(output: Path, proxies: list[dict], debris: list[dict]) -> Path:
    collisions = []
    for proxy in proxies:
        geometry = proxy["geometry"]
        if geometry["type"] == "box":
            size = " ".join(str(value) for value in geometry["size_m"])
            xml = f"<box><size>{size}</size></box>"
        else:
            xml = (
                f"<capsule><radius>{geometry['radius_m']}</radius>"
                f"<length>{geometry['cylinder_length_m']}</length></capsule>"
            )
        collisions.append(
            collision_xml(proxy["name"], sdf_pose(Matrix(proxy["pose"]["matrix"])), xml, proxy["friction"])
        )
    for piece in debris:
        mesh = piece["mesh"]
        scale = " ".join(str(value) for value in piece["pose"]["scale"])
        geometry = (
            f"<mesh><uri>{mesh['path']}</uri>"
            f"<scale>{scale}</scale></mesh>"
        )
        collisions.append(
            collision_xml(piece["name"], sdf_pose(Matrix(piece["pose"]["matrix"])), geometry, piece["friction"])
        )
    sdf = """<?xml version="1.0"?>
<sdf version="1.9">
  <model name='pulso_settled_occupants'>
    <static>true</static>
    <link name='settled_collision'>
""" + "\n".join(collisions) + """
    </link>
  </model>
</sdf>
"""
    path = output / "model.sdf"
    path.write_text(sdf, encoding="utf-8")
    return path


def main() -> None:
    args = parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    mesh_root = args.output / "meshes"
    mesh_root.mkdir(exist_ok=True)
    for stale in mesh_root.glob("pulso_ragdoll_*_debris_*.obj"):
        stale.unlink()

    proxies, final_bones = recover_survivor_proxies(args.simulation)
    debris_physics = recover_debris_mass(args.simulation)
    canonical_transforms = debris_transform_map(args.canonical)
    open_blend(args.navigable)
    pose_validation = validate_survivor_pose(proxies, final_bones)

    debris = []
    for obj in sorted(bpy.data.objects, key=lambda item: item.name):
        if obj.type != "MESH" or not DEBRIS_PATTERN.match(obj.name):
            continue
        filename = f"{safe_name(obj.name)}.obj"
        mesh_path = mesh_root / filename
        stats = write_local_obj(obj, mesh_path)
        canonical = canonical_transforms[obj.name]
        change_m = (obj.matrix_world.translation - canonical.translation).length
        debris.append(
            {
                "name": obj.name,
                **debris_physics[obj.name],
                "runtime_policy": "settled_static_collision",
                "pose": pose_record(obj.matrix_world),
                "translation_from_canonical_m": round(float(change_m), 8),
                "mesh": {
                    "path": f"meshes/{filename}",
                    "sha256": sha256(mesh_path),
                    **stats,
                },
            }
        )
    if len(debris) != 26:
        raise RuntimeError(f"Expected 26 collapse debris pieces, found {len(debris)}")

    sdf_path = write_sdf(args.output, proxies, debris)
    total_survivor_mass = {
        survivor: round(sum(item["mass_kg"] for item in proxies if item["survivor_id"] == survivor), 8)
        for survivor in ("A", "B")
    }
    manifest = {
        "contract": "pulso.settled-colliders.v1",
        "coordinate_frame": "Blender world XYZ == Gazebo model XYZ; model pose must be zero",
        "source": {
            "simulation": project_path(args.simulation),
            "simulation_sha256": sha256(args.simulation),
            "canonical": project_path(args.canonical),
            "canonical_sha256": sha256(args.canonical),
            "navigable": project_path(args.navigable),
            "navigable_sha256": sha256(args.navigable),
            "blender_version": bpy.app.version_string,
        },
        "counts": {"survivor_proxies": len(proxies), "collapse_debris": len(debris)},
        "mass_reference_kg": {
            "survivors": total_survivor_mass,
            "collapse_debris_total": round(sum(item["mass_kg"] for item in debris), 8),
        },
        "runtime_policy": {
            "model": "static settled checkpoint",
            "reason": "faithful rover collision without re-running collapse dynamics",
            "mass_values": "retained as provenance; unused while model is static",
        },
        "validation": {
            **pose_validation,
            "moved_since_canonical": [
                item["name"] for item in debris if item["translation_from_canonical_m"] > 0.001
            ],
        },
        "survivor_proxies": proxies,
        "collapse_debris": debris,
        "sdf": {"path": sdf_path.name, "sha256": sha256(sdf_path)},
    }
    manifest_path = args.output / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print("PULSO_SETTLED_COLLIDERS_OK")
    print(json.dumps({
        "output": project_path(args.output),
        "counts": manifest["counts"],
        "mass_reference_kg": manifest["mass_reference_kg"],
        "max_bone_matrix_error": pose_validation["max_bone_matrix_error"],
        "moved_since_canonical": manifest["validation"]["moved_since_canonical"],
    }, indent=2))


main()
