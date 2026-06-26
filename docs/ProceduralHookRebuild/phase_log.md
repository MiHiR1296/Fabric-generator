# Phase Log

## Phase 1 - Initial Implementation

- Added hook-mode docs, frontend domain contract, backend sync/render helpers,
  and tests.
- The first Blender pass is intentionally reversible: the old visual prototype
  is preserved as a rollback group before the V2 node group is installed.

## Phase 2 - Continuous Strip Bridge

- MCP topology comparison showed the first V2 bridge emitted one component per
  active cell: 300 components for the standard 15 x 20 preset.
- The preserved old hook prototype emitted two connected arc components for its
  strip, confirming that the visual construction should be strand/arc based
  rather than cell-object based.
- Replaced the backend per-cell hook path with continuous row/phase strips.
  Dense 15 x 20 now emits 30 connected strip components, keeps
  `HookDraft_Live` as the pattern source, and preserves generated attributes
  including `uv_scaled`, `chain_id`, `chain_u_index`, and `material_id`.

## Phase 3 - Modifier Output Repair

- MCP node readback showed the V2 group still contained the preserved visual
  prototype and its linked controls, but final output was wired from
  `Group Input Geometry -> Group Output Geometry`. That bypass made the
  exposed modifier controls appear to do nothing.
- Patched backend hook sync so every live sync repairs the output link to the
  procedural prototype/control chain before writing socket values.
- Applied the same repair to the open `Codex_Parametrichooks.blend` session.
  MCP A/B checks confirmed Row/Columns/Curve Resolution/Tube Resolution change
  evaluated mesh counts, and Leg Width/Loop Height/Handle Scale/Leg Z Offset
  change evaluated vertex positions.
- Remaining limitation: this restores old-style visual modifier control, but
  it is still not the final HookDraft-native graph. Sparse masks and per-chain
  material routing still need to move from the backend bridge into the node
  construction path.

## Phase 4 - Hook/Knit Pattern Pipeline

- Expanded `HookPatternDocument` from four fixed presets into a chart-oriented
  contract: structure family, row direction, tiled repeats, stitch legend,
  gauge hints, source/license metadata, course IDs, and wale IDs.
- Added built-in hook pattern books for starter hooks, crochet symbol charts,
  knit texture charts, and machine-knit 24-stitch repeat grids. Local hook
  pattern-book JSON can be imported in Step 2.
- Backend now preserves reserved nonzero stitch codes while rendering them with
  the V1 standard hook archetype. Empty cells still split geometry.
- Sync now removes stale raw `Socket_*` drivers and outputs the generated hook
  mesh, not the static prototype path, so frontend rows/columns, sparse cells,
  and material slots visibly affect Blender.
- Verified `/api/blender/sync-hook-project` with 7 x 37, sparse 15 x 21,
  two-material 15 x 21, and final standard 15 x 21 states.

## Phase 5 - First Look-Dev Pattern Pass

- Replaced the frontend's first/default hook preset with `Balanced Interlock`,
  a 16 x 18 generated starter fabric with an 8 x 6 tiled repeat, staggered
  chain IDs, intentional openings, and slimmer yarn settings.
- Updated the backend generated hook strip to offset alternating rows and
  compress row pitch, so hooks visually tuck into the next course instead of
  reading as a flat repeated wall.
- Sent `Balanced Interlock` through the live `/sync-hook-project` path and
  confirmed Blender output is driven by `HookDraft_Live`/generated mesh with
  no stale modifier drivers.
- Screenshot captured at `/tmp/hook_balanced_interlock_16x18.png` for visual
  review. This is a better look-dev baseline, not the final approved knit/hook
  language.

## Phase 6 - Live Blender Modifier Controls

- Found that the active node group still exposed the Pre-V2 controls, but the
  evaluated output was `Group Input Geometry -> Output`; the frontend-generated
  mesh was visible, while manual modifier edits were not part of the generation
  path.
- Added a Blender live-control bridge during hook sync. The bridge stores the
  source hook pattern on `ProceduralHook`, polls the exposed `Hook` modifier
  sockets, and rebuilds `HookDraft_Live` plus the generated hook mesh whenever
  rows, columns, shape, tube, or texture settings change.
- Verified manual socket changes in the open Blender session:
  - `Loop Height` / `Half Tube Radius` changed the generated mesh Z span.
  - `Row=7` and `Columns=11` rebuilt `HookDraft_Live` to 77 faces and the
    generated hook mesh to 41624 vertices / 41272 faces.
  - Restored the approved look-dev baseline to 16 x 18 afterward.
- Note: this bridge is installed by `/sync-hook` and `/sync-hook-project` in the
  active Blender session. A future node-native rebuild should move this logic
  fully into Geometry Nodes so manual controls persist without the Python bridge.

## Phase 7 - Visual Archetype Repair

- User review correctly identified the first generated hook as inverted
  triangles rather than believable hook/knit construction.
- Appended the old `Codex_Parametrichooks.pre-hook-v2-20260618_151434.blend`
  `ProceduralHook` object as a temporary reference and captured
  `/tmp/hook_pre_v2_reference.png`.
- Replaced the row-wise two-arc strip generator with `interlocking_vertical_wales`:
  column-wise rounded S-curves, alternating over/under depth, and continuous
  dense wale runs that resemble the Pre-V2 hook prototype.
- Updated backend and frontend defaults to the dense `Classic Hook Wale 15x21`
  baseline: `Leg Width=0.95`, `Loop Height=2.05`, `Handle Scale=0.72`,
  `Half Tube Radius=0.18`, `Curve Resolution=12`, `Tube Resolution=13`.
- Moved the sparse/staggered `Balanced Interlock` preset out of the first
  default slot so the app opens on the visually stable dense hook baseline.

## Phase 8 - Native Pre-V2 Visual Lock

- Superseded by Phase 9. This phase preserved a useful visual reference, but it
  was not the correct production architecture.
- Screenshot iteration on 2026-06-20 showed the generated bridge could be made
  denser, but still did not match the desired hook shape as well as the original
  Pre-V2 setup.
- Replaced the visible `ProceduralHook` object with a fresh `ProceduralHook`
  appended from `Codex_Parametrichooks.pre-hook-v2-20260618_151434.blend`.
- Kept the object/modifier names stable: `ProceduralHook > Hook`, with the
  native Pre-V2 node group marked as the visual baseline.
- Patched hook sync so native Pre-V2 visual groups are not overwritten by the
  generated mesh bridge. Frontend sync now updates the native modifier sockets
  and keeps the native Geometry Nodes output.
- Verified visually:
  - `/tmp/hook_fresh_native_baseline.png`
  - `/tmp/hook_native_control_changed_after_refresh.png`
  - `/tmp/hook_final_restored_desired_shape_20260620.png`

## Phase 9 - Intent Pipeline Correction

- User clarified that the Pre-V2 setup is only a visual correction reference.
  The product goal is frontend/backend intent collection and Blender
  interpretation.
- Added `HookBuildSpec` as the missing backend interpreter layer between
  `HookPatternDocument` and Blender generation.
- Patched hook sync so production always uses the generated/data-driven path:
  `HookPatternDocument -> HookBuildSpec -> HookDraft_Live -> ProceduralHook`.
- The active production object now stores:
  - `hook_visual_mode = generated_data_driven_production`
  - `hook_visual_reference_role = pre_v2_calibration_reference_only`
  - `_hook_build_spec_json`
- Pre-V2 remains a calibration reference for screenshots and silhouette tuning,
  not the renderer used by frontend sync.

## Phase 10 - Shape Workbench Documentation Split

- User asked to pause implementation and first understand the freshly
  reingested Pre-V2 Geometry Nodes setup.
- Created `../docs/ProceduralHookShapeWorkbench/` in the shared
  `yarnseamless UI/docs` folder as a separate source of truth for the shape
  workbench anatomy.
- Documented:
  - current live object and source `.blend`,
  - graph construction pipeline,
  - exposed modifier controls,
  - object-level row/column drivers,
  - node-group drivers for `Mesh Line Count` and `Array Count`,
  - nested half-tube surfacing group,
  - production adaptation notes.
- This keeps shape-language discovery separate from the broader
  frontend/backend `HookPatternDocument` production pipeline.
