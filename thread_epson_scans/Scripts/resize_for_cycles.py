"""
resize_for_cycles.py
====================

Cycles silently caps any single texture dimension at 16384 px. Several of our
preprocessed yarn scans (and their alpha mattes) come out wider than that, so
when Blender loads them it auto-clamps to 16384 with no warning, breaking the
DPI-to-Blender-unit math the GN graph relies on.

This script walks every yarn folder under bands_out/ (one per processed yarn,
each with a meta.json), reads the rgb + alpha paths, and if either exceeds
16384 px on any axis writes a downscaled copy into bands_out/_resized/ named
"{stem}_max16384.{ext}". Files already at or below the cap are left alone.

Run once after the band_segmenter pass; safe to re-run (existing resized
files are skipped).

Usage:
    python Scripts/resize_for_cycles.py
"""
from __future__ import annotations

import json
import os
import sys

from PIL import Image

Image.MAX_IMAGE_PIXELS = None  # silence DecompressionBombWarning on big TIFFs

MAX_DIM = 16384
HERE = os.path.dirname(os.path.abspath(__file__))
BANDS_ROOT = os.path.normpath(os.path.join(HERE, "..", "bands_out"))
RESIZED_DIR = os.path.join(BANDS_ROOT, "_resized")


def ensure_under_max(src_path: str) -> str | None:
    if not os.path.isfile(src_path):
        return None
    im = Image.open(src_path)
    w, h = im.size
    if max(w, h) <= MAX_DIM:
        return src_path
    base, ext = os.path.splitext(os.path.basename(src_path))
    out = os.path.join(RESIZED_DIR, f"{base}_max16384{ext}")
    if os.path.isfile(out):
        return out
    scale = MAX_DIM / max(w, h)
    new_size = (int(w * scale), int(h * scale))
    print(f"  resize {os.path.basename(src_path):60s} {w}x{h} -> {new_size[0]}x{new_size[1]}")
    im.resize(new_size, Image.LANCZOS).save(out)
    return out


def main() -> int:
    os.makedirs(RESIZED_DIR, exist_ok=True)
    n_seen = n_resized = 0
    for name in sorted(os.listdir(BANDS_ROOT)):
        folder = os.path.join(BANDS_ROOT, name)
        meta_path = os.path.join(folder, "meta.json")
        if not os.path.isfile(meta_path):
            continue
        meta = json.load(open(meta_path))
        for key in ("rgb", "alpha"):
            src = meta["input"][key]
            n_seen += 1
            out = ensure_under_max(src)
            if out and out != src:
                n_resized += 1
    print(f"\nDone. Inspected {n_seen} files, downscaled {n_resized} into {RESIZED_DIR}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
