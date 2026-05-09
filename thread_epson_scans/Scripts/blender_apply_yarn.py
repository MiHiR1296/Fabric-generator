"""
blender_apply_yarn.py
=====================

Run inside Blender (Text Editor or via MCP execute_blender_code) to apply a
single yarn's meta.json values to the ParametricWeave.001 modifier:

    - Build / refresh a Material named after the yarn (rgb image -> Base
      Color, alpha image -> BSDF.Alpha, Mapping passthrough, Attribute
      reading 'uv_scaled' which is what the GN graph writes).
    - Assign that material to all four GN modifier Material slots.
    - Push Image Width Px + the four V-band sockets from meta.json into
      the modifier (with the fiber-band swap; see build_batch_index.py).
    - Leave Texture Scale U at the user-set multiplier.

Edit YARN below or pass via Blender's --python-expr.

The "uv_scaled" attribute is the FLOAT2 the GN writes into via
Store Named Attribute.002 (Combine XYZ.006 -> uv_scaled). Materials must
read this attribute -- a default "UVMap" attribute does NOT exist on the
GN-generated geometry, and reading it produces (0, 0) for every sample
which collapses the texture to a single constant color.
"""
from __future__ import annotations

import json
import os

import bpy

# --- pick yarn ---------------------------------------------------------------
YARN = "china_grey_matte20260422_15445317"

BATCH_INDEX = "/Users/mihirbotle/Desktop/Impetus/3D Fabric/thread_epson_scans/bands_out/_batch_index.json"
NODE_GROUP_NAME = "Parametric Weave knotty"
OBJECT_NAME = "ParametricWeave.001"


def load_image(path: str) -> bpy.types.Image:
    for img in bpy.data.images:
        if bpy.path.abspath(img.filepath) == path:
            return img
    return bpy.data.images.load(path)


def build_material(name: str, rgb_path: str, alpha_path: str) -> bpy.types.Material:
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()

    n_out  = nt.nodes.new("ShaderNodeOutputMaterial");   n_out.location  = ( 600,    0)
    n_bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled");   n_bsdf.location = ( 300,    0)
    n_rgb  = nt.nodes.new("ShaderNodeTexImage");         n_rgb.location  = (   0,    0)
    n_alp  = nt.nodes.new("ShaderNodeTexImage");         n_alp.location  = (   0, -300)
    n_map  = nt.nodes.new("ShaderNodeMapping");          n_map.location  = (-300,    0)
    n_attr = nt.nodes.new("ShaderNodeAttribute");        n_attr.location = (-600,    0)
    n_attr.attribute_name = "uv_scaled"
    n_attr.attribute_type = 'GEOMETRY'

    n_rgb.image = load_image(rgb_path)
    n_alp.image = load_image(alpha_path)
    n_alp.image.colorspace_settings.name = 'Non-Color'

    nt.links.new(n_attr.outputs["Vector"], n_map.inputs["Vector"])
    nt.links.new(n_map.outputs["Vector"],  n_rgb.inputs["Vector"])
    nt.links.new(n_map.outputs["Vector"],  n_alp.inputs["Vector"])
    nt.links.new(n_rgb.outputs["Color"],   n_bsdf.inputs["Base Color"])
    nt.links.new(n_alp.outputs["Color"],   n_bsdf.inputs["Alpha"])
    nt.links.new(n_bsdf.outputs["BSDF"],   n_out.inputs["Surface"])

    n_bsdf.inputs["Roughness"].default_value = 0.6
    n_bsdf.inputs["Metallic"].default_value = 0.0
    n_bsdf.inputs["Sheen Weight"].default_value = 0.2

    # Blender 4.2+: works for both Eevee Next and Cycles transparency.
    m.surface_render_method = 'DITHERED'
    return m


def apply_yarn(yarn: str) -> None:
    batch = json.load(open(BATCH_INDEX))
    info = batch[yarn]

    ng = bpy.data.node_groups[NODE_GROUP_NAME]
    obj = bpy.data.objects[OBJECT_NAME]
    mod = next(m for m in obj.modifiers if m.type == 'NODES' and m.node_group == ng)
    sock = {it.name: it.identifier
            for it in ng.interface.items_tree
            if it.item_type == 'SOCKET' and it.in_out == 'INPUT'}

    mat = build_material(yarn, info["rgb"], info["alpha"])
    for s in ("Material 1", "Material 2", "Material 3", "Material 4"):
        mod[sock[s]] = mat

    mod[sock["Image Width Px"]]        = float(info["image_width_px"])
    mod[sock["Image Core V Min"]]      = info["core_v_min"]
    mod[sock["Image Core V Max"]]      = info["core_v_max"]
    mod[sock["Image Fiber Top V Min"]] = info["fiber_bot_v_outer"]   # outer-bottom V
    mod[sock["Image Fiber Bot V Max"]] = info["fiber_top_v_outer"]   # outer-top V

    obj.update_tag()
    print(f"Applied yarn: {yarn}")


if __name__ == "__main__":
    apply_yarn(YARN)
