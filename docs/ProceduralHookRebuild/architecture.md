# Architecture

## Separation From Weave

Hook mode is parallel to weave mode, not a replacement. Existing weave names
remain stable:

- `ParametricWeave`
- `WebDraft_Live`
- `Parametric Weave knotty.001`

Hook mode uses:

- `ProceduralHook`
- `HookDraft_Live`
- `Procedural Hook`

## Flow

```text
frontend hook preset
  -> HookPatternDocument
  -> backend normalize/validate
  -> HookBuildSpec intent interpreter
  -> HookDraft_Live face attributes
  -> continuous hook-strip construction
  -> generated ProceduralHook mesh
  -> ProceduralHook modifier sockets as readback/look metadata
  -> yarn material metadata push
  -> render/live preview
```

## V1 Geometry Policy

V1 productionizes the current visual hook archetype. Empty cells and per-chain
metadata are part of the contract immediately; additional stitch shapes can be
added without changing the document shell.

The Pre-V2 node setup is only the visual ruler. It can stay in the `.blend` as
`HookVisualReference_PreV2` or `Procedural Hook.pre-v2-*`, but it must not be
the active production path. Production output is created from the frontend
document and the backend `HookBuildSpec`.

The current implementation is still a mesh-backed bridge, but the bridge should
follow the old construction model: build continuous arc strips, then let
`HookDraft_Live` decide which cells are active and which material each span
uses. The first bridge pass emitted one finished hook per active cell; MCP
topology readback showed 300 disconnected components on a 15 x 20 preset. The
old prototype emitted two long connected arc components for its strip. The V2
bridge now moves toward that old model by emitting continuous row/phase strips
instead of isolated cell hooks.

The previous `Procedural Hook` graph is preserved as `Procedural
Hook.pre-v2-*` for rollback and visual reference.

## Intent Interpreter

The frontend document records what the user means: chart family, dimensions,
symbols, repeats, source metadata, yarn/material choices, and optional gauge or
look hints. The backend converts that into a `HookBuildSpec` before Blender
receives the script. The build spec is the concrete instruction sheet for
Blender:

- grid size and active/empty counts,
- unsupported stitch codes and their V1 fallback archetype,
- chain/course/wale continuity,
- sparse-safe `chain_u_index` travel,
- material slots used by generated strands,
- current visual calibration baseline.

This keeps Blender from guessing user intent from raw rows and columns. Rows,
columns, stitch codes, repeats, yarn chains, and materials come from the
frontend contract; the Pre-V2 graph only informs the desired hook silhouette.

## Live Modifier State

The first mesh-backed V2 bridge accidentally left the visible modifier output
linked directly from input geometry, so the exposed hook controls were only
being written by sync code and did not drive the evaluated result. The sync path
now repairs the output link to the generated object input:

```text
Generated ProceduralHook mesh -> Procedural Hook output
```

This makes frontend rows/columns, empty cells, material slots, and
`chain_u_index` visible immediately. The Pre-V2 prototype values remain the
visual baseline for generated mesh settings, but the native graph is not used as
production output.

All raw `Socket_*` drivers on `ProceduralHook > Hook` are removed during sync.
Those drivers were unsafe after socket additions; one had drifted onto
`Material 1`.

## Construction Model

The frontend document is not a mesh recipe. It is a draft:

- `stitchCodes` masks active/empty cells.
- `chainIds` and `chain_u_index` describe yarn identity and continuous texture
  travel.
- `chains[].materialSlot` binds generated spans to `Material 1..16`.

The geometry recipe should stay close to the old hook graph:

- create a line/strip of control points,
- bend the strip into repeating hook arcs,
- build the second interlocking phase/arc,
- apply the half-tube/yarn surface and UV attributes,
- split only when the draft has holes.

## Pattern Pipeline

Hook/Knit mode is a chart pipeline:

- Step 2 can load built-in starter structures, crochet symbol charts, knit
  texture charts, machine-knit repeat grids, and local hook pattern-book JSON.
- The frontend preserves chart intent: structure family, reading direction,
  repeat unit, stitch legend, source/license metadata, gauge, and reserved
  stitch codes.
- Blender V1 renders empty cells and active cells only, but unsupported
  nonzero stitch codes stay in the document for later native archetypes.
