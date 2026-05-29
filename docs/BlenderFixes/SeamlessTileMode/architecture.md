# Architecture — seamless tile mode

> **Read this if** you are about to design or implement tileable fabric export for `Parametric Weave knotty`.

## Baseline

The current renderer is a swatch renderer.

```text
WebDraft_Live
  one face per drawdown cell
  cell_code / warp_material_id / weft_material_id face attributes
        |
        v
ParametricWeave
  Weave modifier -> Parametric Weave knotty
  Fit To Space modifier -> Fit Geometry To Space Plane
        |
        v
Camera render -> preview.png
```

The graph already has many ingredients tile mode will need:

- `Draft Object`, `Draft Columns`, `Draft Rows`
- `Warp Threads`, `Weft Threads`, `Spacing`, `Amplitude`
- warp/weft material cycles and draft-sampled material IDs
- per-material yarn metadata sockets
- `Seed`, `Pattern Noise X`, `Pattern Noise Y`
- `UV Random U`, `UV Random V`
- `U Stride Per Warp End`, `U Stride Per Weft Pick`
- post-bend `u_along` storage and same-strand Arc 2 U transfer
- `Sub Strand Enable` and Arc 1 / Arc 2 band mapping

That means tile mode should be feasible without replacing the renderer. The missing piece is a tile boundary contract.

## Why ordinary tiling shows seams

Tiling the final PNG only works if opposite edges represent the same procedural state. Today that is not guaranteed.

Typical seam sources:

- the camera crop does not land on an exact repeat boundary
- the generated fabric extends only to the swatch edge, so lighting, alpha, and antialiasing are cut there
- draft cells and material IDs may not repeat exactly across left/right or top/bottom
- yarn texture U phase may be different on opposite edges
- `UV Random U`, wobble, pattern noise, or seed-driven fields may not be periodic
- the scanned yarn strip itself may not be seamless along U
- perspective camera or nonuniform lighting can create edge brightness differences

## Proposed mode shape

Tile mode is an optional branch around the existing render path.

```text
Normal mode:
  generate current swatch
  render current preview

Tile mode:
  choose tile dimensions in weave/thread units
  generate an overscan region around the final tile
  force periodic or edge-compatible state at tile boundaries
  render larger than final output
  crop the center tile
```

Do not add a visible border. The "edge" is a procedural constraint zone plus render overscan.

## Current implementation path

The current tile export path is wired across the frontend, backend, and `.blend`:

| Layer | File | Responsibility |
|---|---|---|
| Frontend API | `frontend/src/utils/parserApi.ts` | `requestProjectTileRender(...)` calls `/api/blender/render-project-tiles`. |
| Frontend UI | `frontend/src/components/RenderPanel.tsx` | Adds `Build Tile Texture`, render-count control, and a mode-switched preview area for either swatch or stitched tile output. |
| Wizard state | `frontend/src/App.tsx` | Tracks tile job state and polls the existing render-job status endpoint. |
| FastAPI route | `backend/app/main.py` | Adds `POST /api/blender/render-project-tiles`. |
| Backend job | `backend/app/render_jobs.py` | Validates bindings, renders guarded tiles, stitches final PNG, and exposes it through the existing job image route. |
| Blender file | `Codex_ParametricWeave.blend` | Stores `SeamlessTileCamera`, `SeamlessTileMode` collection, tile README text block, and scene/object/node-group metadata. |

The first-pass backend job reuses the existing Blender script builder, but overrides each tile render with:

```text
full_warp_threads = base_warp_threads + 2 * guard_threads
full_weft_threads = base_weft_threads + 2 * guard_threads
full_resolution = tile_resolution * max(full/base thread ratios)
```

Before those counts are expanded, the backend snaps the base tile size to the active repeat:

```text
warp_repeat = lcm(draft_width, warp_material_cycle_length)
weft_repeat = lcm(draft_height, weft_material_cycle_length)

base_warp_threads = next_multiple(base_warp_threads, warp_repeat)
base_weft_threads = next_multiple(base_weft_threads, weft_repeat)
```

This keeps the exported tile boundary on a repeat boundary instead of whatever thread count the normal swatch happened to use.

Tile renders also switch the generated Blender script into tile mode:

```text
SeamlessTileCamera
  type: ORTHO
  source bounds: Space object, falling back to ParametricWeave
  view: top-down XY
  scale: max(Space X, Space Y)
```

The camera is now saved in the `.blend`. The render script still creates/repairs it if a copied file is missing the rig, but the canonical file carries the setup. Normal preview renders continue to use the normal `Camera`; tile jobs explicitly switch to `SeamlessTileCamera`.

Each tile render writes:

```text
runtime/render_jobs/<job_id>/tiles/tile_XX_overscan.png
```

Then the stitcher overlap-blends the guard regions and writes:

```text
runtime/render_jobs/<job_id>/tile_export.png
```

Guard pixels are accumulated with periodic wrapping. In other words, pixels that would fall past the left/top/right/bottom of the stitched canvas wrap to the opposite side before blending. This is important because clipping overscan at the outside of the combined texture would preserve the exact seam this mode is trying to hide.

The existing endpoint serves that final PNG:

```text
GET /api/blender/render-jobs/<job_id>/image
```

Normal `POST /api/blender/render-project` behavior is unchanged.

Frontend control policy:

```text
User-facing:
  tile count: 4 / 9 / 12

Internal defaults:
  tile resolution: 1200
  guard threads: 0
  cycles samples: 40
  SeamlessTileCameraData.ortho_scale: 2.975
  variation strength: 0.25
```

Guard threads are extra warp/weft strands generated around the exported tile. They are not a user-facing creative control. The current value is `0`, which means the backend renders exact tile cells and pastes them edge-to-edge. There is no overlap blending or image repair in zero-guard mode.

## Tile boundary contract

A tile is valid only if its opposite or neighboring edges agree on the values that produce pixels.

For a simple repeatable tile:

```text
left edge state  == right edge state
top edge state   == bottom edge state
```

For a Wang-tile style set:

```text
tile_a.right_edge_type == tile_b.left_edge_type
tile_a.bottom_edge_type == tile_c.top_edge_type
```

The edge contract should eventually cover:

- draft lookup state
- warp/weft material IDs
- yarn `u_along` phase
- per-strand U stride continuity
- random/noise/wobble fields
- strand positions and over/under state
- halo/alpha sampling

Interior variation can be free. Boundary variation must be controlled.

## Guard band

Tile mode can render more fabric than it exports, but the current default does not.

Example:

```text
render area: 1200 x 1200
export crop: 1200 x 1200
guard band: 0 px per side
```

In geometry terms, the guard band should likely be expressed as extra warp ends / weft picks rather than raw pixels. That lets strand crossings, shadows, halos, and antialiasing continue naturally outside the exported crop.

## Periodic draft and material state

The safest first version should use tile dimensions that are integer multiples of:

- draft repeat width
- draft repeat height
- warp material cycle length
- weft material cycle length
- yarn assignment cycle

If the tile is not an exact repeat, the graph or backend needs explicit wrapping logic so draft and material sampling at the border still matches.

## Periodic UV and random state

The hardest part is not mesh position. It is texture and randomness.

Tile mode must control:

- `u_along` phase at the tile edges
- `U Stride Per Warp End`
- `U Stride Per Weft Pick`
- `UV Random U`
- `Pattern Noise X`
- `Pattern Noise Y`
- `Seed`
- any future wobble or loose-strand randomness used inside the tile

Initial proof mode should freeze or disable random controls near the boundary. Later tile-set mode can use edge profiles and only randomize the interior.

## First proof target

The first useful milestone is not a 12-tile set. It is one reliable tile.

Suggested proof:

```text
1. Orthographic top-down render.
2. Noise/random disabled or locked.
3. Tile dimensions aligned to draft/material repeat.
4. Overscan generated outside the export crop.
5. Center crop exported as 1200 x 1200.
6. Result tiled 3 x 3 for inspection.
```

Only after this works should we add multiple edge-compatible variations.

## Future tile-set mode

Once one tile works, tile-set mode can generate many variants:

```text
tile_seed
edge_left_type
edge_right_type
edge_top_type
edge_bottom_type
interior_variation_amount
```

The assembler would place tiles only when neighboring edge types match. This should reduce visible repetition more effectively than rendering many unconstrained random swatches.
