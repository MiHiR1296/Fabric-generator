# Parametric Weave geometry-node guide

This guide describes the cleaned `Parametric Weave knotty` node group in
`Codex_ParametricWeave.blend`. Use it when you need to understand what each
major chunk does before editing the graph.

## Cleanup snapshot

Cleanup date: 2026-05-27.

The cleanup kept the active render behavior and removed graph/UI pieces that no
longer reached the `Group Output`.

| Item | Before | After |
|---|---:|---:|
| Total nodes | 580 | 315 |
| Functional dead nodes | 140 | 0 |
| Interface items removed | 60 | n/a |
| Frames | 12 mixed/legacy frames | 14 semantic frames |
| Helper node groups | 0 cleanup-owned helpers | 4 helper groups |

The cleanup also moved the `Geometry` input to the first input position. That
fixes Blender's load warning:

```text
Node group's geometry input must be the first
```

## How the graph works

The modifier object is `ParametricWeave`. Its first modifier, `Weave`, points to
the `Parametric Weave knotty` node group. The object itself contributes no
important base mesh; the node graph generates the woven fabric.

The hidden `WebDraft_Live` mesh is the live data source. It has one face per
drawdown cell and carries these face attributes:

| Attribute | Meaning |
|---|---|
| `cell_code` | over/under state for the drawdown cell |
| `warp_material_id` | zero-based material slot for the warp strand at that cell |
| `weft_material_id` | zero-based material slot for the weft strand at that cell |

The active graph flow is:

1. `Draft Sampling` reads `WebDraft_Live`.
2. `Strand Generation / Drawdown` creates warp and weft curves and bends them in Z from `cell_code`.
3. `Profile / Mesh` builds the Arc 1 / Arc 2 strand profile and turns curves into mesh.
4. `Texture Coordinates` computes U along the visible strand after bend.
5. `Arc 1 / Arc 2 V Band Mapping` maps cross-section `v_around` into the scanned yarn's V bands.
6. `Same-Strand U Transfer` samples the Arc 1 mesh and makes Arc 2 borrow Arc 1's U from the same physical strand, while keeping Arc 2's own V.
7. `Material Assignment` applies `Material 1..16` based on sampled material IDs.
8. `Loose Strands` adds flyaways.
9. `Assembly` joins everything and sends final geometry to `Output`.

## Modifier interface after cleanup

Root inputs:

| Socket | Purpose |
|---|---|
| `Geometry` | Structural geometry input; kept first for Blender modifier validity. |
| `Scanner Pixels Per BU` | Converts scan pixel width into Blender units for U repeat length. |
| `Texture Scale U` | Global U multiplier. Kept neutral by the backend for scan-driven yarns. |
| `Draft Object` | The `WebDraft_Live` mesh object. |
| `Draft Columns` / `Draft Rows` | Drawdown dimensions used to sample `WebDraft_Live`. |
| `Arc 1 V Padding` | Expands the sampled core band, clamped inside Arc 2. |

Panels:

| Panel | Active sockets |
|---|---|
| `Pattern` | `Warp Threads`, `Weft Threads`, `Spacing`, `Amplitude` |
| `Surface` | `Thread Subdivisions`, `Arc 2 Boundary Inset`, `Arc 2 Match Arc 1 V Rate` |
| `Texture` | `Texture Scale V`, `Texture Offset V` |
| `General` | `Seed` |
| `Imperfections` | Wobble, pattern noise, UV random, U stride controls |
| `Loose Strands` | Density, length, thickness, frizz |
| `Material Slots` | `Material 1..16` |
| `Sub Strand` | `Sub Strand Enable`, `Sub Texture Scale V`, `Sub Texture Offset V` |
| `V-Band Mapping` | `Material N Image Width Px`, `Texture Scale U`, `Arc 1 V Min/Max`, `Arc 2 V Min/Max` |

## Removed UI sockets

These were removed because every downstream node was unreachable from the final
output, or because the current procedural/draft path replaced the older manual
control.

| Removed socket/panel | Why |
|---|---|
| `Over Count`, `Under Count` | Drawdown bend now comes only from `WebDraft_Live.cell_code`. |
| `Main Strand Radius` | Active Arc 1 / Arc 2 profile uses graph-owned fixed radii. |
| `Sub Strand Width`, `Sub Strand Height` | Their radius/sweep adjustment chain was unreachable. |
| `Texture Side Flatten` | The active mapping no longer consumes the side-flatten projection branch. |
| `Material N Top Halo Frac`, `Material N Bot Halo Frac` | Superseded by the current centered/procedural Arc 2 split path. |
| `Match Section Slopes`, `Arc 2 Edge Angle Mapping` | Historical experiments; their switch branches were unreachable. |
| `Warp/Weft Material Cycle` panels | Material IDs now arrive on `WebDraft_Live` attributes instead of legacy cycle sockets. |

## Frame map

The graph is now arranged into these readable frames:

| Frame | What belongs there |
|---|---|
| `Inputs / Live Data` | Group inputs that feed broad global controls. |
| `Draft Sampling` | `WebDraft_Live` object info, drawdown cell sampling, material ID sampling. |
| `Strand Generation / Drawdown` | Warp/weft strand curve generation and Z over/under bend. |
| `Surface` | Active surface controls such as Arc 2 boundary inset. |
| `Profile / Mesh` | Arc profile construction, curve-to-mesh conversion, strand attributes, and the Arc 1 sampling mesh used by same-strand U transfer. |
| `Texture Coordinates` | U-length math and strand-space texture coordinate setup. |
| `Texture U/V Output` | Final UV vector assembly and V scale/offset application. |
| `Arc 1 / Arc 2 V Band Mapping` | Per-material V-band switches, Arc 1 padding, Arc 2 piecewise/matched mapping. |
| `Same-Strand U Transfer` | Nearest-surface transfer that borrows Arc 1 U for Arc 2 on the same strand. |
| `Material Assignment` | Material socket inputs and `Set Material` chain. |
| `General / Imperfections` | Wobble/noise controls. |
| `Loose Strands` | Flyaway yarn generation. |
| `Assembly` | Final joins and realization. |
| `Output` | Final `Group Output`. |

## Helper node groups

These helper groups hide repeated switch/math internals while keeping the main
flow readable.

| Helper group | Main graph node(s) | What it does |
|---|---|---|
| `PW Helper - Select Material Float 16` | Six `PW Select Active Material - ...` nodes in `Arc 1 / Arc 2 V Band Mapping` | Replaces the old six 16-way switch chains for per-material image width, U scale, Arc 1 V Min/Max, and Arc 2 V Min/Max. |
| `PW Helper - Apply Material Slots 16` | `PW Apply Active Material Slots` in `Material Assignment` | Defaults geometry to Material 1, then applies Material 2..16 where `material_id` matches. |
| `PW Helper - Arc 1 Padding Clamp` | `PW Clamp Arc 1 V Band Inside Arc 2` | Computes padded Arc 1 V Min/Max and clamps them inside Arc 2's outer silhouette. |
| `PW Helper - Arc 2 Match Arc 1 Range` | `PW Match Arc 2 V To Arc 1 Range` | Optional Surface-panel branch that replaces piecewise Arc 2 V with the padded Arc 1 V range when `Arc 2 Match Arc 1 V Rate` is enabled. |

## Arc 1 same-strand sampling path

The same-strand U transfer depends on a real Arc 1/main-strand mesh being
available as the sampling surface. That path is intentionally explicit in the
main graph instead of hidden inside a helper group:

```text
PW Arc1 Sample Profile
  -> PW Arc1 Sample Store v_around
  -> PW Arc1 Sample Curve To Mesh
  -> PW Arc1 Sample Tag Main
```

`PW Arc1 Sample Tag Main` stores `is_sub_strand = 0`, then feeds two places:

```text
Join Geometry.001.Geometry
PW StrandXferU - Sample Same-Strand Arc1 U.Mesh
```

This keeps the main Arc 1 mesh present in the final strand assembly and gives
`PW StrandXferU - Sample Same-Strand Arc1 U` a same-strand surface to sample
from using `pw_strand_id` as both the source and target group id.

## Active data contracts

Per material, the backend pushes six V/U sockets:

```text
Material N Image Width Px
Material N Texture Scale U
Material N Arc 1 V Min
Material N Arc 1 V Max
Material N Arc 2 V Min
Material N Arc 2 V Max
```

Global/pinned sockets still pushed by the backend:

```text
Scanner Pixels Per BU
Sub Strand Enable = True
Texture Scale V = 1.0
Texture Offset V = 0.0
Sub Texture Scale V = 1.0
Sub Texture Offset V = 0.0
```

The backend no longer pushes `Top Halo Frac`, `Bot Halo Frac`, or
`Texture Side Flatten` to the cleaned graph.

## Future group extraction notes

The highest-value pure switch/math clusters are now helper groups. Remaining
candidate regions carry more field-domain/context risk and should be extracted
one at a time with a render diff after each extraction:

| Candidate subgroup | Risk |
|---|---|
| Draft sampling | Safe once material ID and `cell_code` sample domains are verified. |
| Remaining Arc 1 / Arc 2 V resolver | High value, high risk; it owns the approved visual baseline. |
| Same-strand U transfer | Compact and isolated, but depends on strand IDs and sample groups. |
| Profile builder | Geometry-domain sensitive; should be extracted only after visual signoff. |
