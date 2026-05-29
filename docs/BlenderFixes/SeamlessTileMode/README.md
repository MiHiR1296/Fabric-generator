# Seamless Tile Mode

Planning and implementation log for making the Blender fabric render usable as a repeatable texture tile.

This folder is intentionally scoped under `docs/BlenderFixes/` because the work will touch the same surface as the existing Blender integration: `Codex_ParametricWeave.blend`, `ParametricWeave`, the `Weave` modifier, and the `Parametric Weave knotty` geometry-node graph. It should stay separate from the main BlenderFixes phase log until a change is ready to land in the canonical graph.

## Current status

**Date**: 2026-05-25

Status: frontend, backend, and Blender file are wired for the first complete seamless tile export pass.

Baseline backup before this investigation:

```text
Codex_ParametricWeave.pre-seamless-tile-mode-study-20260525_141429.blend
```

The backup is next to the canonical file and has the same SHA-256 as the source copy at creation time:

```text
43074f83fc4781826366e4fb9b124e60108eb41843a7c187eff0895c6a077fa3
```

Final Blender-file backup before the persistent tile rig was saved:

```text
Codex_ParametricWeave.pre-final-seamless-tile-wire-20260525_150203.blend
```

The canonical file now contains:

- `SeamlessTileCamera`
- `SeamlessTileMode` collection
- `SeamlessTileMode_README` text block
- scene/object/node-group metadata marking the tile export contract

## Documentation index

Read in this order:

| # | doc | what it covers |
|---|---|---|
| 1 | [architecture.md](architecture.md) | The proposed tileable-render architecture: boundary contract, guard band, periodic draft/material/UV/random state, and render crop. |
| 2 | [phase_log.md](phase_log.md) | Append-only investigation and implementation log. Start here to see what has actually been changed or verified. |
| 3 | [lessons.md](lessons.md) | Rules learned while designing tileable procedural fabric output. |

## Goal

Add an optional mode that can export tileable fabric renders without disturbing the normal swatch renderer.

Normal mode should continue to behave exactly as it does today:

```text
Web UI -> FastAPI -> Blender render -> swatch preview
```

Tile mode is a separate export path:

```text
Web UI -> FastAPI -> Blender tile setup -> overscan render -> center crop -> tileable PNG
```

The important principle is that the tile boundary must be owned procedurally before rendering. Postprocessing can hide small defects, but the main guarantee should come from geometry, draft state, material IDs, UV phase, and random fields agreeing at the tile edges.

## Current implementation pass

The first implementation pass adds a new frontend and backend path:

```text
Render Preview step
  Build Tile Texture
        |
        v
POST /api/blender/render-project-tiles
        |
        v
backend tile job
  render N guarded overscan tiles
  overlap-blend guard regions
  write runtime/render_jobs/<job_id>/tile_export.png
        |
        v
frontend polls /api/blender/render-jobs/<job_id>
frontend displays final stitched PNG
```

This pass is practical and wired end to end:

- it reuses the current `Parametric Weave knotty` graph
- it uses existing geometry-node sockets for `Warp Threads`, `Weft Threads`, draft dimensions, material cycles, seed/noise, and UV random state
- it stores a persistent `SeamlessTileCamera` in the `.blend`
- it adds extra guard threads by rendering a larger thread count per tile
- it renders a larger image per tile and overlap-blends the guard regions during stitching
- it supports 4, 9, or 12 renders from the frontend
- the frontend only exposes render count; resolution, guard width, and variation are internal defaults
- the preview area shows either the normal Blender preview or the tile output, not both at once
- it keeps normal Render Preview untouched

This is the complete current export workflow. It is not yet a Wang-tile / named edge-profile system for interchangeable individual tile pieces.

## Logging rules

- Any Blender graph edit gets a new timestamped `.blend` backup first.
- Every phase entry records Motivation, Diagnosis, Fix or Plan, Verification, and What was NOT done.
- If an experiment is only a live-session probe and is not saved into the canonical `.blend`, say that explicitly.
- If a backend or frontend change becomes part of the tile export path, link the exact files and explain whether normal render behavior is affected.
