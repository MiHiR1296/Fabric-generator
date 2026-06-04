# Diagnostic Validation

Date: 2026-06-03, updated 2026-06-04

## Scope

This pass checks whether the proposed texture-resolution fixes match the
actual running frontend, backend, runtime assets, and live Blender graph.

The diagnostic target was the active live scene through Blender MCP
`127.0.0.1:9876`, with the backend on `127.0.0.1:8000` and frontend on
`127.0.0.1:5180`.

## Short Verdict

2026-06-04 correction:

```text
Do not treat the earlier V-scale rewrite as final truth.
The live Blender graph and rebuild script have been restored to:
v_scale = Texture Scale V + is_sub_strand * Sub Texture Scale V
with Sub Texture Scale V = 1.0.
```

The current confirmed causes are:

```text
1. Material alpha handling is the dominant visible haze contributor.
   The source RGBA and UDIM tiles are full resolution, but raw alpha was fed
   directly into the shader. backend/app/render_jobs.py now inserts a
   configurable FabricStudioAlphaRemap Map Range node by default, with an
   optional FabricStudioAlphaCurve POWER node when gamma is not 1.0.

2. Arc 2 Same-Strand U Transfer is a mapping suspect.
   Bypassing the nearest-surface transfer removes measured zero/reversed U
   steps on Arc 2, but visual review rejected the bypass because Arc 2 must
   continue Arc 1's yarn texture. Live Blender now uses deterministic
   same-strand U: Arc 2 receives the same base yarn U stream without the
   nearest-surface lookup.
```

The image pipeline is preserving the original pixels. The active blur is not
caused by the frontend resizing the image, the backend writing smaller UDIM
tiles, or Blender loading a downscaled texture.

The old `Texture Scale U = 0.8` finding is real, but it is not large enough to
explain the plane-sharp / strand-blurry symptom. It is a sync hygiene bug.

2026-06-04 superseded note: the geometry-density lead was tested and did not
resolve the haze. A later V-scale rewrite around `Sub Texture Scale V` was
also tested and rejected by visual review because it degraded Arc 2. Keep this
paragraph as diagnostic history only.

Rejected V-scale rewrite:

```text
Texture Scale V     = 1.0
Sub Texture Scale V = 1.0
Sub Texture Offset V = 0.0

old formula: v_scale = Texture + is_sub * Sub
tested rejected formula: v_scale = Texture + is_sub * (Sub - Texture)
```

Remaining confirmed contributor:

```text
Alpha softness/translucency suppresses fine fiber/twist detail. A non-binary
alpha remap is needed, but the default must stay mild; hard thresholding is
sharp but visually harsh, and strong mid-alpha boosting makes Arc 2 noisy.
```

Geometry and UV sampling density remain useful quality levers on the
parametric weave surface:

```text
U density lever: Thread Subdivisions
V density lever: PW Profile - Mesh Line Count + Offset together
```

The earlier proposed `Ply Resolution = 5 -> 24` fix does not apply to the
current `Parametric Weave knotty` graph because that socket is not exposed on
the live graph.

## Confirmed Asset Integrity

Runtime yarn asset audit:

```text
assets scanned: 23
problems found: 0
rgba_tiled assets: 22
rgba_single assets: 1
```

For every tiled asset:

```text
source rgba.png dimensions == metadata image_size_px
source rgba.png dimensions == bandMeta.blender.image_width_px / height
tile widths sum to source width
tile heights match source height
stitched UDIM tiles pixel-compare equal to source, maxdiff = 0
```

Active examples checked:

```text
059e1c0937b5 / Greyrescan07
source: 47058 x 607
tiles: 3
stitched diff vs source: 0

08a7db9d6113 / greyrescan0008
source: 47058 x 607
tiles: 3
stitched diff vs source: 0
```

Conclusion:

```text
No evidence of source-image or UDIM downscaling.
```

## Live Material Validation

The active Blender material uses RGBA UDIM images:

```text
FabricStudioDiffuseNode -> RGBA UDIM
FabricStudioAlphaNode   -> same RGBA UDIM
source                  -> TILED
path                    -> runtime/yarn_assets/<asset>/cycles_tiled/rgba_<UDIM>.png
interpolation           -> Linear
extension               -> CLIP
```

Conclusion:

```text
The live material is not using the atlas fallback and not using a
Cycles-safe downscale.
```

## Sync Path Validation

### Full Project Push

The full setup/live path was tested with:

```text
POST /api/blender/push-project-bandmeta
```

using the latest render-job project JSON:

```text
runtime/render_jobs/60f5b85d4bb8/project.json
```

Immediate Blender readback after that push:

```text
Texture Scale U              = 1.0
Texture Scale V              = 1.0
Texture Offset V             = 0.0
Sub Texture Scale V          = 1.0
Sub Texture Offset V         = 0.0
Arc 1 V Padding              = 0.00800000037997961
Thread Subdivisions          = 8.0
Material 1 Image Width Px    = 47058.0
Material 1 Texture Scale U   = 0.07530806958675385
U Stride Per Warp/Weft       = 0.209680438041687
```

Conclusion:

```text
The full setup path already resets root Texture Scale U to 1.0 for the
current Parametric Weave knotty graph. This historical readback also shows
the old Sub Texture Scale V = 1.0 value that Phase 0.9 later proved was not
neutral.
```

### Metadata-Only Push

The metadata-only path was tested by temporarily setting live root
`Texture Scale U` to `0.8` and calling:

```text
POST /api/blender/push-bandmeta
```

Immediate Blender readback:

```text
Texture Scale U stayed at 0.800000011920929
V hygiene pins stayed correct
```

Then the live value was restored to `1.0`.

Conclusion:

```text
Adding ("Texture Scale U", 1.0) to PINNED_FOOTGUN_SOCKETS is correct for
the metadata-only push path, but it is not the primary texture-blur fix.
```

### 2026-06-04 V Mapping Correction

The V sweep was run after the geometry-density renders remained blurry. Output:

```text
runtime/texture_resolution_v_mapping_tests/20260604_020718/
```

The sweep first compared the old sub-strand additive V scale against an
equivalent effective scale. Later live review showed that setting
`Sub Texture Scale V` to `0.0` makes Arc 2 controls misleading/wrong. The
correct final fix keeps `Sub Texture Scale V = 1.0` and changes the graph
formula.

```text
old graph:
  Texture Scale V = 1.0, Sub Texture Scale V = 1.0
  v_scale = Texture + is_sub * Sub

correct graph:
  Texture Scale V = 1.0, Sub Texture Scale V = 1.0
  v_scale = Texture + is_sub * (Sub - Texture)
```

Measured `uv_scaled.y` ranges:

```text
old sub-strand range: 0.40280..0.60049  span 0.19769
new sub-strand range: 0.45140..0.55025  span 0.09885
```

Same-crop edge metrics:

```text
00_current_original_subdelta1: edge_mean 3.44
01_original_subdelta0:         edge_mean 4.39
04_alpha_boost_subdelta0:      edge_mean 5.10
05_alpha_threshold_subdelta0:  edge_mean 6.35
```

Conclusion:

```text
Sub Texture Scale V should stay 1.0. The graph must treat it as an absolute
sub-strand scale instead of an additive delta. The mapping fix improves
clarity, and alpha remapping is the next needed visual fix.
```

Live MCP readback after rewiring the graph:

```text
Texture Scale V     = 1.0
Sub Texture Scale V = 1.0

main uv_scaled.y = 0.45917..0.54248  span 0.08331
sub  uv_scaled.y = 0.45140..0.55025  span 0.09885
```

## Saved Blend Drift

Background readback of the saved blend showed:

```text
Codex_ParametricWeave.blend
Texture Scale U / Socket_97 = 0.800000011920929
```

The checkpoint says:

```text
docs/CHECKPOINT_2026-05-19.md
Texture Scale U / Socket_97 = 1
```

Conclusion:

```text
The saved blend should be reset and saved at Texture Scale U = 1.0, even
though the full setup path already repairs the live value.
```

## Current Geometry Facts

The live graph is:

```text
ParametricWeave
modifier: Weave
node group: Parametric Weave knotty
```

The current graph exposes `Thread Subdivisions`, but it does not expose
`Ply Resolution`.

Baseline evaluated mesh:

```text
Thread Subdivisions = 8
PW Profile - Mesh Line Count = 31
PW Profile - Mesh Line Offset = 1 / 30

vertices = 4,300,800
faces    = 4,089,600
v_around unique values = 31
pw_profile_natural unique values = 31
pw_profile_actual unique values = 31
```

### V-Density Test

Naive test:

```text
PW Profile - Mesh Line Count: 31 -> 61
Offset left at 1 / 30
```

Result:

```text
vertices jumped, but profile domain became 0..2
v_around stayed at 31 useful values
```

Conclusion:

```text
Count-only is wrong.
```

Correct domain-preserving test:

```text
PW Profile - Mesh Line Count: 31 -> 61
PW Profile - Mesh Line Offset: 1/30 -> 1/60
```

Result:

```text
vertices = 7,372,800
faces    = 7,156,800
v_around unique values = 61
pw_profile_natural unique values = 61
pw_profile_actual unique values = 61
```

The values were restored to Count `31` and Offset `1/30` after the test.

Conclusion:

```text
The V-density fix is valid, but only if Count and Offset are driven together.
```

### U-Density Test

`Thread Subdivisions` was tested with an explicit dependency graph refresh:

```text
Thread Subdivisions = 4   -> 2,150,400 vertices / 2,041,600 faces
Thread Subdivisions = 8   -> 4,300,800 vertices / 4,089,600 faces
Thread Subdivisions = 16  -> 8,601,600 vertices / 8,185,600 faces
Thread Subdivisions = 32  -> 17,203,200 vertices / 16,377,600 faces
```

The value was restored to `8`.

Conclusion:

```text
Thread Subdivisions is a real U-density lever. It scales mesh cost linearly.
```

## Proposed Fix Validation Matrix

| Proposed solution | Status | Reason |
| --- | --- | --- |
| Rebuild / audit UDIM tiles | Already validated | UDIM tiles stitch back to the source with maxdiff `0`; no active downscale found. |
| Fix frontend image resizing | Not active cause | Frontend sends asset IDs / metadata / file paths, not resized texture pixels. |
| Reset saved root `Texture Scale U` to `1.0` | Correct hygiene | Saved blend has drifted to `0.8`; checkpoint expects `1.0`. |
| Pin root `Texture Scale U` in metadata-only live push | Correct hygiene | `/api/blender/push-bandmeta` does not currently repair stale root U. |
| Treat root `Texture Scale U = 0.8` as primary blur cause | Incorrect | It is only a 20 percent U change and cannot explain plane sharp / strand blurry. |
| Increase `Ply Resolution` | Incorrect for current graph | `Parametric Weave knotty` does not expose `Ply Resolution`; this is legacy graph vocabulary. |
| Increase profile V resolution | Correct lead | `PW Profile - Mesh Line Count + Offset` controls the actual V profile sampling. |
| Increase `Thread Subdivisions` | Correct U lever | Verified mesh doubles when value doubles. |
| Raise preview / tile render resolution | Valid diagnostic and final-quality lever | It helps only if the remaining blur is pixel-budget limited; it cannot explain viewport-only blur by itself. |
| Change texture interpolation / MIP settings | Diagnostic only | A filter setting alone would affect a plane and strand more similarly; still useful after geometry is fixed. |
| Avoid atlas fallback | Correct risk guard | Atlas code can resize, but the active material path is not atlas. |

## Attack Plan

### Phase 1 - Freeze A Reproducible Fixture

Use a single project JSON and asset through all experiments:

```text
runtime/render_jobs/60f5b85d4bb8/project.json
asset: 08a7db9d6113
source: 47058 x 607
```

Capture:

```text
viewport screenshot, current graph
preview render at 3200
same crop rectangle from the strand region
flat-plane material comparison
```

Acceptance:

```text
Every later test compares the same camera, asset, crop, and material.
```

### Phase 2 - Lock The Sync Baseline

Implement and verify:

```text
Codex_ParametricWeave.blend saved with Texture Scale U = 1.0
backend/app/blender_live.py pins ("Texture Scale U", 1.0)
tests cover the pin
```

Acceptance:

```text
/api/blender/push-project-bandmeta leaves root U at 1.0
/api/blender/push-bandmeta also leaves root U at 1.0
```

### Phase 3 - Run Geometry Matrix

Test V profile steps with Count and Offset tied:

```text
31 steps: Count=31, Offset=1/30   (current)
45 steps: Count=45, Offset=1/44
61 steps: Count=61, Offset=1/60   (validated mechanically)
91 steps: Count=91, Offset=1/90   (only if performance allows)
```

Test U density:

```text
Thread Subdivisions = 8   (current)
Thread Subdivisions = 16
Thread Subdivisions = 24
Thread Subdivisions = 32  (expensive; verified 17.2M verts)
```

Recommended first visual matrix:

```text
baseline:  V=31, Thread=8
balanced:  V=61, Thread=16
high:      V=61, Thread=24
extreme:   V=91, Thread=24
```

Acceptance:

```text
The viewport strand detail improves before touching render resolution.
The smallest acceptable V/U settings are known.
```

### Phase 4 - Make The Graph Controllable

Add a current-graph input, not `Ply Resolution`:

```text
Profile V Steps
```

It must drive both:

```text
PW Profile - Mesh Line Count  = Profile V Steps
PW Profile - Mesh Line Offset = 1 / (Profile V Steps - 1)
```

Keep the default at `31` until visual and performance validation selects a
new default.

Acceptance:

```text
The backend can set V profile density without manual Blender node edits and
without breaking the 0..1 profile domain.
```

### Phase 5 - Add Quality Presets

After the geometry matrix picks acceptable values, map render quality to both
geometry and render resolution.

Initial candidate:

```text
draft     -> Profile V Steps 31, Thread Subdivisions 8,  render 3200
high      -> Profile V Steps 61, Thread Subdivisions 16, render 6400
seamless  -> Profile V Steps 61, Thread Subdivisions 24, tile render
```

Acceptance:

```text
The user chooses quality, not internal node counts.
```

### Phase 6 - Then Run Render Resolution And Filter Sweeps

Only after the viewport geometry result is improved, test final render limits:

```text
render 3200
render 6400
render 8192
tile render / stitched output
Linear vs Closest vs Cubic interpolation
```

Acceptance:

```text
We know how much remaining blur is unavoidable pixel budget vs filter choice.
```

### Phase 7 - Final Acceptance Criteria

The fix is complete when:

```text
asset source and UDIM audit still pass with maxdiff 0
full project push sets root Texture Scale U to 1.0
metadata-only push sets root Texture Scale U to 1.0
high-quality preview uses the selected Profile V Steps and Thread Subdivisions
viewport plane-vs-strand comparison no longer shows obvious geometry blur
render preview crop is visibly sharper at the selected quality tier
performance remains acceptable for interactive live preview and final render
```
