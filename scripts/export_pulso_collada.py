"""Direct Collada 1.4.1 export for the accepted static Pulso scene.

This spike intentionally does not invoke Assimp or Blender's Collada exporter.
It writes evaluated world-space geometry, normals, UVs, material triangle
groups, and references the bounded runtime textures already produced beside
the accepted OBJ.

Run with:

    blender --background --factory-startup \
      --python scripts/export_pulso_collada.py
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import xml.etree.ElementTree as ET
from collections import defaultdict, deque
from pathlib import Path

import bpy


PROJECT = Path(__file__).resolve().parents[1]
SOURCE_BLEND = (
    PROJECT / "art/current/ragdoll/navigable/pulso_ragdoll_navigable.blend"
)
OUTPUT_ROOT = (
    PROJECT
    / "sim/ros2_ws/src/pulso_gazebo/models/pulso_disaster_scene/meshes"
)
OUTPUT_DAE = OUTPUT_ROOT / "pulso_disaster_visual.dae"
TEXTURE_ROOT = OUTPUT_ROOT / "textures"
VISUAL_COLLECTIONS = {
    "VISUAL_ARCH",
    "VISUAL_DEBRIS_STATIC",
    "VISUAL_DETAIL",
    "VISUAL_NAVIGATION",
    "VISUAL_RAGDOLL",
    "VISUAL_SURVIVORS",
}


def safe_id(prefix: str, name: str, index: int) -> str:
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("_.-") or "unnamed"
    if not stem[0].isalpha() and stem[0] != "_":
        stem = f"n_{stem}"
    return f"{prefix}_{index}_{stem}"


def numbers(values) -> str:
    return " ".join(f"{float(value):.9g}" for value in values)


def wrapped_values(values, *, per_line: int, formatter=str) -> str:
    """Serialize large numeric arrays without creating multi-megabyte lines."""

    encoded = [formatter(value) for value in values]
    return "\n".join(
        " ".join(encoded[start : start + per_line])
        for start in range(0, len(encoded), per_line)
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def selected_meshes() -> list[bpy.types.Object]:
    missing = sorted(VISUAL_COLLECTIONS - set(bpy.data.collections.keys()))
    if missing:
        raise RuntimeError(f"Missing visual collections: {missing}")
    objects = {
        obj
        for collection_name in VISUAL_COLLECTIONS
        for obj in bpy.data.collections[collection_name].all_objects
        if obj.type == "MESH"
    }
    return sorted(objects, key=lambda obj: obj.name)


def upstream_image_nodes(socket) -> list[bpy.types.Node]:
    queue = deque(link.from_node for link in socket.links)
    visited = set()
    images = []
    while queue:
        node = queue.popleft()
        pointer = node.as_pointer()
        if pointer in visited:
            continue
        visited.add(pointer)
        if node.type == "TEX_IMAGE" and node.image is not None:
            images.append(node)
            continue
        for input_socket in node.inputs:
            queue.extend(link.from_node for link in input_socket.links)
    return images


def material_profile(material: bpy.types.Material, index: int) -> dict:
    colour = tuple(float(value) for value in material.diffuse_color)
    image_node = None
    alpha_images = set()
    if material.use_nodes and material.node_tree is not None:
        principled = next(
            (node for node in material.node_tree.nodes if node.type == "BSDF_PRINCIPLED"),
            None,
        )
        if principled is not None:
            base = principled.inputs.get("Base Color")
            if base is not None:
                colour = tuple(float(value) for value in base.default_value)
                candidates = upstream_image_nodes(base)
                image_node = candidates[0] if candidates else None
            alpha = principled.inputs.get("Alpha")
            if alpha is not None:
                alpha_images = {
                    node.image.as_pointer() for node in upstream_image_nodes(alpha)
                }

    texture = None
    projection = None
    mapping_scale = (1.0, 1.0, 1.0)
    mapping_location = (0.0, 0.0, 0.0)
    uses_alpha = False
    if image_node is not None:
        texture_path = TEXTURE_ROOT / Path(image_node.image.filepath).name
        if not texture_path.is_file():
            raise RuntimeError(
                f"Missing bounded runtime texture for {material.name}: {texture_path}"
            )
        texture = f"textures/{texture_path.name}"
        projection = image_node.projection
        uses_alpha = image_node.image.as_pointer() in alpha_images
        vector = image_node.inputs.get("Vector")
        if vector is not None and vector.links:
            mapping = vector.links[0].from_node
            if mapping.type == "MAPPING":
                mapping_scale = tuple(float(value) for value in mapping.inputs["Scale"].default_value)
                mapping_location = tuple(
                    float(value) for value in mapping.inputs["Location"].default_value
                )

    return {
        "index": index,
        "name": material.name,
        "id": safe_id("material", material.name, index),
        "effect_id": safe_id("effect", material.name, index),
        "symbol": safe_id("symbol", material.name, index),
        "colour": colour,
        "texture": texture,
        "projection": projection,
        "mapping_scale": mapping_scale,
        "mapping_location": mapping_location,
        "uses_alpha": uses_alpha,
    }


def projected_uv(vertex, normal, bounds_min, bounds_max, profile) -> tuple[float, float]:
    dominant = max(range(3), key=lambda axis: abs(normal[axis]))
    if dominant == 0:
        axes = (1, 2) if normal.x >= 0.0 else (2, 1)
    elif dominant == 1:
        axes = (2, 0) if normal.y >= 0.0 else (0, 2)
    else:
        axes = (0, 1) if normal.z >= 0.0 else (1, 0)
    uv = []
    for axis in axes:
        span = bounds_max[axis] - bounds_min[axis]
        if span <= 1e-10:
            raise RuntimeError("Cannot project UVs on a zero-width mesh")
        generated = (vertex[axis] - bounds_min[axis]) / span
        uv.append(
            generated * profile["mapping_scale"][axis]
            + profile["mapping_location"][axis]
        )
    return float(uv[0]), float(uv[1])


def add_source(mesh_element, source_id: str, rows, params: tuple[str, ...]) -> None:
    source = ET.SubElement(mesh_element, "source", id=source_id)
    array_id = f"{source_id}_array"
    flattened = [value for row in rows for value in row]
    ET.SubElement(
        source,
        "float_array",
        id=array_id,
        count=str(len(flattened)),
    ).text = wrapped_values(
        flattened,
        per_line=12,
        formatter=lambda value: f"{float(value):.9g}",
    )
    technique = ET.SubElement(source, "technique_common")
    accessor = ET.SubElement(
        technique,
        "accessor",
        source=f"#{array_id}",
        count=str(len(rows)),
        stride=str(len(params)),
    )
    for name in params:
        ET.SubElement(accessor, "param", name=name, type="float")


def add_material_libraries(root, profiles: list[dict]) -> None:
    images = {}
    for profile in profiles:
        texture = profile["texture"]
        if texture is not None and texture not in images:
            images[texture] = safe_id("image", Path(texture).stem, len(images))
    if images:
        library_images = ET.SubElement(root, "library_images")
        for texture, image_id in sorted(images.items()):
            image = ET.SubElement(library_images, "image", id=image_id, name=image_id)
            ET.SubElement(image, "init_from").text = texture

    library_effects = ET.SubElement(root, "library_effects")
    library_materials = ET.SubElement(root, "library_materials")
    for profile in profiles:
        effect = ET.SubElement(library_effects, "effect", id=profile["effect_id"])
        common = ET.SubElement(effect, "profile_COMMON")
        sampler_sid = None
        if profile["texture"] is not None:
            image_id = images[profile["texture"]]
            surface_sid = f"{profile['effect_id']}_surface"
            sampler_sid = f"{profile['effect_id']}_sampler"
            surface_param = ET.SubElement(common, "newparam", sid=surface_sid)
            surface = ET.SubElement(surface_param, "surface", type="2D")
            ET.SubElement(surface, "init_from").text = image_id
            sampler_param = ET.SubElement(common, "newparam", sid=sampler_sid)
            sampler = ET.SubElement(sampler_param, "sampler2D")
            ET.SubElement(sampler, "source").text = surface_sid
        technique = ET.SubElement(common, "technique", sid="common")
        phong = ET.SubElement(technique, "phong")
        ET.SubElement(ET.SubElement(phong, "emission"), "color").text = "0 0 0 1"
        ET.SubElement(ET.SubElement(phong, "ambient"), "color").text = "0.12 0.12 0.12 1"
        diffuse = ET.SubElement(phong, "diffuse")
        if sampler_sid is not None:
            ET.SubElement(diffuse, "texture", texture=sampler_sid, texcoord="UVMap")
        else:
            ET.SubElement(diffuse, "color").text = numbers(profile["colour"])
        ET.SubElement(ET.SubElement(phong, "specular"), "color").text = "0.08 0.08 0.08 1"
        ET.SubElement(ET.SubElement(phong, "shininess"), "float").text = "12"
        if sampler_sid is not None and profile["uses_alpha"]:
            transparent = ET.SubElement(phong, "transparent", opaque="A_ONE")
            ET.SubElement(
                transparent, "texture", texture=sampler_sid, texcoord="UVMap"
            )
            ET.SubElement(ET.SubElement(phong, "transparency"), "float").text = "1"
        material = ET.SubElement(
            library_materials,
            "material",
            id=profile["id"],
            name=profile["name"],
        )
        ET.SubElement(material, "instance_effect", url=f"#{profile['effect_id']}")


def main() -> None:
    if Path(bpy.data.filepath).resolve() != SOURCE_BLEND.resolve():
        bpy.ops.wm.open_mainfile(filepath=str(SOURCE_BLEND))
    bpy.context.view_layer.update()
    objects = selected_meshes()
    depsgraph = bpy.context.evaluated_depsgraph_get()

    fallback = bpy.data.materials.get("PULSO_COLLADA_FALLBACK")
    if fallback is None:
        fallback = bpy.data.materials.new("PULSO_COLLADA_FALLBACK")
        fallback.diffuse_color = (0.35, 0.36, 0.38, 1.0)
    profiles = []
    profile_by_pointer = {}

    def profile_for(material):
        material = material or fallback
        pointer = material.as_pointer()
        if pointer not in profile_by_pointer:
            profile_by_pointer[pointer] = len(profiles)
            profiles.append(material_profile(material, len(profiles)))
        return profiles[profile_by_pointer[pointer]]

    positions = []
    normals = []
    uvs = []
    indices_by_material = defaultdict(list)
    bounds_min = [math.inf, math.inf, math.inf]
    bounds_max = [-math.inf, -math.inf, -math.inf]

    for source in objects:
        evaluated = source.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh(preserve_all_data_layers=True, depsgraph=depsgraph)
        try:
            mesh.calc_loop_triangles()
            position_offset = len(positions)
            world = evaluated.matrix_world
            normal_matrix = world.to_3x3().inverted().transposed()
            local_min = [min(vertex.co[axis] for vertex in mesh.vertices) for axis in range(3)]
            local_max = [max(vertex.co[axis] for vertex in mesh.vertices) for axis in range(3)]
            for vertex in mesh.vertices:
                transformed = world @ vertex.co
                positions.append(tuple(transformed))
                for axis in range(3):
                    bounds_min[axis] = min(bounds_min[axis], transformed[axis])
                    bounds_max[axis] = max(bounds_max[axis], transformed[axis])

            active_uv = mesh.uv_layers.active.data if mesh.uv_layers.active else None
            corner_normals = mesh.corner_normals
            for triangle in mesh.loop_triangles:
                polygon = mesh.polygons[triangle.polygon_index]
                material = (
                    mesh.materials[polygon.material_index]
                    if polygon.material_index < len(mesh.materials)
                    else fallback
                )
                profile = profile_for(material)
                packed = indices_by_material[profile["index"]]
                for vertex_index, loop_index in zip(
                    triangle.vertices, triangle.loops, strict=True
                ):
                    normal = normal_matrix @ corner_normals[loop_index].vector
                    normal.normalize()
                    normal_index = len(normals)
                    normals.append(tuple(normal))
                    if active_uv is not None and profile["projection"] != "BOX":
                        uv = tuple(float(value) for value in active_uv[loop_index].uv)
                    else:
                        uv = projected_uv(
                            mesh.vertices[vertex_index].co,
                            triangle.normal,
                            local_min,
                            local_max,
                            profile,
                        )
                    uv_index = len(uvs)
                    uvs.append(uv)
                    packed.extend(
                        (position_offset + vertex_index, normal_index, uv_index)
                    )
        finally:
            evaluated.to_mesh_clear()

    root = ET.Element(
        "COLLADA",
        xmlns="http://www.collada.org/2005/11/COLLADASchema",
        version="1.4.1",
    )
    asset = ET.SubElement(root, "asset")
    contributor = ET.SubElement(asset, "contributor")
    ET.SubElement(contributor, "authoring_tool").text = "Pulso direct Blender Collada exporter"
    ET.SubElement(asset, "created").text = "2026-07-31T00:00:00Z"
    ET.SubElement(asset, "modified").text = "2026-07-31T00:00:00Z"
    ET.SubElement(asset, "unit", name="meter", meter="1")
    ET.SubElement(asset, "up_axis").text = "Z_UP"
    add_material_libraries(root, profiles)

    library_geometries = ET.SubElement(root, "library_geometries")
    geometry = ET.SubElement(
        library_geometries,
        "geometry",
        id="pulso_scene_geometry",
        name="Pulso disaster visual",
    )
    mesh_element = ET.SubElement(geometry, "mesh")
    add_source(mesh_element, "pulso_positions", positions, ("X", "Y", "Z"))
    add_source(mesh_element, "pulso_normals", normals, ("X", "Y", "Z"))
    add_source(mesh_element, "pulso_uvs", uvs, ("S", "T"))
    vertices = ET.SubElement(mesh_element, "vertices", id="pulso_vertices")
    ET.SubElement(vertices, "input", semantic="POSITION", source="#pulso_positions")
    for material_index in sorted(indices_by_material):
        profile = profiles[material_index]
        packed = indices_by_material[material_index]
        triangles = ET.SubElement(
            mesh_element,
            "triangles",
            material=profile["symbol"],
            count=str(len(packed) // 9),
        )
        ET.SubElement(triangles, "input", semantic="VERTEX", source="#pulso_vertices", offset="0")
        ET.SubElement(triangles, "input", semantic="NORMAL", source="#pulso_normals", offset="1")
        ET.SubElement(
            triangles,
            "input",
            semantic="TEXCOORD",
            source="#pulso_uvs",
            offset="2",
            set="0",
        )
        ET.SubElement(triangles, "p").text = wrapped_values(
            packed, per_line=24
        )

    visual_scenes = ET.SubElement(root, "library_visual_scenes")
    visual_scene = ET.SubElement(
        visual_scenes, "visual_scene", id="pulso_visual_scene", name="Pulso visual scene"
    )
    node = ET.SubElement(visual_scene, "node", id="pulso_scene_node", name="Pulso scene")
    instance = ET.SubElement(node, "instance_geometry", url="#pulso_scene_geometry")
    bind_material = ET.SubElement(instance, "bind_material")
    common = ET.SubElement(bind_material, "technique_common")
    for profile in profiles:
        instance_material = ET.SubElement(
            common,
            "instance_material",
            symbol=profile["symbol"],
            target=f"#{profile['id']}",
        )
        ET.SubElement(
            instance_material,
            "bind_vertex_input",
            semantic="UVMap",
            input_semantic="TEXCOORD",
            input_set="0",
        )
    scene = ET.SubElement(root, "scene")
    ET.SubElement(scene, "instance_visual_scene", url="#pulso_visual_scene")

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    ET.indent(root, space="  ")
    ET.ElementTree(root).write(
        OUTPUT_DAE, encoding="utf-8", xml_declaration=True, short_empty_elements=True
    )
    triangle_count = sum(len(values) // 9 for values in indices_by_material.values())
    report = {
        "path": str(OUTPUT_DAE.relative_to(PROJECT)),
        "bytes": OUTPUT_DAE.stat().st_size,
        "sha256": sha256(OUTPUT_DAE),
        "objects": len(objects),
        "positions": len(positions),
        "normals": len(normals),
        "uvs": len(uvs),
        "triangles": triangle_count,
        "material_groups": len(indices_by_material),
        "materials": len(profiles),
        "textured_materials": sum(profile["texture"] is not None for profile in profiles),
        "colour_materials": sum(profile["texture"] is None for profile in profiles),
        "bounds_min_m": [round(float(value), 6) for value in bounds_min],
        "bounds_max_m": [round(float(value), 6) for value in bounds_max],
    }
    print("PULSO_COLLADA_EXPORT_OK")
    print(json.dumps(report, indent=2))


main()
