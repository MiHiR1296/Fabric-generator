"""Export the parametric weave object as a GLB-friendly evaluated mesh.

This script is meant to be run by Blender, not by system Python.

Example:

    /Applications/Blender.app/Contents/MacOS/Blender \
      -b Codex_ParametricWeave.blend \
      --python scripts/export_parametric_weave_glb.py -- \
      --output GLB/parametric_weave.glb

Pipeline:

1. Evaluate the live `ParametricWeave` object, including geometry nodes.
2. Duplicate it as a real mesh so the live parametric object is untouched.
3. Copy the geometry-node `uv_scaled` FLOAT2 attribute into a real UV map.
4. Convert the Blender-only yarn material setup into simple glTF materials.
5. Export only the duplicate as `.glb`.

The default material mode, `source-atlas`, is usually the best first try for
this project. It preserves the existing yarn texture sampling by using the new
UV map and turns UDIM/split alpha inputs into ordinary PNG textures. Use
`--material-mode bake` if a material graph cannot be converted directly.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

import bpy


DEFAULT_OBJECT_NAME = "ParametricWeave"
DEFAULT_UV_ATTRIBUTE = "uv_scaled"
DEFAULT_UV_MAP = "UVMap"
DEFAULT_EXPORT_OBJECT = "ParametricWeave_GLB_Export"
DEFAULT_TEXTURE_SIZE = 4096
STATUS_JSON: Path | None = None


class ExportError(RuntimeError):
    """Raised for expected export-prep failures with actionable messages."""


def parse_args() -> argparse.Namespace:
    argv = sys.argv
    passthrough = argv[argv.index("--") + 1 :] if "--" in argv else []
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--object", default=DEFAULT_OBJECT_NAME, help="Source object to evaluate.")
    parser.add_argument("--output", required=True, help="Output .glb path.")
    parser.add_argument(
        "--uv-attribute",
        default=DEFAULT_UV_ATTRIBUTE,
        help="Evaluated mesh FLOAT2/vector attribute to copy into a real UV map.",
    )
    parser.add_argument("--uv-map", default=DEFAULT_UV_MAP, help="Real UV map name for GLB export.")
    parser.add_argument(
        "--export-object",
        default=DEFAULT_EXPORT_OBJECT,
        help="Temporary evaluated mesh object name.",
    )
    parser.add_argument(
        "--material-mode",
        choices=("source-atlas", "bake", "keep"),
        default="source-atlas",
        help=(
            "source-atlas converts FabricStudio image/UDIM nodes to simple glTF "
            "materials; bake uses Cycles diffuse+alpha baking; keep leaves "
            "materials untouched for mesh/UV diagnostics."
        ),
    )
    parser.add_argument(
        "--texture-size",
        type=int,
        default=DEFAULT_TEXTURE_SIZE,
        help="Maximum generated texture dimension for source-atlas and bake modes.",
    )
    parser.add_argument("--bake-samples", type=int, default=64, help="Cycles samples for bake mode.")
    parser.add_argument("--bake-margin", type=int, default=16, help="Bake image margin in pixels.")
    parser.add_argument(
        "--bake-uv-map",
        default="BakeUV",
        help="Wrapped U UV map used only for bake mode.",
    )
    parser.add_argument(
        "--decimate-ratio",
        type=float,
        default=1.0,
        help="Optional export decimation ratio in (0, 1]. Applied to duplicate only.",
    )
    parser.add_argument(
        "--keep-export-object",
        action="store_true",
        help="Leave the temporary export object in the scene after exporting.",
    )
    parser.add_argument(
        "--status-json",
        help="Optional status JSON path to update at each export phase.",
    )
    return parser.parse_args(passthrough)


def info(message: str) -> None:
    print(f"[weave-glb] {message}")
    if STATUS_JSON is not None:
        payload = {
            "status": "running",
            "message": message,
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        STATUS_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def abspath(path: str | Path) -> Path:
    raw = str(path)
    if raw.startswith("//"):
        return Path(bpy.path.abspath(raw)).resolve()
    return Path(raw).expanduser().resolve()


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
        raise ExportError(f"Could not build evaluated mesh from {source_name!r}")

    mesh.name = f"{export_name}Mesh"
    export_obj = bpy.data.objects.new(export_name, mesh)
    export_obj.matrix_world = source.matrix_world.copy()
    bpy.context.scene.collection.objects.link(export_obj)

    for material in mesh.materials:
        if material is not None:
            material.use_fake_user = True

    info(
        "evaluated mesh created: "
        f"{len(mesh.vertices):,} verts, {len(mesh.polygons):,} faces"
    )
    return export_obj


def clone_material_slots(obj: bpy.types.Object, suffix: str = "_GLBSource") -> None:
    """Copy materials on the export object so source scene materials stay untouched."""

    copied: dict[str, bpy.types.Material] = {}
    for slot in obj.material_slots:
        material = slot.material
        if material is None:
            continue
        if material.name not in copied:
            clone = material.copy()
            clone.name = f"{material.name}{suffix}"
            copied[material.name] = clone
        slot.material = copied[material.name]


def attribute_value_2d(mesh: bpy.types.Mesh, attribute: bpy.types.Attribute, polygon, loop_index: int) -> tuple[float, float]:
    domain = getattr(attribute, "domain", "")
    if domain == "POINT":
        data_index = mesh.loops[loop_index].vertex_index
    elif domain in {"CORNER", "FACE_CORNER"}:
        data_index = loop_index
    elif domain == "FACE":
        data_index = polygon.index
    else:
        raise ExportError(
            f"Unsupported attribute domain for {attribute.name!r}: {domain!r}. "
            "Expected POINT, FACE_CORNER/CORNER, or FACE."
        )

    item = attribute.data[data_index]
    if hasattr(item, "vector"):
        vector = item.vector
        return float(vector[0]), float(vector[1])
    if hasattr(item, "color"):
        color = item.color
        return float(color[0]), float(color[1])
    if hasattr(item, "value"):
        value = float(item.value)
        return value, 0.0
    raise ExportError(f"Attribute {attribute.name!r} does not expose vector/color/value data.")


def copy_attribute_to_uv_map(
    mesh: bpy.types.Mesh,
    attribute_name: str,
    uv_map_name: str,
    *,
    wrap_u: bool = False,
    wrap_v: bool = False,
) -> bpy.types.MeshUVLoopLayer:
    attribute = mesh.attributes.get(attribute_name)
    if attribute is None:
        names = ", ".join(sorted(attr.name for attr in mesh.attributes))
        raise ExportError(
            f"Evaluated mesh is missing attribute {attribute_name!r}. "
            f"Available attributes: {names or '(none)'}"
        )

    uv_layer = mesh.uv_layers.get(uv_map_name) or mesh.uv_layers.new(name=uv_map_name)
    if getattr(attribute, "domain", "") == "POINT" and getattr(attribute, "data_type", "") == "FLOAT2":
        copy_point_float2_attribute_to_uv_layer(mesh, attribute, uv_layer, wrap_u=wrap_u, wrap_v=wrap_v)
    else:
        info(
            f"using slow UV copy path for {attribute.name!r} "
            f"({getattr(attribute, 'domain', '')}/{getattr(attribute, 'data_type', '')})"
        )
        for polygon in mesh.polygons:
            for loop_index in polygon.loop_indices:
                u, v = attribute_value_2d(mesh, attribute, polygon, loop_index)
                if wrap_u:
                    u = u - math.floor(u)
                if wrap_v:
                    v = v - math.floor(v)
                uv_layer.data[loop_index].uv = (u, v)

    mesh.uv_layers.active = uv_layer
    try:
        uv_layer.active_render = True
    except Exception:
        pass
    mesh.update()
    mode = "wrapped U" if wrap_u else "raw"
    info(f"copied {attribute_name!r} into real UV map {uv_map_name!r} ({mode})")
    return uv_layer


def copy_point_float2_attribute_to_uv_layer(
    mesh: bpy.types.Mesh,
    attribute: bpy.types.Attribute,
    uv_layer: bpy.types.MeshUVLoopLayer,
    *,
    wrap_u: bool = False,
    wrap_v: bool = False,
) -> None:
    import numpy as np

    vertex_count = len(attribute.data)
    loop_count = len(mesh.loops)
    info(f"bulk-copying {attribute.name!r}: {vertex_count:,} point UVs -> {loop_count:,} loop UVs")

    point_uvs = np.empty(vertex_count * 2, dtype=np.float32)
    attribute.data.foreach_get("vector", point_uvs)
    point_uvs = point_uvs.reshape((vertex_count, 2))

    loop_vertex_indices = np.empty(loop_count, dtype=np.int32)
    mesh.loops.foreach_get("vertex_index", loop_vertex_indices)

    loop_uvs = point_uvs[loop_vertex_indices]
    if wrap_u or wrap_v:
        loop_uvs = loop_uvs.copy()
        if wrap_u:
            loop_uvs[:, 0] = loop_uvs[:, 0] - np.floor(loop_uvs[:, 0])
        if wrap_v:
            loop_uvs[:, 1] = loop_uvs[:, 1] - np.floor(loop_uvs[:, 1])

    uv_layer.data.foreach_set("uv", np.ascontiguousarray(loop_uvs).ravel())


def apply_decimate(obj: bpy.types.Object, ratio: float) -> None:
    if ratio >= 1.0:
        return
    if ratio <= 0.0:
        raise ExportError("--decimate-ratio must be greater than 0")
    bpy.ops.object.select_all(action="DESELECT")
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    modifier = obj.modifiers.new("GLB_Decimate", "DECIMATE")
    modifier.ratio = ratio
    bpy.ops.object.modifier_apply(modifier=modifier.name)
    info(f"decimated export mesh with ratio {ratio:g}")


def image_paths(image: bpy.types.Image) -> list[Path]:
    if image is None:
        return []

    filepath = bpy.path.abspath(image.filepath or "")
    if getattr(image, "source", None) == "TILED":
        tile_numbers = sorted(tile.number for tile in image.tiles)
        paths = []
        for number in tile_numbers:
            if "<UDIM>" in filepath:
                candidate = Path(filepath.replace("<UDIM>", str(number)))
            elif "1001" in filepath:
                candidate = Path(filepath.replace("1001", str(number), 1))
            else:
                candidate = Path(filepath)
            if candidate.exists():
                paths.append(candidate.resolve())
        return paths

    path = Path(filepath)
    return [path.resolve()] if path.exists() else []


def find_image_node(material: bpy.types.Material, preferred_names: tuple[str, ...]) -> bpy.types.Node | None:
    if material is None or not material.use_nodes:
        return None
    nodes = material.node_tree.nodes
    for name in preferred_names:
        node = nodes.get(name)
        if node is not None and getattr(node, "image", None) is not None:
            return node
    for node in nodes:
        if node.bl_idname == "ShaderNodeTexImage" and getattr(node, "image", None) is not None:
            return node
    return None


def find_alpha_node(material: bpy.types.Material, diffuse_node: bpy.types.Node | None) -> bpy.types.Node | None:
    if material is None or not material.use_nodes:
        return None
    node = material.node_tree.nodes.get("FabricStudioAlphaNode")
    if node is not None and getattr(node, "image", None) is not None:
        return node
    for candidate in material.node_tree.nodes:
        if candidate.bl_idname != "ShaderNodeTexImage":
            continue
        if getattr(candidate, "image", None) is None:
            continue
        if diffuse_node is not None and candidate == diffuse_node:
            continue
        name = f"{candidate.name} {candidate.label}".lower()
        if "alpha" in name or "opacity" in name:
            return candidate
    return None


def material_has_colour_id(material: bpy.types.Material) -> bool:
    if material is None or not material.use_nodes:
        return False
    for node in material.node_tree.nodes:
        if node.bl_idname == "ShaderNodeAttribute" and getattr(node, "attribute_name", "") == "colour_id":
            return True
    return False


def principled_base_color(material: bpy.types.Material) -> tuple[float, float, float, float]:
    if material is not None and material.use_nodes:
        for node in material.node_tree.nodes:
            if node.bl_idname == "ShaderNodeBsdfPrincipled" and "Base Color" in node.inputs:
                value = node.inputs["Base Color"].default_value
                return (float(value[0]), float(value[1]), float(value[2]), float(value[3]))
    if material is not None:
        value = material.diffuse_color
        return (float(value[0]), float(value[1]), float(value[2]), float(value[3]))
    return (0.72, 0.72, 0.72, 1.0)


def load_scaled_pixels(
    path: Path,
    width: int,
    height: int,
    *,
    colorspace: str,
) -> list[float]:
    image = bpy.data.images.load(str(path), check_existing=False)
    try:
        image.colorspace_settings.name = colorspace
    except Exception:
        pass
    if tuple(image.size) != (width, height):
        image.scale(width, height)
    pixels = list(image.pixels)
    bpy.data.images.remove(image)
    return pixels


def compute_scaled_size(paths: list[Path], max_size: int) -> tuple[int, int]:
    if not paths:
        return (max_size, max_size)
    probe = bpy.data.images.load(str(paths[0]), check_existing=False)
    try:
        source_w, source_h = int(probe.size[0]), int(probe.size[1])
    finally:
        bpy.data.images.remove(probe)

    tile_count = max(1, len(paths))
    max_size = max(64, int(max_size))
    scale = min(1.0, max_size / max(source_w * tile_count, source_h, 1))
    tile_w = max(1, int(round(source_w * scale)))
    tile_h = max(1, int(round(source_h * scale)))
    return tile_w, tile_h


def create_rgba_texture_from_sources(
    material: bpy.types.Material,
    output_dir: Path,
    max_size: int,
) -> bpy.types.Image | None:
    diffuse_node = find_image_node(material, ("FabricStudioDiffuseNode",))
    if diffuse_node is None:
        return None
    alpha_node = find_alpha_node(material, diffuse_node)

    diffuse_paths = image_paths(diffuse_node.image)
    alpha_paths = image_paths(alpha_node.image) if alpha_node is not None else []
    if not diffuse_paths:
        return None
    if alpha_paths and len(alpha_paths) != len(diffuse_paths):
        info(
            f"alpha tile count for {material.name!r} does not match diffuse; "
            "falling back to diffuse alpha"
        )
        alpha_paths = []

    tile_w, tile_h = compute_scaled_size(diffuse_paths, max_size)
    width = tile_w * len(diffuse_paths)
    height = tile_h
    pixels = [0.0] * (width * height * 4)

    for tile_index, diffuse_path in enumerate(diffuse_paths):
        diffuse_pixels = load_scaled_pixels(diffuse_path, tile_w, tile_h, colorspace="sRGB")
        alpha_pixels = None
        if alpha_paths:
            alpha_pixels = load_scaled_pixels(alpha_paths[tile_index], tile_w, tile_h, colorspace="Non-Color")

        for y in range(tile_h):
            dst_x0 = tile_index * tile_w
            for x in range(tile_w):
                src = (y * tile_w + x) * 4
                dst = (y * width + dst_x0 + x) * 4
                pixels[dst] = diffuse_pixels[src]
                pixels[dst + 1] = diffuse_pixels[src + 1]
                pixels[dst + 2] = diffuse_pixels[src + 2]
                if alpha_pixels is not None:
                    pixels[dst + 3] = alpha_pixels[src]
                else:
                    pixels[dst + 3] = diffuse_pixels[src + 3]

    image_name = f"{safe_name(material.name)}_glb_rgba"
    image = bpy.data.images.new(image_name, width=width, height=height, alpha=True)
    image.pixels.foreach_set(pixels)
    image.update()
    try:
        image.colorspace_settings.name = "sRGB"
    except Exception:
        pass
    output_path = output_dir / f"{image_name}.png"
    image.filepath_raw = str(output_path)
    image.file_format = "PNG"
    image.save()
    info(f"created portable material texture {output_path.name} ({width}x{height})")
    return image


def safe_name(value: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in value)
    return safe.strip("_")[:80] or "material"


def create_simple_material(
    name: str,
    uv_map_name: str,
    *,
    image: bpy.types.Image | None = None,
    base_color: tuple[float, float, float, float] | None = None,
    alpha: bool = True,
) -> bpy.types.Material:
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()

    output = nodes.new("ShaderNodeOutputMaterial")
    output.location = (520, 0)
    shader = nodes.new("ShaderNodeBsdfPrincipled")
    shader.location = (260, 0)
    if base_color is not None and "Base Color" in shader.inputs:
        shader.inputs["Base Color"].default_value = base_color
    if "Roughness" in shader.inputs:
        shader.inputs["Roughness"].default_value = 0.72
    if "Alpha" in shader.inputs:
        shader.inputs["Alpha"].default_value = 1.0

    if image is not None:
        uv_node = nodes.new("ShaderNodeUVMap")
        uv_node.location = (-520, 0)
        uv_node.uv_map = uv_map_name
        tex = nodes.new("ShaderNodeTexImage")
        tex.location = (-260, 0)
        tex.image = image
        tex.extension = "REPEAT"
        try:
            tex.interpolation = "Linear"
        except Exception:
            pass
        links.new(uv_node.outputs["UV"], tex.inputs["Vector"])
        links.new(tex.outputs["Color"], shader.inputs["Base Color"])
        if alpha and "Alpha" in shader.inputs and "Alpha" in tex.outputs:
            links.new(tex.outputs["Alpha"], shader.inputs["Alpha"])

    links.new(shader.outputs["BSDF"], output.inputs["Surface"])

    if alpha:
        material.blend_method = "BLEND"
        material.use_screen_refraction = False
        if hasattr(material, "surface_render_method"):
            material.surface_render_method = "BLENDED"
    return material


def convert_materials_from_sources(
    obj: bpy.types.Object,
    uv_map_name: str,
    texture_dir: Path,
    max_size: int,
) -> None:
    converted: dict[str, bpy.types.Material] = {}
    for slot in obj.material_slots:
        material = slot.material
        if material is None:
            continue
        if material.name in converted:
            slot.material = converted[material.name]
            continue
        if material_has_colour_id(material):
            raise ExportError(
                f"Material {material.name!r} uses the colour_id attribute. "
                "Use --material-mode bake for this atlas-style material."
            )

        image = create_rgba_texture_from_sources(material, texture_dir, max_size)
        if image is not None:
            simple = create_simple_material(
                f"{safe_name(material.name)}_GLB",
                uv_map_name,
                image=image,
                alpha=True,
            )
        else:
            simple = create_simple_material(
                f"{safe_name(material.name)}_GLB",
                uv_map_name,
                base_color=principled_base_color(material),
                alpha=False,
            )
            info(f"material {material.name!r} had no image texture; exported as flat color")
        converted[material.name] = simple
        slot.material = simple


def requires_bake_for_source_atlas(obj: bpy.types.Object) -> bool:
    for material in unique_slot_materials(obj):
        if material_has_colour_id(material):
            info(
                f"material {material.name!r} reads colour_id; "
                "using bake mode so the attribute-driven atlas selection is preserved"
            )
            return True
    return False


def configure_bake_scene(samples: int) -> None:
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    try:
        scene.cycles.samples = max(1, int(samples))
        scene.cycles.use_denoising = False
    except Exception:
        pass
    scene.render.bake.target = "IMAGE_TEXTURES"
    scene.render.bake.use_pass_direct = False
    scene.render.bake.use_pass_indirect = False
    scene.render.bake.use_pass_color = True


def add_bake_target(material: bpy.types.Material, image: bpy.types.Image) -> bpy.types.Node:
    nodes = material.node_tree.nodes
    node = nodes.new("ShaderNodeTexImage")
    node.name = "GLB_Bake_Target"
    node.image = image
    node.select = True
    nodes.active = node
    return node


def unique_slot_materials(obj: bpy.types.Object) -> list[bpy.types.Material]:
    materials: list[bpy.types.Material] = []
    seen: set[str] = set()
    for slot in obj.material_slots:
        material = slot.material
        if material is None or material.name in seen:
            continue
        seen.add(material.name)
        materials.append(material)
    return materials


def active_output_node(material: bpy.types.Material) -> bpy.types.Node | None:
    for node in material.node_tree.nodes:
        if node.bl_idname == "ShaderNodeOutputMaterial" and getattr(node, "is_active_output", False):
            return node
    for node in material.node_tree.nodes:
        if node.bl_idname == "ShaderNodeOutputMaterial":
            return node
    return None


def alpha_source_socket(material: bpy.types.Material):
    if not material.use_nodes:
        return None, 1.0
    output = active_output_node(material)
    if output is not None and "Surface" in output.inputs and output.inputs["Surface"].is_linked:
        source = output.inputs["Surface"].links[0].from_node
        if source.bl_idname == "ShaderNodeMixShader":
            return source.inputs[0], None
    for node in material.node_tree.nodes:
        if node.bl_idname == "ShaderNodeBsdfPrincipled" and "Alpha" in node.inputs:
            socket = node.inputs["Alpha"]
            default = float(socket.default_value) if not socket.is_linked else None
            return socket, default
    return None, 1.0


def switch_material_to_alpha_emission(material: bpy.types.Material):
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    output = active_output_node(material)
    if output is None or "Surface" not in output.inputs:
        return None

    surface = output.inputs["Surface"]
    original_links = [(link.from_socket, link.to_socket) for link in list(surface.links)]
    for link in list(surface.links):
        links.remove(link)

    emission = nodes.new("ShaderNodeEmission")
    emission.name = "GLB_Alpha_Bake_Emission"
    emission.location = (80, -260)
    source_socket, default_alpha = alpha_source_socket(material)
    if source_socket is not None and source_socket.is_linked:
        links.new(source_socket.links[0].from_socket, emission.inputs["Color"])
    elif source_socket is not None and default_alpha is None:
        links.new(source_socket, emission.inputs["Color"])
    else:
        alpha_value = 1.0 if default_alpha is None else default_alpha
        emission.inputs["Color"].default_value = (alpha_value, alpha_value, alpha_value, 1.0)
    links.new(emission.outputs[0], surface)
    return output, original_links, emission


def restore_alpha_emission(material: bpy.types.Material, state) -> None:
    if state is None:
        return
    output, original_links, emission = state
    links = material.node_tree.links
    surface = output.inputs["Surface"]
    for link in list(surface.links):
        links.remove(link)
    for from_socket, to_socket in original_links:
        try:
            links.new(from_socket, to_socket)
        except Exception:
            pass
    material.node_tree.nodes.remove(emission)


def combine_alpha(base_image: bpy.types.Image, alpha_image: bpy.types.Image, output_path: Path) -> None:
    base = list(base_image.pixels)
    alpha = list(alpha_image.pixels)
    pixel_count = min(len(base), len(alpha)) // 4
    for index in range(pixel_count):
        base[index * 4 + 3] = alpha[index * 4]
    base_image.pixels.foreach_set(base)
    base_image.update()
    base_image.filepath_raw = str(output_path)
    base_image.file_format = "PNG"
    base_image.save()


def bake_materials(
    obj: bpy.types.Object,
    uv_map_name: str,
    texture_dir: Path,
    texture_size: int,
    samples: int,
    margin: int,
) -> None:
    configure_bake_scene(samples)
    materials = unique_slot_materials(obj)
    if not materials:
        return

    base_images: dict[str, bpy.types.Image] = {}
    alpha_images: dict[str, bpy.types.Image] = {}

    for material in materials:
        image_name = f"{safe_name(material.name)}_baked_rgba"
        base_image = bpy.data.images.new(image_name, width=texture_size, height=texture_size, alpha=True)
        base_image.colorspace_settings.name = "sRGB"
        base_images[material.name] = base_image
        add_bake_target(material, base_image)

    select_only(obj)
    info(f"baking diffuse color for {len(materials)} material(s)")
    bpy.ops.object.bake(type="DIFFUSE", margin=margin, use_clear=True)

    alpha_states = {}
    for material in materials:
        image_name = f"{safe_name(material.name)}_baked_alpha"
        alpha_image = bpy.data.images.new(image_name, width=texture_size, height=texture_size, alpha=True)
        alpha_image.colorspace_settings.name = "Non-Color"
        alpha_images[material.name] = alpha_image
        add_bake_target(material, alpha_image)
        alpha_states[material.name] = switch_material_to_alpha_emission(material)

    info(f"baking alpha for {len(materials)} material(s)")
    bpy.ops.object.bake(type="EMIT", margin=margin, use_clear=True)

    for material in materials:
        restore_alpha_emission(material, alpha_states.get(material.name))

    converted: dict[str, bpy.types.Material] = {}
    for material in materials:
        output_path = texture_dir / f"{safe_name(material.name)}_baked_rgba.png"
        combine_alpha(base_images[material.name], alpha_images[material.name], output_path)
        simple = create_simple_material(
            f"{safe_name(material.name)}_GLB",
            uv_map_name,
            image=base_images[material.name],
            alpha=True,
        )
        converted[material.name] = simple
        info(f"created baked material texture {output_path.name}")

    for slot in obj.material_slots:
        material = slot.material
        if material is not None and material.name in converted:
            slot.material = converted[material.name]


def select_only(obj: bpy.types.Object) -> None:
    bpy.ops.object.mode_set(mode="OBJECT") if bpy.ops.object.mode_set.poll() else None
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def export_glb(obj: bpy.types.Object, output_path: Path) -> None:
    select_only(obj)
    kwargs = {
        "filepath": str(output_path),
        "export_format": "GLB",
        "use_selection": True,
        "export_texcoords": True,
        "export_normals": True,
        "export_materials": "EXPORT",
        "export_apply": True,
    }
    try:
        bpy.ops.export_scene.gltf(**kwargs)
    except TypeError:
        for optional_key in ("export_texcoords", "export_normals", "export_materials", "export_apply"):
            kwargs.pop(optional_key, None)
        bpy.ops.export_scene.gltf(**kwargs)
    info(f"wrote {output_path}")


def main() -> None:
    global STATUS_JSON
    args = parse_args()
    STATUS_JSON = abspath(args.status_json) if args.status_json else None
    output_path = abspath(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    texture_dir = output_path.parent / f"{output_path.stem}_textures"
    texture_dir.mkdir(parents=True, exist_ok=True)

    export_obj = evaluated_mesh_object(args.object, args.export_object)
    clone_material_slots(export_obj)

    apply_decimate(export_obj, args.decimate_ratio)

    copy_attribute_to_uv_map(export_obj.data, args.uv_attribute, args.uv_map)
    export_uv_map = args.uv_map

    if args.material_mode == "bake":
        copy_attribute_to_uv_map(
            export_obj.data,
            args.uv_attribute,
            args.bake_uv_map,
            wrap_u=True,
        )
        export_uv_map = args.bake_uv_map

    material_mode = args.material_mode
    if material_mode == "source-atlas" and requires_bake_for_source_atlas(export_obj):
        material_mode = "bake"
        copy_attribute_to_uv_map(
            export_obj.data,
            args.uv_attribute,
            args.bake_uv_map,
            wrap_u=True,
        )
        export_uv_map = args.bake_uv_map

    if material_mode == "source-atlas":
        convert_materials_from_sources(export_obj, export_uv_map, texture_dir, args.texture_size)
    elif material_mode == "bake":
        bake_materials(
            export_obj,
            export_uv_map,
            texture_dir,
            args.texture_size,
            args.bake_samples,
            args.bake_margin,
        )
    else:
        info("keeping source materials; this is useful for UV diagnostics but may not be portable")

    export_glb(export_obj, output_path)

    if not args.keep_export_object:
        mesh = export_obj.data
        bpy.data.objects.remove(export_obj, do_unlink=True)
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)


if __name__ == "__main__":
    try:
        main()
    except ExportError as exc:
        print(f"[weave-glb] ERROR: {exc}", file=sys.stderr)
        sys.exit(2)
