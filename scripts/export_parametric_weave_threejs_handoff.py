"""Export ParametricWeave as a Three.js shader handoff package.

Run inside Blender:

    /Applications/Blender.app/Contents/MacOS/Blender \
      -b Codex_ParametricWeave.blend \
      --python scripts/export_parametric_weave_threejs_handoff.py -- \
      --output GLB/parametric_weave_threejs.glb

The GLB intentionally contains geometry and mapping data, not the yarn texture
images. The sidecar manifest points Three.js at the original segmented/UDIM
texture files and documents the sampling math used by the Blender material.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path
from typing import Any

import bpy


DEFAULT_OBJECT_NAME = "ParametricWeave"
DEFAULT_EXPORT_OBJECT_NAME = "ParametricWeave_ThreeJS_Handoff"
DEFAULT_UV_ATTRIBUTE = "uv_scaled"
DEFAULT_UV_MAP = "UVMap"
DEFAULT_SHADER_ATTRIBUTES = (
    "material_id",
    "thread_kind",
    "u_along",
    "v_around",
    "pw_strand_id",
    "colour_id",
)

STATUS_JSON: Path | None = None


class ExportError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    argv = sys.argv
    passthrough = argv[argv.index("--") + 1 :] if "--" in argv else []
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--object", default=DEFAULT_OBJECT_NAME)
    parser.add_argument("--output", required=True)
    parser.add_argument("--manifest", help="Defaults to output path with .manifest.json suffix.")
    parser.add_argument("--status-json")
    parser.add_argument("--export-object", default=DEFAULT_EXPORT_OBJECT_NAME)
    parser.add_argument("--uv-attribute", default=DEFAULT_UV_ATTRIBUTE)
    parser.add_argument("--uv-map", default=DEFAULT_UV_MAP)
    parser.add_argument(
        "--shader-attribute",
        action="append",
        dest="shader_attributes",
        help="Evaluated mesh attribute to duplicate as a glTF custom _attribute. Can be repeated.",
    )
    parser.add_argument(
        "--decimate-ratio",
        type=float,
        default=1.0,
        help="Optional diagnostic decimation. Leave at 1.0 for the full-fidelity handoff.",
    )
    parser.add_argument("--keep-export-object", action="store_true")
    return parser.parse_args(passthrough)


def abspath(path: str | Path) -> Path:
    raw = str(path)
    if raw.startswith("//"):
        return Path(bpy.path.abspath(raw)).resolve()
    return Path(raw).expanduser().resolve()


def write_status(message: str, **extra: Any) -> None:
    print(f"[threejs-handoff] {message}")
    if STATUS_JSON is None:
        return
    payload = {
        "status": extra.pop("status", "running"),
        "message": message,
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        **extra,
    }
    STATUS_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def remove_object_if_exists(name: str) -> None:
    obj = bpy.data.objects.get(name)
    if obj is None:
        return
    mesh = obj.data if getattr(obj, "type", None) == "MESH" else None
    bpy.data.objects.remove(obj, do_unlink=True)
    if mesh is not None and mesh.users == 0:
        bpy.data.meshes.remove(mesh)


def evaluated_mesh_object(source_name: str, export_name: str) -> bpy.types.Object:
    source = bpy.data.objects.get(source_name)
    if source is None:
        raise ExportError(f"Source object not found: {source_name!r}")

    remove_object_if_exists(export_name)
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated = source.evaluated_get(depsgraph)
    mesh = bpy.data.meshes.new_from_object(
        evaluated,
        depsgraph=depsgraph,
        preserve_all_data_layers=True,
    )
    if mesh is None:
        raise ExportError(f"Could not evaluate mesh from {source_name!r}")

    mesh.name = f"{export_name}Mesh"
    obj = bpy.data.objects.new(export_name, mesh)
    obj.matrix_world = source.matrix_world.copy()
    bpy.context.scene.collection.objects.link(obj)
    write_status(
        f"evaluated mesh: {len(mesh.vertices):,} verts, {len(mesh.polygons):,} faces, {len(mesh.loops):,} loops",
        vertices=len(mesh.vertices),
        faces=len(mesh.polygons),
        loops=len(mesh.loops),
    )
    return obj


def copy_point_float2_to_uv(
    mesh: bpy.types.Mesh,
    attribute: bpy.types.Attribute,
    uv_layer: bpy.types.MeshUVLoopLayer,
) -> None:
    import numpy as np

    vertex_count = len(attribute.data)
    loop_count = len(mesh.loops)
    write_status(
        f"copying {attribute.name!r} into standard UV map: {vertex_count:,} point UVs -> {loop_count:,} loop UVs"
    )
    point_uvs = np.empty(vertex_count * 2, dtype=np.float32)
    attribute.data.foreach_get("vector", point_uvs)
    point_uvs = point_uvs.reshape((vertex_count, 2))

    loop_vertex_indices = np.empty(loop_count, dtype=np.int32)
    mesh.loops.foreach_get("vertex_index", loop_vertex_indices)
    loop_uvs = point_uvs[loop_vertex_indices]
    uv_layer.data.foreach_set("uv", np.ascontiguousarray(loop_uvs).ravel())


def copy_attribute_to_uv_map(mesh: bpy.types.Mesh, attribute_name: str, uv_map_name: str) -> None:
    attribute = mesh.attributes.get(attribute_name)
    if attribute is None:
        raise ExportError(f"Missing evaluated UV attribute {attribute_name!r}")
    uv_layer = mesh.uv_layers.get(uv_map_name) or mesh.uv_layers.new(name=uv_map_name)
    if getattr(attribute, "domain", "") == "POINT" and getattr(attribute, "data_type", "") == "FLOAT2":
        copy_point_float2_to_uv(mesh, attribute, uv_layer)
    else:
        write_status(f"using slow UV copy path for {attribute_name!r}")
        for polygon in mesh.polygons:
            for loop_index in polygon.loop_indices:
                data_index = mesh.loops[loop_index].vertex_index if attribute.domain == "POINT" else loop_index
                value = attribute.data[data_index].vector
                uv_layer.data[loop_index].uv = (float(value[0]), float(value[1]))
    mesh.uv_layers.active = uv_layer
    try:
        uv_layer.active_render = True
    except Exception:
        pass
    mesh.update()


def data_prop_for_attribute(attribute: bpy.types.Attribute) -> tuple[str, int, str]:
    data_type = getattr(attribute, "data_type", "")
    if data_type in {"FLOAT", "INT", "BOOLEAN"}:
        return "value", 1, "FLOAT"
    if data_type == "FLOAT2":
        return "vector", 2, "FLOAT2"
    if data_type in {"FLOAT_VECTOR", "FLOAT_COLOR", "BYTE_COLOR"}:
        return "vector" if data_type == "FLOAT_VECTOR" else "color", 3 if data_type == "FLOAT_VECTOR" else 4, data_type
    raise ExportError(f"Unsupported shader attribute type {attribute.name!r}: {data_type}")


def copy_shader_attribute(mesh: bpy.types.Mesh, source_name: str) -> str | None:
    source = mesh.attributes.get(source_name)
    if source is None:
        return None

    target_name = "_" + source_name.lstrip("_")
    if mesh.attributes.get(target_name) is not None:
        mesh.attributes.remove(mesh.attributes[target_name])

    source_prop, width, target_type = data_prop_for_attribute(source)
    if target_type not in {"FLOAT", "FLOAT2", "FLOAT_VECTOR", "FLOAT_COLOR", "BYTE_COLOR"}:
        target_type = "FLOAT"

    target = mesh.attributes.new(target_name, target_type, source.domain)
    count = len(source.data)
    write_status(f"copying shader attribute {source_name!r} -> {target_name!r} ({source.domain}/{source.data_type})")

    if target_type == "FLOAT":
        import numpy as np

        values = np.empty(count, dtype=np.float32)
        source.data.foreach_get(source_prop, values)
        if getattr(source, "data_type", "") == "BOOLEAN":
            values = values.astype(np.float32)
        target.data.foreach_set("value", values)
        return target_name

    import numpy as np

    values = np.empty(count * width, dtype=np.float32)
    source.data.foreach_get(source_prop, values)
    target_prop, target_width, _ = data_prop_for_attribute(target)
    if target_width != width:
        adjusted = np.zeros(count * target_width, dtype=np.float32)
        reshaped = adjusted.reshape((count, target_width))
        reshaped[:, : min(width, target_width)] = values.reshape((count, width))[:, : min(width, target_width)]
        values = adjusted
    target.data.foreach_set(target_prop, values)
    return target_name


def apply_decimate(obj: bpy.types.Object, ratio: float) -> None:
    if ratio >= 1.0:
        return
    if ratio <= 0.0:
        raise ExportError("--decimate-ratio must be greater than 0")
    select_only(obj)
    modifier = obj.modifiers.new("ThreeJS_Handoff_Decimate", "DECIMATE")
    modifier.ratio = ratio
    write_status(f"applying diagnostic decimate ratio {ratio:g}")
    bpy.ops.object.modifier_apply(modifier=modifier.name)


def placeholder_material(name: str, index: int) -> bpy.types.Material:
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    material.diffuse_color = material_color(index)
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    shader = nodes.new("ShaderNodeBsdfPrincipled")
    shader.inputs["Base Color"].default_value = material.diffuse_color
    shader.inputs["Roughness"].default_value = 0.75
    links.new(shader.outputs["BSDF"], output.inputs["Surface"])
    return material


def material_color(index: int) -> tuple[float, float, float, float]:
    palette = [
        (0.76, 0.70, 0.62, 1.0),
        (0.52, 0.62, 0.78, 1.0),
        (0.67, 0.55, 0.72, 1.0),
        (0.54, 0.72, 0.61, 1.0),
    ]
    return palette[index % len(palette)]


def image_tile_paths(image: bpy.types.Image | None) -> list[Path]:
    if image is None:
        return []
    filepath = bpy.path.abspath(image.filepath or "")
    if not filepath:
        return []
    if getattr(image, "source", None) == "TILED":
        paths = []
        for tile in sorted(image.tiles, key=lambda item: item.number):
            if "<UDIM>" in filepath:
                candidate = Path(filepath.replace("<UDIM>", str(tile.number)))
            elif "1001" in filepath:
                candidate = Path(filepath.replace("1001", str(tile.number), 1))
            else:
                candidate = Path(filepath)
            if candidate.exists():
                paths.append(candidate.resolve())
        return paths
    path = Path(filepath)
    return [path.resolve()] if path.exists() else []


def image_node(material: bpy.types.Material, node_name: str) -> bpy.types.Node | None:
    if material is None or not material.use_nodes:
        return None
    node = material.node_tree.nodes.get(node_name)
    if node is not None and getattr(node, "image", None) is not None:
        return node
    return None


def relative_paths(paths: list[Path], base_dir: Path) -> list[str]:
    result = []
    for path in paths:
        try:
            result.append(Path(path).resolve().relative_to(base_dir.resolve()).as_posix())
        except Exception:
            result.append(Path(path).resolve().as_posix())
    return result


def image_info(image: bpy.types.Image | None) -> dict[str, Any] | None:
    if image is None:
        return None
    return {
        "name": image.name,
        "source": getattr(image, "source", None),
        "size": [int(image.size[0]), int(image.size[1])],
        "filepath": bpy.path.abspath(image.filepath or ""),
        "tiles": [tile.number for tile in getattr(image, "tiles", [])],
    }


def material_texture_manifest(material: bpy.types.Material, base_dir: Path) -> dict[str, Any]:
    diffuse = image_node(material, "FabricStudioDiffuseNode")
    alpha = image_node(material, "FabricStudioAlphaNode")
    normal_height = image_node(material, "FabricStudioNormalHeightNode")
    roughness_specular = image_node(material, "FabricStudioRoughnessSpecularNode")

    rgba_paths = image_tile_paths(diffuse.image if diffuse else None)
    alpha_paths = image_tile_paths(alpha.image if alpha else None)
    normal_height_paths = image_tile_paths(normal_height.image if normal_height else None)
    roughness_specular_paths = image_tile_paths(roughness_specular.image if roughness_specular else None)

    return {
        "material_name": material.name if material else None,
        "texture_mode": "udim_or_segmented_tiles" if len(rgba_paths) > 1 else "single_or_flat",
        "rgba": {
            "image": image_info(diffuse.image if diffuse else None),
            "paths": relative_paths(rgba_paths, base_dir),
        },
        "alpha": {
            "image": image_info(alpha.image if alpha else None),
            "paths": relative_paths(alpha_paths, base_dir),
        },
        "normal_height": {
            "image": image_info(normal_height.image if normal_height else None),
            "paths": relative_paths(normal_height_paths, base_dir),
        },
        "roughness_specular": {
            "image": image_info(roughness_specular.image if roughness_specular else None),
            "paths": relative_paths(roughness_specular_paths, base_dir),
        },
    }


def replace_materials_with_placeholders(obj: bpy.types.Object) -> list[dict[str, Any]]:
    mesh = obj.data
    old_materials = [slot.material for slot in obj.material_slots]
    used_source_slots = sorted(
        {
            int(poly.material_index)
            for poly in mesh.polygons
            if 0 <= int(poly.material_index) < max(1, len(old_materials))
        }
    )
    if not used_source_slots:
        used_source_slots = [0]

    source_to_gltf = {source_slot: gltf_index for gltf_index, source_slot in enumerate(used_source_slots)}
    for poly in mesh.polygons:
        poly.material_index = source_to_gltf.get(int(poly.material_index), 0)

    mesh.materials.clear()
    materials = []
    for gltf_index, source_slot in enumerate(used_source_slots):
        source = old_materials[source_slot] if source_slot < len(old_materials) else None
        source_name = source.name if source else f"Material_{source_slot + 1:02d}"
        placeholder = placeholder_material(f"ThreeJS_Handoff_{gltf_index + 1:02d}_{source_name}", gltf_index)
        mesh.materials.append(placeholder)
        materials.append(
            {
                "source_slot": source_slot,
                "gltf_material_index": gltf_index,
                "source_material": source,
            }
        )
    return materials


def build_manifest(
    *,
    output_path: Path,
    source_object: str,
    export_object: bpy.types.Object,
    exported_attributes: list[str],
    source_materials: list[dict[str, Any]],
    base_dir: Path,
) -> dict[str, Any]:
    mesh = export_object.data
    materials = []
    for entry in source_materials:
        source = entry["source_material"]
        materials.append(
            {
                "source_slot": entry["source_slot"],
                "gltf_material_index": entry["gltf_material_index"],
                "gltf_material_name": export_object.material_slots[entry["gltf_material_index"]].material.name,
                **material_texture_manifest(source, base_dir),
            }
        )

    return {
        "schema": "yarnseamless.threejs_handoff.v1",
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source_object": source_object,
        "glb": output_path.name,
        "mesh": {
            "vertices": len(mesh.vertices),
            "faces": len(mesh.polygons),
            "loops": len(mesh.loops),
            "uv_attribute": "uv",
            "uv_source_attribute": DEFAULT_UV_ATTRIBUTE,
            "custom_attributes": exported_attributes,
        },
        "shader_contract": {
            "uv": "geometry.attributes.uv contains Blender's final uv_scaled values.",
            "material_selection": "Use GLB primitive/material index first; _material_id is included when present for debugging.",
            "segmented_tile_sampling_glsl": [
                "float x = fract(vUv.x) * float(tileCount);",
                "int tileIndex = int(clamp(floor(x), 0.0, float(tileCount - 1)));",
                "vec2 tileUv = vec2(fract(x), vUv.y);",
                "vec4 yarn = texture(tileSamplers[tileIndex], tileUv);",
            ],
            "notes": [
                "The GLB intentionally uses placeholder materials. Replace them in Three.js.",
                "Original yarn textures remain external so the browser can load segmented tiles instead of one over-wide atlas.",
            ],
        },
        "materials": materials,
    }


def select_only(obj: bpy.types.Object) -> None:
    if bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def export_glb(obj: bpy.types.Object, output_path: Path) -> None:
    select_only(obj)
    kwargs = {
        "filepath": str(output_path),
        "export_format": "GLB",
        "use_selection": True,
        "export_materials": "EXPORT",
        "export_texcoords": True,
        "export_normals": True,
        "export_attributes": True,
        "export_apply": True,
    }
    write_status(f"exporting GLB to {output_path}")
    try:
        bpy.ops.export_scene.gltf(**kwargs)
    except TypeError:
        kwargs.pop("export_apply", None)
        bpy.ops.export_scene.gltf(**kwargs)


def main() -> None:
    global STATUS_JSON

    args = parse_args()
    output_path = abspath(args.output)
    manifest_path = abspath(args.manifest) if args.manifest else output_path.with_suffix(".manifest.json")
    STATUS_JSON = abspath(args.status_json) if args.status_json else None
    output_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    write_status("starting Three.js handoff export", output=str(output_path), manifest=str(manifest_path))
    export_obj = evaluated_mesh_object(args.object, args.export_object)
    apply_decimate(export_obj, args.decimate_ratio)
    copy_attribute_to_uv_map(export_obj.data, args.uv_attribute, args.uv_map)

    requested = args.shader_attributes or list(DEFAULT_SHADER_ATTRIBUTES)
    exported_attributes = []
    for attribute_name in requested:
        exported = copy_shader_attribute(export_obj.data, attribute_name)
        if exported:
            exported_attributes.append(exported)

    source_materials = replace_materials_with_placeholders(export_obj)
    export_glb(export_obj, output_path)

    manifest = build_manifest(
        output_path=output_path,
        source_object=args.object,
        export_object=export_obj,
        exported_attributes=exported_attributes,
        source_materials=source_materials,
        base_dir=manifest_path.parent,
    )
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    write_status(
        "Three.js handoff export finished",
        status="done",
        output=str(output_path),
        manifest=str(manifest_path),
        size_bytes=output_path.stat().st_size if output_path.exists() else 0,
    )

    if not args.keep_export_object:
        mesh = export_obj.data
        bpy.data.objects.remove(export_obj, do_unlink=True)
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)


if __name__ == "__main__":
    try:
        main()
    except ExportError as exc:
        write_status(str(exc), status="error")
        print(f"[threejs-handoff] ERROR: {exc}", file=sys.stderr)
        sys.exit(2)
