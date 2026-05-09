"""
blender_batch_render.py
=======================

Run inside Blender (Text Editor or via MCP). For every yarn in the batch
index, build/refresh its material, assign it to the GN modifier, push the
band metadata, and render a PNG into that yarn's bands_out folder.

Render output: bands_out/{yarn_name}/render.png

Settings (edit at the top): engine, resolution, samples. Camera + lighting
are taken from the current scene.

Side effects:
    - Each material is created (or reset) under the yarn name in bpy.data.materials.
    - Modifier sockets Material 1..4, Image Width Px, four V-band sockets
      get overwritten on every iteration.
    - After completion the modifier holds the LAST yarn's settings.
"""
from __future__ import annotations

import json
import os
import time

import bpy

from blender_apply_yarn import build_material  # type: ignore  # same dir on sys.path

# --- config ------------------------------------------------------------------
BATCH_INDEX = "/Users/mihirbotle/Desktop/Impetus/3D Fabric/thread_epson_scans/bands_out/_batch_index.json"
NODE_GROUP_NAME = "Parametric Weave knotty"
OBJECT_NAME = "ParametricWeave.001"

ENGINE = 'CYCLES'        # 'CYCLES' | 'BLENDER_EEVEE_NEXT'
RES_X = 768
RES_Y = 768
SAMPLES = 64
OUTFILE = "render.png"   # written into each yarn's bands_out folder


def main() -> None:
    batch = json.load(open(BATCH_INDEX))
    ng = bpy.data.node_groups[NODE_GROUP_NAME]
    obj = bpy.data.objects[OBJECT_NAME]
    mod = next(m for m in obj.modifiers if m.type == 'NODES' and m.node_group == ng)
    sock = {it.name: it.identifier
            for it in ng.interface.items_tree
            if it.item_type == 'SOCKET' and it.in_out == 'INPUT'}

    sc = bpy.context.scene
    sc.render.engine = ENGINE
    sc.render.resolution_x = RES_X
    sc.render.resolution_y = RES_Y
    if ENGINE == 'CYCLES':
        sc.cycles.samples = SAMPLES
    sc.render.image_settings.file_format = 'PNG'

    total = len(batch)
    for i, (name, info) in enumerate(sorted(batch.items()), 1):
        t0 = time.time()
        print(f"\n[{i}/{total}] {name}")
        mat = build_material(name, info["rgb"], info["alpha"])
        for s in ("Material 1", "Material 2", "Material 3", "Material 4"):
            mod[sock[s]] = mat
        mod[sock["Image Width Px"]]        = float(info["image_width_px"])
        mod[sock["Image Core V Min"]]      = info["core_v_min"]
        mod[sock["Image Core V Max"]]      = info["core_v_max"]
        mod[sock["Image Fiber Top V Min"]] = info["fiber_bot_v_outer"]
        mod[sock["Image Fiber Bot V Max"]] = info["fiber_top_v_outer"]
        obj.update_tag()

        out_path = os.path.join(info["render_dir"], OUTFILE)
        sc.render.filepath = out_path
        bpy.ops.render.render(write_still=True)
        print(f"  -> {out_path}  ({time.time()-t0:.1f}s)")


if __name__ == "__main__":
    main()
