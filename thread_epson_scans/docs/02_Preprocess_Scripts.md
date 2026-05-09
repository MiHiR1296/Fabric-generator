# 02 — Preprocess Scripts

All scripts live in `thread_epson_scans/Scripts/`. They are standalone Python with a small dependency footprint:

- `pillow`, `numpy`, `opencv-python`, `scikit-image` — for the image work.
- `torch`, `simple-lama-inpainting` — required for `seamless_converter.py` (LaMa weights expected next to it).
- `bpy` — the four `blender_*.py` scripts run inside Blender.

## Stage 1-3 wrapper: `yarn_pipeline.py`

The orchestrator. Given a raw TIFF, runs preprocess → seamless → alpha and returns the three output paths.

```bash
python yarn_pipeline.py INPUT.tif OUTPUT_DIR
    [--preset auto|white_bg|black_bg]
    [--orientation auto|horizontal|vertical]
    [--hardcut-cutoff INT]
    [--keep-intermediate]
    [--quiet]
```

Returns single-line JSON on stdout: `{"seamless": "...", "alpha": "...", "preprocessed": "..."}`.

## Stage 1: `alpha_pipeline.py — preprocess()`

Read the raw scan, detect orientation, rotate horizontal, white-balance against the paper background, level a mild rotation if needed, crop to the yarn band. Writes a clean `_preproc.png`.

Also exposes `run()` (the Stage 3 alpha extractor; see below) and a few low-level helpers reused by other scripts:
- `luma()` — luminance from RGB, used by the band segmenter.
- `_core_mask()` — robust foreground mask (Otsu + morphological cleanup).
- `row_thread_score()` — per-row "how much yarn is here" score, used to find the leveling angle.

## Stage 2: `seamless_converter.py`

LaMa-inpaint the U-direction seam (left + right edges) so the seamless image can tile horizontally without a visible cut. Loads `big-lama.pt` from the script's directory; if you move the script, copy the weights file too. CPU works but is slow; CUDA / Metal-backed Torch is dramatically faster.

## Stage 3: `alpha_pipeline.py — run()`

Take the seamless image and produce a clean alpha matte. Three presets:
- `white_bg` — Otsu on luminance with hardcut against paper.
- `black_bg` — inverted preset for dark-background scans.
- `auto` — picks white/black by sampling the image corners.

Output: 8-bit greyscale PNG. White = solid yarn body, mid grey = fiber halo, black = background.

## Stage 4: `band_segmenter.py`

The contract maker between PIL-pixel-space and the GN graph.

Input: `(rgb, alpha)` paths (from yarn_pipeline). Output: a folder under `bands_out/{name}/` with:

- `meta.json` — the only output the GN graph reads. Contains:
  - `image_size_px`, `bands_px` (raw pixel rows), `bands_v_norm` (Blender V convention: V=0 bottom, V=1 top).
  - `thickness_px` for core / fiber_top / fiber_bot.
  - `blender_uv_remap` — pre-computed Map Range in/out values for the Arc 1 (core-only) and Arc 2 (three-segment) mappings.
  - `twist` — FFT-detected twist period (px), twists-in-image, top-5 candidate periods.
  - `outputs` — relative paths to the debug PNGs.
- `normal.png`, `roughness.png`, `overlay.png` — debug; not currently sampled by the GN material.

Algorithm: per-row alpha-density curve → FWHM core band → noise-floor fiber bands above and below the core. Twist detection is a 1-D FFT of the centerline luminance.

```bash
python band_segmenter.py RGB.png ALPHA.png OUT_DIR
```

Validated on 6 yarns. Out-of-domain inputs (e.g. `white_red_tile`, which is a fabric-tile scan, not a single yarn) are detected and produce a `meta.json` with degenerate band ranges — those entries should be ignored by the renderer.

## Stage 5: `resize_for_cycles.py`

Cycles silently caps any single texture dimension at 16384 px. For each yarn's rgb + alpha that exceeds the cap, write a downscaled `_max16384` copy into `bands_out/_resized/`. Idempotent: re-running skips files already resized. The `image_size_px` in meta.json is **never** overwritten — Blender's procedural Scale U math always uses the original (true) pixel width, regardless of which file is loaded into the texture node.

## Stage 6: `build_batch_index.py`

Walk `bands_out/`, collapse every `meta.json` into a single `_batch_index.json` keyed by yarn name. Per-yarn entries:

```jsonc
{
  "rgb":   "...path...",                  // _resized version if it exists
  "alpha": "...path...",
  "image_width_px":     15949,            // true width, not resized
  "core_v_min":         0.4588,           // bands_v_norm.core[0]
  "core_v_max":         0.5304,           // bands_v_norm.core[1]
  "fiber_bot_v_outer":  0.3887,           // bands_v_norm.fiber_bot[0]   <-- swap below
  "fiber_top_v_outer":  0.6140,           // bands_v_norm.fiber_top[1]   <-- swap below
  "render_dir":         "...path..."
}
```

**The fiber-band swap.** Inside the GN graph, the sockets named `Image Fiber Top V Min` and `Image Fiber Bot V Max` actually receive the OUTER edges of the fiber bands. Because Arc 2 sweeps in the opposite geometric direction from Arc 1 (its sweep angle is signed the other way), the "top of Arc 2's V parameter" maps to the LOWEST V of the image, and vice versa. The names stuck because the GN was authored before the convention was nailed down. `build_batch_index.py` does the swap so downstream consumers don't have to think about it.

## Stage 7 — Blender side: `blender_apply_yarn.py`

Run inside Blender (Text Editor `Run Script`, or `exec(open(...).read())` in the Python console, or via the MCP `execute_blender_code` tool). Sets `YARN` at the top to a key in `_batch_index.json`. Builds (or rebuilds) the material, assigns it to all four GN modifier `Material 1..4` sockets, pushes Image Width Px and the four band-V values into the modifier. Leaves `Texture Scale U` (the manual multiplier) untouched.

The material is a minimal 6-node tree:
```
ShaderNodeAttribute('uv_scaled') → ShaderNodeMapping (passthrough) → ShaderNodeTexImage(rgb) → BSDF.Base Color
                                                       └────────────→ ShaderNodeTexImage(alpha) → BSDF.Alpha
```
Plus `surface_render_method = 'DITHERED'` so transparency renders identically in Eevee Next and Cycles.

**Critical:** the Attribute node MUST read `'uv_scaled'`, not `'UVMap'`. The GN graph stores its final UV as a custom FLOAT2 attribute named `uv_scaled` (Combine XYZ.006 → Store Named Attribute.002). A material reading the default `UVMap` attribute samples (0, 0) for every fragment and produces a single uniform color across the whole cloth.

## Stage 7 — batch: `blender_batch_render.py`

Loops over every yarn in `_batch_index.json`, reuses `build_material()` from `blender_apply_yarn.py`, and writes `render.png` into each yarn's bands_out folder.

Render settings live at the top of the file (`ENGINE`, `RES_X`, `RES_Y`, `SAMPLES`). Camera and lighting are taken from the current scene — make sure they're framed before kicking the batch off, since this script does not adjust them.
