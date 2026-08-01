"""Export the accepted Blender checkpoint as static Gazebo assets.

Run with:

    /Applications/Blender.app/Contents/MacOS/Blender \
      -b art/current/ragdoll/navigable/pulso_ragdoll_navigable.blend \
      --python scripts/export_pulso_gazebo_assets.py

The project root is derived from this script. ``PULSO_PROJECT_ROOT``,
``PULSO_SOURCE_BLEND``, and ``PULSO_GAZEBO_MESH_OUTPUT`` may override the
defaults when Blender runs from another checkout or machine.

The source blend is never modified. The visual OBJ bakes evaluated meshes at
the accepted frame. Physics uses the deliberately simple COLLISION_* objects.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

import bpy


DEFAULT_PROJECT = Path(__file__).resolve().parents[1]
PROJECT = Path(
    os.environ.get("PULSO_PROJECT_ROOT", str(DEFAULT_PROJECT))
).expanduser().resolve()
SOURCE_BLEND = Path(
    os.environ.get(
        "PULSO_SOURCE_BLEND",
        str(PROJECT / "art/current/ragdoll/navigable/pulso_ragdoll_navigable.blend"),
    )
).expanduser().resolve()
OUTPUT = Path(
    os.environ.get(
        "PULSO_GAZEBO_MESH_OUTPUT",
        str(PROJECT / "sim/ros2_ws/src/pulso_gazebo/models/pulso_disaster_scene/meshes"),
    )
).expanduser().resolve()

# Pulso authors the simulation directly in Blender's X/Y/Z world frame.  The
# rover spawn poses, survivor annotations, and navigation checkpoints use that
# same frame, so the runtime OBJ must preserve it.  Blender's conventional
# ``NEGATIVE_Y`` OBJ export rotates X/Y by 180 degrees and silently separates
# the Gazebo geometry from every authored pose.
OBJ_FORWARD_AXIS = "Y"
OBJ_UP_AXIS = "Z"

# Ogre2 in Gazebo Fortress keeps imported OBJ textures in a comparatively
# small streaming pool.  Twenty 2K survivor / PBR textures expand to roughly
# 450 MiB once decoded with mipmaps and can black out the GUI even on a GPU
# with ample physical VRAM.  A 1K runtime copy is still above the useful texel
# density of the 640x480 phone camera and the operator viewport.  The packed
# 2K images in SOURCE_BLEND remain untouched because this script never saves
# the opened blend file.
RUNTIME_TEXTURE_MAX_DIMENSION = 1024

VISUAL_COLLECTIONS = {
    "VISUAL_ARCH",
    "VISUAL_DEBRIS_STATIC",
    "VISUAL_DETAIL",
    # These are the two authored rubble ramps that correspond to the physical
    # navigation collision. Planned routes / candidate colours are published
    # later as MetaView overlays and never baked into raw camera pixels.
    "VISUAL_NAVIGATION",
    "VISUAL_RAGDOLL",
    "VISUAL_SURVIVORS",
}
COLLISION_COLLECTIONS = {
    "COLLISION_ARCH",
    "COLLISION_DEBRIS_STATIC",
    "COLLISION_NAVIGATION",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def selected_meshes(collection_names: set[str]) -> list[bpy.types.Object]:
    missing = sorted(collection_names - set(bpy.data.collections.keys()))
    if missing:
        raise RuntimeError(f"Missing required collections: {missing}")

    result = {
        obj
        for collection_name in collection_names
        for obj in bpy.data.collections[collection_name].all_objects
        if obj.type == "MESH"
    }
    if not result:
        raise RuntimeError(f"No meshes found in {sorted(collection_names)}")
    return sorted(result, key=lambda obj: obj.name)


def select(objects: list[bpy.types.Object]) -> None:
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.hide_set(False)
        obj.hide_viewport = False
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]


def batched_evaluated_visual(
    objects: list[bpy.types.Object],
) -> bpy.types.Object:
    """Bake 500 authored objects into one runtime mesh with shared materials.

    Gazebo Fortress / Ogre2 creates a separate GPU material instance for each
    OBJ shape. Exporting the Blender object hierarchy verbatim therefore loads
    the same 2K texture hundreds of times and can leave the GUI black after its
    texture budget is exhausted. The phone still needs all evaluated geometry,
    UVs, normals, and materials, but it does not need Blender's authoring object
    boundaries. One mesh with deduplicated material slots preserves the pixels
    while reducing runtime draw/material batches to the real material count.
    """

    depsgraph = bpy.context.evaluated_depsgraph_get()
    fallback = bpy.data.materials.get("PULSO_RUNTIME_FALLBACK")
    if fallback is None:
        fallback = bpy.data.materials.new("PULSO_RUNTIME_FALLBACK")
        fallback.diffuse_color = (0.35, 0.36, 0.38, 1.0)

    copies: list[bpy.types.Object] = []
    for source in objects:
        evaluated = source.evaluated_get(depsgraph)
        mesh = bpy.data.meshes.new_from_object(
            evaluated,
            preserve_all_data_layers=True,
            depsgraph=depsgraph,
        )
        if len(mesh.materials) == 0:
            mesh.materials.append(fallback)
        copy = bpy.data.objects.new(f"RUNTIME_{source.name}", mesh)
        copy.matrix_world = source.matrix_world.copy()
        bpy.context.scene.collection.objects.link(copy)
        copies.append(copy)

    select(copies)
    bpy.context.view_layer.objects.active = copies[0]
    bpy.ops.object.join()
    joined = bpy.context.active_object
    joined.name = "PULSO_RUNTIME_VISUAL_BATCH"

    old_slots = list(joined.data.materials)
    unique: list[bpy.types.Material] = []
    new_index_by_pointer: dict[int, int] = {}
    remap: dict[int, int] = {}
    for old_index, material in enumerate(old_slots):
        material = material or fallback
        pointer = material.as_pointer()
        if pointer not in new_index_by_pointer:
            new_index_by_pointer[pointer] = len(unique)
            unique.append(material)
        remap[old_index] = new_index_by_pointer[pointer]
    polygon_material_indices = [
        remap.get(polygon.material_index, 0) for polygon in joined.data.polygons
    ]
    joined.data.materials.clear()
    for material in unique:
        joined.data.materials.append(material)
    for polygon, material_index in zip(
        joined.data.polygons, polygon_material_indices
    ):
        polygon.material_index = material_index
    joined.data.update()
    return joined


def materialize_packed_images() -> list[dict[str, object]]:
    texture_root = OUTPUT / "textures"
    texture_root.mkdir(parents=True, exist_ok=True)
    written: list[dict[str, object]] = []
    used_names: set[str] = set()
    for image in sorted(bpy.data.images, key=lambda item: item.name):
        if image.type != "IMAGE" or image.packed_file is None:
            continue
        original = Path(image.filepath).name or image.name
        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", original)
        stem, suffix = Path(safe_name).stem, Path(safe_name).suffix
        candidate = safe_name
        index = 2
        while candidate.lower() in used_names:
            candidate = f"{stem}_{index}{suffix}"
            index += 1
        used_names.add(candidate.lower())
        target = texture_root / candidate

        source_width, source_height = image.size
        runtime_width, runtime_height = source_width, source_height
        if max(source_width, source_height) > RUNTIME_TEXTURE_MAX_DIMENSION:
            scale = RUNTIME_TEXTURE_MAX_DIMENSION / max(
                source_width, source_height
            )
            runtime_width = max(1, round(source_width * scale))
            runtime_height = max(1, round(source_height * scale))
            image.scale(runtime_width, runtime_height)
            image.filepath_raw = str(target)
            if target.suffix.lower() in {".jpg", ".jpeg"}:
                image.file_format = "JPEG"
            elif target.suffix.lower() == ".png":
                image.file_format = "PNG"
            else:
                raise RuntimeError(
                    f"Unsupported packed runtime texture format: {target}"
                )
            image.save()
        else:
            target.write_bytes(image.packed_file.data)
        image.filepath = str(target)
        # The glTF exporter prefers packed bytes over the resized pixel buffer.
        # Unpack only this in-memory copy so GLB / downstream DAE conversion
        # consume the bounded runtime texture instead of silently embedding
        # the original 2K payload. SOURCE_BLEND is never saved.
        image.unpack(method="REMOVE")
        written.append(
            {
                "path": str(target.relative_to(PROJECT)),
                "source_size": [source_width, source_height],
                "runtime_size": [runtime_width, runtime_height],
                "bytes": target.stat().st_size,
            }
        )
    return written


def export_obj(path: Path, objects: list[bpy.types.Object], materials: bool) -> None:
    select(objects)
    bpy.ops.wm.obj_export(
        filepath=str(path),
        export_selected_objects=True,
        export_animation=False,
        apply_modifiers=True,
        apply_transform=True,
        forward_axis=OBJ_FORWARD_AXIS,
        up_axis=OBJ_UP_AXIS,
        export_uv=materials,
        export_normals=True,
        export_materials=materials,
        export_pbr_extensions=materials,
        path_mode="RELATIVE" if materials else "AUTO",
        export_triangulated_mesh=True,
        export_object_groups=False,
        export_material_groups=materials,
    )
    if not path.is_file() or path.stat().st_size == 0:
        raise RuntimeError(f"Blender did not create {path}")

    # Blender can preserve the packed image's old relative path in MTL even
    # after materializing it beside the export. Gazebo Fortress resolves those
    # paths literally, so normalize every texture reference to our export-owned
    # `textures/` directory.
    mtl_path = path.with_suffix(".mtl")
    if materials and mtl_path.is_file():
        normalized = []
        for line in mtl_path.read_text(encoding="utf-8").splitlines():
            if line.startswith(("map_", "bump ", "disp ", "decal ", "refl ")):
                prefix, image_path = line.rsplit(" ", 1)
                line = f"{prefix} textures/{Path(image_path).name}"
            normalized.append(line)
        mtl_path.write_text("\n".join(normalized) + "\n", encoding="utf-8")


def export_glb(path: Path, objects: list[bpy.types.Object]) -> None:
    select(objects)
    bpy.ops.export_scene.gltf(
        filepath=str(path),
        export_format="GLB",
        use_selection=True,
        export_apply=True,
        export_texcoords=True,
        export_normals=True,
        export_materials="EXPORT",
        export_image_format="AUTO",
        export_cameras=False,
        export_lights=False,
    )
    if not path.is_file() or path.stat().st_size == 0:
        raise RuntimeError(f"Blender did not create {path}")


def mesh_stats(objects: list[bpy.types.Object]) -> dict[str, int]:
    return {
        "objects": len(objects),
        "source_vertices": sum(len(obj.data.vertices) for obj in objects),
        "source_polygons": sum(len(obj.data.polygons) for obj in objects),
    }


if Path(bpy.data.filepath).resolve() != SOURCE_BLEND.resolve():
    raise RuntimeError(
        f"Expected {SOURCE_BLEND}, Blender opened {Path(bpy.data.filepath).resolve()}"
    )

OUTPUT.mkdir(parents=True, exist_ok=True)
runtime_textures = materialize_packed_images()
visual_objects = selected_meshes(VISUAL_COLLECTIONS)
collision_objects = selected_meshes(COLLISION_COLLECTIONS)
runtime_visual = batched_evaluated_visual(visual_objects)

visual_path = OUTPUT / "pulso_disaster_visual.obj"
collision_path = OUTPUT / "pulso_disaster_collision.obj"
export_obj(visual_path, [runtime_visual], materials=True)
export_glb(OUTPUT / "pulso_disaster_visual.glb", [runtime_visual])
export_obj(collision_path, collision_objects, materials=False)

produced = sorted(
    path
    for path in OUTPUT.rglob("*")
    if path.is_file() and path.name not in {"README.md", "pulso_blender_export_manifest.json"}
)
manifest = {
    "contract": "pulso.blender-gazebo-export.v1",
    "runtime_coordinate_frame": {
        "source": "Blender world XYZ",
        "obj_forward_axis": OBJ_FORWARD_AXIS,
        "obj_up_axis": OBJ_UP_AXIS,
        "preserves_source_xy": True,
    },
    "blender_version": bpy.app.version_string,
    "source": str(SOURCE_BLEND.relative_to(PROJECT)),
    "source_sha256": sha256(SOURCE_BLEND),
    "visual_collections": sorted(VISUAL_COLLECTIONS),
    "collision_collections": sorted(COLLISION_COLLECTIONS),
    "visual": mesh_stats(visual_objects),
    "runtime_visual_batching": {
        "objects": 1,
        "material_slots": len(runtime_visual.data.materials),
        "reason": "Ogre2 material/texture instance budget",
    },
    "runtime_textures": {
        "max_dimension": RUNTIME_TEXTURE_MAX_DIMENSION,
        "source_blend_unchanged": True,
        "files": runtime_textures,
    },
    "collision": mesh_stats(collision_objects),
    "files": [
        {
            "path": str(path.relative_to(PROJECT)),
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        }
        for path in produced
    ],
}
manifest_path = OUTPUT / "pulso_blender_export_manifest.json"
manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

print("PULSO_GAZEBO_EXPORT_OK")
print(json.dumps(manifest, indent=2))
