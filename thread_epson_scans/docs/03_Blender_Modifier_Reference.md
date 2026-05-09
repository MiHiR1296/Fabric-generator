# 03 — Blender Modifier Reference

The geometry node group `Parametric Weave knotty` (231 nodes) lives in `weave.blend` and drives the modifier on `ParametricWeave.001`. Below is every input socket on the group, what it does, and where its value comes from in this pipeline. Sockets we *added* during the yarn-image work are flagged **[NEW]**; the rest are pre-existing weave parameters.

Scene units are **METRIC METERS**, `unit_settings.scale_length = 1.0`. So everywhere below, "BU" means "meter".

## Yarn-image bands and U-scaling group **[NEW]**

These are the sockets you change to swap one yarn for another. All come from the yarn's `meta.json` via `build_batch_index.py` (`Texture Scale U` is the only one you tune by hand).

| Socket | Default | What feeds it |
|---|---|---|
| `Scanner Pixels Per BU` | `62992.126` | Constant — the Epson scanner is 1600 DPI, and 1 BU = 1 m, so `1600 × 39.3701`. Set once; never changes per yarn. |
| `Image Width Px` | `15949` | `meta.image_size_px[0]` of the active yarn. Use the TRUE width even when the loaded texture is the `_resized` copy. |
| `Texture Scale U` | `1.0` | Manual multiplier on top of the procedural auto-scale. `1.0` keeps the procedurally derived density; lower values stretch the image along the strand; higher values tile it. |
| `Image Core V Min` | `0.469` | `meta.bands_v_norm.core[0]` |
| `Image Core V Max` | `0.541` | `meta.bands_v_norm.core[1]` |
| `Image Fiber Top V Min` | `0.386` | `meta.bands_v_norm.fiber_bot[0]` — outer-LOW V edge of the bot fiber band (see swap note below). |
| `Image Fiber Bot V Max` | `0.611` | `meta.bands_v_norm.fiber_top[1]` — outer-HIGH V edge of the top fiber band (see swap note below). |
| `Main Strand Radius` | `0.025` | Outer (Arc 1) radius. Drives the `r = main_radius / (main_radius + sub_strand_width)` split inside Arc 2's three-segment V remap. Coupled with `Sub Strand Width` below. |

### Why fiber socket names are flipped

Arc 2 sweeps with the opposite signed angle from Arc 1 (`Sweep Angle` on `Arc.001` is positive vs Arc's negative). The result is that Arc 2's V=0 corresponds to the geometric BOTTOM of the cross-section, which we want to map to the LOWEST V of the source image — the outer edge of the **bot** fiber band. Hence `Image Fiber Top V Min` (Arc 2's "top side" of the V parameter) actually receives `fiber_bot[0]`. Same for `Image Fiber Bot V Max`. `build_batch_index.py` performs this swap so callers never see it.

## Weave geometry

| Socket | Default | Meaning |
|---|---|---|
| `Over Count` / `Under Count` | `1`, `1` | Twill / satin pattern bias. `1, 1` = plain weave. |
| `Warp Threads` / `Weft Threads` | `20`, `20` | Strand counts. With `Spacing`, sets fabric size. Keep equal — see limits doc. |
| `Spacing` | `0.12` | Distance between adjacent threads (BU). |
| `Amplitude` | `0.035` | How far each strand bows up/down at over/under crossings. |
| `Thread Subdivisions` | `4.0` | Resampling density of each strand curve. |
| `Texture Side Flatten` | `0.7` | Compresses the V mapping near the strand edges so the visible side of each thread shows more of the core band. |

`Strand straight length = Warp Threads × Spacing` (BU). This is what the U-scale chain divides `Image Width Px / Scanner Pixels Per BU` into.

## V mapping (existing controls — left in place)

| Socket | Default | Meaning |
|---|---|---|
| `Texture Scale V` | `1.0` | Multiplier for the band-V output. Leave at 1.0 unless you want to compress/expand the band layout. |
| `Texture Offset V` | `0.0` | Adds a constant V offset on top. |

## Variation / wobble

| Socket | Default | Meaning |
|---|---|---|
| `Seed` | `0` | RNG seed for per-strand variation. |
| `Wobble Amount` / `Wobble Scale` | `0.0`, `12.0` | Curl applied per strand. |
| `Pattern Noise X/Y` | `0.0` | Adds spatial noise to the over/under pattern. |
| `UV Random U/V` | `0.0` | Random per-strand UV offset (uses `uv_offset_u/v` attributes inside the graph). |

## Loose strand layer

| Socket | Default | Meaning |
|---|---|---|
| `Loose Strand Density` | `0.0` | Probability of a stray fiber strand. |
| `Loose Strand Length` | `0.04` | Curve length of stray fibers (BU). |
| `Loose Strand Thickness` | `0.18` | Multiplier on the loose-strand radius. |
| `Loose Strand Frizz` | `0.015` | Random tangent jitter for the loose strands. |

## Materials (per-strand cycle)

| Socket | What it does |
|---|---|
| `Material 1..4` | Pool of materials. The pipeline assigns the same yarn material to all four when running `blender_apply_yarn.py`. |
| `Warp Offset`, `Warp Length 1..4`, `Warp Material 1..4` | Cycling pattern for warp strands — picks which Material slot a given warp uses. With Length 1 = 1 and Lengths 2..4 = 0, every warp uses Material 1. |
| `Weft Offset`, `Weft Length 1..4`, `Weft Material 1..4` | Same for weft. |

## Sub-strand (planned secondary fiber halo)

| Socket | Default | Meaning |
|---|---|---|
| `Sub Strand Enable` | `False` | Toggle the second arc layer. |
| `Sub Strand Width` | `0.0` | Width of the sub-strand. Coupled with `Main Strand Radius` to compute `r` for Arc 2's three-segment V remap. |
| `Sub Strand Height` | `0.0` | Vertical offset. |
| `Sub Texture Scale V` / `Sub Texture Offset V` | `0.0` | Per-sub-strand V mapping. Currently unused while `Sub Strand Enable = False`. |
