# Phase log — seamless tile mode

> **Read this if** you want to know what has been investigated, backed up, changed, or verified for tileable fabric renders. Append-only. Each phase should record Motivation / Diagnosis / Fix or Plan / Verification / What was NOT done.

---

## Phase 0 — start tileability investigation

**Date**: 2026-05-25

### Motivation

The current Blender render works as a fabric swatch preview, but when the rendered PNG is tiled into a larger texture, seams are visible. The user proposed using the procedural nature of the geometry-node setup to add controlled boundary geometry or edge constraints, so multiple generated tiles can become seamless without making every tile identical.

The user specifically wants this explored as an optional mode that can be enabled or disabled, leaving the normal swatch renderer unconcerned.

### Diagnosis

Read-only inspection of the running Blender scene and existing docs/code confirmed the current renderer is procedural enough to support this direction:

- target object: `ParametricWeave`
- modifier: `Weave`
- node group: `Parametric Weave knotty`
- draft source: `WebDraft_Live`
- exposed node-group inputs: 202
- key controls already exposed: draft dimensions, warp/weft thread counts, spacing, seed, pattern noise, UV random, U stride, per-material yarn sockets, Arc 1 padding, Arc 2 controls
- current render path builds one `preview.png`; it does not own a tile boundary contract

The seam problem is therefore not just an image-export problem. The tile edges need procedural agreement across geometry, draft/material state, UV phase, and randomness.

### Backup

Created a baseline backup before any tileability work:

```text
Codex_ParametricWeave.pre-seamless-tile-mode-study-20260525_141429.blend
```

SHA-256 at creation time:

```text
43074f83fc4781826366e4fb9b124e60108eb41843a7c187eff0895c6a077fa3
```

This matched the canonical `Codex_ParametricWeave.blend` at backup time.

### Plan

Keep normal rendering unchanged. Add a future optional tile mode around the current renderer:

```text
Normal mode:
  current swatch render

Tile mode:
  tile-aware dimensions
  guard-band geometry
  periodic draft/material lookup
  edge-controlled UV/random state
  overscan render
  center crop
```

First proof should be one reliable tile, not a full tile set:

1. Render top-down, preferably orthographic.
2. Align tile size to exact draft/material repeat.
3. Disable or freeze random/noise near boundaries.
4. Generate overscan/guard strands outside the final crop.
5. Crop a 1024 x 1024 tile.
6. Tile it 3 x 3 and inspect seams.

After that, expand into edge-compatible variants or Wang-style tiles.

### Verification

- Backup file exists and is byte-identical to the canonical `.blend` at creation.
- New documentation folder created under `docs/BlenderFixes/SeamlessTileMode/`.
- No Blender graph edits were made in this phase.

### What was NOT done

- Did not edit `Codex_ParametricWeave.blend`.
- Did not save changes from the live Blender session.
- Did not add sockets or node groups.
- Did not change backend render jobs.
- Did not add frontend UI.
- Did not attempt postprocessing seam fixes.

### Lesson

Tileability is a boundary-condition problem. Rendering many slightly different swatches can reduce obvious repetition, but unless their edges obey a shared contract, it creates more seam combinations rather than fewer.

---

## Phase 1 — frontend-triggered guarded tile export job

**Date**: 2026-05-25

### Motivation

User clarified the intended product workflow:

1. User chooses a material look/feel in the frontend.
2. User clicks a frontend button.
3. Backend starts a Blender process.
4. Blender renders the needed number of guarded tile renders.
5. Backend stitches them together.
6. Frontend shows the final output.

This should be possible without immediately changing the existing normal swatch preview.

### Diagnosis

The existing render system already had the right primitives:

- `requestProjectRender(...)` sends draft + yarn assets + color bindings.
- `submit_project_render_job(...)` validates bindings and builds material payloads.
- `build_headless_render_script(...)` can target either live MCP Blender or headless Blender.
- `RenderJob` polling and `/api/blender/render-jobs/{job_id}/image` already show finished PNGs in the UI.

Missing pieces:

- no frontend button for tile export
- no backend route for multiple guarded renders
- no job runner that loops through tile renders
- no stitcher that composites the guarded outputs into a final texture

### Fix

Added a first-pass tile export path.

Backend:

- `backend/app/main.py`
  - Added `ProjectTileRenderRequest`.
  - Added `POST /api/blender/render-project-tiles`.
- `backend/app/render_jobs.py`
  - Added tile options: tile count, tile resolution, guard threads, variation strength.
  - Added `submit_project_tile_render_job(...)`.
  - Added `_run_tile_render_job(...)`.
  - Added guarded-tile thread expansion:
    - `full_warp_threads = base_warp_threads + 2 * guard_threads`
    - `full_weft_threads = base_weft_threads + 2 * guard_threads`
  - Added per-tile render resolution expansion.
  - Added modest per-tile seed/noise/UV variation.
  - Added `_stitch_tile_grid(...)`, which overlap-blends guard pixels into one final `tile_export.png`.
  - Extended `build_headless_render_script(...)` with an optional `render_resolution` parameter.

Frontend:

- `frontend/src/domain/types.ts`
  - Added `TileRenderOptions`.
- `frontend/src/utils/parserApi.ts`
  - Added `requestProjectTileRender(...)`.
- `frontend/src/App.tsx`
  - Added tile job state, polling, and handler.
- `frontend/src/components/ColorMappingStep.tsx`
  - Passed tile job props through to `RenderPanel`.
- `frontend/src/components/RenderPanel.tsx`
  - Added `Build Tile Texture`.
  - Added controls for 4 / 9 / 12 renders, tile size, guard threads, and variation.
  - Added stitched tile output preview.
- `frontend/src/styles/index.css`
  - Added small layout rules for tile export controls/result.

### Verification

- `backend/.venv/bin/python -m py_compile backend/app/main.py backend/app/render_jobs.py`
- backend import smoke:
  - `_tile_grid_for_count(12)` returned `(4, 3)`
  - tile option normalization returned expected values
- `cd frontend && npm run build`
- `GET /api/parser/health` returned ok
- `GET /api/blender/health` saw live Blender on port 9876

### What was NOT done

- Did not edit `Codex_ParametricWeave.blend`.
- Did not add edge-profile sockets to `Parametric Weave knotty`.
- Did not make tiles mathematically interchangeable yet.
- Did not guarantee outer-edge seamlessness of the final stitched PNG.
- Did not add a download button yet; the image is available through the existing render-job image URL once complete.

### Lesson

A useful product workflow can be scaffolded before the perfect graph-level edge contract exists. Guarded overscan + overlap stitching gives the frontend/backend pipeline a real output to inspect, while future Blender graph work can replace the approximate seam hiding with explicit procedural boundary matching.

---

## Phase 2 — simplify tile controls and make preview mode exclusive

**Date**: 2026-05-25

### Motivation

User clarified the frontend behavior:

- do not expose tile resolution, variation, or guard-thread controls
- the tile output should not add a second empty preview box
- when tile preview is active, hide the normal Blender preview
- when normal Blender preview is active, hide the tile preview

### Diagnosis

Phase 1 exposed too many implementation details. Guard threads, tile resolution, and variation strength are tuning parameters for the backend pipeline, not material look controls. The UI also showed a second tile output panel even before the user requested a tile export, which made the render step feel noisy and incorrect.

### Fix

Frontend:

- `frontend/src/components/RenderPanel.tsx`
  - Kept only the tile render-count control.
  - Moved tile resolution, guard threads, and variation strength into hidden defaults:
    - `tileResolution = 1024`
    - `guardThreads = 8`
    - `variationStrength = 0.25`
  - Replaced the two-output layout with an exclusive preview mode.
- `frontend/src/App.tsx`
  - Added `activePreviewMode`.
  - Clicking `Render Preview` switches to normal render mode.
  - Clicking `Build Tile Texture` switches to tile mode.
- `frontend/src/components/ColorMappingStep.tsx`
  - Passes the active preview mode into the render panel.
- `frontend/src/styles/index.css`
  - Adjusted tile settings layout for a single visible control.

### Verification

- `cd frontend && npm run build`
- `cd frontend && npm run test:unit`
- `backend/.venv/bin/python -m py_compile backend/app/main.py backend/app/render_jobs.py`

### What was NOT done

- Did not change backend tile defaults.
- Did not change the tile job API shape; the frontend still sends the hidden defaults.
- Did not edit the `.blend`.

### Lesson

Tile export has implementation knobs and user controls. Keep them separate. The user chooses how many renders they want; the system owns guard width, output size, and stitching variation until those choices become meaningful creative controls.

---

## Phase 3 — tile-aware Blender render setup and wrap-aware stitcher

**Date**: 2026-05-25

### Motivation

After the frontend and backend scaffold existed, the remaining gap was that the tile export path still behaved too much like a normal swatch render plus image compositing. Tile export needs the Blender render itself to be stable for texture work: square orthographic framing, repeat-aligned thread counts, and guard pixels that contribute across the final image boundary.

### Backup

Created a fresh backup before the Blender-side tile render work:

```text
Codex_ParametricWeave.pre-seamless-tile-render-20260525_145040.blend
```

SHA-256 at creation time:

```text
43074f83fc4781826366e4fb9b124e60108eb41843a7c187eff0895c6a077fa3
```

This matched `Codex_ParametricWeave.blend` at backup time.

### Diagnosis

The `.blend` graph already generates the cloth procedurally and the backend can change warp/weft thread counts. For this phase, a deep node-graph rewrite was not the safest next move. The useful Blender-side contract can be added through the generated render script:

- use a dedicated top-down orthographic tile camera
- frame the `Space` object, falling back to `ParametricWeave`
- align base tile dimensions to draft/material repeat boundaries
- keep guard threads internal
- make the stitcher periodic at the final canvas edges

### Fix

Backend:

- `backend/app/render_jobs.py`
  - Added `tile_render_mode` to `build_headless_render_script(...)`.
  - In tile mode, the generated Blender Python creates or reuses `SeamlessTileCamera`.
  - The tile camera is orthographic, top-down, and framed from `Space` bounds.
  - `_run_tile_render_job(...)` now enables `tile_render_mode=True` for all tile renders.
  - Base warp/weft thread counts snap to the least common multiple of draft repeat and material cycle length.
  - Added `_wrapped_segments(...)`.
  - Updated `_stitch_tile_grid(...)` so guard pixels wrap around the stitched output instead of being clipped at the outside edges.
- `backend/app/blender_sync.py`
  - Updated the default MCP port to `9876`, matching the Makefile and current BlenderMCP setup.

Tests:

- `backend/tests/test_render_jobs.py`
  - Added coverage for tile-camera script generation.
  - Added coverage for repeat alignment helper behavior.
  - Added a small stitcher test proving wrapped pixels contribute to the opposite canvas edge.
- `backend/tests/test_blender_sync.py`
  - Added coverage for the default live Blender MCP port.

Docs:

- Updated `architecture.md` with the tile camera, repeat alignment, and periodic guard blending.

### Verification

- `backend/.venv/bin/python -m py_compile backend/app/main.py backend/app/render_jobs.py backend/app/blender_sync.py`
- generated tile render script compile smoke passed
- `cd backend && . .venv/bin/activate && python -m unittest tests.test_render_jobs tests.test_blender_sync tests.test_blender_live`
- `cd frontend && npm run build`
- `cd frontend && npm run test:unit`
- `git diff --check`
- `GET /api/parser/health` returned ok.
- `GET /api/blender/health` returned ok and saw the live Blender bridge on port `9876`.

### What was NOT done

- Did not edit or save `Codex_ParametricWeave.blend`.
- Did not add graph-level edge-profile sockets yet.
- Did not make separate individual tiles interchangeable by edge type.
- Did not run a full live multi-tile render in this phase; that can take several Blender render passes.

### Lesson

The first robust tile mode does not need to start with a risky node-graph mutation. A script-owned tile camera plus repeat-aligned thread counts gives the geometry-node setup a cleaner procedural boundary, and periodic guard blending prevents the stitcher from reintroducing a hard outer seam.

---

## Phase 4 — save persistent tile rig into the Blender file

**Date**: 2026-05-25

### Motivation

The frontend and backend tile export path was wired, but the canonical `.blend` still did not visibly carry the final tile setup. That made the implementation feel incomplete: the backend could create the camera dynamically, but opening the Blender file did not show the tile-mode render rig or the contract.

### Backup

Created a fresh backup immediately before saving the persistent tile rig:

```text
Codex_ParametricWeave.pre-final-seamless-tile-wire-20260525_150203.blend
```

SHA-256 at creation time:

```text
43074f83fc4781826366e4fb9b124e60108eb41843a7c187eff0895c6a077fa3
```

After saving the tile rig, `Codex_ParametricWeave.blend` changed to:

```text
6e099f4a3b5e9eeb7701ef9de01e152fb788c3ae66342c1f5342b37ffcde7f0f
```

### Diagnosis

The live Blender file already had the procedural controls tile mode needs:

- `ParametricWeave`
- `WebDraft_Live`
- `Space`
- `Weave` modifier
- `Parametric Weave knotty`
- interface sockets for `Draft Object`, `Draft Columns`, `Draft Rows`, `Warp Threads`, `Weft Threads`, `Spacing`, `Seed`, `Pattern Noise X/Y`, and `UV Random U/V`

The missing saved object was the tile render camera/rig.

### Fix

Saved the following into `Codex_ParametricWeave.blend`:

- `SeamlessTileCamera`
  - type: `CAMERA`
  - camera type: `ORTHO`
  - framed to `Space`
  - location: `(1.5, 1.5, 6.004...)`
  - orthographic scale: `3.0015`
- `SeamlessTileMode` collection
- `SeamlessTileMode_README` Blender text block
- scene custom properties:
  - `seamless_tile_mode_ready`
  - `seamless_tile_camera`
  - `seamless_tile_default_resolution`
  - `seamless_tile_default_guard_threads`
  - `seamless_tile_backend_route`
  - `seamless_tile_contract`
- `ParametricWeave` custom properties marking the tile geometry contract
- `Parametric Weave knotty` custom properties marking that tile mode uses the existing procedural sockets

The saved scene camera remains the normal `Camera`. Tile export jobs explicitly switch to `SeamlessTileCamera`; normal preview renders are not hijacked.

Docs:

- Updated `README.md` so current status no longer says no `.blend` edit was made.
- Updated `architecture.md` so the current path includes the saved Blender rig.

### Verification

Live Blender readback after save:

```text
filepath: Codex_ParametricWeave.blend
scene_camera: Camera
tile_ready: true
tile_camera: SeamlessTileCamera, ORTHO, ortho_scale 3.001499891281128
has_text_doc: true
target_tile_ready: true
node_group_tile_ready: true
```

Code checks:

- `backend/.venv/bin/python -m py_compile backend/app/main.py backend/app/render_jobs.py backend/app/blender_sync.py`
- `cd backend && . .venv/bin/activate && python -m unittest tests.test_render_jobs tests.test_blender_sync tests.test_blender_live`
- `cd frontend && npm run build`
- `cd frontend && npm run test:unit`
- generated tile render script compile smoke passed
- `git diff --check`
- `GET /api/parser/health` returned ok
- `GET /api/blender/health` returned ok and listed `SeamlessTileCamera`

### What was NOT done

- Did not replace the existing `Parametric Weave knotty` graph.
- Did not add a named Wang-tile edge-profile socket system.
- Did not expose guard threads, resolution, or variation controls to the user.

### Lesson

When the product behavior depends on Blender-specific setup, the canonical `.blend` should visibly carry that setup. Runtime repair code is useful, but it should not be the only place where the final render rig exists.

---

## Phase 5 — reduce internal guard width after visible overlap mark

**Date**: 2026-05-25

### Motivation

The user observed a large plus-shaped mark in the middle of the tile output. That lines up with the intersection where stitched tile seams cross. The `8` guard-thread default made the overlap/blend region too wide for the current renderer.

### Backup

Created a fresh `.blend` backup before changing the saved guard-thread metadata:

```text
Codex_ParametricWeave.pre-guardthreads-2-20260525_151646.blend
```

SHA-256 at creation time:

```text
6e099f4a3b5e9eeb7701ef9de01e152fb788c3ae66342c1f5342b37ffcde7f0f
```

After updating the metadata, `Codex_ParametricWeave.blend` changed to:

```text
3a94a2d2f616f01aa0e5cefc510bc68f504c1a540067ba056ca4d67862330d23
```

### Diagnosis

Guard threads are useful because they keep strand geometry, alpha, antialiasing, and lighting from ending exactly on the crop. But too much guard area means the stitcher blends a wide band through every tile boundary. In a 2x2 or 3x3 stitched output, those horizontal and vertical bands intersect as a visible plus sign.

### Fix

Reduced the internal guard default from `8` to `2`.

Code:

- `backend/app/render_jobs.py`
  - `DEFAULT_TILE_GUARD_THREADS = 2`
- `backend/app/main.py`
  - `ProjectTileRenderRequest.guardThreads = 2`
- `frontend/src/components/RenderPanel.tsx`
  - hidden `TILE_EXPORT_DEFAULTS.guardThreads = 2`

Blender:

- saved `Codex_ParametricWeave.blend` with:
  - `scene['seamless_tile_default_guard_threads'] = 2`
  - `ParametricWeave['seamless_tile_default_guard_threads'] = 2`
  - `Parametric Weave knotty['seamless_tile_default_guard_threads'] = 2`
  - updated `SeamlessTileMode_README`

Docs:

- Updated `architecture.md`.
- Updated `lessons.md`.
- Added this phase entry.

### Verification

Live Blender save response reported:

```text
scene_guard_threads: 2
target_guard_threads: 2
group_guard_threads: 2
```

Code checks:

- `backend/.venv/bin/python -m py_compile backend/app/main.py backend/app/render_jobs.py backend/app/blender_sync.py`
- `cd backend && . .venv/bin/activate && python -m unittest tests.test_render_jobs tests.test_blender_sync tests.test_blender_live`
- `cd frontend && npm run build`
- `cd frontend && npm run test:unit`
- `git diff --check`
- `GET /api/blender/health` returned ok and listed `SeamlessTileCamera`

### What was NOT done

- Did not expose guard threads in the UI.
- Did not change tile resolution or variation strength.
- Did not change the saved tile camera.

### Lesson

Guard width is a seam-management tuning value. Wider is not automatically better; once the guard band itself becomes visible, shrink it and keep the user-facing control surface unchanged.

---

## Phase 6 — reduce internal guard width to one thread

**Date**: 2026-05-25

### Motivation

The plus-shaped mark was still visible after reducing the default guard from `8` to `2`. The user called out that the Python image merge may be contributing to the cross, and asked to try `1` guard thread.

### Backup

Created a fresh `.blend` backup before changing the saved guard-thread metadata again:

```text
Codex_ParametricWeave.pre-guardthreads-1-20260525_154848.blend
```

SHA-256 at creation time:

```text
3a94a2d2f616f01aa0e5cefc510bc68f504c1a540067ba056ca4d67862330d23
```

After updating the metadata, `Codex_ParametricWeave.blend` changed to:

```text
c903f4026b6b941ecd6389955a4b3c3f17c308a9c982412a9f41a6cf06f30a16
```

### Diagnosis

With the current stitcher, every guarded tile edge contributes a blend band. When many slightly different renders are stitched into one texture, those blend bands can still be seen as a horizontal/vertical cross. Narrowing the guard band should reduce the visual footprint while keeping a small crop cushion.

### Fix

Reduced the internal guard default from `2` to `1`.

Code:

- `backend/app/render_jobs.py`
  - `DEFAULT_TILE_GUARD_THREADS = 1`
- `backend/app/main.py`
  - `ProjectTileRenderRequest.guardThreads = 1`
- `frontend/src/components/RenderPanel.tsx`
  - hidden `TILE_EXPORT_DEFAULTS.guardThreads = 1`

Blender:

- saved `Codex_ParametricWeave.blend` with:
  - `scene['seamless_tile_default_guard_threads'] = 1`
  - `ParametricWeave['seamless_tile_default_guard_threads'] = 1`
  - `Parametric Weave knotty['seamless_tile_default_guard_threads'] = 1`
  - updated `SeamlessTileMode_README`

Docs:

- Updated `architecture.md`.
- Added this phase entry.

### Verification

Live Blender save response reported:

```text
scene_guard_threads: 1
target_guard_threads: 1
group_guard_threads: 1
tile_camera: SeamlessTileCamera
```

Code checks:

- `backend/.venv/bin/python -m py_compile backend/app/main.py backend/app/render_jobs.py backend/app/blender_sync.py`
- `cd backend && . .venv/bin/activate && python -m unittest tests.test_render_jobs tests.test_blender_sync tests.test_blender_live`
- `cd frontend && npm run build`
- `cd frontend && npm run test:unit`
- `git diff --check`
- source scan confirms current app/architecture defaults are `1`

### What was NOT done

- Did not expose guard threads in the UI.
- Did not change tile resolution or variation strength.
- Did not replace the image stitcher yet.

### Lesson

If the cross remains at `1`, the next suspect is no longer guard width; it is the merge strategy itself or the per-tile variation. At that point the stitcher should move away from broad overlap blending and toward crop/placement or a lower-variation edge pass.

---

## Phase 7 — zero-guard edge-to-edge tile paste

**Date**: 2026-05-25

### Motivation

The user asked to remove guard edges entirely and stop doing image merging/editing. The desired behavior is simple adjacency: render each pattern tile at the final size and place tiles directly next to each other with no overlap and no gap.

### Backup

No new `.blend` backup was made for this tiny tuning step, per user preference. The previous recovery point is:

```text
Codex_ParametricWeave.pre-guardthreads-1-20260525_154848.blend
```

### Diagnosis

Even a one-thread guard still runs through the blend/wrap stitcher. That means the stitcher can still contribute visible seam structure. To test the cleanest possible behavior, zero-guard mode needs a separate paste-only path rather than passing through the weighted merge path with a zero-width guard.

### Fix

Reduced the internal guard default from `1` to `0`.

Code:

- `backend/app/render_jobs.py`
  - `DEFAULT_TILE_GUARD_THREADS = 0`
  - `_stitch_tile_grid(...)` now uses paste-only behavior when `guard_px <= 0`.
  - zero-guard mode rejects rendered tiles that are not exactly `tile_resolution x tile_resolution`, so it does not silently crop, resize, blend, wrap, or repair images.
- `backend/app/main.py`
  - `ProjectTileRenderRequest.guardThreads = 0`
- `frontend/src/components/RenderPanel.tsx`
  - hidden `TILE_EXPORT_DEFAULTS.guardThreads = 0`

Blender:

- saved `Codex_ParametricWeave.blend` with:
  - `scene['seamless_tile_default_guard_threads'] = 0`
  - `ParametricWeave['seamless_tile_default_guard_threads'] = 0`
  - `Parametric Weave knotty['seamless_tile_default_guard_threads'] = 0`
  - updated `SeamlessTileMode_README`

Tests:

- Added zero-guard paste-only coverage.
- Added zero-guard size-mismatch rejection coverage.

Docs:

- Updated `architecture.md`.
- Added this phase entry.

### Verification

Live Blender save response reported:

```text
scene_guard_threads: 0
target_guard_threads: 0
group_guard_threads: 0
tile_camera: SeamlessTileCamera
```

Code checks:

- `backend/.venv/bin/python -m py_compile backend/app/main.py backend/app/render_jobs.py backend/app/blender_sync.py`
- `cd backend && . .venv/bin/activate && python -m unittest tests.test_render_jobs tests.test_blender_sync tests.test_blender_live`
- `cd frontend && npm run build`
- `cd frontend && npm run test:unit`
- `git diff --check`
- source scan confirms current app/architecture defaults are `0`

### What was NOT done

- Did not expose guard threads in the UI.
- Did not resize or crop tiles in zero-guard mode.
- Did not add overlap blending in zero-guard mode.

### Lesson

Zero guard means the output is only as continuous as the rendered tile edges themselves. That is useful for diagnosing the renderer: if seams remain now, they are coming from procedural edge mismatch or per-tile variation, not from the image merge.

---

## Phase 8 — tighten tile camera crop and set 1200 px tile defaults

**Date**: 2026-05-25

### Motivation

The user shared `Visible Gap.png`, showing a gap between pasted tiles even after zero-guard mode. The requested defaults were:

- render resolution: `1200 x 1200`
- `bpy.data.cameras["SeamlessTileCameraData"].ortho_scale = 2.975`
- `cycles.samples = 40`

### Backup

No new `.blend` backup was made for this small tuning step, per user preference. The previous recovery point remains:

```text
Codex_ParametricWeave.pre-guardthreads-1-20260525_154848.blend
```

### Diagnosis

The visible gap is not coming from overlap blending anymore because zero-guard mode is paste-only. The screenshot shows an edge rim inside each rendered tile, including around the outer border. When those tile images are pasted together, the captured rims meet and form the visible vertical/horizontal gap. This points to tile-camera framing: the tile render is capturing a little outside the fabric edge. Lowering the orthographic scale from the previous `3.0015` to `2.975` zooms in slightly and should crop out that captured rim.

### Fix

Code:

- `backend/app/render_jobs.py`
  - `DEFAULT_TILE_RESOLUTION = 1200`
  - `DEFAULT_TILE_RENDER_SAMPLES = 40`
  - `DEFAULT_TILE_ORTHO_SCALE = 2.975`
  - `build_headless_render_script(...)` now accepts `render_samples` and `tile_ortho_scale`.
  - Tile jobs pass `render_samples=40` and `tile_ortho_scale=2.975`.
  - Tile camera setup names the camera data block `SeamlessTileCameraData`.
- `backend/app/main.py`
  - `ProjectTileRenderRequest.tileResolution = 1200`
- `frontend/src/components/RenderPanel.tsx`
  - hidden `TILE_EXPORT_DEFAULTS.tileResolution = 1200`

Blender:

- saved `Codex_ParametricWeave.blend` with:
  - `scene.render.resolution_x = 1200`
  - `scene.render.resolution_y = 1200`
  - `scene.cycles.samples = 40`
  - `bpy.data.cameras["SeamlessTileCameraData"].ortho_scale = 2.975`
  - scene/object/node-group metadata updated with the same defaults
  - updated `SeamlessTileMode_README`

Docs:

- Updated `architecture.md`.
- Updated `lessons.md`.
- Added this phase entry.

### Verification

Live Blender save response reported:

```text
scene_resolution: [1200, 1200]
scene_samples: 40
camera_data_name: SeamlessTileCameraData
camera_ortho_scale: 2.9749999046325684
scene_tile_resolution: 1200
scene_guard_threads: 0
scene_tile_samples: 40
```

### What was NOT done

- Did not re-enable overlap blending.
- Did not add guard edges.
- Did not change normal swatch preview defaults.

### Lesson

Once zero-guard mode is paste-only, a visible gap is usually a render-framing problem or a procedural edge-fill problem, not an image-merge problem. Start by making the tile camera crop exactly to the usable fabric area.
