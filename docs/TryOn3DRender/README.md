# Try-On 3D Render

The Step 4 "Try On 3D" page lets a user pick one or more real 3D objects, press
**Render**, and watch Blender drape their generated fabric onto each object,
**one at a time**, with each finished image appearing in a gallery as it lands.

This replaces the old Step 4, which was a faked three.js mannequin/sofa that
just tiled the flat swatch in the browser. The new step renders the same kind of
"draped" images you can see under `Renders/TMPrenders/` (per pattern: a seamless
tile texture → a set of draped Cycles renders), but driven from the UI.

Read in this order:

| # | file | what it covers |
|---|------|----------------|
| 1 | [plan.md](plan.md) | Architecture, request flow, render-script design, and the build phases. |
| 2 | [data_contract.md](data_contract.md) | The target catalog shape, API request/response shapes, and the Blender material/object contract inside `Objects.blend`. |
| 3 | [decision_log.md](decision_log.md) | Why the texture source, target model, sequencing, and headless-only choices are what they are. |

## TL;DR

- **Scene file:** `Renders/Objects.blend` is tracked in Git (override with `TRYON_BLEND_FILE`).
  Organized into one collection per showcase object (`Backdrop_Cloth_08`,
  `Cushion`, `Sphere`) that share the fabric material `Material.001`.
- **What gets applied:** the user's seamless **tile** texture from Step 3
  (preferred) or the flat render-preview image (fallback) is swapped into
  `Material.001`'s base-color image-texture node.
- **Targets:** a small, JSON-overridable catalog
  (`Renders/tryon_targets.json`) of selectable objects. Each target names the
  collection(s) to enable; the **authored camera is used as-is** (its angled,
  cropped framing is intentional).
- **Sequencing:** all selected targets are submitted at once but rendered by a
  single-worker queue, so Blender runs one render at a time. The UI polls each
  job and shows results progressively.
- **Always headless:** Try-On renders spawn headless Blender against
  `Objects.blend`. They never use the live MCP session (that session holds the
  weave file, not the object scene). The backend preflights the configured
  Blender binary before queueing the batch.
- **Reuses** the existing render-job registry and the
  `/api/blender/render-jobs/{id}` + `/image` endpoints for status + preview.

## Status

| Phase | Status |
|---|---|
| Planning docs | ✓ |
| Render script for `Objects.blend` (texture swap + isolate + frame) | ✓ verified headless on both default targets |
| Backend `tryon_render.py` module + `/api/blender/tryon/*` endpoints | ✓ (sequential queue; integration-tested end to end) |
| Frontend Step 4 rewrite (checkbox picker + progressive gallery) | ✓ builds; replaces the old three.js mockup |
| Tests | ✓ backend `tests/test_tryon_render.py` (7) + full suite 101 pass; frontend build + 15 unit tests pass |

### Default targets shipped

`draped_cloth` (collection `Backdrop_Cloth_08`) and `cushion` (collection
`Cushion`). Each render enables the target's collection, keeps the camera's
collection, excludes the rest, and renders with the **authored camera** (its
angled, intentionally-cropped framing — never moved). Collections the artist
excluded from the view layer are re-enabled for their render. Add more objects by
giving them their own collection in `Objects.blend` and a target naming it in
`Renders/tryon_targets.json`.
