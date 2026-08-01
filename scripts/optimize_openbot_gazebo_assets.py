"""Build a lightweight, visually faithful OpenBot mesh for Gazebo.

Run with Blender, not the system Python:

    /Applications/Blender.app/Contents/MacOS/Blender \
      --background --factory-startup \
      --python scripts/optimize_openbot_gazebo_assets.py

The official source STLs remain untouched. Gazebo renders the generated LOD
meshes while physics uses compound primitives authored in the world SDF.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import bpy
from mathutils import Vector


PROJECT = Path(__file__).resolve().parents[1]
MESH_ROOT = PROJECT / "sim/ros2_ws/src/pulso_gazebo/models/pulso_openbot/meshes"
MANIFEST_PATH = MESH_ROOT / "openbot_visual_lod_manifest.json"
DECIMATE_RATIO = 0.25
PARTS = ("body_bottom", "body_top")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def bounds_millimetres(obj: bpy.types.Object) -> dict[str, list[float]]:
    points = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    return {
        "min": [min(point[axis] for point in points) for axis in range(3)],
        "max": [max(point[axis] for point in points) for axis in range(3)],
    }


def build_part(name: str) -> dict[str, object]:
    source = MESH_ROOT / f"{name}.stl"
    output = MESH_ROOT / f"{name}_visual_lod25.stl"
    if not source.is_file():
        raise RuntimeError(f"Missing official OpenBot mesh: {source}")

    clear_scene()
    bpy.ops.wm.stl_import(filepath=str(source))
    obj = bpy.context.active_object
    source_triangles = len(obj.data.polygons)
    source_bounds = bounds_millimetres(obj)

    modifier = obj.modifiers.new(name="GazeboVisualLOD25", type="DECIMATE")
    modifier.ratio = DECIMATE_RATIO
    modifier.use_collapse_triangulate = True
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier=modifier.name)

    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.wm.stl_export(
        filepath=str(output),
        export_selected_objects=True,
        ascii_format=False,
        apply_modifiers=True,
    )
    if not output.is_file() or output.stat().st_size == 0:
        raise RuntimeError(f"Blender did not create {output}")

    return {
        "part": name,
        "source": source.name,
        "source_sha256": sha256(source),
        "source_bytes": source.stat().st_size,
        "source_triangles": source_triangles,
        "source_bounds_mm": source_bounds,
        "lod": output.name,
        "lod_sha256": sha256(output),
        "lod_bytes": output.stat().st_size,
        "lod_triangles": len(obj.data.polygons),
        "lod_bounds_mm": bounds_millimetres(obj),
    }


MESH_ROOT.mkdir(parents=True, exist_ok=True)
parts = [build_part(name) for name in PARTS]
manifest = {
    "contract": "pulso.openbot-visual-lod.v1",
    "blender_version": bpy.app.version_string,
    "decimate_ratio": DECIMATE_RATIO,
    "purpose": "visual-only; never use these triangle meshes as dynamic collision",
    "parts": parts,
    "totals": {
        "source_triangles": sum(int(part["source_triangles"]) for part in parts),
        "lod_triangles": sum(int(part["lod_triangles"]) for part in parts),
        "source_bytes": sum(int(part["source_bytes"]) for part in parts),
        "lod_bytes": sum(int(part["lod_bytes"]) for part in parts),
    },
}
MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

print("PULSO_OPENBOT_LOD_OK")
print(json.dumps(manifest, indent=2))
