# Blender Rebuild Phase Log

This is the new chronological log for rebuilding the weave geometry-node graph
from a clean base. It starts after the older `docs/BlenderFixes` history became
too tangled to safely use as the active rebuild notebook.

## Phase 0 - Read-only live graph audit

Date: 2026-05-29

### Motivation

The current Blender geometry-node graph is visually difficult to maintain. The
goal for this phase was to understand and document the active setup before
making any new node changes.

### Actions

- Queried live Blender on `127.0.0.1:9876`.
- Confirmed the active file is `Codex_ParametricWeave.blend`.
- Confirmed `ParametricWeave.modifiers["Weave"]` uses `Parametric Weave knotty`.
- Counted 360 nodes, 645 links, 17 frames, and 0 unreachable functional nodes.
- Captured the active socket layout and current live values.
- Mapped the high-level data flow from `WebDraft_Live` through draft sampling,
  strand generation, profile/mesh, U/V mapping, same-strand U transfer, material
  assignment, loose strands, debug stores, and output.

### Findings

- The live graph does not match the older `geometry_nodes_guide.md` snapshot.
  It now has additional Arc 2 shaping frames/sockets and more nodes.
- The live graph still uses modulo for along-strand draft sampling:

```text
PW Draft Warp Row Mod.operation = MODULO
PW Draft Weft Col Mod.operation = MODULO
```

- That conflicts with the older Phase 10w note that says the floor-divide fix
  was saved. The rebuild should not copy raw point-modulo sampling.
- Later Phase 1 live testing refined this: the active frontend path needs
  logical-thread repeat sampling, not stretched floor-divide sampling.
- `UV Random U` is currently `1.0` in Blender, while backend defaults describe
  `0.0`. The backend can preserve the stale live value unless explicitly pushed.
- The current graph has no unreachable functional nodes, but many important
  links still cross frames or sit outside frames, making the graph hard to edit
  confidently.

### Output

Created [README.md](README.md), the current rebuild audit and proposed staged
rebuild plan.

### Graph changes

None.

## Phase 1 - Flat Arc1 resolution diagnostic rebuild

Date: 2026-05-29

### Motivation

The most important failure mode to isolate is texture resolution loss. Previous
iterations mixed draft sampling, Arc1/Arc2 profile shaping, same-strand U
transfer, halo mapping, loose strands, and material selection into one dense
visual graph. This phase intentionally removes Arc2 and starts with Arc1-only
ribbons so source pixels, UV scale, interpolation, and render resolution can be
debugged separately.

### Actions

- Added `scripts/build_flat_arc1_rebuild.py`.
- Saved a working copy as `Codex_ParametricWeave.flat-arc1-rebuild.blend`.
- Preserved the live target path:

```text
ParametricWeave -> Weave -> Parametric Weave knotty
```

- Renamed the previous active group to a timestamped
  `Parametric Weave knotty.pre-flat-arc1-*` rollback group inside the copy.
- Built a new `Parametric Weave knotty` node group with 11 named frames:

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

- Kept the existing socket contract, including Material 1..16 and Arc2 V-band
  sockets, so backend scripts continue to work.
- Implemented first-pass floor-divide along-strand draft sampling:

```text
warp_row = floor(Index in Curve * Draft Rows / (Weft Threads * Thread Subdivisions))
weft_col = floor(Index in Curve * Draft Columns / (Warp Threads * Thread Subdivisions))
```

- Kept across-strand tiling as modulo:

```text
warp_col = Curve Index % Draft Columns
weft_row = Curve Index % Draft Rows
```

- Generated warp/weft centerline curves, over/under Z offsets, first-pass flat
  profiles, `uv_scaled`, material index writes, and diagnostic attributes.
- Patched backend sync to honor `renderSettings.threadSubdivisions`.
- Changed the frontend default `uvRandomU` to `0` so diagnostics do not inherit
  random U scatter by default.

### Correction after frontend live test

The first pass technically followed the planned floor-divide diagnostic, but a
plain-weave draft sent from the frontend exposed the wrong product behavior:
an 8x8 plain repeat at the default 80-thread preview became 10-thread blocks.
For the frontend, `Warp Threads` / `Weft Threads` are preview strand counts and
the drawdown is a repeat, not something to stretch once across the swatch.

The rebuild was corrected to sample by logical thread:

```text
logical_thread = floor(Index in Curve / Thread Subdivisions)
warp_row       = logical_thread % Draft Rows
weft_col       = logical_thread % Draft Columns
```

The node group is marked with:

```text
flat_arc1_sampling_contract = logical_thread_tiling_v1
```

Backend sync checks that marker and skips the legacy draft relink pass so it
does not overwrite the logical-thread wiring. The material path was also
upgraded from material-index-only to an explicit Material 1..16 `Set Material`
chain, so live Blender preview uses the texture material directly.

### Live readback

Blender socket used: `127.0.0.1:9876`.

Node group summary:

| Item | Count |
|---|---:|
| Nodes | 281 |
| Links | 477 |
| Frames | 11 |
| Input sockets | 148 |

Draft node operations after correction:

| Node | Operation |
|---|---|
| `PW FlatArc1 Warp Logical Thread Divide` | `DIVIDE` |
| `PW FlatArc1 Warp Logical Thread Floor` | `FLOOR` |
| `PW Draft Warp Row Mod` | `MODULO` |
| `PW Draft Warp Col Mod` | `MODULO` |
| `PW FlatArc1 Weft Logical Thread Divide` | `DIVIDE` |
| `PW FlatArc1 Weft Logical Thread Floor` | `FLOOR` |
| `PW Draft Weft Col Mod` | `MODULO` |
| `PW Draft Weft Row Mod` | `MODULO` |

Evaluated mesh attributes present:

```text
cell_code_sampled
material_id
u_along
uv_scaled
source_image_width_px
texture_world_width_bu
screen_texel_ratio_estimate
```

Small live probes:

- 8x8 plain weave sent through the frontend-style live setup path and previewed
  at 80 threads produced per-thread `0,1,0,1...` alternation on both branches.
- 4x4 2/2 twill expanded to 8x8 threads avoids raw-subdivision wrapping.
- A material probe confirmed one-based `material_id` readback from
  `warp_material_id` / `weft_material_id` and zero-based Blender material-index
  assignment.
- A frontend-style live setup probe loaded
  `FabricStudioMaterial_01_059e1c0937b5` as an RGBA UDIM material from
  `runtime/yarn_assets/059e1c0937b5/cycles_tiled/rgba_<UDIM>.png`, assigned it
  to object material slot 1, and set the modifier `Material 1` socket to the
  same texture material.

Current Material 1 diagnostic values:

| Attribute | Value |
|---|---:|
| `source_image_width_px` | `47058` |
| `texture_world_width_bu` | `0.747045` |
| `screen_texel_ratio_estimate` | `62992.160156` |

### Findings

- The backend sync verification pass must skip the marked Flat Arc1 group;
  otherwise it can relink draft nodes back to assumptions from the older graph.
- The frontend default zoom values require repeat-style sampling by logical
  thread. Floor-dividing across the full zoom count is useful for a stretched
  diagnostic plate, but it is not the pattern-builder behavior users expect.
- The frontend default `uvRandomU=1` would have made the first comparison
  nondeterministic. It is now `0` by default, matching backend comments/tests.
- `screen_texel_ratio_estimate` is currently a source-density proxy, not the
  final camera-space screen-pixel ratio. The render job still needs to record
  actual camera/render density.

### Still open

- Render visual comparisons with `WEAVE_TEXTURE_INTERPOLATION=Closest` and
  `Linear`.
- Record one single-RGBA, one RGBA-UDIM, and one split diffuse/alpha fallback
  material test.
- Add a true camera-space screen-pixels-per-source-texel metric.
- Reintroduce Pattern Noise, Arc2, loose strands, and shaping modules only after
  the Arc1 texture path is trusted.

## Phase 2 - Restore curved Arc1 profile

Date: 2026-06-01

### Motivation

The flat diagnostic strip fixed some plumbing but made the frontend visual read
harder than the old arcs. The user asked to go back to Arc1 because the arcs
were smoother and easier to understand in the weave flow.

### Actions

- Kept the fixed logical-thread draft sampling and Material 1..16 assignment
  chain from Phase 1.
- Replaced the two-point flat profile with a multi-point Arc1 crown profile.
- Renamed the visible frame label from `Flat Arc1 Profile` to `Arc1 Profile`.
- Arc1 profile point count is:

```text
Thread Subdivisions + 4
```

- At the default `Thread Subdivisions=8`, the profile has 12 points.
- Arc1 radius is:

```text
Spacing * 0.58
```

- Ribbon half-width remains:

```text
Spacing * 0.45
```

- The endpoint sagitta is subtracted from the circular arc so the profile is a
  crown shape rather than a full half-circle lifted away from the strand path.

### Live readback

Blender socket used: `127.0.0.1:9876`.

Current node group summary:

| Item | Count |
|---|---:|
| Nodes | 297 |
| Links | 501 |
| Frames | 11 |

Evaluated mesh at default 80 x 80 threads and `Thread Subdivisions=8`:

| Mesh | Count |
|---|---:|
| Vertices | 1,228,800 |
| Faces | 1,124,640 |

Debug attributes still present:

```text
cell_code_sampled
material_id
u_along
v_around
uv_scaled
source_image_width_px
texture_world_width_bu
screen_texel_ratio_estimate
```

### Notes

- The current profile is Arc1-only. Arc2 halo/sub-strand geometry is still not
  present, by design.
- This is heavier than the flat strip because the default profile now has 12
  points instead of 2. That is acceptable for the current rebuild checkpoint,
  but we can add a profile-resolution socket later if viewport speed becomes a
  problem.

## Phase 3 - Restore original Arc1 + Arc2 profile structure

Date: 2026-06-02

### Motivation

The Arc1-only rebuild fixed draft sampling and material plumbing, but the
visual still did not feel like the original Blender file. The user asked to
inspect the original file and replicate how it looked. The original graph was
therefore opened through the live Blender socket and measured directly before
changing the rebuild.

### Original readback

Blender socket used: `127.0.0.1:9876`.

Original file inspected:

```text
Codex_ParametricWeave.blend
```

Measured original mesh:

| Item | Count |
|---|---:|
| Vertices | 4,300,800 |
| Faces | 4,089,600 |
| Path samples | 102,400 |
| Arc1/main profile points | 11 |
| Arc2/sub-strand profile points | 31 |
| First Arc2 vertex index | 1,126,400 |

Measured original constants:

```text
Arc1 radius = 0.015
Arc2 radius = 0.025
core_frac = 0.6
Split Minus = 0.2
Split Plus = 0.8
```

The original first Arc1 V samples were cosine-projected:

```text
v_around:    0.0      0.5      1.0
uv_scaled.y: 0.463170 0.500824 0.538478
```

The original Arc2 halo used free-flow V:

```text
v_around:    0.0      0.5      1.0
uv_scaled.y: 0.402801 0.501647 0.600494
```

### Actions

- Kept the Phase 1 logical draft-sampling fix.
- Kept direct Material 1..16 assignment and `uv_scaled` material path.
- Replaced the Phase 2 Arc1-only crown with two explicit surfaces:
  - Arc1 core surface from `PW Arc1 Sample Profile`;
  - Arc2 halo surface from `PW Arc2 Profile Arc` sampled by 31 profile points.
- Changed the visible frame label to `Arc1 + Arc2 Profile`.
- Restored the `Sub Strand Enable` switch. When enabled, the output is joined
  Arc1 + Arc2; when disabled, it falls back to Arc1-only.
- Restored debug attributes:

```text
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

- Rebuilt Texture V to match the original graph:
  - Arc1 uses `(1 - cos(v_around * pi)) / 2`;
  - padded Arc1 V clamps inside Arc2 min/max;
  - Arc2 uses free-flow halo extrapolation from the raw Arc1 core slope;
  - final V is centered around `0.5`, then scaled by
    `Texture Scale V + is_sub_strand * Sub Texture Scale V`.

### Live readback after rebuild

Active copied file:

```text
Codex_ParametricWeave.flat-arc1-rebuild.blend
```

Node group summary:

| Item | Count |
|---|---:|
| Nodes | 391 |
| Links | 674 |
| Frames | 11 |

Evaluated mesh:

| Item | Count |
|---|---:|
| Vertices | 4,300,800 |
| Faces | 4,089,600 |
| Main vertices | 1,126,400 |
| Sub vertices | 3,174,400 |
| First Arc2 vertex index | 1,126,400 |
| Main profile estimate | 11.0 |
| Sub profile estimate | 31.0 |

The rebuilt V readback matches the original Material 1 samples:

| Surface | `v_around` | `uv_scaled.y` |
|---|---:|---:|
| Arc1 | 0.0 | 0.463170 |
| Arc1 | 0.5 | 0.500824 |
| Arc1 | 1.0 | 0.538478 |
| Arc2 | 0.0 | 0.402801 |
| Arc2 | 0.5 | 0.501647 |
| Arc2 | 1.0 | 0.600494 |

Plain-weave sampling check:

```text
path points 0..7   -> cell 0
path points 8..15  -> cell 1
path points 16..23 -> cell 0
logical threads    -> 0,1,0,1...
```

Material check:

- `Material 1` is assigned to `FabricStudioMaterial_01_08a7db9d6113`.
- The material uses RGBA UDIM image
  `runtime/yarn_assets/08a7db9d6113/cycles_tiled/rgba_<UDIM>.png`.
- The material reads `uv_scaled`.
- The image texture node currently reports `Linear` interpolation.

### Notes

- U starts at `0` in this rebuild because diagnostic `UV Random U` is pinned to
  `0`; the old original file had an inherited offset, which is not needed for
  texture-resolution diagnosis.
- The optional original shaping modules are still intentionally left out:
  boundary inset, endpoint pinch, apex pinch, apex min radius, bend smoothing,
  wobble, and loose strands.
