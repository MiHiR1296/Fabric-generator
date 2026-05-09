# 01 — Pipeline Overview

## Goal

Reproduce the look of a real, scanned yarn on a procedural weave inside Blender. Every yarn we have was scanned at **1600 DPI on an Epson scanner**. The output of the scan is a long horizontal strip of yarn against a paper background. We want the woven cloth in Blender to look exactly like the source scan — same color, same twist period, same fiber halo — and we want it to do so dynamically as the user changes weave parameters (Spacing, Threads, Amplitude).

## Data flow

```
RAW TIFF
   │  (Stage 1) Scripts/alpha_pipeline.py preprocess()
   ▼
PREPROC PNG  preproc_out/{name}_preproc.png
   │   - rotated horizontal, white-balanced, leveled, cropped to yarn band
   │
   │  (Stage 2) Scripts/seamless_converter.py
   ▼
SEAMLESS PNG  preproc_out/{name}_seamless.png
   │   - LaMa inpaint patches the U-direction seam so the texture tiles
   │
   │  (Stage 3) Scripts/alpha_pipeline.py run()
   ▼
ALPHA PNG  alpha_out/{name}_alpha.png
   │   - 8-bit matte: white where yarn, black where background; fiber halo grey
   │
   │  Stages 1-3 are bundled by Scripts/yarn_pipeline.py
   │
   │  (Stage 4) Scripts/band_segmenter.py
   ▼
BAND METADATA  bands_out/{name}/
   │   - normal.png, roughness.png, overlay.png   (debug + display maps)
   │   - meta.json                                (the contract with Blender)
   │
   │  (Stage 5) Scripts/resize_for_cycles.py     (only if > 16384 px on any axis)
   ▼
CYCLES-SAFE DOWNSCALES  bands_out/_resized/
   │
   │  (Stage 6) Scripts/build_batch_index.py
   ▼
BATCH INDEX  bands_out/_batch_index.json
   │
   │  (Stage 7) Scripts/blender_apply_yarn.py    or blender_batch_render.py
   ▼
RENDERED FABRIC  bands_out/{name}/render.png
```

## What each stage actually produces

| Stage | Output | What's in it |
|---|---|---|
| Preprocess | `*_preproc.png` | Horizontal RGB strip of yarn, leveled, paper-white background, single yarn isolated. |
| Seamless | `*_seamless.png` | Same image with a LaMa-inpainted patch across the left/right edge, so the U axis tiles cleanly. |
| Alpha | `*_alpha.png` | Greyscale matte. White inside the yarn body, fading through grey at the fiber halo, black on background paper. |
| Band-segment | `meta.json` | Per-yarn data: image width in px, the V-coordinate ranges of the **core**, **fiber_top**, **fiber_bot** bands, and an FFT-derived twist period. |
| Band-segment | `normal.png`, `roughness.png` | Debug shading maps. Currently unused by the GN material; kept for future micro-detail. |
| Band-segment | `overlay.png` | Visual sanity check — RGB with the detected band edges drawn on. |
| Resize | `_resized/*_max16384.png` | Bilinear downscale used at material-texture-load time only; physical width (`image_size_px[0]` from meta.json) is unchanged. |

## What the GN graph does with the meta.json

The Parametric Weave knotty graph builds the woven cloth from two **arcs** per strand cross-section:

- **Arc 1** — wide outer arc, 1.0 radius units, sweep ≈ 120° in front of the visible side.
- **Arc 2** — narrower inner arc behind it, sweep ≈ 120° from the opposite direction; its radius is `Main Strand Radius`.

Each arc's parametric V (0..1 sweep coordinate) is mapped to a different vertical band of the source yarn image:

- Arc 1 → **core** band of the image (the dense thread body).
- Arc 2 → **fiber_top + core + fiber_bot** in three piecewise segments, split at `r = main_radius / (main_radius + sub_strand_width)` so the wider Arc 2 visually wraps the same yarn around a smaller curvature.

Along the strand length (U direction), `u_along` is computed by Spline Parameter × spline-length / straight-length, giving a normalized parameter that compensates for the over/under wave. We multiply that by an effective **Texture Scale U** to pick how many image-widths span one strand — see [04_GN_Architecture.md](04_GN_Architecture.md).
