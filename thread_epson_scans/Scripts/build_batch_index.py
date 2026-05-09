"""
build_batch_index.py
====================

Walk every yarn folder under bands_out/ (each must contain meta.json from
band_segmenter.py) and emit a single bands_out/_batch_index.json that maps
{yarn_name -> {rgb, alpha, image_width_px, core_v_min, core_v_max,
               fiber_bot_v_outer, fiber_top_v_outer, render_dir}}.

The Blender side (blender_batch_render.py) reads this index to drive material
loading and modifier socket assignments without re-parsing every meta.json.

If a yarn's rgb or alpha is wider than 16384 px, this script automatically
substitutes the downscaled copy from bands_out/_resized/ (run
resize_for_cycles.py first to populate it).

Notes on the V-band socket convention:
    The GN modifier exposes "Image Fiber Top V Min" and "Image Fiber Bot V
    Max", but their values are the OUTER edges of the fiber bands in Blender V
    convention (V=0 bottom, V=1 top). Because Arc 2 sweeps in the opposite
    geometric direction from Arc 1, the socket names are flipped relative to
    the meta.json keys:

        Image Fiber Top V Min  <-  bands_v_norm.fiber_bot[0]   (lowest V)
        Image Fiber Bot V Max  <-  bands_v_norm.fiber_top[1]   (highest V)

    This file applies the swap so consumers don't have to think about it.

Usage:
    python Scripts/build_batch_index.py
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BANDS_ROOT = os.path.normpath(os.path.join(HERE, "..", "bands_out"))
RESIZED_DIR = os.path.join(BANDS_ROOT, "_resized")


def maybe_resized(src_path: str) -> str:
    """Return a path that is safe for Cycles (max axis <= 16384)."""
    if not os.path.isfile(src_path):
        return src_path
    base, ext = os.path.splitext(os.path.basename(src_path))
    candidate = os.path.join(RESIZED_DIR, f"{base}_max16384{ext}")
    return candidate if os.path.isfile(candidate) else src_path


def main() -> int:
    out: dict = {}
    for name in sorted(os.listdir(BANDS_ROOT)):
        folder = os.path.join(BANDS_ROOT, name)
        meta_path = os.path.join(folder, "meta.json")
        if not os.path.isfile(meta_path):
            continue
        meta = json.load(open(meta_path))
        rgb = maybe_resized(meta["input"]["rgb"])
        alpha = maybe_resized(meta["input"]["alpha"])
        if not (os.path.isfile(rgb) and os.path.isfile(alpha)):
            print(f"SKIP {name}: missing rgb/alpha source")
            continue
        bv = meta["bands_v_norm"]
        out[name] = {
            "rgb": os.path.abspath(rgb),
            "alpha": os.path.abspath(alpha),
            "image_width_px": meta["image_size_px"][0],
            "core_v_min": bv["core"][0],
            "core_v_max": bv["core"][1],
            "fiber_bot_v_outer": bv["fiber_bot"][0],
            "fiber_top_v_outer": bv["fiber_top"][1],
            "render_dir": os.path.abspath(folder),
        }
        print(f"OK  {name}: w={meta['image_size_px'][0]}px")

    out_path = os.path.join(BANDS_ROOT, "_batch_index.json")
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nWrote {len(out)} entries -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
