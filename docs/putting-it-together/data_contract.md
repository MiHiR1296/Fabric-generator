# Data contract — `yarn_library/<yarn_id>/metadata.json`

> **Read this if**: you are touching anything that writes, reads, or transforms a yarn's metadata between yarnseamless and the Fabric-generator-tryon backend, or you are about to add a new Blender socket and want to know how to source its value.

This is the authoritative reference. If anything else in the docs disagrees, this wins.

---

## The shape

```jsonc
{
  "schemaVersion": 1,
  "id":  "20260512_163059_0b30c1",
  "label": "thread_0",
  "createdAt": "2026-05-12T11:01:00.699766Z",
  "source": { "multithread_session_id": "...", "multifragment_session_id": "...", "scan_size_px": [W, H] },

  // Raw measurements (provenance + re-derivation).
  "image_size_px": [42124, 301],
  "dpi": 1600.0,
  "width":  { "px": 30,    "mm": 0.4762,  "top_y_in_export": 136, "bottom_y_in_export": 165, "description": "..." },
  "length": { "px": 42124, "mm": 668.7185, "description": "..." },
  "bands_px":     { "core": [136, 165], "fiber_top": [123, 136], "fiber_bot": [165, 181] },
  "bands_v_norm": { "_convention": "blender (V=0 bottom, V=1 top)", "core": [...], "fiber_top": [...], "fiber_bot": [...] },
  "thickness_px": { "core_height": 30, "fiber_top_height": 13, "fiber_bot_height": 16 },
  "params": { "fiber_frac": 0.02 },

  // Pre-computed Blender-ready block. Consumer pushes these as-is.
  "blender": {
    "_convention": "Pre-computed for direct push to Parametric Weave knotty...",
    "schema_version": 1,
    "texture_world_width_m":  0.6687185,
    "texture_world_width_mm": 668.7185,
    "image_width_px":         42124,
    "scanner_pixels_per_bu":  62992.16,
    "core_v_min":             0.4518272425249169,
    "core_v_max":             0.548172757475083,
    "fiber_top_v_min":        0.548172757475083,
    "fiber_top_v_max":        0.5913621262458472,
    "fiber_bot_v_min":        0.3986710963455149,
    "fiber_bot_v_max":        0.5913621262458472
  },

  "joins": [ ... ],
  "threads_solid_band": [ ... ],
  "files": { "rgba": "rgba.png", "thumbnail": "input_thumb.jpg", "metadata": "metadata.json" }
}
```

---

## The two zones

| Zone | Who writes it | Source of truth | Who reads it |
|---|---|---|---|
| Top-level (`image_size_px`, `dpi`, `width`, `length`, `bands_*`, `joins`, …) | `backend/app/yarnseamless/yarn_library.py` | The `rgba.png` file on disk + the multifragment session it was exported from | UI provenance, future re-derivation. **NOT pushed to Blender directly.** |
| `physical_scale` | `backend/app/yarnseamless/yarn_library.py` | Declared export DPI cross-checked against embedded source-scan DPI and processed/export image DPI | Confidence/provenance only. Helps separate scanner truth from metadata-only truth. |
| `blender` block | `backend/app/yarnseamless/yarn_library.py` (derived from top-level) | The top-level fields | Fabric-generator-tryon → pushed to the `Parametric Weave knotty` modifier sockets. **One field per socket, no math.** |

**Rule**: the consumer never does unit conversion. If a Blender socket needs a number, that number lives in `blender.*` already, pre-computed.

---

## Runtime render texture fields

These fields live on Fabric-generator-tryon's runtime `YarnAsset`, not in the source `yarn_library/<id>/metadata.json`. They describe how the backend should feed the processed images to Blender.

| Runtime field | Meaning |
|---|---|
| `renderTextureMode` | `"rgba_tiled"` / `"rgba_single"` for the preferred direct material path, or `"tiled"` / `"single"` for legacy split diffuse-alpha fallback. |
| `renderRgbaTilePattern` / `renderRgbaTileFilenames` | Preferred full-resolution RGBA UDIM assets, eg. `cycles_tiled/rgba_<UDIM>.png`. Generated RGBA materials sample color and alpha from the same diffuse/RGBA image node. |
| `renderDiffuseFilename` / `renderAlphaFilename` | Cycles-safe fallback split textures. If the source exceeds the device cap, these point to `cycles_safe/*_max16384.png`. Used when an RGBA texture is not available. |
| `renderDiffuseTilePattern` / `renderAlphaTilePattern` | Legacy split relative `<UDIM>` patterns such as `cycles_tiled/albedo_<UDIM>.png`. Blender receives absolute versions of these patterns. |
| `renderDiffuseTileFilenames` / `renderAlphaTileFilenames` | Concrete split tile filenames, eg. `cycles_tiled/albedo_1001.png` ... `1003.png`. |
| `renderTileCount` / `renderTileWidthPx` / `renderTileHeightPx` | Tile manifest for material generation and diagnostics. |

Phase 4a + 2026-06-05 rule: direct preview materials prefer RGBA UDIM tiles when present. The shader maps `fract(uv_scaled.x) * renderTileCount` into UDIM U space, so the yarn repeat still behaves like one image while each tile stays below the `16384` single-texture cap. RGBA materials link `FabricStudioDiffuseNode.Alpha` directly to `Principled BSDF.Alpha` by default. The split diffuse/alpha path and atlas fallback remain compatibility fallbacks.

Phase 4c/4d/4h/10u + 2026-06-05 rule: Fabric-generator-tryon pushes raw `core_v_min/max`. The `.blend` exposes `Arc 1 V Padding` on the `Weave` modifier and applies the expansion after material selection: Arc 1 V Min moves downward, Arc 1 V Max moves upward, and both clamp inside `fiber_bot_v_min..fiber_top_v_max` so Arc 2 halo sections do not invert. The 2026-06-05 code default is `0.02` and is exposed in the Web UI. Source `metadata.json` remains unmodified.

---

## The `blender` block → Blender socket map

Modifier: `Weave` on `ParametricWeave`, node group `Parametric Weave knotty`. All sockets accept `NodeSocketFloat`.

**Socket vocabulary aligned to Arc 1 / Arc 2 (Phase 3d, 2026-05-14)** — the .blend's internal node names (`PW Band - Arc1 Map`, `PW Band - Arc2 Top/Core/Bot`) define the V-band partition, so the interface socket names now match. Producer keys in `bandMeta.blender` are unchanged (they describe scan data; not coupled to socket names).

| `metadata.blender` field | Blender socket | What it does |
|---|---|---|
| `texture_world_width_m` | `Texture World Width BU` *(reserved — not yet on this .blend)* | Physical U-length of one texture repeat, in BU (1 BU = 1 m). Would replace the legacy two-socket divide. |
| `image_width_px` | `Material N Image Width Px` *(also `Image Width Px` global)* | Image width in pixels. Combined with `Scanner Pixels Per BU` reproduces the world width. |
| `scanner_pixels_per_bu` | `Scanner Pixels Per BU` *(modifier-level; not per-material)* | Per-DPI calibration. `dpi × 39.3701`. |
| `core_v_min` | `Material N Arc 1 V Min` | Lower V edge of the dense core. Feeds `PW Band - Arc1 Map.To Min`, `PW Band - Arc2 Top.To Max`, and `PW Band - Arc2 Core.To Min` after the Phase 7 Arc 2 full-path flip. |
| `core_v_max` | `Material N Arc 1 V Max` | Upper V edge of the dense core. Feeds `PW Band - Arc1 Map.To Max`, `PW Band - Arc2 Core.To Max`, and `PW Band - Arc2 Bot.To Min` after the Phase 7 Arc 2 full-path flip. |
| `fiber_bot_v_min` | `Material N Arc 2 V Min` | **Strand silhouette's bottommost V** (outer edge of the lower halo). Feeds `PW Band - Arc2 Top.To Min` after the Phase 7 Arc 2 full-path flip. |
| `fiber_top_v_max` | `Material N Arc 2 V Max` | **Strand silhouette's topmost V** (outer edge of the upper halo). Feeds `PW Band - Arc2 Bot.To Max` after the Phase 7 Arc 2 full-path flip. |
| `fiber_bot_v_max` (= `core_v_min` by construction) | (no longer pushed to a socket after Phase 3e; retained in metadata for diagnostics) | Inner-edge value made redundant by Arc 1 V Min. |
| `fiber_top_v_min` (= `core_v_max` by construction) | (no longer pushed to a socket after Phase 3e; retained in metadata for diagnostics) | Inner-edge value made redundant by Arc 1 V Max. |

**Band timing note (Phase 3p)**:

- `width.top_y_in_export` / `width.bottom_y_in_export` start as per-thread `c_band` rows during multithread processing, before multifragment assembly and join inpainting. Export then offsets and averages those rows into export-image coordinates.
- `fiber_bot_v_min` / `fiber_top_v_max` are detected later during save-to-library from `export_assembled_alpha.png`, after assemble, regenerate-alpha, join alpha composition, and no-wraparound export trimming.
- Consequence: the core band and the outer strand silhouette are both useful, but they are not detected from one single final-image pass.

**Arc 2 sections, current Phase-3q geometry-owned split test plus Phase-7 full-path flip, map cross-section coordinate → texture-V range:**

Phase 3q keeps Arc 1 geometry stable and computes Arc 2's core interval from profile geometry, not texture V span:

```text
arc1_profile_radius = 0.015
arc2_profile_radius = 0.025
core_frac = clamp(arc1_profile_radius / max(arc2_profile_radius, 0.0001), 0, 1)
Split Minus = 0.5 - core_frac / 2  # geometry split value: 0.2
Split Plus  = 0.5 + core_frac / 2  # geometry split value: 0.8
```

| Cross-section region (`v_around`) | Texture-V output range | Samples |
|---|---|---|
| `[0, Split Minus]` → `Arc2 Top` | `[Arc 2 V Min, Arc 1 V Min]` = `[fiber_bot_v_min, core_v_min]` | Lower halo, outer edge → core edge |
| `[Split Minus, Split Plus]` → `Arc2 Core` | `[Arc 1 V Min, Arc 1 V Max]` = `[core_v_min, core_v_max]` | Dense core, bottom → top |
| `[Split Plus, 1]` → `Arc2 Bot` | `[Arc 1 V Max, Arc 2 V Max]` = `[core_v_max, fiber_top_v_max]` | Upper halo, core edge → outer edge |

The graph stores these evaluated debug attributes on the output mesh:

| Attribute | Current value | Meaning |
|---|---:|---|
| `arc1_radius_geometry` | `0.015` | Arc 1 profile radius source used by the split math |
| `arc2_radius_geometry` | `0.025` | Arc 2 profile radius source used by the split math |
| `arc2_core_frac_raw` | `0.6` | Raw `arc1 / arc2` fraction |
| `arc2_core_frac_geometry` | `0.6` | Clamped core fraction |
| `arc2_core_split_min` | `0.2` in the current Phase 10t saved inspection state | Canonical Top/Core boundary used by Arc 2 V mapping and the custom Arc 2 profile |
| `arc2_core_split_max` | `0.8` in the current Phase 10t saved inspection state | Canonical Core/Bot boundary used by Arc 2 V mapping and the custom Arc 2 profile |

The old Phase 3m centered texture-span leftovers were removed in the 2026-05-27 graph cleanup. Phase 10t keeps `PW Band - Split Minus/Plus` on the geometry-owned vertex split (`0.2 / 0.8`) and routes `PW Band - Diff.Value` through the Top/Core/Bot path. Stabilization Phase 4 (2026-06-05) tested endpoint-fitting Arc 2 to `Arc 2 V Min/Max` plus absolute sub-scale semantics, but that numeric fix was visually rejected because it damaged Arc 2 look and feel. The active contract remains the free-flow halo path with additive sub-scale.

Globals after Phase 3f cleanup: only `Scanner Pixels Per BU` survives. The five legacy `Image Width Px` / `Image Arc 1 V Min/Max` / `Image Arc 2 V Min/Max` sockets were removed from the .blend on 2026-05-14 once an audit confirmed no Group Input was consuming them — the per-Material V-band sockets are the only path the graph uses now. Producer code ([blender_live.py:GLOBAL_SOCKETS](../../backend/app/blender_live.py)) shrunk to one entry to match.

Pinned, **not** pushed per yarn — these six form the live bandMeta "footgun" set: `Sub Strand Enable = True`, root `Texture Scale U = 1`, `Texture Scale V = 1`, `Texture Offset V = 0`, `Sub Texture Scale V = 1`, `Sub Texture Offset V = 0`. Producer asserts them on every bandMeta push via `PINNED_FOOTGUN_SOCKETS`. **`Sub Strand Enable` is the critical one** — without it, Arc 2's halo mapping doesn't fire and the rendered yarn loses its silhouette character. `Texture Offset V` is neutral again in the 2026-05-19 checkpoint; the previous non-zero offset was part of a checker/material phase-alignment experiment. See [../BlenderRenderStabilizationPlan](../BlenderRenderStabilizationPlan) for the current live-source-of-truth log.

### Per-strand U stride sockets (Phase 5, 2026-05-16)

Two new globals on `Parametric Weave knotty` drive **continuous yarn spooling** across warp/weft strands so successive strands pick up where the previous one ended (physically, one weft thread snakes back and forth; one warp end runs the whole loom length). The .blend stores them in the `Imperfections` panel; the producer pushes them as part of the per-render apply-metadata pass.

| Socket | Producer key | Push site | Math |
|---|---|---|---|
| `U Stride Per Warp End` | derived | [blender_live.py:_pw_apply_modifier_material_metadata](../../backend/app/blender_live.py) | `(weft_threads × spacing) / texture_world_width_BU × material_texture_scale_u` |
| `U Stride Per Weft Pick` | derived | same | `(warp_threads × spacing) / texture_world_width_BU × material_texture_scale_u` |

The stride exactly equals "repeats per strand" so strand `N+1`'s U-start = strand `N`'s U-end. Inside the graph: `uv_offset_u = PW Warp/Weft Variation.UV Offset U + curve_index × U Stride Per Warp End/Weft Pick`, added by `PW Warp/Weft U Stride x Index` (MULTIPLY) and `PW Warp/Weft UV Offset U Sum` (ADD) nodes inserted before each Store Named Attribute. Defaults are `0.0` so older bandMeta payloads do not trigger spooling.

### Curve-normal symmetry (Phase 5, 2026-05-16)

Both warp and weft branches carry a `Set Curve Normal` node with `Mode = 'Z Up'` (`PW Warp Set Curve Normal`, `PW Weft Set Curve Normal`) inserted between `Resample Curve` / `Resample Curve.001` and `Store Warp/Weft U`. Without these, Blender's minimum-twist default oriented the cross-section profile differently per axis — the same `v_around` value pointed to different physical positions on warp vs weft strands, so `Arc 1 V Padding` visibly expanded the halo on weft but not warp. Z-up alignment forces both axes to orient `v_around=0.5` toward +Z (the camera-facing top), making V-band behaviour symmetric.

### Render-control sockets (driven by `renderSettings`, not `bandMeta`)

| `renderSettings` field | Blender socket | Notes |
|---|---|---|
| `spacing` (0..1) | `Spacing` | Backend remaps 0..1 → 0.026..0.10 (`map_unit_setting`). |
| `patternNoiseX` (0..1) | `Pattern Noise X` | Backend remaps 0..1 → 0..0.03. |
| `patternNoiseY` (0..1) | `Pattern Noise Y` | Backend remaps 0..1 → 0..0.03. |
| `uvRandomU` (default **`0.0`** after Phase 5) | `UV Random U` | Per-strand random U scatter. **Retired as a default** because per-strand stride now provides natural along-spool variation. Kept as an artist escape hatch. |
| `arc1VPadding` (default `0.02`) | `Arc 1 V Padding` | Expands Arc 1's sampled core band after the material switch chain and clamps inside Arc 2. |
| `warpThreads` / `weftThreads` | `Warp Threads` / `Weft Threads` | Driven together by Web UI zoom presets: `80`, `120`, `160`, `200`. Lower count = closer inspection; `200` = widest swatch preset. |
| — | `UV Random V` | Pinned to `0`. User direction: U-axis only. |
| — | `Texture Scale U` (root) | Pinned to `1.0`. The Phase 4i fit-math + Phase 4d `textureUCalibration` chain was retired in Phase 5 — per-yarn U scale comes from `Material N Texture Scale U` and per-strand stride. |

---

## Derivations (so anyone can re-prove them)

```
texture_world_width_m  =  image_width_px / dpi × 0.0254          # 1 inch = 0.0254 m
scanner_pixels_per_bu  =  dpi × 39.3701                          # 1 BU = 1 m = 39.3701 in
core_v_min             =  1 − bottom_y_in_export / image_height
core_v_max             =  1 − top_y_in_export    / image_height
```

The `1 −` flips the image-Y axis (top of image = high Y in pixels) into Blender's V axis (top of texture = V=1).

---

## Schema versioning

`schemaVersion: 1` lives at the top level. The `blender` block also carries its own `schema_version: 1` so the two can evolve independently.

Bumping the schema is a producer-side decision. The consumer should:
1. Check `schemaVersion` on import.
2. If unknown, fail loudly. Do not silently fall back to defaults — the whole point of the contract is that defaults are wrong.

---

## What is NOT in the contract

These are explicitly out and should never be added without revisiting this doc:

- `dpi` is not pushed to Blender. It lives in `metadata.dpi` purely for provenance and to let the producer re-derive `texture_world_width_m`. If you find yourself needing dpi in `render_jobs.py`, you are doing math the producer should have done.
- `physical_scale.confidence` is not pushed to Blender. It records whether declared DPI was corroborated by source image metadata (`high`) or is only carried by export metadata (`metadata_only`).
- `twist_period_px` / FFT outputs. No socket consumes this.
- `normal.png` / `roughness.png` / `overlay.png`. The Blender material consumes color/alpha from `rgba.png` or RGBA UDIM tiles by default; split `albedo.png` + `alpha.png` remains a fallback texture format.
- Per-thread variance in `threads_solid_band`. The unified `core_v_min/max` is the only consumed band; per-thread is diagnostic.

---

## Source of truth for the file on disk

`rgba.png` is. If `metadata.image_size_px` disagrees with `Image.open(rgba.png).size`, the file wins. We hit this in Phase 1 — see [phase_log.md](phase_log.md) → "Phase 1".

The producer enforces this by always opening the file before writing metadata.

---

## Complete mapping reference — metadata.json → Blender modifier sockets

Five tables, organised by where the data originates. Read the **bandMeta** table for the per-yarn path; the other four for everything else that lands on the modifier each render.

Example values use yarn `bb5464ffe724` (thread001) where applicable — image_width_px=45058, dpi=1600, library yarn id `20260514_014216_ccb942`.

### 1. Per-yarn V-band & U-scale path (bandMeta → modifier)

The yarn-specific path. Producer ([backend/app/yarnseamless/yarn_library.py](../../backend/app/yarnseamless/yarn_library.py)) writes the top-level fields from the seamless scan, then derives a `blender` sub-block with pre-computed values for direct push. The tryon backend ([backend/app/yarn_assets.py](../../backend/app/yarn_assets.py)) projects those onto a runtime `YarnAsset.bandMeta` shape, and [backend/app/blender_live.py:PER_MATERIAL_SOCKETS](../../backend/app/blender_live.py) decides which `bandMeta.blender` field lands on which socket per material.

For N = the asset's slot index + 1 (so warp/weft cycle ids match):

| metadata.json source | Derivation | bandMeta.blender key | Blender socket | What it drives | thread001 value |
|---|---|---|---|---|---|
| `image_size_px[0]` | (file truth — see Phase 1 Rule 1) | `image_width_px` | `Material N Image Width Px` | Combined with Scanner Pixels Per BU → physical U length per texture repeat | `45058` |
| `blender.texture_scale_u` (or auto-derived) | `(core_v_max − core_v_min) × AUTO_TEXTURE_SCALE_U_CORE_FRACTION` when producer ships `1.0`/unset; otherwise producer value | `texture_scale_u` | `Material N Texture Scale U` | **Per-yarn core-band U scale.** The auto path uses the detected material core band directly, then applies the graph's `0.6` Arc 1/Arc 2 core fraction. Root `Texture Scale U` stays neutral; `Arc 1 V Padding` only widens V and does not change along-strand source consumption. | `0.03558` for the live-inspection yarn (`0.05931 × 0.6`) |
| `bands_v_norm.core[0]` | `1 − bottom_y_in_export / image_height` | `core_v_min` | `Material N Arc 1 V Min` | Lower V edge of the dense core. Feeds `PW Band - Arc1 Map.To Min`, `PW Band - Arc2 Top.To Max`, and `PW Band - Arc2 Core.To Min` after Phase 7 | `0.4835` |
| `bands_v_norm.core[1]` | `1 − top_y_in_export / image_height` | `core_v_max` | `Material N Arc 1 V Max` | Upper V edge of the dense core. Feeds `PW Band - Arc1 Map.To Max`, `PW Band - Arc2 Core.To Max`, and `PW Band - Arc2 Bot.To Min` after Phase 7 | `0.5165` |
| `bands_v_norm.fiber_bot[0]` | `1 − fby1 / image_height` (lowest pixel where fiber-density still exceeds floor) | `fiber_bot_v_min` | `Material N Arc 2 V Min` | Strand silhouette's **bottommost V**. Feeds `PW Band - Arc2 Top.To Min` after Phase 7 | `0.4582` |
| `bands_v_norm.fiber_top[1]` | `1 − fty0 / image_height` (highest pixel where fiber-density still exceeds floor) | `fiber_top_v_max` | `Material N Arc 2 V Max` | Strand silhouette's **topmost V**. Feeds `PW Band - Arc2 Bot.To Max` after Phase 7 | `0.5367` |
| `bands_v_norm.fiber_top[0]` (= core[1]) | n/a | `fiber_top_v_min` | (no socket — kept in entry dict for diagnostics) | Was used pre-Phase-3e as inner upper boundary of Arc 2; now `Arc 1 V Max` serves that role | `0.5165` |
| `bands_v_norm.fiber_bot[1]` (= core[0]) | n/a | `fiber_bot_v_max` | (no socket — kept in entry dict for diagnostics) | Was used pre-Phase-3e as inner lower boundary of Arc 2; now `Arc 1 V Min` serves that role | `0.4835` |

The two "diagnostic only" rows (`fiber_top_v_min` / `fiber_bot_v_max`) are pre-Phase-3e legacy keys. They mirror `core_v_max` / `core_v_min` exactly because the yarn bands are contiguous in V. Producer still emits them; consumer reads but doesn't push them anywhere.

### 2. Per-yarn world-scale path (bandMeta → modifier global)

Pushed once per render from the **first** ordered yarn asset (Material 1's). The graph reads this single global to convert pixel-space U back into world-space U.

| metadata.json source | Derivation | bandMeta.blender key | Blender socket (modifier-level, not per-material) | What it drives | thread001 value |
|---|---|---|---|---|---|
| `dpi` | `dpi × 39.3701` (1 BU = 1 m = 39.3701 in) | `scanner_pixels_per_bu` | `Scanner Pixels Per BU` | Internal divisor: `texture_world_width_BU = Material N Image Width Px / Scanner Pixels Per BU` | `62992.16` |

`bandMeta.blender.texture_world_width_m` (= `image_width_px / dpi × 0.0254`, eg. 0.7153 m for thread001) is **computed by the producer and shipped** but **no socket reads it yet** — the .blend's legacy two-socket path (`Image Width Px` ÷ `Scanner Pixels Per BU`) does the equivalent divide. Adding a `Texture World Width BU` socket is in the [open scope](README.md#whats-remaining).

### 3. Render-settings path (draft.renderSettings → modifier)

Per-project, set in the wizard's Step 3 Render Preview controls. Producer-side normalization in [frontend/src/domain/draft.ts:normalizeRenderSettings](../../frontend/src/domain/draft.ts); consumer-side `map_unit_setting` remap in [backend/app/blender_sync.py](../../backend/app/blender_sync.py).

| renderSettings field | Range on UI | Backend remap | Blender socket | What it drives |
|---|---|---|---|---|
| `spacing` | 0..1 (default 0) | `0..1 → 0.026..0.10` via `map_unit_setting` | `Spacing` | Strand-to-strand spacing in world units. 0.026 m = tightest weave; 0.10 m = loosest. |
| `patternNoiseX` | 0..1 (default 0) | `0..1 → 0..0.03` | `Pattern Noise X` | Horizontal positional jitter per strand. Breaks regular-grid artefacts. |
| `patternNoiseY` | 0..1 (default 0) | `0..1 → 0..0.03` | `Pattern Noise Y` | Vertical positional jitter per strand. |
| `uvRandomU` | 0..20 (default 0) | identity (pushed as float) | `UV Random U` | Per-strand U-shift on texture sampling. 0 = deterministic spool; higher = more visible variation across strands. Phase 5 made stride the default variation source. |
| `textureUCalibration` | hidden default 0.1 | identity multiplier | `Material N Texture Scale U` formula | Divides the fit-aware U scale by 10 by default. Not exposed in the Web UI; use JSON/env override only for debugging. |
| `arc1VPadding` | 0..0.25 (default 0.02) | identity | `Arc 1 V Padding` | Expands the core texture band on both sides inside the .blend graph. |
| `warpThreads` / `weftThreads` | presets `80`, `120`, `160`, `200` | identity ints | `Warp Threads` / `Weft Threads` | One Web UI zoom selector writes both values together. The frontend still floors to the draft's actual end/pick count if that exceeds a preset. |
| (always 0) | n/a | n/a | `UV Random V` | Pinned to 0. V-axis randomization is off by user direction (would misalign the Arc 1/2 V-band partition). |

### 4. Pinned footgun defaults

Asserted by the producer ([blender_live.py:PINNED_FOOTGUN_SOCKETS](../../backend/app/blender_live.py)) on every bandMeta push. The set contains one halo gate plus four V-related controls. In the 2026-05-19 checkpoint, the approved values are neutral V offset, sub texture scale `1`, and sub texture offset `0`. Leave the set at the pinned values unless you are intentionally changing the view-projection/material-phase contract. See [../BlenderFixes/lessons.md](../BlenderFixes/lessons.md) Rules 11, 12, 34, 35, 36, and 37.

| Blender socket | Pinned value | What happens if it drifts |
|---|---|---|
| `Sub Strand Enable` | `True` *(critical)* | `False` → main-strand geometry only → `is_sub_strand=0` everywhere → `PW Band - Band V` falls back to `Arc1 Map` only → halo never renders. Phase 3g's central fix was pinning this on. |
| `Texture Scale V` | `1.0` | Drift multiplies the V output, misaligning the entire Arc 1/2 band partition vs the actual yarn V positions in the texture. |
| `Texture Offset V` | `0` | Neutral V phase for the approved direct-material checkpoint. The old `0.031914920` value was a checker/material phase-alignment experiment. |
| `Sub Texture Scale V` | `1.0` | Approved checkpoint value for the sub-strand V scale socket. Keep it pinned with `Sub Texture Offset V = 0` unless a future graph contract is visually accepted with crop renders. |
| `Sub Texture Offset V` | `0.0` | Same idea on the offset axis. |

### 5. Draft-driven sockets (DraftDocument → modifier)

Pushed each render from the [DraftDocument](../../frontend/src/domain/types.ts) and project bindings. Geometry comes from the live `WebDraft_Live` mesh that [build_blender_sync_code](../../backend/app/blender_sync.py) writes per render.

| DraftDocument source | Blender socket | What it drives | Notes |
|---|---|---|---|
| `WebDraft_Live` object | `Draft Object` | Source of `cell_code` / `warp_material_id` / `weft_material_id` face attributes the graph samples | Built per render from `draft.drawdown` |
| `draft.threading.length` | `Draft Columns` | Cell count along U | |
| `draft.treadling.length` | `Draft Rows` | Cell count along V | |
| `renderSettings.warpThreads` | `Warp Threads` | Warp strand count along the swatch | Web UI zoom presets: `80`, `120`, `160`, `200`; frontend floors to `draft.threading.length` when needed |
| `renderSettings.weftThreads` | `Weft Threads` | Weft strand count along the swatch | Same zoom preset as warp; frontend floors to `draft.treadling.length` when needed |
| `colorBindings.warp[i].yarnAssetId` | `WebDraft_Live.warp_material_id` attribute | Per-cell warp material selection. | Legacy `Warp Material Cycle` sockets were removed in the 2026-05-27 graph cleanup. |
| `colorBindings.weft[i].yarnAssetId` | `WebDraft_Live.weft_material_id` attribute | Per-cell weft material selection. | Legacy `Weft Material Cycle` sockets were removed in the 2026-05-27 graph cleanup. |
| ordered asset list | `Material 1..16` (NodeSocketMaterial inputs in `Material Slots` panel) | Per-slot material picks. Slot index = ordered position of the yarn asset in the project bindings (first-seen first). | Material 1 also link-drives `Set Material.Material` inside the graph; Materials 2-16 feed `PW Set Material 2..16.Material` through `PW Input - Material Slots` Group Input. |

### 6. Quick alphabetical index — every modifier socket the producer touches

Helpful when you're staring at the modifier panel trying to figure out where a value comes from. Skipped: the 96 V-band sockets in `V-Band Mapping` panel (all covered in table 1).

| Socket | Lives in panel | Driven by | Range / default |
|---|---|---|---|
| Amplitude | Pattern | (none — artist default in .blend) | n/a |
| Draft Columns | (root) | `draft.threading.length` | int |
| Draft Object | (root) | live `WebDraft_Live` mesh | NodeSocketObject |
| Draft Rows | (root) | `draft.treadling.length` | int |
| Geometry | (root) | (modifier input from object base mesh) | n/a |
| Material 1..16 | Material Slots | ordered asset list | NodeSocketMaterial |
| Pattern Noise X | Imperfections | `renderSettings.patternNoiseX` | 0..0.03 (after remap) |
| Pattern Noise Y | Imperfections | `renderSettings.patternNoiseY` | 0..0.03 (after remap) |
| Scanner Pixels Per BU | (root) | `bandMeta.blender.scanner_pixels_per_bu` (first asset) | float, ~62992 at 1600 dpi |
| Seed | General | (none — artist default) | int |
| Spacing | Pattern | `renderSettings.spacing` | 0.026..0.10 (after remap) |
| Sub Strand Enable | Sub Strand | **pinned True** | bool |
| Sub Texture Offset V | Sub Strand | **pinned 0** | float |
| Sub Texture Scale V | Sub Strand | **pinned 1** | float |
| Texture Offset V | Texture | **pinned 0** | float |
| Texture Scale U | (root) | **Pinned `1.0` after Phase 5.** Per-yarn scale lives on `Material N Texture Scale U`; per-strand spool offset lives on `U Stride Per Warp End/Weft Pick`. The Phase 4i fit-math + Phase 4d calibration retired. | float |
| Texture Scale V | Texture | **pinned 1** | float |
| Thread Subdivisions | Surface | (artist default) | float |
| U Stride Per Warp End | Imperfections | derived: `(weft_threads × spacing) / texture_world_width_BU × resolved_material_scale_u` (Phase 10h/10u) | float, typical value depends on spacing and resolved per-material U scale; independent of `Arc 1 V Padding` |
| U Stride Per Weft Pick | Imperfections | derived: `(warp_threads × spacing) / texture_world_width_BU × resolved_material_scale_u` (Phase 10h/10u) | float, typical value depends on spacing and resolved per-material U scale; independent of `Arc 1 V Padding` |
| UV Random U | Imperfections | `renderSettings.uvRandomU` (default `0.0` since Phase 5; stride provides natural variation) | 0..20 |
| UV Random V | Imperfections | **forced 0** | float |
| Warp Threads | Pattern | `renderSettings.warpThreads` from the Web UI zoom preset | int |
| Weft Threads | Pattern | `renderSettings.weftThreads` from the same zoom preset | int |
| Wobble Amount / Wobble Scale | Imperfections | (artist default) | float |
| Loose Strand Density / Length / Thickness / Frizz | Loose Strands | (artist default) | float |

U-scale formula for scan-driven yarns (Phase 5 — uniform aspect + spool):

```text
ARC1_V_AROUND_SPAN               = 0.6  # geometry provenance from Phase 3q split
AUTO_TEXTURE_SCALE_U_CORE_FRACTION = ARC1_V_AROUND_SPAN

# Per-render/per-material:
core_v_span                 = core_v_max - core_v_min
material_texture_scale_u    = core_v_span * AUTO_TEXTURE_SCALE_U_CORE_FRACTION  # auto mode

# Per-render globals (read off the modifier at push time):
texture_world_width_BU      = Material N Image Width Px / Scanner Pixels Per BU
warp_strand_length_BU       = Weft Threads × Spacing               # cross-strand span
weft_strand_length_BU       = Warp Threads × Spacing

# Strides — equal to repeats-per-strand so strand N+1 starts where strand N ended:
U Stride Per Warp End       = warp_strand_length_BU / texture_world_width_BU × material_texture_scale_u
U Stride Per Weft Pick      = weft_strand_length_BU / texture_world_width_BU × material_texture_scale_u

# Inside the graph (sampled per vertex, after Phase 10i):
post_bend_length_ratio      = Spline Length after PW Warp/Weft Set Position / straight_strand_length
u_along                     = Spline Parameter Factor after Set Position × post_bend_length_ratio
post_bend_stride            = U Stride socket × post_bend_length_ratio
PW U Scale U Final          = (source_strand_length / texture_world_width_BU) × Material N Texture Scale U
uv_offset_u                 = PW Warp/Weft Variation.UV Offset U + curve_index × post_bend_stride
base_u                      = u_along × PW U Scale U Final + uv_offset_u

# Phase 10k Blender-internal Arc 2 transfer:
pw_strand_id                = curve_index for warp, curve_index + 10000 for weft
arc2_u_from_arc1            = Sample Nearest Surface(base_u on Arc 1, grouped by pw_strand_id)
uv_scaled.x                 = base_u for Arc 1
uv_scaled.x                 = arc2_u_from_arc1 for Arc 2

# Phase 10t/10u Blender-internal project-from-view V + free-flow Arc 2 halo mapping:
projected_v_arc1            = (1 - cos(pi * v_around)) / 2
phase_offset_v              = 0
uv_scaled.y                 = map(projected_v_arc1, 0..1 -> Arc 1 padded V) + phase_offset_v for Arc 1
uv_scaled.y                 = piecewise Arc 2 Top/Core/Bot V + phase_offset_v for Arc 2
Arc 2 top/bot outer V       = raw core seam +/- core_v_slope * outer_section_width
Arc 2 Match Arc 1 V Rate    = False
```

Phase 10j tried an Arc 2 projected-shell U correction but it distorted the texture and was reverted. Phase 10k replaces that with a Blender-internal same-strand U transfer: Arc 2 borrows Arc 1's U from the matching `pw_strand_id` only, while keeping its own V mapping. `pw_strand_id` is not a producer contract field. Current active graph does not expose `pw_visual_u_correction`, `pw_u_factor`, or `pw_thread_kind`.

Phase 10t changes only Blender's internal V mapping. The producer still sends the same Arc 1/Arc 2 V boundaries. The graph maps Arc 1 with its top-view cosine projection, keeps Arc 2 on the Top/Core/Bot path, restores the Arc 2 section masks to `Split Minus/Plus`, and lets Arc 2's top/bottom halo flow from the raw core seam at the core V rate. `Arc 2 Match Arc 1 V Rate` remains in the .blend for comparison but is OFF in the saved state because it would collapse Arc 2 onto Arc 1's core texture range. Phase 10u then sets the approved checkpoint's V phase offset to `0` and the automatic U denominator to `1.0`.

For the current 47052 px / 1600 dpi live-inspection yarn at the default zoom preset (`Warp Threads = 80`, `Spacing = 0.026`):

```text
texture_world_width_BU        = 47052 / 62992.16          = 0.7470
core V span                   = 0.05931
material_texture_scale_u      = 0.05931 × 0.6             = 0.03558
PW U Scale U Auto             = 2.08 / 0.7470             = 2.785
repeats per strand            = 2.785 × 0.03558           = 0.099
u_stride                      = 0.099  (= repeats per strand -> seamless join)
total texture passes (80x)    = 80 × 0.099                = 7.9
```

### Worked example — a single thread001 cell of a 2×2 twill

Given the latest web-UI project (id `23bde041afd6`, 2/2 Twill 8×8, both warp+weft bound to thread001=`bb5464ffe724`):

1. **Producer** writes [yarn_library/20260514_014216_ccb942/metadata.json](../../../yarn_library/20260514_014216_ccb942/metadata.json) with `image_size_px=[45058, 395]`, `dpi=1600`, and a pre-computed `blender` block holding `image_width_px=45058`, `scanner_pixels_per_bu=62992.16`, `core_v_min=0.4835`, `core_v_max=0.5165`, `fiber_top_v_max=0.5367`, `fiber_bot_v_min=0.4582`.
2. **Tryon backend** ([yarn_assets.py:_build_band_meta_from_library](../../backend/app/yarn_assets.py)) mirrors the file into `YarnAsset.bandMeta`, with `library_yarn_id` for provenance.
3. **At render time** ([blender_live.py:build_material_asset_entry](../../backend/app/blender_live.py)) flattens the bandMeta into the entry dict the live-push and headless paths both consume.
4. **Push** writes (for asset slot 1 / Material 1):
   - `Material 1 Image Width Px = 45058`
   - `Material 1 Texture Scale U ≈ 0.03558` (auto U: `(core_v_max - core_v_min) × 0.6`, independent of `Arc 1 V Padding`)
   - `Material 1 Arc 1 V Min = 0.4835`
   - `Material 1 Arc 1 V Max = 0.5165`
   - `Material 1 Arc 2 V Min = 0.4582`
   - `Material 1 Arc 2 V Max = 0.5367`
   - `Scanner Pixels Per BU = 62992.16`
   - `U Stride Per Warp End` and `U Stride Per Weft Pick` derive from spacing, thread count, texture world width, and resolved material U scale; strand `N+1` starts at U = `(N+1) × resolved_scale`.
   - `Sub Strand Enable = True` (footgun)
   - `Texture Scale V = 1.0`, `Texture Offset V = 0`, `Sub Texture Scale V = 1`, `Sub Texture Offset V = 0` (checkpoint footgun pins)
5. **Render settings push** from the project's `draft.renderSettings = {spacing:0, patternNoiseX:0, patternNoiseY:0, uvRandomU:0}` (Phase 5 default for `uvRandomU` is now `0`):
   - `Spacing = 0.026` (remap of 0 → 0.026)
   - `Pattern Noise X = 0.0`
   - `Pattern Noise Y = 0.0`
   - `UV Random U = 0.0` (Phase 5 default; stride spool replaces random scatter)
   - `UV Random V = 0.0`
6. **Cycle push** from `colorBindings = [{scope:warp, yarnAssetId:bb5464...}, {scope:weft, yarnAssetId:bb5464...}]`:
   - `Warp Offset = 0`, `Warp Length 1 = 1`, `Warp Material 1 = 1`, rest 0
   - `Weft Offset = 0`, `Weft Length 1 = 1`, `Weft Material 1 = 1`, rest 0
7. **Material assignment**: `mod["Socket_61"] = WebYarn_thread001_bb5464ff` (Material 1 modifier input → drives Set Material via Group Input link). `obj.material_slots[0].material = WebYarn_thread001_bb5464ff`.

Result: 180 × 180 weave geometry, each face textured with thread001's albedo + alpha using measured V destinations. With Sub Strand Enable on, Arc 2's three-section mapping fires on sub-strand geometry and the halo path is active. Phase 3p keeps the exact Arc 2 split area open because the split should be derived from generated geometry, not texture V-span alone.
