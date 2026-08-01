"""Export the six rover-interactive debris pieces as real Gazebo bodies.

The accepted Blender scene contains matching VIS_DYN_* render meshes and
COL_DYN_* collision proxies. This exporter keeps each render mesh local to its
link, uses the authored proxy as a stable box collider, and derives mass and
box inertia from material density. The large entrapment slabs are deliberately
handled by ``export_pulso_settled_colliders.py`` as a fixed collapse checkpoint.

Run with Blender:

    /Applications/Blender.app/Contents/MacOS/Blender --background \
      --factory-startup --python scripts/export_pulso_dynamic_debris.py
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path

import bpy
from mathutils import Matrix


PROJECT = Path(__file__).resolve().parents[1]
SOURCE_BLEND = PROJECT / "art/current/ragdoll/navigable/pulso_ragdoll_navigable.blend"
OUTPUT = (
    PROJECT
    / "sim/ros2_ws/src/pulso_gazebo/models/pulso_dynamic_debris"
)
VISUAL_COLLECTION = "VISUAL_DEBRIS_DYNAMIC"
COLLISION_COLLECTION = "COLLISION_DEBRIS_DYNAMIC"
VISUAL_PREFIX = "VIS_DYN_"
COLLISION_PREFIX = "COL_DYN_"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def safe_name(name: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", name.lower()).strip("_")


def rounded(values, digits: int = 8) -> list[float]:
    return [round(float(value), digits) for value in values]


def quaternion_to_rpy(quaternion) -> tuple[float, float, float]:
    w, x, y, z = (float(value) for value in quaternion)
    roll = math.atan2(2.0 * (w * x + y * z), 1.0 - 2.0 * (x * x + y * y))
    pitch_term = max(-1.0, min(1.0, 2.0 * (w * y - z * x)))
    pitch = math.asin(pitch_term)
    yaw = math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))
    return roll, pitch, yaw


def pose_values(matrix: Matrix) -> tuple[list[float], list[float]]:
    location, rotation, scale = matrix.decompose()
    return [*rounded(location), *rounded(quaternion_to_rpy(rotation))], rounded(scale)


def sdf_pose(matrix: Matrix) -> str:
    values, _ = pose_values(matrix)
    return " ".join(f"{value:.9g}" for value in values)


def projected_uv(vertex, normal, bounds_min, bounds_max) -> tuple[float, float]:
    """Return a deterministic box-projected UV whose winding follows normal."""
    dominant = max(range(3), key=lambda axis: abs(normal[axis]))
    if dominant == 0:
        axes = (1, 2) if normal.x >= 0.0 else (2, 1)
    elif dominant == 1:
        axes = (2, 0) if normal.y >= 0.0 else (0, 2)
    else:
        axes = (0, 1) if normal.z >= 0.0 else (1, 0)

    result = []
    for axis in axes:
        span = bounds_max[axis] - bounds_min[axis]
        if span <= 1e-9:
            raise RuntimeError("Cannot UV-project a zero-width debris mesh")
        result.append((vertex[axis] - bounds_min[axis]) / span)
    return float(result[0]), float(result[1])


def write_local_obj(obj: bpy.types.Object, path: Path) -> dict[str, object]:
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    try:
        mesh.calc_loop_triangles()
        bounds_min = [min(vertex.co[axis] for vertex in mesh.vertices) for axis in range(3)]
        bounds_max = [max(vertex.co[axis] for vertex in mesh.vertices) for axis in range(3)]
        uv_coordinates: list[tuple[float, float]] = []
        faces: list[tuple[list[int], list[int]]] = []
        minimum_uv_area = math.inf
        for triangle in mesh.loop_triangles:
            triangle_uvs = [
                projected_uv(
                    mesh.vertices[index].co,
                    triangle.normal,
                    bounds_min,
                    bounds_max,
                )
                for index in triangle.vertices
            ]
            (u0, v0), (u1, v1), (u2, v2) = triangle_uvs
            uv_area = abs((u1 - u0) * (v2 - v0) - (v1 - v0) * (u2 - u0)) * 0.5
            if uv_area <= 1e-12:
                raise RuntimeError(f"Degenerate projected UV triangle on {obj.name}")
            minimum_uv_area = min(minimum_uv_area, uv_area)
            first_uv = len(uv_coordinates) + 1
            uv_coordinates.extend(triangle_uvs)
            faces.append(
                (
                    [index + 1 for index in triangle.vertices],
                    [first_uv, first_uv + 1, first_uv + 2],
                )
            )

        lines = [f"o {obj.name}"]
        for vertex in mesh.vertices:
            lines.append("v " + " ".join(f"{value:.9g}" for value in vertex.co))
        for u, v in uv_coordinates:
            lines.append(f"vt {u:.9g} {v:.9g}")
        # Explicit normals plus non-degenerate UVs let Assimp / Ogre generate
        # tangents without changing the authored visual geometry.
        for vertex in mesh.vertices:
            lines.append("vn " + " ".join(f"{value:.9g}" for value in vertex.normal))
        for vertex_indices, uv_indices in faces:
            lines.append(
                "f "
                + " ".join(
                    f"{vertex}/{uv}/{vertex}"
                    for vertex, uv in zip(vertex_indices, uv_indices, strict=True)
                )
            )
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return {
            "vertices": len(mesh.vertices),
            "triangles": len(mesh.loop_triangles),
            "uv_coordinates": len(uv_coordinates),
            "minimum_uv_triangle_area": round(minimum_uv_area, 12),
            "tangent_ready": True,
            "sha256": sha256(path),
        }
    finally:
        evaluated.to_mesh_clear()


def material_profile(name: str) -> tuple[float, tuple[float, float, float, float]]:
    if "PLANK" in name:
        return 650.0, (0.28, 0.20, 0.13, 1.0)
    if "BRICK" in name:
        return 1800.0, (0.39, 0.22, 0.14, 1.0)
    return 1700.0, (0.42, 0.43, 0.45, 1.0)


def box_inertia(mass: float, size: tuple[float, float, float]) -> dict[str, float]:
    x, y, z = size
    return {
        "ixx": mass * (y * y + z * z) / 12.0,
        "iyy": mass * (x * x + z * z) / 12.0,
        "izz": mass * (x * x + y * y) / 12.0,
    }


def link_xml(piece: dict[str, object]) -> str:
    size = piece["collision_size_m"]
    size_text = " ".join(f"{value:.9g}" for value in size)
    scale_text = " ".join(f"{value:.9g}" for value in piece["visual_scale"])
    colour = " ".join(f"{value:.5g}" for value in piece["colour_rgba"])
    inertia = piece["inertia_kg_m2"]
    return f"""    <link name='{piece['link_name']}'>
      <pose>{piece['world_pose']}</pose>
      <inertial>
        <mass>{piece['mass_kg']:.9g}</mass>
        <inertia>
          <ixx>{inertia['ixx']:.9g}</ixx><iyy>{inertia['iyy']:.9g}</iyy><izz>{inertia['izz']:.9g}</izz>
          <ixy>0</ixy><ixz>0</ixz><iyz>0</iyz>
        </inertia>
      </inertial>
      <velocity_decay><linear>0.12</linear><angular>0.2</angular></velocity_decay>
      <collision name='collision'>
        <geometry><box><size>{size_text}</size></box></geometry>
        <surface>
          <friction><ode><mu>0.86</mu><mu2>0.78</mu2></ode></friction>
          <bounce><restitution_coefficient>0.015</restitution_coefficient><threshold>0.05</threshold></bounce>
        </surface>
      </collision>
      <visual name='visual'>
        <geometry>
          <mesh>
            <uri>model://pulso_dynamic_debris/{piece['mesh_path']}</uri>
            <scale>{scale_text}</scale>
          </mesh>
        </geometry>
        <material><ambient>{colour}</ambient><diffuse>{colour}</diffuse></material>
      </visual>
    </link>"""


if not SOURCE_BLEND.is_file():
    raise RuntimeError(f"Missing accepted Blender checkpoint: {SOURCE_BLEND}")
bpy.ops.wm.open_mainfile(filepath=str(SOURCE_BLEND))
bpy.context.view_layer.update()

visual_collection = bpy.data.collections.get(VISUAL_COLLECTION)
collision_collection = bpy.data.collections.get(COLLISION_COLLECTION)
if visual_collection is None or collision_collection is None:
    raise RuntimeError("Accepted checkpoint is missing dynamic debris collections")

visuals = {
    obj.name.removeprefix(VISUAL_PREFIX): obj
    for obj in visual_collection.all_objects
    if obj.type == "MESH" and obj.name.startswith(VISUAL_PREFIX)
}
collisions = {
    obj.name.removeprefix(COLLISION_PREFIX): obj
    for obj in collision_collection.all_objects
    if obj.type == "MESH" and obj.name.startswith(COLLISION_PREFIX)
}
if visuals.keys() != collisions.keys() or len(visuals) != 6:
    raise RuntimeError(
        f"Expected six matched visual/collision pieces, got {sorted(visuals)} / {sorted(collisions)}"
    )

mesh_root = OUTPUT / "meshes"
mesh_root.mkdir(parents=True, exist_ok=True)
pieces: list[dict[str, object]] = []
for key in sorted(visuals):
    visual = visuals[key]
    collision = collisions[key]
    density, colour = material_profile(key)
    size = tuple(float(value) for value in collision.dimensions)
    mass = density * size[0] * size[1] * size[2]
    mesh_name = f"{safe_name(visual.name)}.obj"
    mesh_path = mesh_root / mesh_name
    mesh_stats = write_local_obj(visual, mesh_path)
    visual_relative = collision.matrix_world.inverted() @ visual.matrix_world
    relative_pose, visual_scale = pose_values(visual_relative)
    if max(abs(value) for value in relative_pose) > 1e-5:
        raise RuntimeError(f"Visual and collider transforms diverge for {key}: {relative_pose}")
    piece = {
        "id": key,
        "link_name": safe_name(key),
        "world_pose": sdf_pose(collision.matrix_world),
        "world_matrix": [rounded(row) for row in collision.matrix_world],
        "collision_size_m": rounded(size),
        "density_kg_m3": density,
        "mass_kg": mass,
        "inertia_kg_m2": box_inertia(mass, size),
        "colour_rgba": colour,
        "visual_scale": visual_scale,
        "mesh_path": f"meshes/{mesh_name}",
        "mesh": mesh_stats,
    }
    pieces.append(piece)

sdf = """<?xml version='1.0'?>
<sdf version='1.8'>
  <model name='pulso_dynamic_debris'>
    <static>false</static>
    <self_collide>true</self_collide>
""" + "\n".join(link_xml(piece) for piece in pieces) + """
  </model>
</sdf>
"""
model_path = OUTPUT / "model.sdf"
model_path.write_text(sdf, encoding="utf-8")
(OUTPUT / "model.config").write_text(
    """<?xml version='1.0'?>
<model>
  <name>Pulso dynamic debris</name>
  <version>1.0.0</version>
  <sdf version='1.8'>model.sdf</sdf>
  <description>Six rover-interactive debris bodies from the accepted Blender scene.</description>
</model>
""",
    encoding="utf-8",
)
manifest = {
    "contract": "pulso.dynamic-debris.v1",
    "source": str(SOURCE_BLEND.relative_to(PROJECT)),
    "source_sha256": sha256(SOURCE_BLEND),
    "blender_version": bpy.app.version_string,
    "coordinate_frame": "Blender world XYZ == Gazebo model XYZ; include pose must be zero",
    "runtime_policy": "six independent dynamic links with authored visual meshes and box colliders",
    "pieces": pieces,
    "totals": {
        "links": len(pieces),
        "mass_kg": round(sum(float(piece["mass_kg"]) for piece in pieces), 8),
        "visual_triangles": sum(int(piece["mesh"]["triangles"]) for piece in pieces),
    },
    "sdf_sha256": sha256(model_path),
}
(OUTPUT / "manifest.json").write_text(
    json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
)

print("PULSO_DYNAMIC_DEBRIS_EXPORT_OK")
print(json.dumps(manifest["totals"], indent=2))
