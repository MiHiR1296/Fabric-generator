# Blender Rebuild Notes

Fresh start date: 2026-05-29.

This folder is the new source of truth for rebuilding the `Parametric Weave
knotty` geometry-node setup one piece at a time. It starts with a read-only
audit of the currently open Blender file. No node edits were made during this
pass.

## Scope

Goal: understand the current graph and preserve the socket/data contract before
building a cleaner replacement.

Non-goal for this first pass: fixing the graph in place. The current file is too
visually tangled to use as the rebuild surface.

## Sources inspected

- Live Blender file over the socket server on `127.0.0.1:9876`.
- `Codex_ParametricWeave.blend`, currently open in Blender.
- `docs/BlenderFixes/geometry_nodes_guide.md`.
- `docs/BlenderFixes/architecture.md`.
- `docs/BlenderFixes/phase_log.md`.
- `docs/putting-it-together/data_contract.md`.
- `backend/app/blender_sync.py`.
- `backend/app/blender_live.py`.

Note: the local MCP wrapper and the app should both target the live Blender
socket on `127.0.0.1:9876`. For this audit, the repo's own
`backend/app/blender_sync.py::send_blender_command` client was used.

## Live scene snapshot

Open file:

```text
/Users/mihirbotle/Desktop/Impetus/3D Fabric/yarnseamless UI/Fabric-generator-tryon/Codex_ParametricWeave.blend
```

Important objects:

| Object | Type | Role |
|---|---|---|
| `ParametricWeave` | Mesh | Target object. Its base mesh is not the main source; the modifiers generate the fabric. |
| `WebDraft_Live` | Mesh | Hidden draft source. One face per drawdown cell. |
| `Space` | Mesh | Fit target for the second modifier. |
| `Camera`, `SeamlessTileCamera`, `Area`, `Sun`, `Empty` | Scene support | Lighting/camera/viewport helpers. |

Modifier stack on `ParametricWeave`:

| Modifier | Type | Node group |
|---|---|---|
| `Weave` | Nodes | `Parametric Weave knotty` |
| `Fit To Space` | Nodes | `Fit Geometry To Space Plane` |

Current active node group:

| Item | Count |
|---|---:|
| Nodes | 360 |
| Links | 645 |
| Frames | 17 |
| Group Input nodes | 11 |
| Unreachable functional nodes found by output-backtrace | 0 |

Current evaluated mesh readback:

| Mesh | Vertices | Faces | Notes |
|---|---:|---:|---|
| `WebDraft_Live` | 81 | 64 | Current live draft is 8 x 8. |
| `ParametricWeave` evaluated | 4,300,800 | 4,089,600 | Includes active generated weave geometry. |

## Node groups in the file

Relevant active groups:

| Node group | Nodes | Links | Role |
|---|---:|---:|---|
| `Parametric Weave knotty` | 360 | 645 | Active weave generator. |
| `Fit Geometry To Space Plane` | 28 | 45 | Scales final weave to the `Space` plane. |
| `PW Strand Variation` | 39 | 61 | Helper used twice for warp/weft random offsets. |
| `PW Helper - Select Material Float 16` | 32 | 61 | 16-way float selector for per-material V/U metadata. |
| `PW Helper - Apply Material Slots 16` | 33 | 63 | Applies Material 1..16 by `material_id`. |
| `PW Helper - Arc 1 Padding Clamp` | 6 | 10 | Computes padded Arc 1 V min/max clamped inside Arc 2. |
| `PW Helper - Arc 2 Match Arc 1 Range` | 9 | 14 | Optional Arc 2 V range switch. |

Historical groups still exist but are not the active modifier target:

- `Weave From Draft`
- `Array`
- `Knit From Stitch Map`
- `Hook Half Tube Surface`
- `Procedural Hook`
- `Randomize Transforms`

## Current modifier sockets

Root sockets:

| Socket | Identifier | Current value | Notes |
|---|---|---:|---|
| `Geometry` | `Socket_0` | n/a | Must remain first input for Blender modifier validity. |
| `Scanner Pixels Per BU` | `Socket_98` | `62992.160156` | Pushed from first yarn asset. |
| `Texture Scale U` | `Socket_97` | `1.0` | Root U scale; backend keeps this neutral. |
| `Draft Object` | `Socket_100` | `WebDraft_Live` | Source object for draft sampling. |
| `Draft Columns` | `Socket_101` | `8` | Current live draft width. |
| `Draft Rows` | `Socket_102` | `8` | Current live draft height. |
| `Arc 1 V Padding` | `Socket_244` | `0.008` | Expands the core V range before Arc 1/2 mapping. |
| `Arc 2 Endpoint Pinch` | `Socket_252` | `0.0` | Current live experimental control, not backend-driven. |
| `Arc 2 Apex Pinch` | `Socket_253` | `0.0` | Current live experimental control, not backend-driven. |
| `Arc 2 Apex Min Radius` | `Socket_254` | `0.0` | Current live experimental control, not backend-driven. |
| `Arc 2 Bend Smoothing` | `Socket_255` | `0.0` | Current live experimental control, not backend-driven. |

Panel sockets:

| Panel | Sockets and current values |
|---|---|
| `Pattern` | `Warp Threads=80`, `Weft Threads=80`, `Spacing=0.026`, `Amplitude=0.008` |
| `Surface` | `Thread Subdivisions=8`, `Arc 2 Boundary Inset=0`, `Arc 2 Match Arc 1 V Rate=False` |
| `Texture` | `Texture Scale V=1`, `Texture Offset V=0` |
| `General` | `Seed=1` |
| `Imperfections` | `Wobble Amount=0`, `Wobble Scale=13.52`, `Pattern Noise X=0`, `Pattern Noise Y=0`, `UV Random U=1`, `UV Random V=0`, `U Stride Per Warp End=0.20968`, `U Stride Per Weft Pick=0.20968` |
| `Loose Strands` | `Density=0`, `Length=0.02`, `Thickness=0.0001`, `Frizz=0.005` |
| `Material Slots` | `Material 1=FabricStudioMaterial_01_059e1c0937b5`; Material 2..16 empty in the live file |
| `Sub Strand` | `Sub Strand Enable=True`, `Sub Texture Scale V=1`, `Sub Texture Offset V=0` |
| `V-Band Mapping` | 16 material slots x 6 float sockets each: `Image Width Px`, `Texture Scale U`, `Arc 1 V Min/Max`, `Arc 2 V Min/Max` |

Example live V-band values:

| Socket family | Material 1 | Material 2 |
|---|---:|---:|
| `Image Width Px` | `47058` | `30876` |
| `Texture Scale U` | `0.075308` | `0.108308` |
| `Arc 1 V Min` | `0.471170` | `0.454701` |
| `Arc 1 V Max` | `0.530478` | `0.547009` |
| `Arc 2 V Min` | `0.446458` | `0.401709` |
| `Arc 2 V Max` | `0.555189` | `0.603419` |

## Backend socket contract to preserve

The backend currently pushes these families.

Per-material, for Material N where N is 1..16:

```text
Material N Image Width Px
Material N Texture Scale U
Material N Arc 1 V Min
Material N Arc 1 V Max
Material N Arc 2 V Min
Material N Arc 2 V Max
```

Global and pinned sockets:

```text
Scanner Pixels Per BU
Sub Strand Enable = True
Texture Scale V = 1.0
Texture Offset V = 0.0
Sub Texture Scale V = 1.0
Sub Texture Offset V = 0.0
```

Draft/render sockets:

```text
Draft Object
Draft Columns
Draft Rows
Warp Threads
Weft Threads
Spacing
Pattern Noise X
Pattern Noise Y
UV Random U
UV Random V = 0
Amplitude
Thread Subdivisions
Arc 1 V Padding
```

The new Arc 2 controls (`Endpoint Pinch`, `Apex Pinch`, `Apex Min Radius`,
`Bend Smoothing`) are present in the live file but are not currently part of
the backend push contract. Treat them as optional experiment controls until we
decide they belong in the rebuild.

## Major live frames

| Frame | Child nodes | Purpose |
|---|---:|---|
| `Inputs / Live Data` | 12 | Broad group inputs, sub-strand switch, Arc 1 sampling mesh path, final join nearby. |
| `Draft Sampling` | 23 | Reads `WebDraft_Live`, samples `cell_code`, `warp_material_id`, `weft_material_id`. |
| `Strand Generation / Drawdown` | 18 | Creates warp/weft curves and applies raw over/under Z offsets. |
| `Surface` | 4 | Curve type/subdivision setup. |
| `Bend Smoothing` | 22 | Optional smoothing of Z bend near over/under transition zones. |
| `General / Imperfections` | 4 | Warp/weft variation helper groups and final offset application. |
| `Texture Coordinates` | 46 | U length, U stride, V offset, and final UV scalar math. |
| `Strand ID + U Stride` | 7 | Stores `pw_strand_id`; applies per-strand post-bend U stride. |
| `Match Project V` | 5 | Top-view/cosine V projection retained from Phase 10s. |
| `HaloFlow V` | 5 | Free-flow Arc 2 halo V extrapolation from the core seam. |
| `V Band Mapping` | 46 | Per-material V/U selection, Arc 1 padding, Arc 2 section mapping, U section ratio. |
| `Same-Strand U Transfer` | 5 | Arc 2 samples Arc 1 U by `pw_strand_id`. |
| `Apex Pinch` | 9 | Optional radius scaling at Z apex. |
| `Endpoint Pinch` | 9 | Optional profile position pull near Arc 2 split endpoints. |
| `Loose Strands` | 51 | Optional flyaway curve generation. Currently density is 0. |
| `Debug Stores` | 8 | Stores evaluated split/radius/section debug attributes. |
| `Output` | 1 | Group output. |

Several important profile/mesh nodes are currently outside frames. This is one
reason the file is hard to reason about and should be rebuilt cleanly instead of
edited in place.

## Data flow

### 1. Web UI/backend builds the draft source

`backend/app/blender_sync.py` creates or updates `WebDraft_Live`.

Current live mesh:

```text
8 x 8 faces
cell_code: face int, 0 = weft over, 1 = warp over
warp_material_id: face int, zero-based material slot
weft_material_id: face int, zero-based material slot
```

The backend then assigns:

```text
Draft Object = WebDraft_Live
Draft Columns = draft width
Draft Rows = draft height
Warp Threads / Weft Threads = render zoom/thread count
Spacing / Pattern Noise / UV Random / Arc 1 V Padding = render settings
```

### 2. Draft sampling inside the graph

The graph samples `WebDraft_Live` with `GeometryNodeSampleIndex`.

Current live formulas:

```text
warp_col = Curve Index % Draft Columns
warp_row = Index in Curve % Draft Rows
warp_face_index = warp_row * Draft Columns + warp_col

weft_row = Curve Index % Draft Rows
weft_col = Index in Curve % Draft Columns
weft_face_index = weft_row * Draft Columns + weft_col
```

Then:

```text
warp_sign = cell_code * 2 - 1
weft_sign = cell_code * -2 + 1
z_offset = sign * Amplitude * 0.5
```

Material IDs use the same face index:

```text
warp material_id = sampled warp_material_id + 1
weft material_id = sampled weft_material_id + 1
```

Important discrepancy: the docs say Phase 10w changed the along-strand row/col
mapping to a floor-divide formula, but the live graph currently still has:

```text
PW Draft Warp Row Mod.operation = MODULO
PW Draft Weft Col Mod.operation = MODULO
```

Those nodes feed face index directly. That means the current live graph still
wraps the drawdown across each strand when `Warp/Weft Threads` is larger than
`Draft Rows/Columns`. This is the same family of issue previously linked to
wrong twill geometry. The rebuild should not copy this part as-is.

The intended rebuild formula should be:

```text
warp_row = floor(Index in Curve * Draft Rows / Weft Threads)
weft_col = floor(Index in Curve * Draft Columns / Warp Threads)
```

Phase 1 correction: that stretched-draft formula is useful for a diagnostic
plate, but not for the frontend pattern builder. The active Flat Arc1 group now
uses logical-thread repeat sampling instead:

```text
logical_thread = floor(Index in Curve / Thread Subdivisions)
warp_row       = logical_thread % Draft Rows
weft_col       = logical_thread % Draft Columns
```

Across-strand tiling can still use modulo:

```text
warp_col = Curve Index % Draft Columns
weft_row = Curve Index % Draft Rows
```

### 3. Strand generation

The graph creates straight warp/weft curve scaffolds from mesh lines and
instances:

```text
Warp thread count -> Mesh Line / instances
Weft thread count -> Mesh Line / instances
Spacing -> X/Y offsets
Draft sign -> Z offset
```

The raw over/under bend is applied before resampling/sweeping. After that the
curves pass through:

```text
Resample Curve
optional Bend Smoothing
Set Curve Normal (Z Up)
PW Strand Variation
Store u_along
Store uv_offset_u / uv_offset_v
Store pw_strand_id
```

The `Set Curve Normal` nodes are important: they keep warp and weft profile
orientation symmetric so `v_around` points to the same physical side for both
axes.

### 4. Profile and mesh construction

The graph builds an Arc 1 / Arc 2 cross-section profile. Current fixed geometry
provenance:

```text
Arc 1 radius = 0.015
Arc 2 radius = 0.025
core_frac = 0.015 / 0.025 = 0.6
Split Minus = 0.5 - 0.6 / 2 = 0.2
Split Plus  = 0.5 + 0.6 / 2 = 0.8
```

The output mesh stores:

```text
v_around
is_sub_strand
pw_profile_natural
pw_profile_actual
```

`Sub Strand Enable` gates whether Arc 2/sub-strand geometry exists. When it is
off, `is_sub_strand` is effectively 0 and the material falls back to Arc 1
mapping only. The backend pins it to `True` because the current approved yarn
look requires the Arc 2 halo.

The current live graph also contains:

- `Arc 2 Boundary Inset`
- `Arc 2 Endpoint Pinch`
- `Arc 2 Apex Pinch`
- `Arc 2 Apex Min Radius`
- `Arc 2 Bend Smoothing`

All of those live controls are currently zero. They should be treated as
optional profile-shaping modules, not as core rebuild requirements.

### 5. Texture U

U is based on visible strand length and the scanned yarn's physical texture
width.

Backend side:

```text
texture_world_width_BU = Material N Image Width Px / Scanner Pixels Per BU
Material N Texture Scale U = resolved visible V span in auto mode
U Stride Per Warp End = weft_threads * spacing / texture_world_width_BU * material_scale_u
U Stride Per Weft Pick = warp_threads * spacing / texture_world_width_BU * material_scale_u
```

Graph side:

```text
post_bend_length_ratio = Spline Length after bend / straight strand length
u_along = Spline Parameter Factor * post_bend_length_ratio
post_bend_stride = U Stride socket * post_bend_length_ratio
uv_offset_u = variation_offset + curve_index * post_bend_stride
base_u = u_along * U scale + uv_offset_u
```

The same post-bend ratio drives both `u_along` and stride, so strand N+1 starts
where strand N ended even if bending lengthens the visible curve.

### 6. Texture V

V starts from the stored `v_around`.

Arc 1:

```text
projected_v = top-view/cosine projection of v_around
padded_arc1_min = max(Material Arc 1 V Min - Arc 1 V Padding, Material Arc 2 V Min)
padded_arc1_max = min(Material Arc 1 V Max + Arc 1 V Padding, Material Arc 2 V Max)
Arc1 V = map(projected_v, 0..1 -> padded_arc1_min..padded_arc1_max)
```

Arc 2:

```text
0..Split Minus       -> Top halo
Split Minus..Plus    -> Core
Split Plus..1        -> Bottom halo
```

The current `HaloFlow V` path does not force the outer halo to the raw Arc 2
texture endpoints. It extrapolates from the raw Arc 1 core seam at the core V
rate, which was the Phase 10t "free-flow halo" behavior.

Final selector:

```text
Band V = is_sub_strand * (Arc2 V - Arc1 V) + Arc1 V
```

So:

- main/Arc 1 geometry reads the padded core band;
- sub/Arc 2 geometry reads halo + core + halo.

### 7. Same-strand U transfer

The graph keeps an explicit Arc 1 sample mesh:

```text
PW Arc1 Sample Profile
PW Arc1 Sample Store v_around
PW Arc1 Sample Curve To Mesh
PW Arc1 Sample Tag Main
```

That mesh is joined into the final output and also feeds:

```text
PW StrandXferU - Sample Same-Strand Arc1 U
```

Arc 2 then borrows U from Arc 1 using `pw_strand_id` as both source and target
group ID, while keeping its own V mapping. This is intended to keep halo/core U
registration aligned on the same physical strand.

### 8. Material assignment

`material_id` is stored on generated warp/weft geometry from the sampled
`warp_material_id` and `weft_material_id`.

The graph uses:

```text
PW Helper - Select Material Float 16
PW Helper - Apply Material Slots 16
```

Material selection is one-based inside the graph because Material 1 is the
default slot. The producer and `WebDraft_Live` face attributes are zero-based,
so the graph adds 1 after sampling.

### 9. Loose strands

Loose strands are optional flyaway curves. Current live `Loose Strand Density`
is `0`, so they are effectively off. The subsystem samples source material/U
attributes from the main weave so flyaways inherit the same material phase when
enabled.

### 10. Debug attributes

The evaluated mesh currently exposes these useful readback attributes:

```text
u_along
uv_offset_u
uv_offset_v
material_id
.pw_u_density_scale
pw_strand_id
pw_profile_natural
pw_profile_actual
v_around
is_sub_strand
arc1_radius_geometry
arc2_radius_geometry
arc2_core_frac_raw
arc2_core_frac_geometry
arc2_core_split_min
arc2_core_split_max
pw_section_ratio
pw_section_slope
uv_scaled
```

Keep these, or a smaller intentional subset, in the rebuild. They are extremely
useful for checking the graph from Python without relying on viewport guesses.

## Known live mismatches and risks

1. The live graph's along-strand drawdown sampling still uses modulo, despite
   docs saying the floor-divide fix was saved in Phase 10w.
2. `UV Random U` is currently `1.0` in the live file, while backend comments and
   tests describe default `0.0`. The backend preserves existing values unless a
   render setting overrides it, so a stale live value can survive.
3. New Arc 2 shaping sockets exist in the live file but are not documented in
   the older socket contract and are not backend-driven.
4. Several core profile and assembly nodes sit outside frames.
5. The graph has many frame-to-frame cross-links; even though there are no
   unreachable nodes, the visual flow is hard to audit safely.
6. `Weave From Draft` still exists but is not the active modifier group. Avoid
   accidentally rebuilding against the historical group unless we intentionally
   choose that path.

## Rebuild order

Build a new node group in small checkpoints. Do not start by copying all 360
nodes.

### Phase A - Socket shell

Create a new clean geometry-node group with the same required interface:

- root sockets used by backend;
- Pattern, Surface, Texture, General, Imperfections, Loose Strands, Material
  Slots, Sub Strand, V-Band Mapping panels;
- optional Arc 2 shaping controls only after we confirm they are desired.

Acceptance:

- backend can find every required socket by name;
- `Geometry` input is first;
- no render yet required.

### Phase B - WebDraft sampling

Read `WebDraft_Live` and output debug-only simple geometry that proves:

- `cell_code` is sampled correctly;
- warp/weft material IDs are sampled correctly;
- one-based `material_id` matches Material 1..16.

Use logical-thread repeat sampling, not raw point modulo. In practical terms:
divide `Index in Curve` by `Thread Subdivisions`, floor to a thread/pick index,
then modulo that logical index through `Draft Rows` / `Draft Columns`.

Acceptance:

- plain weave, 2/2 twill, basket, satin, herringbone all show expected sampled
  sign plateaus;
- no crescent/moon overlap from high-frequency row wrapping.

### Phase C - Strand curves

Generate warp/weft centerline curves with:

- correct counts;
- spacing;
- over/under Z offset;
- resampling;
- Z-up curve normals.

Acceptance:

- curves alone show correct drawdown structure;
- `u_along`, `pw_strand_id`, and `material_id` read back correctly.

### Phase D - U mapping

Add:

- image-width / scanner-pixels world-width math;
- root `Texture Scale U`;
- per-material `Texture Scale U`;
- post-bend length ratio;
- U stride per warp/weft.

Acceptance:

- strand N+1 starts at the expected U phase;
- `UV Random U=0` produces deterministic continuous spooling;
- `UV Random U>0` is visibly only a scatter knob.

### Phase E - Arc 1 profile only

Build a simple Arc 1 profile and convert curves to mesh.

Acceptance:

- no Arc 2/sub-strand yet;
- material samples only padded Arc 1 core;
- warp/weft V orientation is symmetric.

### Phase F - Arc 2 profile and V mapping

Add:

- Arc 2 profile;
- `is_sub_strand`;
- Split Minus/Plus from geometry radii;
- Arc 2 Top/Core/Bot V mapping;
- `Band V = is_sub_strand * (Arc2 V - Arc1 V) + Arc1 V`.

Acceptance:

- `Sub Strand Enable=False` falls back to Arc 1;
- `Sub Strand Enable=True` shows halo;
- debug split attrs read `0.2` / `0.8` for the current radius pair.

### Phase G - Same-strand U transfer

Add the Arc 1 sample mesh and nearest-surface grouped U transfer.

Acceptance:

- Arc 2 U matches Arc 1 U on the same `pw_strand_id`;
- cross-strand sampling does not occur.

### Phase H - Material slots

Apply Material 1..16 with the helper group or an equivalent clean module.

Acceptance:

- warp and weft can use different yarn assets;
- V-band values switch per face by `material_id`;
- empty slots fall back predictably.

### Phase I - Optional modules

Only after the core is visually accepted:

- loose strands;
- Arc 2 Boundary Inset;
- Endpoint Pinch;
- Apex Pinch;
- Bend Smoothing;
- debug stores;
- final `Fit To Space` review.

Acceptance:

- each module can be disabled to return to the accepted core look;
- each module has one clearly named frame or helper group.

## Rebuild invariants

- Preserve the backend socket names unless intentionally changing
  `blender_live.py` and tests in the same phase.
- Producer owns unit conversion. Blender consumes precomputed numbers.
- Root `Texture Scale U` stays neutral for scan-driven yarns.
- `Texture Scale V`, `Texture Offset V`, `Sub Texture Scale V`, and
  `Sub Texture Offset V` stay pinned at neutral values unless the contract
  changes.
- `Sub Strand Enable=True` is required for the current halo look.
- Keep `uv_scaled` and a few debug attributes until the rebuild is proven.
- Every phase should be checkpointed with a saved `.blend` backup and a short
  doc entry.

## Implemented Phase 1 - Flat Arc1 Resolution Diagnostic Rebuild

Status: implemented in a copied Blender file on 2026-05-29.
Historical checkpoint: this pass was superseded by the original-style
Arc1 + Arc2 profile rebuild on 2026-06-02. Keep this section because it
documents the resolution-diagnostic contract and the logical draft-sampling
fix that the active rebuild still uses.

Files:

- Blend copy: `Codex_ParametricWeave.flat-arc1-rebuild.blend`.
- Build script: `scripts/build_flat_arc1_rebuild.py`.
- Active target preserved: `ParametricWeave -> Weave -> Parametric Weave knotty`.

The production `Codex_ParametricWeave.blend` was not edited. The rebuild script
saves a separate copy, renames the previous node group to a timestamped
`Parametric Weave knotty.pre-flat-arc1-*`, then creates a new group with the
original public name so existing backend scripts keep finding the modifier.

Live readback after the build:

| Item | Value |
|---|---:|
| Node group | `Parametric Weave knotty` |
| Nodes | 250 |
| Links | 415 |
| Frames | 11 |
| Input sockets | 148 |

Frames are deliberately simple and inspectable:

```text
Inputs
Draft Sampling
Warp Curves
Weft Curves
Arc1 Profile
Texture U
Texture V
Material Selection
Resolution Diagnostics
Debug Attributes
Output
```

### Frontend/backend inputs preserved

The rebuild keeps the current web/backend data contract.

`DraftDocument` source fields:

- `drawdown`
- `threading`
- `treadling`
- `warpColors`
- `weftColors`
- `title`
- `sourceLabel`
- `renderSettings`

Backend uses `drawdown` directly for `WebDraft_Live`; `threading` and
`treadling` remain the frontend provenance used to compute that drawdown.

Active render settings consumed in this first rebuild:

| Setting | Destination |
|---|---|
| `warpThreads` | `Warp Threads` |
| `weftThreads` | `Weft Threads` |
| `spacing` | `Spacing`, mapped from UI 0..1 to physical BU |
| `amplitude` | over/under Z offset |
| `threadSubdivisions` | `Thread Subdivisions` and draft plateau denominator |
| `arc1VPadding` | padded Arc1 V min/max |
| `uvRandomU` | deterministic default is now `0`; still available as an explicit scatter knob |
| `fillRatio` | `Fit To Space` modifier, unchanged |

`Pattern Noise X/Y` sockets are preserved but not applied in Phase 1. That is
intentional: the first resolution diagnostic needs a stable straight-ribbon
baseline before we add procedural disturbance.

`colorBindings` still resolve to ordered Material 1..16 slots. The backend
continues to write zero-based `warp_material_id` and `weft_material_id` face
attributes onto `WebDraft_Live`; the graph adds `1` internally so
`material_id` maps to Material 1..16.

`YarnAsset` material payloads are still the source of:

- RGBA or split texture paths;
- RGBA UDIM / split UDIM tile patterns and counts;
- `renderTextureMode`;
- render tile dimensions;
- `bandMeta.blender.image_width_px`;
- `bandMeta.blender.scanner_pixels_per_bu`;
- `bandMeta.blender.texture_scale_u`;
- `bandMeta.blender.core_v_min/max`;
- `bandMeta.blender.fiber_bot_v_min`;
- `bandMeta.blender.fiber_top_v_max`.

Arc2 band values remain on the modifier interface for compatibility but are not
used visually in this Arc1-only pass.

### Phase 1 graph flow

1. `Draft Sampling`

   Reads `WebDraft_Live` through `Draft Object`, then samples `cell_code`,
   `warp_material_id`, and `weft_material_id` from face attributes.

   Along-strand sampling now uses the logical thread index. The frontend zoom
   sockets (`Warp Threads` / `Weft Threads`) are display strand counts; the
   drawdown is a repeat. Sampling raw curve points would make subdivisions look
   like extra picks, while stretching the draft over the full zoom count would
   turn an 8x8 plain weave into 10-thread blocks at the 80-thread preview. The
   rebuild therefore divides out `Thread Subdivisions`, floors to a logical
   thread/pick index, then tiles that index through the draft:

   ```text
   logical_pick = floor(Index in Curve / Thread Subdivisions)
   logical_end  = floor(Index in Curve / Thread Subdivisions)

   warp_row = logical_pick % Draft Rows
   weft_col = logical_end % Draft Columns
   ```

   Across-strand tiling remains modulo:

   ```text
   warp_col = Curve Index % Draft Columns
   weft_row = Curve Index % Draft Rows
   ```

2. `Warp Curves` / `Weft Curves`

   Builds straight centerline splines from mesh-line instances. `cell_code`
   drives the over/under sign:

   ```text
   warp_z = (cell_code * 2 - 1) * Amplitude * 0.5
   weft_z = (cell_code * -2 + 1) * Amplitude * 0.5
   ```

   The graph stores:

   ```text
   cell_code_sampled
   material_id
   u_along
   strand_length_bu
   uv_offset_u
   uv_offset_v
   ```

3. `Arc1 Profile`

   Joins warp and weft curves and sweeps a curved Arc1 crown profile. Ribbon
   width is:

   ```text
   Spacing * 0.9
   ```

   The Arc1 crown uses `Thread Subdivisions + 4` profile points. With the
   default `Thread Subdivisions=8`, that gives 12 points across the profile.
   The radius is `Spacing * 0.58`, with the endpoint sagitta subtracted so the
   profile reads as a rounded yarn crown rather than the old two-point flat
   diagnostic strip.

   The profile stores `v_around` as `0..1`. There is still no Arc2 shell,
   sub-strand geometry, bend smoothing, apex/endpoint pinch, or loose-strand
   subsystem in this pass.

4. `Texture U`

   U is tied to source scan dimensions:

   ```text
   texture_world_width_bu = Material N Image Width Px / Scanner Pixels Per BU
   repeats_per_strand     = strand_length_bu / texture_world_width_bu
   u_scale                = repeats_per_strand * Texture Scale U * Material N Texture Scale U
   uv_scaled.x            = u_along * u_scale + uv_offset_u
   ```

   `uv_offset_u` combines the per-strand U stride and optional `UV Random U`.
   For diagnostics, default `UV Random U` is `0`.

5. `Texture V`

   V maps only the padded Arc1 core band:

   ```text
   padded_min  = Material N Arc 1 V Min - Arc 1 V Padding
   padded_max  = Material N Arc 1 V Max + Arc 1 V Padding
   uv_scaled.y = (v_around * (padded_max - padded_min) + padded_min)
                 * Texture Scale V + Texture Offset V
   ```

6. `Material Selection`

   The group uses inline 16-way switch chains for per-material metadata, writes
   the zero-based material index for inspection, and then applies Material 1..16
   directly through explicit `Set Material` nodes:

   ```text
   Blender material_index = material_id - 1
   Material socket        = Material N where material_id == N
   ```

   Generated render materials in `backend/app/render_jobs.py` still read the
   `uv_scaled` geometry attribute. That path supports single RGBA, RGBA UDIM,
   split diffuse/alpha, and split UDIM assets.

7. `Resolution Diagnostics`

   The graph writes these inspection attributes:

   ```text
   source_image_width_px
   texture_world_width_bu
   screen_texel_ratio_estimate
   ```

   Current caveat: `screen_texel_ratio_estimate` is a source-density proxy
   (`source pixels per BU`). It does not yet calculate true rendered screen
   pixels per source texel from camera and render resolution. That final camera
   ratio should be measured in the render job or viewport diagnostic script.

### Live verification completed

Using the live Blender socket on `127.0.0.1:9876`:

- backend sync still finds `Parametric Weave knotty`;
- backend sync detects the `flat_arc1_sampling_contract` marker and skips the
  legacy draft relink pass;
- logical-thread nodes divide `Index in Curve` by `Thread Subdivisions`, then
  floor;
- `PW Draft Warp Row Mod`, `PW Draft Weft Col Mod`, `PW Draft Warp Col Mod`,
  and `PW Draft Weft Row Mod` are all `MODULO` over logical or strand indices;
- Material 1..16 sockets are consumed by explicit `Set Material` nodes;
- evaluated meshes expose the required debug attributes:

```text
cell_code_sampled
material_id
u_along
uv_scaled
source_image_width_px
texture_world_width_bu
screen_texel_ratio_estimate
```

Plain weave probe:

- 8x8 plain weave sent through the same live setup path used by the frontend;
- 80-thread preview reads the draft as a repeat, producing per-thread
  `0,1,0,1...` alternation instead of 10-thread blocks.

2/2 twill probe:

- 4x4 twill expanded to 8x8 threads;
- branch 0 matched the expected weft sampling;
- branch 1 matched the expected warp sampling;
- both branches avoid raw-subdivision wrapping.

Material probe:

- `warp_material_id` and `weft_material_id` were read from `WebDraft_Live`;
- output `material_id` is one-based;
- material slots map to zero-based Blender `material_index`.
- frontend-style setup loaded `FabricStudioMaterial_01_059e1c0937b5` as an
  RGBA UDIM material from `cycles_tiled/rgba_<UDIM>.png`;
- the generated material reads the `uv_scaled` attribute and uses `Linear`
  interpolation unless `WEAVE_TEXTURE_INTERPOLATION=Closest` is set for the
  render/setup script.

Diagnostic numbers from the current Material 1 metadata:

| Attribute | Value |
|---|---:|
| `source_image_width_px` | `47058` |
| `texture_world_width_bu` | `0.747045` |
| `screen_texel_ratio_estimate` | `62992.160156` |

### Resolution diagnostic checklist

Pixelation must be separated into measurable causes:

| Question | Where to inspect |
|---|---|
| How many source pixels exist? | `source_image_width_px`, source file dimensions |
| Did Blender load full-res, UDIM, or fallback/downscaled textures? | generated material nodes and render-job material summary |
| What physical texture width is being sampled? | `texture_world_width_bu` |
| Did UV compress or stretch the source unexpectedly? | `uv_scaled`, `u_along`, `strand_length_bu` |
| Is texture filtering hiding texels? | `WEAVE_TEXTURE_INTERPOLATION=Closest` vs `Linear` |
| Does the render have enough screen pixels? | render resolution, camera ortho scale, final screen-pixels/source-texel calculation |

Acceptance for this phase is not final fabric beauty. It is a clean Arc1-only
ribbon where source texel density, UV scale, interpolation mode, and camera
resolution can be checked independently.

### Phase 1 limitations

- Arc2 sockets are preserved but visually unused.
- The profile is Arc1 only. Arc2 halo/sub-strand geometry is intentionally not
  rebuilt yet.
- `Pattern Noise X/Y`, wobble, loose strands, endpoint pinch, apex pinch, and
  bend smoothing are preserved as interface concepts but inactive.
- `screen_texel_ratio_estimate` is not yet the final camera-space ratio.
- Texture-mode renders for single RGBA, RGBA UDIM, and split fallback still need
  a recorded visual comparison pass with `Closest` and `Linear`.

## Implemented Phase 3 - Original-Style Arc1 + Arc2 Profile

Status: implemented in `Codex_ParametricWeave.flat-arc1-rebuild.blend` on
2026-06-02.

This is now the active clean rebuild target. It keeps the Phase 1 fixes for
frontend draft sampling, material slots, UV diagnostics, and direct material
assignment, but restores the original visual profile structure:

```text
Arc1 core surface: 11 profile points per path sample
Arc2 halo surface: 31 profile points per path sample
Total:             42 profile points per path sample
```

### Original-file facts used

The original `Codex_ParametricWeave.blend` was opened through the live Blender
socket and inspected before the rebuild was changed.

Readback from the original graph:

| Item | Value |
|---|---:|
| Evaluated vertices | `4,300,800` |
| Evaluated faces | `4,089,600` |
| Path samples | `102,400` |
| Main/Arc1 profile points | `11` |
| Arc2/sub-strand profile points | `31` |
| First Arc2 vertex index | `1,126,400` |
| Arc1 radius | `0.015` |
| Arc2 radius | `0.025` |
| Core fraction | `0.6` |
| Split min / max | `0.2 / 0.8` |

The original V behavior was also copied:

```text
Arc1 V: cosine/projected v_around mapped into padded Arc1 core band
Arc2 V: free-flow halo extrapolated from raw Arc1 core rate
Final V: centered around 0.5, then Texture Scale V + Sub Texture Scale V
```

### Active graph changes

The visible profile frame is now `Arc1 + Arc2 Profile`.

The frame builds two separate inspectable surfaces:

- `PW Arc1 Sample Profile` uses a `Curve Arc` profile with resolution `11`,
  radius `0.015`, start angle `-0.52359879`, and sweep `-2.09090447`.
- `PW Arc2 Profile Arc` uses a larger `Curve Arc` with radius `0.025`; it is
  sampled by a 31-point profile line so `v_around` increments by `1/30`.
- Arc1 is tagged with `is_sub_strand=0`; Arc2 is tagged with
  `is_sub_strand=1`.
- `Sub Strand Enable` switches between Arc1-only output and joined Arc1 + Arc2
  output. The backend currently pins it to `True` for the original look.

The rebuild stores the original debug attributes again:

```text
v_around
is_sub_strand
pw_profile_natural
pw_profile_actual
arc1_radius_geometry
arc2_radius_geometry
arc2_core_frac_raw
arc2_core_frac_geometry
arc2_core_split_min
arc2_core_split_max
pw_section_ratio
pw_section_slope
```

### Active Texture V

Arc1 now matches the old projected V mapping:

```text
projected_v = (1 - cos(v_around * pi)) / 2
padded_min  = max(Material Arc 1 V Min - Arc 1 V Padding,
                  Material Arc 2 V Min)
padded_max  = min(Material Arc 1 V Max + Arc 1 V Padding,
                  Material Arc 2 V Max)
arc1_v      = projected_v * (padded_max - padded_min) + padded_min
```

Arc2 uses the free-flow halo rate:

```text
core_slope  = (Material Arc 1 V Max - Material Arc 1 V Min)
              / (arc2_core_split_max - arc2_core_split_min)
top_outer_v = Material Arc 1 V Min - core_slope * arc2_core_split_min
arc2_v      = top_outer_v + v_around * core_slope
band_v      = is_sub_strand * (arc2_v - arc1_v) + arc1_v
```

Final V applies the original centered scale/offset behavior:

```text
v_center = band_v - 0.5
v_scale  = Texture Scale V + is_sub_strand * Sub Texture Scale V
v_offset = Texture Offset V + is_sub_strand * Sub Texture Offset V
uv.y     = v_center * v_scale + (0.5 + v_offset)
```

With the current Material 1 values, readback matches the original V samples:

| Surface | `v_around` | `uv_scaled.y` |
|---|---:|---:|
| Arc1 | `0.0` | `0.463170` |
| Arc1 | `0.5` | `0.500824` |
| Arc1 | `1.0` | `0.538478` |
| Arc2 | `0.0` | `0.402801` |
| Arc2 | `0.5` | `0.501647` |
| Arc2 | `1.0` | `0.600494` |

### Live verification completed

Using the live Blender socket on `127.0.0.1:9876`:

| Item | Value |
|---|---:|
| Blend file | `Codex_ParametricWeave.flat-arc1-rebuild.blend` |
| Node group | `Parametric Weave knotty` |
| Nodes | `391` |
| Links | `674` |
| Frames | `11` |
| Evaluated vertices | `4,300,800` |
| Evaluated faces | `4,089,600` |
| First Arc2 vertex index | `1,126,400` |
| Main profile estimate | `11.0` |
| Sub profile estimate | `31.0` |

Plain-weave sampling now reads in clean logical plateaus:

```text
path points 0..7   -> cell 0
path points 8..15  -> cell 1
path points 16..23 -> cell 0
logical threads    -> 0,1,0,1...
```

Material readback:

- `Material 1` is `FabricStudioMaterial_01_08a7db9d6113`;
- it is an RGBA UDIM material from
  `runtime/yarn_assets/08a7db9d6113/cycles_tiled/rgba_<UDIM>.png`;
- the material reads the `uv_scaled` attribute;
- image interpolation is currently `Linear` unless the render/setup path sets
  `WEAVE_TEXTURE_INTERPOLATION=Closest`.

### Remaining visual work

This rebuild restores the original cross-section count and V behavior. It does
not yet rebuild the optional shaping modules:

- Arc2 boundary inset;
- endpoint pinch;
- apex pinch;
- apex min radius;
- bend smoothing;
- loose strands and wobble.

Those should be reintroduced one panel at a time only after we confirm the
frontend material payload renders correctly with this simpler original-style
surface.
