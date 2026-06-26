# Action Plan

## Phase 1 - Contracts

- Add frontend `HookPatternDocument`, `HookRenderSettings`, hook presets, and
  hook project helpers.
- Add backend hook normalization and `build_hook_sync_code`.
- Add unit tests for sparse grids, chain U order, material slot validation, and
  generated sync code.

## Phase 2 - Live/Render Paths

- Add `/api/blender/sync-hook`.
- Add `/api/blender/render-hook-project`.
- Reuse ready yarn assets and existing material payload generation.

## Phase 3 - Blender File

- Save a timestamped backup of `Codex_Parametrichooks.blend`.
- Rename the previous `Procedural Hook` node group to a rollback name.
- Install a V2 `Procedural Hook` wrapper that preserves the current visual
  prototype while exposing the hook data/material contract.

## Phase 4 - Node-Native Sampler

- Replace the first per-cell backend hook mesh with a continuous strip bridge
  based on the old graph's construction method.
- Use MCP topology readback as a regression signal: dense presets should no
  longer emit one disconnected component per active cell.
- Replace the backend-generated bridge mesh with Geometry Nodes sampling from
  `HookDraft_Live`.
- Move sparse masking, chain U indexing, and per-chain material selection fully
  into the `HookDraft Sampling`, `Sparse Mask`, `Chain Layout`, and `Material
  Selection` frames.
- Keep the frontend/backend document contract unchanged while the GN
  implementation catches up.

## Phase 5 - Hook/Knit Pattern Catalog

- Replace the temporary four-card hook preset shelf with hook pattern books:
  starter hook structures, crochet symbol charts, knit texture charts,
  machine-knit repeat grids, and imported local hook books.
- Preserve chart semantics that Blender cannot render yet: stitch legend,
  reserved stitch codes, row direction, source/license metadata, gauge hints,
  and repeat units.
- Treat generated built-in entries as generated structural samples, not literal
  external pattern transcriptions.

## Phase 6 - Intent Interpreter And Visual Calibration

- Keep the Pre-V2 hook setup as a visual calibration reference only.
- Add a backend `HookBuildSpec` that records how frontend pattern intent is
  interpreted for Blender.
- Ensure `/sync-hook` and `/sync-hook-project` always generate from
  `HookPatternDocument` data, not from the reference node graph.
- Use screenshots of the generated output against `HookVisualReference_PreV2`
  to tune the generated archetype until the production mesh reaches the desired
  hook silhouette.
