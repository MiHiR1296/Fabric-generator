# Phase Log

## Phase 0 - Investigation Snapshot

Date: 2026-06-03

### User Report

The texture resolution visible in Blender appears different from the original
image texture resolution. Blender MCP is running on port `9876`.

### Environment

```text
repo: /Users/mihirbotle/Desktop/Impetus/3D Fabric/yarnseamless UI/Fabric-generator-tryon
backend: http://127.0.0.1:8000
frontend: http://127.0.0.1:5180
Blender MCP: 127.0.0.1:9876
blend: Codex_ParametricWeave.blend
```

Live scene contained:

```text
ParametricWeave
WebDraft_Live
Space
SeamlessTileCamera
```

### Backend And Frontend Trace

The frontend render/live path goes through:

```text
frontend/src/utils/parserApi.ts
  requestProjectRender(...)
  pushProjectBandmeta(...)

backend/app/main.py
  POST /api/blender/render-project
  POST /api/blender/push-project-bandmeta

backend/app/render_jobs.py
  build_project_material_payloads(...)
  build_headless_render_script(...)

backend/app/yarn_assets.py
  import_yarn_from_library(...)
  ensure_cycles_tiled_rgba_texture_set(...)
```

The frontend does not send resized image pixels to Blender. Blender receives
paths to runtime asset files.

### Active Asset Evidence

Current active live material:

```text
FabricStudioMaterial_01_059e1c0937b5
```

Runtime asset:

```text
id: 059e1c0937b5
label: Greyrescan07
sourceFilename: rgba.png
renderTextureMode: rgba_tiled
renderTileCount: 3
renderTileWidthPx: 15686
renderTileHeightPx: 607
bandMeta.image_size_px: [47058, 607]
bandMeta.blender.image_width_px: 47058
bandMeta.blender.scanner_pixels_per_bu: 62992.16
```

File dimensions:

```text
rgba.png        47058 x 607
rgba_1001.png   15686 x 607
rgba_1002.png   15686 x 607
rgba_1003.png   15686 x 607
```

Pixel comparison:

```text
source size:   47058 x 607
stitched size: 47058 x 607
bbox: None
maxdiff: 0
```

Conclusion:

The active RGBA UDIM tile set is pixel-identical to the original `rgba.png`.

### Live Blender Material Readback

Material nodes:

```text
FabricStudioDiffuseNode
  image: FabricStudioMaterial_01_059e1c0937b5_RGBA_UDIM
  source: TILED
  filepath: runtime/yarn_assets/059e1c0937b5/cycles_tiled/rgba_<UDIM>.png
  Blender tile size readback: 15686 x 607
  tiles: 1001, 1002, 1003
  interpolation: Linear
  extension: CLIP

FabricStudioAlphaNode
  image: same RGBA UDIM image
  interpolation: Linear
  extension: CLIP
```

Conclusion:

The current live material is not using the atlas fallback and is not using a
Cycles-safe downscale. It is using RGBA UDIM tiles from the original source.

### Modifier Socket Readback

Live Blender:

```text
Texture Scale U          Socket_97  = 0.800000011920929
Texture Scale V          Socket_43  = 1.0
Texture Offset V         Socket_44  = 0.0
Sub Texture Scale V      Socket_87  = 1.0
Sub Texture Offset V     Socket_88  = 0.0
Arc 1 V Padding          Socket_244 = 0.00800000037997961
Scanner Pixels Per BU    Socket_98  = 62992.16015625

Material 1 Image Width Px    = 47058.0
Material 1 Texture Scale U   = 0.07530806958675385
U Stride Per Warp End        = 0.209680438041687
U Stride Per Weft Pick       = 0.209680438041687
```

Saved blend readback:

```text
Codex_ParametricWeave.blend
Texture Scale U / Socket_97 = 0.800000011920929
```

Checkpoint expectation:

```text
docs/CHECKPOINT_2026-05-19.md
Socket_97 / Texture Scale U = 1
```

Conclusion:

The saved `.blend` has drifted from the documented approved checkpoint.

### U Sampling Math

Live calculation for Material 1:

```text
image_width_px              = 47058
scanner_pixels_per_bu       = 62992.16015625
texture_world_width_bu      = 0.7470453447424912
warp_threads                = 80
weft_threads                = 80
spacing                     = 0.026000000536441803
strand_length_bu            = 2.0800000429153442
base_repeats_per_strand     = 2.784302261641596
root_texture_scale_u        = 0.800000011920929
material_texture_scale_u    = 0.07530806958675385
effective_u_multiplier      = 0.06024645656714522
effective_repeats_per_strand = 0.16774434527579465
if_root_were_1_effective_repeats = 0.20968042847026144
```

Conclusion:

The active root `Texture Scale U = 0.8` reduces the U sampling density by 20
percent. This is a mapping-scale skew, not source image downsampling.

### Render Preview Evidence

Latest render job:

```text
runtime/render_jobs/60f5b85d4bb8/preview.png
size: 3200 x 3200
```

Render script printed:

```text
phase4f_preview_quality:
  engine: CYCLES
  resolution_x: 3200
  resolution_y: 3200
  cycles_samples: 96
```

Conclusion:

The preview PNG is a camera render, not the source texture. It is expected to
have the configured square preview render size.

### Risk Found: Atlas Resampling

Code:

```text
backend/app/atlas.py
  _fit_tile(...)
  image.resize(size, Image.Resampling.LANCZOS)
```

Current live path:

```text
direct material mode
RGBA UDIM
not atlas
```

Risk:

If direct materials are unavailable or too many materials are used, atlas mode
can resample inputs to common tile dimensions.

### Initial Fix Candidates

1. Restore `Codex_ParametricWeave.blend` root `Texture Scale U` to `1.0`.
2. Pin `Texture Scale U = 1.0` in `backend/app/blender_live.py` so
   bandmeta-only live pushes cannot leave stale U scale in place.
3. Add a test that asserts root U is pinned in live metadata push code.
4. Add a diagnostic endpoint or script for texture source vs Blender material
   vs UV mapping vs preview render resolution.
5. Mark or log atlas fallback whenever it is used because that path can resize.

### Current Conclusion (Phase 0)

The active problem is most likely:

```text
stale root Texture Scale U = 0.8 in the saved/live Blender file
```

not:

```text
downscaled source image
downscaled RGBA UDIM tiles
frontend image resizing
```

## Phase 0.7 - Diagnostic Validation Pass

Date: 2026-06-03

### What Was Rechecked

This pass validated the earlier proposed fixes against the actual running
frontend/backend/live-Blender setup.

### Asset Audit

```text
runtime yarn assets scanned: 23
problems found: 0
rgba_tiled assets: 22
rgba_single assets: 1
```

For every tiled asset:

```text
source rgba.png size == metadata size
source rgba.png size == bandMeta.blender image size
tile widths sum to source width
tile heights match source height
stitched UDIM tiles diff against source: maxdiff = 0
```

Conclusion:

```text
The source and UDIM texture files are not being downscaled.
```

### Full Setup Push

The latest render-job project JSON was pushed through:

```text
POST /api/blender/push-project-bandmeta
```

Immediate live Blender readback:

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
The full setup path already restores root Texture Scale U to 1.0.
```

### Metadata-Only Push

The live root `Texture Scale U` was temporarily set to `0.8`, then:

```text
POST /api/blender/push-bandmeta
```

Readback:

```text
Texture Scale U stayed at 0.800000011920929
```

The live value was restored to `1.0` after the test.

Conclusion:

```text
Pinning ("Texture Scale U", 1.0) in backend/app/blender_live.py is still
correct for metadata-only pushes.
```

### Geometry Socket Validation

The live graph is:

```text
ParametricWeave > Weave > Parametric Weave knotty
```

It exposes:

```text
Thread Subdivisions
Texture Scale U
Texture Scale V
Material N Texture Scale U
```

It does not expose:

```text
Ply Resolution
```

Conclusion:

```text
The proposed Ply Resolution 5 -> 24 fix is incorrect for this current graph.
Use current-graph profile and thread controls instead.
```

### V Profile Density

Baseline:

```text
PW Profile - Mesh Line Count = 31
PW Profile - Mesh Line Offset = 1/30
vertices = 4,300,800
faces = 4,089,600
v_around unique values = 31
```

Naive Count-only probe:

```text
Count 31 -> 61
Offset remained 1/30
```

Result:

```text
profile domain became 0..2
intended v_around resolution did not improve correctly
```

Correct domain-preserving probe:

```text
Count 31 -> 61
Offset 1/30 -> 1/60
```

Result:

```text
vertices = 7,372,800
faces = 7,156,800
v_around unique values = 61
pw_profile_natural unique values = 61
pw_profile_actual unique values = 61
```

Values were restored to Count `31` and Offset `1/30`.

Conclusion:

```text
V profile resolution is a valid lead, but Count and Offset must be tied.
```

### U Thread Density

`Thread Subdivisions` was verified after forcing a dependency graph refresh:

```text
4  -> 2,150,400 vertices / 2,041,600 faces
8  -> 4,300,800 vertices / 4,089,600 faces
16 -> 8,601,600 vertices / 8,185,600 faces
32 -> 17,203,200 vertices / 16,377,600 faces
```

The value was restored to `8`.

Conclusion:

```text
Thread Subdivisions is a real U-density lever, but it has linear mesh-cost
impact and should be controlled by quality presets rather than always pinned.
```

### Proposed Solution Status

```text
validated:
  - asset/UDIM integrity is clean
  - saved blend root Texture Scale U should be reset to 1.0
  - metadata-only live push should pin Texture Scale U = 1.0
  - Thread Subdivisions is a real U-density lever
  - Profile Count + Offset is the real V-density lever

partially valid:
  - render resolution and texture-filter sweeps are useful after geometry is
    fixed, but they cannot explain viewport-only plane-vs-strand blur alone

invalid for current graph:
  - Ply Resolution 5 -> 24 as the primary fix
  - Count-only profile bump without changing Offset
```

This conclusion was revised after Phase 0.5 user testing — see below. The
Phase 0 finding remains true (the U-scale drift is real), but it is no
longer believed to be the primary cause of the visible blur.

## Phase 0.5 - Plane Vs Strand Observation

Date: 2026-06-03

### User Report

Direct quotes, paraphrased only for clarity:

```text
The texture in the Blender file Image Editor (rgba.png) is really very
crisp.
When I see the texture in the Blender file mapped on the weave, it gets
very hazy and blurry, like there is too much detail missing.
When I map the same texture on a simple plane in the Blender file, I can
see the details very nicely.
We are unwrapping the texture so that the stretching does not happen.
Texture Scale U is a good point that might be a reason, but we are
processing all the information needed for that to not give us a problem.
```

### What This Rules Out

A plane and a strand in the same scene, with the same image texture, sharing
the same Blender material and the same image loader path, cannot diverge
because of:

```text
- source file fidelity         (same file, same loader)
- Cycles single-image cap      (same image; UDIM bypass is identical)
- viewport GL_MAX_TEXTURE_SIZE (same image; would affect plane too)
- texture node interpolation   (would affect plane too)
- atlas resampling             (not used by either, confirmed in Phase 0)
- cycles_safe downscale        (RGBA path bypasses; not used here)
```

What is different between the two:

```text
- geometry: flat plane vs woven undulating cylindrical strand
- UV: planar uv vs arc-length unwrap around a tube
- screen coverage: plane fills frame, strand is ~40 px wide
- screen-space derivatives:
    plane     -> small, uniform
    strand    -> large, especially in V around the cylinder
```

So the divergence must live in one of:

```text
- UV mapping density on the curved strand surface
- screen-pixel budget per strand at preview resolution
- Cycles texture filter / MIP selection on curved geometry
- geometry subdivision insufficient to carry texture detail between
  vertices
```

### Pixel Budget Math (Current Asset)

Preview render = 3200 x 3200, weave = 80 warp x 80 weft threads.

```text
strand screen width:        ~40 px  (3200 / 80)
strand screen length:       ~3200 px (across frame)
visible cylinder face:      ~20 px  (front half only)

U direction:
  source pixels per strand   = 0.21 * 47058 ≈ 9882 (after Socket_97 fix)
                             = 0.17 * 47058 ≈ 7906 (current)
  screen pixels per strand   = 3200
  downsample ratio           = ~2.5x to ~3.1x
  likely MIP level           = 1
  effect                     = moderate softening

V direction:
  source pixels per strand   = 607
  visible screen pixels      = ~20
  downsample ratio           = ~30x
  likely MIP level           = 5
  effective V resolution     = ~19 px out of 607
  effect                     = severe softening, dominant blur source
```

The U fix moves the U downsample from 3.1x to 2.5x. That is a real
improvement but it does not touch the V axis, which is the dominant blur
source on the cylinder.

### Code Path Confirmation (Backend Read)

```text
backend/app/yarn_assets.py
  MAX_CYCLES_TEXTURE_DIMENSION = 16384
  ensure_cycles_tiled_rgba_texture_set splits >16384 px into UDIM tiles
  Tiles are crops, not resizes. Active asset uses 3 tiles of 15686 px wide.

backend/app/render_jobs.py
  build_headless_render_script:
    engine     = CYCLES
    resolution = 3200 (default; env override up to 8192)
    samples    = env default
    texture extension     = REPEAT
    texture interpolation = Linear (env override allowed)
  No explicit set of:
    scene.cycles.texture_limit_render
    scene.cycles.texture_limit_viewport
    scene.render.use_simplify
    scene.cycles.dicing_rate
  So those use whatever the .blend has saved.

backend/app/render_jobs.py
  _run_tile_render_job exists and renders the fabric in 4 tiles at up to
  8192 each, then stitches. This is the high-detail path. It is not the
  default preview render.
```

### Updated Hypothesis Ranking

From most likely to least likely as the dominant cause of visible blur:

```text
1. V-direction undersampling on the cylinder (sampling-bandwidth limit)
2. Insufficient screen pixels per strand at preview resolution
3. Cycles filter/MIP selection on curved geometry pushing detail to a
   higher MIP than necessary
4. Geometry subdivision too low to carry texture detail between vertices
5. Socket_97 = 0.8 U-scale drift (real, but ~20 percent effect only)
```

### Decision

The action plan is being reframed. The Socket_97 drift fix is preserved as
hygiene (Phase B1/B2 in the new action_plan.md), but the lead phases are
now A1/A2/A3 diagnostic experiments to determine empirically which lever
moves the picture. Once those are run, Phase C decides whether to default
the preview render to a higher resolution or to expose tile render as a
first-class user choice.

### Open Questions From This Phase

```text
1. Is the user looking at the viewport (EEVEE / Solid / Material preview),
   the rendered preview PNG (Cycles), or both? They behave differently and
   point to different bottlenecks.
2. What does the camera framing look like in the user's setup — how many
   warp threads visible across the 3200 px width?
3. Is the geometry subdivision count visible to the team? If yes, can we
   bump it for a diagnostic render?
```

## Phase 0.6 - Viewport Confirmation And Geometry-Density Lead

Date: 2026-06-03

### User Report

```text
I see the texture being blurry in the viewport itself.
Rendering at higher resolution is a second-level diagnostic — I understand
that will give more detail — but the viewport preview itself is very blurry.
I have done the plane-vs-strand A/B; I can easily see the texture gets blurry
only after applying it to the pattern.
```

This collapses several open hypotheses:

```text
- Confirmed: blur is geometry-specific (plane sharp, strand blurry, same scene)
- Confirmed: blur is viewport-side, not Cycles-only — therefore Cycles MIP
  selection math is not the primary explanation
- Eliminated: file/loader divergence (plane reads the same image)
- Eliminated: GL_MAX_TEXTURE_SIZE viewport limit (plane reads the same image)
```

### Backend Geometry-Density Sockets (Corrected By Phase 0.7)

The first version of this phase used the older `Ply Resolution` vocabulary
from legacy graph paths. Phase 0.7 checked the actual live node group and
corrected the implementation target:

```text
live graph: Parametric Weave knotty
exposed U control: Thread Subdivisions
legacy/not exposed here: Ply Resolution
actual V control: PW Profile - Mesh Line Count + Offset
```

Current baseline:

```text
Thread Subdivisions = 8
PW Profile - Mesh Line Count = 31
PW Profile - Mesh Line Offset = 1/30
vertices = 4,300,800
faces = 4,089,600
v_around unique values = 31
```

The geometry-density hypothesis still stands, but the fix target changes:

```text
V fix: increase Profile V Steps by driving Count and Offset together
U fix: increase Thread Subdivisions through quality presets
```

### Updated Cause Ranking (Viewport-Specific)

```text
1. Profile V density = 31 samples around the active profile
   Effect: V texture detail may be weakened by interpolation across a narrow,
   curved, low-screen-pixel strand surface.

2. Thread Subdivisions = 8
   Effect: U texture detail is smoothed across long strand spans; verified
   to scale mesh size linearly when increased.

3. Warp x Weft thread count vs strand screen pixels
   Effect: Even with higher subdivision, ~40 px wide strands cannot show
   arbitrary high-V detail. User-controlled via warp/weft/camera framing.

4. EEVEE / viewport anisotropic filter on curved tubes at grazing angles
   Effect: Bands of softness near silhouettes.

5. Socket_97 = 0.8 root U scale drift
   Effect: 20% U-density skew. Real hygiene issue, not the primary cause.
```

### Correct Immediate Action

In Blender, use temporary node edits only for diagnosis:

```text
Texture Scale U:               keep/restored to 1.0
Thread Subdivisions:           8 -> 16
PW Profile - Mesh Line Count:  31 -> 61
PW Profile - Mesh Line Offset: 1/30 -> 1/60
```

Do not change Count without Offset. Do not implement a current-graph fix by
adding `plyResolution` to the backend.

If the strand texture sharpens visibly, Phase A0 moves to exposing a new
current-graph socket named `Profile V Steps`, with quality presets owning both
`Profile V Steps` and `Thread Subdivisions`.

Tradeoff:

```text
Thread 8 -> 16 doubles mesh size: 4.30M -> 8.60M vertices
Profile 31 -> 61 raises mesh size: 4.30M -> 7.37M vertices
Combined increases will be expensive and must be quality-tier controlled.
```

## Phase 0.8 - Mapping And Alpha Diagnostic Follow-Up

Date: 2026-06-04

### User Report

After rendering the geometry-density comparison set, the user reported that
none of the renders were clear enough:

```text
The texture still looks very blurry and hazy.
The twists and turns on the small strand threads are still missing.
The same details are visible in the RGBA input.
The UV mapping or curve mapping may be the issue.
```

### Comparison Renders

Full-frame geometry-density renders were written to:

```text
runtime/texture_resolution_comparison/20260604_012821/
```

The tested variants were:

```text
00_baseline_profile31_thread8.png
01_recommended_profile61_thread16.png
02_high_profile61_thread24.png
```

The user judged all three still too blurry/hazy. Therefore geometry density is
not sufficient as the primary fix.

### Material Coordinate Path

The material does not use a regular Blender UV map. It samples the texture
through a generated named attribute:

```text
ShaderNodeAttribute(attribute_name="uv_scaled")
  -> Separate XYZ
  -> FRACT(U)
  -> multiply U by UDIM tile count
  -> Combine XYZ
  -> FabricStudioDiffuseNode / FabricStudioAlphaNode
```

So the real texture lookup is owned by Geometry Nodes:

```text
u_along + uv_offset_u + material scale -> uv_scaled.x
v_around + Arc 1/Arc 2 band mapping    -> uv_scaled.y
```

This makes the user's suspicion plausible: the image can be full resolution
and still look wrong if `uv_scaled` samples the wrong rows, compresses detail,
or uses the wrong curve projection.

### Active Asset Band Evidence

For active asset `08a7db9d6113`:

```text
rgba.png size: 47058 x 607
metadata core height: 37 px
metadata top halo: 15 px
metadata bot halo: 15 px
detected visible band: ~67 px
```

Metadata V rows:

```text
fiber_bot_v_min 0.446458 -> row 271
core_v_min      0.471170 -> row 286
core_v_max      0.530478 -> row 322
fiber_top_v_max 0.555189 -> row 337
```

Alpha analysis:

```text
alpha nonzero rows: 25..606
coverage >= 50% rows: 270..337
coverage >= 90% rows: 282..324
avg alpha >= 50% rows: 285..320
```

Conclusion:

```text
The RGBA is 607 px tall, but the graph is intentionally sampling a narrow,
mostly opaque yarn band near rows 271..337. The full source image can look
detailed while the active rendered sampling window only sees a thin,
semi-transparent strip.
```

### uv_scaled Numeric Readback

Live evaluated mesh at baseline:

```text
vertices: 268,800
faces:    254,400
uv_scaled.x range: 0.4343..11.1690
uv_scaled.y range: 0.4028..0.6005
v_around unique values: 31
```

By strand type:

```text
main strands uv_scaled.y: 0.4592..0.5425
sub strands  uv_scaled.y: 0.4028..0.6005
```

Interpretation:

```text
Main strand geometry samples an even narrower V slice than the full detected
visible band. Sub strands sample wider, but still not the full RGBA height.
```

### Lighting / Alpha / Filter Diagnostics

Additional diagnostic renders were written to:

```text
runtime/texture_resolution_mapping_diagnostics/20260604_0210/
```

Renders:

```text
00_current_lit_reference_profile61_thread16.png
01_unlit_emission_alpha_linear.png
02_unlit_emission_opaque_linear.png
03_unlit_emission_opaque_closest.png
```

Observations:

```text
unlit + alpha + linear remains hazy -> lighting is not the primary cause
opaque renders expose black/dark transparent RGB -> alpha/RGB padding matters
closest sampling does not rescue the opaque path -> Linear vs Closest is not
the main fix
```

### Updated Cause Ranking

```text
1. Generated uv_scaled mapping / V-band projection
   The current graph does not use a normal unwrap. Arc 1/Arc 2 remap a thin
   detected band through a curve projection. This is now the lead suspect.

2. Active V sampling window is too narrow
   Main strands sample roughly rows 279..329, while the user may be comparing
   against the visually richer full RGBA or wider alpha fringe.

3. Alpha/mipmap treatment of translucent fibers
   Transparent pixels carry dark RGB. Filtering alpha/RGB together can make
   fiber detail read as haze, especially on sub-strands.

4. Pixel footprint
   Even with correct mapping, the source micro-fibers are low-contrast and
   semi-transparent. At full-fabric camera scale they are near or below the
   render pixel budget.
```

### Next Tests

```text
1. Render a synthetic high-contrast UV test texture through the current graph.
   If checker/numbered rows blur or bend incorrectly, uv_scaled is proven bad.

2. Add a temporary V Mapping Mode switch:
   current projected/band mapping vs linear v_around -> visible band vs full
   alpha bbox.

3. Store uv_scaled on face-corner / real UV domain instead of point domain and
   compare against the named point attribute.

4. Generate an alpha-dilated/premultiplied texture variant so transparent
   pixels do not contribute black/dark RGB to filtered samples.

5. Render a close-up camera over fewer strands. If details appear only then,
   remaining loss is pixel footprint. If not, mapping is still wrong.
```

## Phase 0.9 - V Mapping And Alpha Variant Proof

Date: 2026-06-04

### User Follow-Up

The user pushed back that the diagnostic renders were still blurry while the
input RGB/RGBA looked crisp, and suspected V-band / curve mapping:

```text
The image is mostly blank space and only a little bit of threads.
Only the yarn part should be mapped.
Alpha/filtering may also be a problem.
```

### Finding 1: Sub Texture Scale V Was Not Neutral

The Geometry Nodes graph computes the final V scale as:

```text
v_scale = is_sub_strand * Sub Texture Scale V + Texture Scale V
```

With the live/backend pinned defaults:

```text
Texture Scale V     = 1.0
Sub Texture Scale V = 1.0
```

sub-strands get:

```text
v_scale = 2.0
```

This is not neutral. It doubles the sub-strand V span around the center of the
source image and pulls in blank / low-alpha rows.

### V Sweep Renders

New renders were written to:

```text
runtime/texture_resolution_v_mapping_tests/20260604_020718/
```

Variants:

```text
00_current_original_subdelta1.png
01_original_subdelta0.png
02_original_subdelta0_pad0.png
03_original_subdelta0_arc2_core_pad0.png
04_alpha_boost_subdelta0.png
05_alpha_threshold_subdelta0.png
```

Each variant also has:

```text
*_crop_900_900_2300_2300.png
*_crop_2x_nearest.png
render_manifest.json
```

### V Range Proof

Current behavior:

```text
Sub Texture Scale V = 1.0
main uv_scaled.y = 0.46317..0.53848  span 0.07531
sub  uv_scaled.y = 0.40280..0.60049  span 0.19769
```

Corrected neutral sub V delta:

```text
Sub Texture Scale V = 0.0
main uv_scaled.y = 0.46317..0.53848  span 0.07531
sub  uv_scaled.y = 0.45140..0.55025  span 0.09885
```

Interpretation:

```text
The user's V-band suspicion is correct. The sub-strand path was sampling
roughly 2x the intended V band, so it blended yarn pixels with blank/halo
pixels and made the result hazy.
```

### Crop Sharpness Metrics

Same crop, grayscale edge metric:

```text
00_current_original_subdelta1:        edge_mean 3.44
01_original_subdelta0:                edge_mean 4.39
02_original_subdelta0_pad0:           edge_mean 4.35
03_original_subdelta0_arc2_core_pad0: edge_mean 4.35
04_alpha_boost_subdelta0:             edge_mean 5.10
05_alpha_threshold_subdelta0:         edge_mean 6.35
```

Interpretation:

```text
Sub Texture Scale V = 0.0 improves detail without changing the source image.
Alpha boosting improves it further.
Hard alpha thresholding is sharpest but visually too cut-out/chunky to use as
the final production treatment.
```

### Finding 2: Alpha Softness Is A Second Problem

Previous alpha tests were written to:

```text
runtime/texture_resolution_alpha_tests/20260604_020236/
```

Results:

```text
original_copy:                 edge_mean 3.43
alpha_boost_sqrt_rgb_same:     edge_mean 4.47
alpha_threshold_24_rgb_same:   edge_mean 6.91
rgb_bleed_original_alpha:      edge_mean 3.43
rgb_bleed_alpha_boost_sqrt:    edge_mean 4.45
precomposite_gray_opaque:      edge_mean 5.25
```

Interpretation:

```text
RGB bleed alone did not help, so dark transparent RGB is not the primary
cause. Alpha opacity/softness is real: hardening the alpha greatly increases
visible detail, but a binary threshold is too harsh.
```

### Code Change Made

The neutral sub-strand V default was changed from `1.0` to `0.0` in:

```text
backend/app/blender_live.py
backend/app/blender_sync.py
scripts/build_flat_arc1_rebuild.py
backend/tests/test_blender_live.py
backend/tests/test_blender_sync.py
```

Focused tests:

```text
python3 -m unittest backend.tests.test_blender_live backend.tests.test_blender_sync
Ran 10 tests - OK
```

`pytest` could not be run because it is not installed in the current Python
environment.

Live Blender MCP readback after applying the fix to the running scene:

```text
ParametricWeave > Weave
Texture Scale V:     before 1.0 -> after 1.0
Sub Texture Scale V: before 1.0 -> after 0.0
Sub Texture Offset V: before 0.0 -> after 0.0
```

### Updated Solution Direction

The likely production fix is now two-part:

```text
1. Mapping fix:
   Pin Sub Texture Scale V to 0.0, not 1.0, because it is an additive delta.

2. Alpha fix:
   Add a non-binary alpha opacity curve/levels step so yarn fibers become
   opaque enough to survive curved-surface filtering without hard jagged
   threshold artifacts.
```

Geometry density remains useful for quality presets, but it is not the
primary cause of the hazy texture in these tests.

## Phase 1.0 - Mapping Fix Applied And Documentation Updated

Date: 2026-06-04

Status: superseded by Phase 1.1 for the final `Sub Texture Scale V`
interpretation. Phase 1.0 is kept as diagnostic history: setting
`Sub Texture Scale V = 0.0` proved the old graph was double-sampling Arc 2,
but it is not the production fix.

### Goal

Convert the Phase 0.9 diagnostic result into an actionable repo state and
record the result phase-by-phase so the next fix can continue without
repeating the investigation.

### What Was Done

1. Ran a controlled V-mapping render sweep from the saved diagnostic blend:

   ```text
   source blend:
   runtime/texture_resolution_comparison/20260604_012821/comparison_source_live_state.blend

   output folder:
   runtime/texture_resolution_v_mapping_tests/20260604_020718/
   ```

2. Rendered these variants:

   ```text
   00_current_original_subdelta1.png
     Current behavior. Original RGBA. Sub Texture Scale V = 1.0.

   01_original_subdelta0.png
     Original RGBA. Sub Texture Scale V = 0.0.

   02_original_subdelta0_pad0.png
     Original RGBA. Sub Texture Scale V = 0.0. Arc 1 V Padding = 0.

   03_original_subdelta0_arc2_core_pad0.png
     Original RGBA. Sub Texture Scale V = 0.0. Arc 2 forced to core bounds.

   04_alpha_boost_subdelta0.png
     Alpha-boosted RGBA. Sub Texture Scale V = 0.0.

   05_alpha_threshold_subdelta0.png
     Hard-threshold alpha RGBA. Sub Texture Scale V = 0.0.
   ```

3. Generated same-region crops for each render:

   ```text
   *_crop_900_900_2300_2300.png
   *_crop_2x_nearest.png
   ```

4. Measured evaluated `uv_scaled.y` ranges from the Blender mesh:

   ```text
   Current behavior:
     main_y = 0.46317..0.53848  span 0.07531
     sub_y  = 0.40280..0.60049  span 0.19769

   Corrected sub V delta:
     main_y = 0.46317..0.53848  span 0.07531
     sub_y  = 0.45140..0.55025  span 0.09885
   ```

5. Measured crop sharpness with a grayscale edge metric:

   ```text
   00_current_original_subdelta1:        edge_mean 3.44
   01_original_subdelta0:                edge_mean 4.39
   02_original_subdelta0_pad0:           edge_mean 4.35
   03_original_subdelta0_arc2_core_pad0: edge_mean 4.35
   04_alpha_boost_subdelta0:             edge_mean 5.10
   05_alpha_threshold_subdelta0:         edge_mean 6.35
   ```

6. Temporarily updated code so new live/headless setup pushes used
   `Sub Texture Scale V = 0.0`. This was later superseded by Phase 1.1:
   the production fix keeps `Sub Texture Scale V = 1.0` and changes the graph
   formula instead.

   ```text
   backend/app/blender_live.py
     PINNED_FOOTGUN_SOCKETS now pins ("Sub Texture Scale V", 0.0)

   backend/app/blender_sync.py
     full setup temporarily wrote Sub Texture Scale V = 0.0

   scripts/build_flat_arc1_rebuild.py
     rebuild interface default and modifier assignment now use 0.0
   ```

7. Updated tests:

   ```text
   backend/tests/test_blender_live.py
   backend/tests/test_blender_sync.py
   ```

8. Applied the corrected value to the running Blender MCP scene:

   ```text
   Blender MCP: 127.0.0.1:9876
   object: ParametricWeave
   modifier: Weave

   Texture Scale V:      1.0 -> 1.0
   Sub Texture Scale V:  1.0 -> 0.0
   Sub Texture Offset V: 0.0 -> 0.0
   ```

9. Updated documentation:

   ```text
   docs/TextureResolutionFix/README.md
     Added latest status and marked older geometry-first sections as historical.

   docs/TextureResolutionFix/diagnostic_validation.md
     Added 2026-06-04 V mapping correction and metrics.

   docs/TextureResolutionFix/action_plan.md
     Reordered priority: mapping fix first, alpha curve second, geometry as
     quality preset.

   docs/TextureResolutionFix/phase_log.md
     Added Phase 0.9 and this Phase 1.0 entry.
   ```

### Test Results

`pytest` was attempted first, but the current system Python does not have it:

```text
python3 -m pytest backend/tests/test_blender_live.py backend/tests/test_blender_sync.py
No module named pytest
```

The focused stdlib unittest pass succeeded:

```text
python3 -m unittest backend.tests.test_blender_live backend.tests.test_blender_sync
Ran 10 tests in 0.001s
OK
```

### Interpretation

The user's V-band suspicion was correct. The source RGBA is mostly vertical
blank/transparent space with the useful yarn detail in a narrow band. The
previous sub-strand mapping sampled too much vertical texture range, so it
mixed useful yarn pixels with blank/low-alpha halo rows and made the strands
look foggy.

The mapping fix is necessary and measurable:

```text
Sub Texture Scale V 1.0 -> 0.0
sub-strand V span 0.19769 -> 0.09885
edge_mean 3.44 -> 4.39
```

The mapping fix alone does not fully recover the crisp twist/fiber detail.
The alpha tests show a second contributor:

```text
alpha_boost_sqrt_rgb_same:   edge_mean 4.47
alpha_threshold_24_rgb_same: edge_mean 6.91
```

This means alpha opacity softness is suppressing fine detail after filtering.
Hard thresholding proves detail exists, but it creates jagged/cut-out
artifacts, so the production fix should be a tunable alpha curve rather than
a binary alpha cutoff.

### Important Caveats

1. Superseded by Phase 1.1: a saved `.blend` should not be saved with
   `Sub Texture Scale V = 0.0` as the final fix. It should be saved with
   `Sub Texture Scale V = 1.0` and the corrected absolute sub-scale graph
   formula.

2. The rebuild script now uses the corrected default, so future rebuilds should
   not reintroduce the old `1.0` value.

3. Geometry-density work is not abandoned. It remains useful for high-quality
   presets, but Phase 0.8 proved it is not the first-order blur fix.

4. The alpha curve has not been implemented yet. The rendered alpha variants
   are diagnostics only.

### Next Phase

Phase 1.1 should implement and render a non-binary alpha opacity curve:

```text
candidate A: alpha_out = pow(alpha_in, 0.45..0.70)
candidate B: alpha_out = smoothstep(low=0.04..0.08, high=0.45..0.70, alpha_in)
candidate C: low-alpha cleanup floor + mild alpha sharpening
```

Acceptance for Phase 1.1:

```text
Keep most of the extra detail seen in hard-threshold render
without the chunky/jagged cut-out appearance.
```

## Phase 1.1 - Corrected Arc 2 Scale Interpretation

Date: 2026-06-04

### User Correction

The user reported that removing / zeroing `Sub Texture Scale V` made the Arc 2
mapping change drastically and look wrong, even though the texture looked a bit
clearer. The visible issue after that was:

```text
The texture is getting stretched and screwed when the warp/weft goes up and
down.
```

This is an important correction to Phase 1.0.

### Revised Interpretation

Phase 1.0 correctly found that the old graph doubled the sub-strand V span, but
it drew the wrong final implementation conclusion.

Wrong final conclusion:

```text
Set Sub Texture Scale V to 0.0.
```

Correct conclusion:

```text
Keep Sub Texture Scale V = 1.0.
Treat it as Arc 2's absolute V scale.
Do not add it on top of Texture Scale V.
```

The old live graph did this:

```text
v_scale = Texture Scale V + is_sub_strand * Sub Texture Scale V
```

So with both scales set to `1.0`, sub-strands used:

```text
v_scale = 2.0
```

The corrected graph does this:

```text
v_scale = Texture Scale V
        + is_sub_strand * (Sub Texture Scale V - Texture Scale V)
```

So with both scales set to `1.0`, sub-strands use:

```text
v_scale = 1.0
```

This preserves the meaning of the `Sub Texture Scale V` socket while avoiding
the doubled Arc 2 sample span.

### Code Changes

Revised the Phase 1.0 code change so `Sub Texture Scale V` remains `1.0`:

```text
backend/app/blender_live.py
  PINNED_FOOTGUN_SOCKETS pins ("Sub Texture Scale V", 1.0)

backend/app/blender_sync.py
  full setup writes Sub Texture Scale V = 1.0

backend/tests/test_blender_live.py
backend/tests/test_blender_sync.py
  assertions restored to 1.0
```

Updated the rebuild script so future generated graphs use absolute sub-scale
math:

```text
scripts/build_flat_arc1_rebuild.py

old:
  v_scale = Texture Scale V + is_sub * Sub Texture Scale V
  v_offset = Texture Offset V + is_sub * Sub Texture Offset V

new:
  v_scale = Texture Scale V + is_sub * (Sub Texture Scale V - Texture Scale V)
  v_offset = Texture Offset V + is_sub * (Sub Texture Offset V - Texture Offset V)
```

### Live Blender MCP Patch

The running Blender graph did not use the rebuild node names. Its active nodes
were:

```text
Math.015 label: Scale V + Sub*is_sub
Math.016 label: Offset V + Sub*is_sub
```

These were rewired in the live graph to use explicit delta nodes:

```text
PW Live Sub Scale V Delta  = Sub Texture Scale V - Texture Scale V
PW Live Sub Offset V Delta = Sub Texture Offset V - Texture Offset V

Math.015 = Texture Scale V + is_sub * ScaleDelta
Math.016 = Texture Offset V + is_sub * OffsetDelta
```

Live socket readback after patch:

```text
Texture Scale V      = 1.0
Sub Texture Scale V  = 1.0
Texture Offset V     = 0.0
Sub Texture Offset V = 0.0
```

### Live UV Readback After Corrected Formula

With `Sub Texture Scale V = 1.0` kept in place, the evaluated `uv_scaled.y`
ranges are now:

```text
main uv_scaled.y = 0.45917..0.54248  span 0.08331
sub  uv_scaled.y = 0.45140..0.55025  span 0.09885
```

This preserves the clearer/narrowed effective Arc 2 sampling from Phase 1.0
without making `Sub Texture Scale V` itself zero.

### Test Results

Focused tests pass:

```text
python3 -m unittest backend.tests.test_blender_live backend.tests.test_blender_sync
Ran 10 tests in 0.001s
OK
```

Syntax checks pass:

```text
python3 -m py_compile scripts/build_flat_arc1_rebuild.py backend/app/blender_live.py backend/app/blender_sync.py
```

### Current Correct Result

The correct result is:

```text
Sub Texture Scale V = 1.0
Texture Scale V = 1.0
Graph formula = Texture + is_sub * (Sub - Texture)
```

Do not use `Sub Texture Scale V = 0.0` as the production fix. That was a
diagnostic way to cancel the old additive bug, but it also changes the meaning
of Arc 2 controls and can make the up/down strand mapping look wrong.

### Next Phase

Now that Arc 2 V scale is semantically correct, retest the visual stretch when
warp/weft moves over and under. If the texture still visibly stretches at
up/down transitions, the next target is likely the V coordinate basis on the
curved profile:

```text
Arc 1 uses projected_v = (1 - cos(v_around * pi)) / 2
Arc 2 currently uses a linear v_around-derived HaloFlow mapping
```

The next diagnostic should compare Arc 2's linear `v_around` mapping against a
projected/cosine-matched Arc 2 mapping so the halo follows the same visual
projection as Arc 1 during over-under undulation.

## Phase 1.2 - Live Alpha Curve A/B Validation

Date: 2026-06-04

### Goal

Confirm the Phase 0.9 alpha-softness hypothesis using the actually-running
Blender scene rather than from saved diagnostic renders, and pin down the
exact production change.

### Live Scene Baseline (Read From Blender MCP)

```text
modifier:               ParametricWeave > Weave > Parametric Weave knotty
Texture Scale U:        1.0
Texture Scale V:        1.0
Sub Texture Scale V:    1.0     (Phase 1.1 absolute interpretation, live formula corrected)
Sub Texture Offset V:   0.0
Arc 1 V Padding:        0.012   (user widened from 0.008)
Thread Subdivisions:    8
Warp Threads:           60
Weft Threads:           60
Spacing:                0.026
Amplitude:              0.005

Material 1 (active):    FabricStudioMaterial_01_08a7db9d6113
Material 1 Image Width Px:    47058
Material 1 Texture Scale U:   0.0833
Material 1 Arc 1 V Min..Max:  0.4712..0.5305  (core band, ~36 source px tall)
Material 1 Arc 2 V Min..Max:  0.4465..0.5552  (outer band, ~66 source px tall)
```

The viewport showed the same hazy/soft-halo symptom the user described. The
shader alpha path (next section) is independent of which V-combiner formula
the team standardises on, so the finding below is valid regardless of
whether the live graph carries the original `Texture + is_sub * Sub`
combiner or the Phase 1.1 `Texture + is_sub * (Sub - Texture)` variant.

### Material Shader Path (Read From Blender)

```text
FabricStudioMaterial_01_08a7db9d6113
  use_nodes: True
  blend_method: BLEND
  surface_render_method: BLENDED

  FabricStudioDiffuseNode.Color  --> Principled BSDF.Base Color
  FabricStudioAlphaNode.Alpha    --> Principled BSDF.Alpha       (DIRECT, no remap)

  Both texture nodes: TILED RGBA UDIM (3 tiles, 15686 x 607 each)
  interpolation: Linear
  extension: CLIP
  colorspace: sRGB
```

The shader path matches `ensure_texture_preview_material` in
`backend/app/render_jobs.py:367-491`. There was no intermediate alpha curve,
levels, or remap node anywhere in the graph. Phase 0.9 had already proven
this is what is suppressing visible detail.

### A/B Procedure

1. Snapshot viewport at baseline (no alpha curve).
2. On Material 1 only, insert a `ShaderNodeMath POWER` node tagged
   `PW_AB_AlphaCurve_Power` between `FabricStudioAlphaNode.Alpha` and
   `Principled BSDF.Alpha`:

   ```text
   FabricStudioAlphaNode.Alpha
     --> Math.POWER(alpha, exponent)
     --> Principled BSDF.Alpha
   ```

3. Snapshot viewport at exponent = 0.5 (Phase 0.9 `alpha_boost_sqrt` candidate).
4. Snapshot viewport at exponent = 0.35 (stronger boost, still non-binary).
5. Remove the inserted node, restore the original direct link.

### Visual Result

Baseline:

```text
- Pattern geometry crisp, but yarn surface reads as gray haze.
- Soft fiber halo bleeds into and around each strand body.
- Yarn twist direction not visible at any zoom in viewport.
```

Exponent = 0.5 (alpha = sqrt(alpha)):

```text
- Yarn twist direction clearly readable on individual strands.
- Dark crevices between threads regain definition.
- Fiber halo still present but defined, not blurred-out.
- Gray haze largely removed.
```

Exponent = 0.35:

```text
- Stronger effect; diagonal twist on each strand is sharply visible.
- No binary/cut-out artifacts (different shape than alpha threshold).
- Halo still preserved as soft fiber tail.
```

Both states were captured to screenshots and reviewed. The improvement is
larger than any geometry-density, render-resolution, or interpolation change
tested in earlier phases.

### Why It Works

The source RGBA contains the actual yarn body in a narrow ~36 px V core
band, with semi-transparent fiber tails on either side. Without a curve:

```text
- A pixel sampled in the fiber-tail zone has alpha ~ 0.15..0.30.
- Linear texture filtering blends those low-alpha pixels with their
  neighbors across each strand's screen area.
- The result on screen is 15..30% opaque pixels stacked across the strand,
  reading as gray haze that drowns out the high-contrast twist detail.
```

`pow(alpha, 0.5)` does not change which pixels are sampled. It maps
mid-alpha values upward (0.25 -> 0.50, 0.50 -> 0.71) without introducing
the cut-out edges of a hard threshold. Yarn twist pixels were always being
sampled correctly; they were drowned by soft-alpha fringe.

### Edge Metric Reference (From Phase 0.9 Renders)

```text
00_current_original_subdelta1:        edge_mean 3.44
01_original_subdelta0:                edge_mean 4.39
04_alpha_boost_subdelta0:             edge_mean 5.10
05_alpha_threshold_subdelta0:         edge_mean 6.35
```

The Phase 1.2 viewport A/B is consistent with the Phase 0.9 alpha boost row
(`edge_mean 5.10`), and the user explicitly rejected the threshold look in
Phase 1.0 (the cut-out edges of `05_alpha_threshold`). A tunable curve
covers the range between these.

### Recommended Production Patch

Single-point change in `backend/app/render_jobs.py:485-487`:

```python
# Before
alpha_output = alpha_tex.outputs['Alpha'] if (use_rgba_tiled or use_rgba_single) else alpha_tex.outputs['Color']
links.new(alpha_output, shader.inputs['Alpha'])

# After
alpha_output = alpha_tex.outputs['Alpha'] if (use_rgba_tiled or use_rgba_single) else alpha_tex.outputs['Color']
alpha_curve_gamma = float(os.environ.get('WEAVE_ALPHA_CURVE_GAMMA', '0.5'))
if alpha_curve_gamma != 1.0:
    alpha_power = nodes.new('ShaderNodeMath')
    alpha_power.name = 'FabricStudioAlphaCurve'
    alpha_power.operation = 'POWER'
    alpha_power.location = (260, -180)
    alpha_power.inputs[1].default_value = alpha_curve_gamma
    links.new(alpha_output, alpha_power.inputs[0])
    alpha_output = alpha_power.outputs[0]
links.new(alpha_output, shader.inputs['Alpha'])
```

Rationale:

```text
- Env var WEAVE_ALPHA_CURVE_GAMMA controls the exponent without code changes.
- Default 0.5 matches Phase 0.9 alpha_boost_sqrt; the most-defensive option.
- 1.0 disables the curve (back to current behavior) for clean A/B testing.
- 0.35 is a stronger setting users can opt into.
- The node is named FabricStudioAlphaCurve so future diagnostics can find it.
```

The same patch automatically applies to the headless render path because
`ensure_texture_preview_material` is the single materializer used for both
single-pass render and tile render paths.

### Scene State

The A/B nodes were removed and the original direct alpha link restored
before this phase was closed. The live scene is byte-identical to its
Phase 1.1 state. No persistent edits.

### Outstanding Work After Phase 1.2

```text
1. Land the production patch above.
2. Pick the default exponent. 0.5 is the safe default; 0.35 is stronger.
3. Save the corrected Codex_ParametricWeave.blend so its on-disk default
   carries the Phase 1.1 graph formula and Texture Scale U = 1.0.
4. Decide whether Arc 1 V Padding = 0.012 (user's current live value) should
   become the new default vs the 0.008 checkpoint value.
5. Reframe action_plan Phase A-2 around the validated curve approach.
6. Quality presets (Phase A-3) remain follow-on work, not blocking.
```

### Confidence

High. This is the first phase where the recommended fix was applied to the
running scene, the visual delta was directly observed, and the change was
small enough to be a single-node patch on the existing material generator.
The remaining steps are production hygiene, not further investigation.

---

## Phase 1.3 - Correction After Arc 2 Regression Report

Date: 2026-06-04

### User Feedback

The user reported that the attempted `Sub Texture Scale V` graph rewrite made
Arc 2 unrecognizable and that the docs should not be treated as final truth.

### Retraction

The following production fixes are rejected:

```text
Sub Texture Scale V = 0.0
v_scale = Texture Scale V + is_sub_strand * (Sub Texture Scale V - Texture Scale V)
```

Live Blender and `scripts/build_flat_arc1_rebuild.py` were restored to:

```text
Sub Texture Scale V = 1.0
v_scale = Texture Scale V + is_sub_strand * Sub Texture Scale V
```

Live graph readback after restore:

```text
Math.015 label     = Scale V + Sub*is_sub
Math.015 operation = MULTIPLY_ADD
input 0            = is_sub_strand
input 1            = Sub Texture Scale V
input 2            = Texture Scale V

Math.016 label     = Offset V + Sub*is_sub
Math.016 operation = MULTIPLY_ADD
input 0            = is_sub_strand
input 1            = Sub Texture Offset V
input 2            = Texture Offset V
```

### Padding Diagnostic

Tested `Arc 1 V Padding` values:

```text
0.0120000001
0.008
0.004
0.002
0.0
```

Result:

```text
Arc 2/sub uv_scaled.y min/max/span stayed identical:
0.4028006 .. 0.6004943, span 0.1976936
```

Conclusion:

```text
Arc 1 V Padding is not causing the current Arc 2 texture stretch / haze.
```

### Same-Strand U Transfer Diagnostic

Temporary live test, restored afterward:

```text
Current Same-Strand U Transfer:
  zero U steps     = 0.292%
  reversed U steps = 0.019%
  tiny U steps     = 0.125%
  median du        = 0.00029136
  p99 du           = 0.00077578

Bypassed transfer, Arc 2 uses own U:
  zero U steps     = 0%
  reversed U steps = 0%
  tiny U steps     = 0%
  median du        = 0.00036635
  p99 du           = 0.00036759
```

Interpretation:

```text
The nearest-surface Same-Strand U Transfer is a real mapping suspect.
It introduces local Arc 2 U plateaus/reversals that disappear when bypassed.
The first visual EEVEE comparison was subtle at swatch zoom, so this should be
validated with closer Cycles/debug renders before changing the saved .blend.
```

Render folder:

```text
runtime/texture_resolution_arc2_u_transfer_tests/20260604_030521/
```

### Alpha / Material Diagnostic

The active RGBA and UDIM tiles are full resolution. The material path was:

```text
uv_scaled -> UDIM U tiling -> Image Texture -> Principled BSDF Alpha
```

The source asset has a narrow core/fiber band inside a tall transparent RGBA,
and raw alpha blending makes the render read as gray haze. A live alpha ramp
made the fibers obvious but was too hard/cut-out. A softer power curve was
then selected for production:

```text
alpha_out = pow(alpha_in, WEAVE_ALPHA_CURVE_GAMMA)
default WEAVE_ALPHA_CURVE_GAMMA = 0.5
WEAVE_ALPHA_CURVE_GAMMA = 1.0 disables the curve
```

Code change landed:

```text
backend/app/render_jobs.py
  adds FabricStudioAlphaCurve between alpha texture and shader alpha
  env vars:
    WEAVE_ALPHA_REMAP_ENABLED
    WEAVE_ALPHA_CURVE_GAMMA
```

Render folders:

```text
runtime/texture_resolution_alpha_mapping_tests/20260604_030657/
runtime/texture_resolution_alpha_curve_tests/20260604_031509/
```

### Verification

```text
python3 -m py_compile backend/app/render_jobs.py backend/tests/test_render_jobs.py backend/app/blender_live.py backend/app/blender_sync.py scripts/build_flat_arc1_rebuild.py
python3 -m unittest backend.tests.test_render_jobs backend.tests.test_blender_live backend.tests.test_blender_sync
```

Result:

```text
34 tests passed.
```

## Phase 1.8 - Direct RGBA Alpha Default

### Trigger

The user reviewed the live Blender material and found the better current output
with the diffuse/RGBA texture's own alpha channel linked directly to the shader,
without using the generated alpha texture and without the Map Range boost.

### Change

The material-generator contract changed from "RGBA diffuse plus separate
RGBA_Alpha image" to "RGBA diffuse supplies both color and alpha" for RGBA
single and RGBA UDIM assets.

```text
Default RGBA path:
  FabricStudioDiffuseNode.Color -> Principled BSDF.Base Color
  FabricStudioDiffuseNode.Alpha -> Principled BSDF.Alpha

Opt-in diagnostic:
  WEAVE_ALPHA_REMAP_ENABLED=1 inserts FabricStudioAlphaRemap
```

The split diffuse/alpha fallback path still uses a separate alpha map because
those assets do not carry an alpha channel in the diffuse image.

### Arc 1 Padding

The same review changed the current code default for `Arc 1 V Padding` to
`0.02` in backend and frontend render settings.

### Verification

```text
python3 -m py_compile backend/app/render_jobs.py backend/app/blender_sync.py
python3 -m unittest backend.tests.test_render_jobs backend.tests.test_blender_sync

31 tests passed.
```

---

## Phase 1.4 - Live Alpha Cleanup And Arc 2 U Transfer Bypass

Date: 2026-06-04

Status: superseded by Phase 1.5 and Phase 1.6. The Arc 2 own-U bypass below
was rejected by visual review and replaced with deterministic same-strand U.

### User Feedback

The user agreed that alpha blending explains the blur/haze and asked to fix
that in the live Blender scene. They also asked to apply the correction for the
nearest-surface transfer finding on Arc 2, because the measured zero/reversed
steps are consistent with the visible stretch when the yarn goes up and down.

The user also updated the docs. Reviewed changes:

```text
docs/README.md
  TextureResolutionFix/ is now in the top-level read order.

docs/putting-it-together/lessons.md
docs/putting-it-together/phase_log.md
  MCP port wording now points Blender/app/docs/Codex to 9876.
```

These changes match the current investigation and were kept.

### Live Blender Setup

The approved Arc 2 V mapping was preserved:

```text
Texture Scale V     = 1.0
Sub Texture Scale V = 1.0
v_scale             = Texture Scale V + is_sub_strand * Sub Texture Scale V
```

The rejected formulas from earlier phases were not reapplied.

Active materials on `ParametricWeave` were changed from direct alpha:

```text
FabricStudioAlphaNode.Alpha -> Principled BSDF.Alpha
```

to:

```text
FabricStudioAlphaNode.Alpha
  -> FabricStudioAlphaRemap
  -> FabricStudioAlphaCurve
  -> Principled BSDF.Alpha
```

Live alpha settings:

```text
FabricStudioAlphaRemap:
  From Min = 0.04
  From Max = 0.55
  To Min   = 0.0
  To Max   = 1.0
  Clamp    = true
  Smootherstep interpolation where supported by Blender

FabricStudioAlphaCurve:
  Operation = POWER
  Gamma     = 0.75
```

Rationale:

```text
The source RGBA has visible twist detail, but much of the strand edge is low
alpha haze. The remap removes the broad transparent halo before it reaches the
shader. The mild POWER curve then keeps fibers visible without the cut-out look
of a hard threshold.
```

### Arc 2 U Transfer Correction In Live Scene

The live graph now bypasses the same-strand nearest-surface U transfer for
Arc 2 so Arc 2 uses its own continuous U coordinate during visual review.

Live diagnostic node:

```text
Node:
  PW StrandXferU - Use Same-Strand Arc1 U On Arc2

State:
  Switch input is unlinked
  Switch default_value = False
  Label = Arc2 U transfer bypassed for texture diagnostic
```

Measured effect:

```text
Current nearest-surface transfer:
  segments      = 287400
  negative_pct  = 0.018789
  zero_pct      = 0.292276
  tiny_pct      = 0.125261
  du_median     = 0.00029136
  du_p99        = 0.00077578

Bypassed transfer, Arc 2 own U:
  segments      = 287400
  negative_pct  = 0.0
  zero_pct      = 0.0
  tiny_pct      = 0.0
  du_median     = 0.00036635
  du_p99        = 0.00036759
```

This is a diagnostic live-state change, not yet a saved .blend contract. If the
user approves the look, the saved graph should replace this switch/bypass with
a deliberate Arc 2 U mapping path.

### Backend Patch

`backend/app/render_jobs.py` now generates the same alpha cleanup for preview
materials by default:

```text
WEAVE_ALPHA_REMAP_ENABLED = true
WEAVE_ALPHA_REMAP_LOW     = 0.04
WEAVE_ALPHA_REMAP_HIGH    = 0.55
WEAVE_ALPHA_CURVE_GAMMA   = 0.75
```

Implementation details:

```text
ensure_texture_preview_material(...)
  alpha_output = alpha texture Alpha for RGBA sources, Color for split-alpha
  link_alpha_to_shader(...)

link_alpha_to_shader(...)
  if WEAVE_ALPHA_REMAP_ENABLED=0:
    direct alpha link
  else:
    FabricStudioAlphaRemap Map Range
    optional FabricStudioAlphaCurve POWER, skipped only when gamma = 1.0
```

Endpoint scope:

```text
/api/blender/push-project-bandmeta
  uses build_headless_render_script(..., render_still=False)
  will create/refresh the alpha remap material graph

/api/blender/push-bandmeta
  uses blender_live.py metadata-only push
  will not create/refresh material nodes
```

### Render Artifact

Latest live corrected render:

```text
runtime/texture_resolution_live_corrected_tests/20260604_033543/00_live_alpha_remap_arc2_u_bypass.png
```

### Verification

```text
python3 -m py_compile backend/app/render_jobs.py backend/tests/test_render_jobs.py backend/app/blender_live.py backend/app/blender_sync.py scripts/build_flat_arc1_rebuild.py
python3 -m unittest backend.tests.test_render_jobs backend.tests.test_blender_live backend.tests.test_blender_sync
git diff --check -- backend/app/render_jobs.py backend/tests/test_render_jobs.py docs/TextureResolutionFix/README.md docs/TextureResolutionFix/action_plan.md docs/TextureResolutionFix/diagnostic_validation.md docs/TextureResolutionFix/phase_log.md
```

Result:

```text
34 tests passed.
diff whitespace check passed.
```

### Current Recommendation

Keep the live scene in this diagnostic state while the user reviews it:

```text
1. Alpha remap + mild curve should remain as the lead material fix.
2. Arc 2 U transfer bypass should be judged visually in Blender before saving.
3. Do not reapply Sub Texture Scale V = 0.0 or the absolute-sub-scale formula.
```

---

## Phase 1.5 - Rejection Of Arc 2 Own-U And Strong Alpha Boost

Date: 2026-06-04

### User Feedback

The user rejected the Phase 1.4 live look:

```text
Arc 2 cannot have independent U.
Arc 2 is the fiber/strand halo of the same yarn and must visually continue
Arc 1's texture flow.
The bypassed Arc 2 look is noisy, unrealistic, and makes the whole texture
feel hazy.
There also appears to be a small U-scale shrink across the texture.
```

### Immediate Live Corrections

Restored Arc 2 same-strand U:

```text
Node:
  PW StrandXferU - Use Same-Strand Arc1 U On Arc2

Switch:
  linked back to PW StrandXferU - Is Arc2.Result

False:
  PW U - Per Section Multiplier

True:
  PW StrandXferU - Sample Same-Strand Arc1 U
```

This restores the intended design:

```text
Arc 1 carries the thick/core yarn.
Arc 2 carries the fiber/halo surface.
Arc 2 must borrow/continue Arc 1 U from the same physical strand while keeping
its own V band.
```

The live alpha setup was also reduced from the strong Phase 1.4 setting:

```text
Rejected:
  low/high = 0.04 / 0.55
  gamma    = 0.75

Live revised:
  low/high = 0.10 / 0.78
  gamma    = 1.0
```

This keeps a mild low-alpha halo cleanup but no longer boosts mid-alpha Arc 2
fibers into a noisy opaque layer.

### U-Scale / Stride Finding

The evaluated mesh confirmed the user's small-shrink observation:

```text
Arc 1/main median U span per strand = 0.17550468
Arc 2/sub median U span per strand  = 0.17479706
Difference                          ~= 0.4% shorter on Arc 2
```

This shrink remains after restoring same-strand U and appears to come from the
nearest-surface transfer losing a small amount of endpoint continuity.

Separately, the live modifier had stale/inconsistent stride:

```text
Material 1 Image Width Px = 47058
Material 1 Texture Scale U = 0.08330807
Old live U Stride Per Warp/Weft = 0.52189845
```

Because the shader maps UDIM with:

```text
fract(uv_scaled.x) * texture_tile_count
```

`uv_scaled.x` is normalized to the full source width, not to one tile. The
consistent stride for the active 60x60, spacing 0.026 setup is:

```text
texture_world_width_bu = 47058 / 62992.16015625 = 0.74704534
strand_length_bu       = 60 * 0.026 = 1.56
material_scale_u       = 0.08330807
correct U stride       = strand_length / texture_world_width * material_scale_u
                       = 0.17396614
```

Live Blender was updated to:

```text
UV Random U = 0.0
U Stride Per Warp End = 0.17396614
U Stride Per Weft Pick = 0.17396614
```

### Render/Viewport Captures

```text
runtime/texture_resolution_live_corrected_tests/current_live_preview_after_rejected_bypass.png
runtime/texture_resolution_live_corrected_tests/current_live_preview_restored_arc2_same_u.png
runtime/texture_resolution_live_corrected_tests/current_live_preview_restored_same_u_direct_alpha.png
runtime/texture_resolution_live_corrected_tests/current_live_preview_restored_same_u_mild_alpha.png
runtime/texture_resolution_live_corrected_tests/current_live_preview_same_u_mild_alpha_stride_fullwidth.png
```

### Production Code Adjustment

`backend/app/render_jobs.py` defaults now match the milder live alpha setting:

```text
DEFAULT_ALPHA_REMAP_LOW = 0.10
DEFAULT_ALPHA_REMAP_HIGH = 0.78
DEFAULT_ALPHA_CURVE_GAMMA = 1.0
```

The curve remains available through `WEAVE_ALPHA_CURVE_GAMMA`, but the default
is now remap-only cleanup.

### Revised Recommendation

```text
1. Do not save or ship the Arc 2 own-U bypass.
2. Keep same-strand Arc 1 U transfer conceptually.
3. Fix the transfer implementation so Arc 2 samples a continuous, endpoint-
   matched Arc 1 U, not a nearest-surface value with plateaus/reversals.
4. Keep alpha cleanup mild by default; use stronger gamma only as an opt-in.
5. Keep U stride derived from the full source image width, not tile width.
```

---

## Phase 1.6 - Deterministic Same-Strand Arc 2 U Fix

Date: 2026-06-04

### Goal

Implement the Phase 1.5 recommendation:

```text
Remove the nearest-surface U lookup that caused Arc 2 endpoint shrink, but do
not give Arc 2 an independent texture stream.
```

### Live Blender Graph Patch

Patched the active `ParametricWeave > Weave > Parametric Weave knotty` graph:

```text
Node:
  PW StrandXferU - Use Same-Strand Arc1 U On Arc2

Switch:
  <- PW StrandXferU - Is Arc2.Result

False / Arc 1:
  <- PW U - Per Section Multiplier.Value

True / Arc 2:
  <- PW UV U Add.Value
```

The old nearest-surface node is no longer active:

```text
PW StrandXferU - Sample Same-Strand Arc1 U
  muted = true
  label = UNUSED - nearest-surface Arc2 U caused endpoint shrink
```

This is not the rejected own-U bypass. Arc 2 is still in the same yarn U stream
as Arc 1; it simply receives the deterministic base U directly instead of
through a surface-nearest sample.

### Validation

Evaluated mesh readback after the patch:

```text
Arc 1/main U span per strand:
  min/median/max = 0.1755046844 / 0.1755046844 / 0.1755046844

Arc 2/sub U span per strand:
  min/median/max = 0.1755046844 / 0.1755046844 / 0.1755046844

main - sub median span delta = 0.0
```

Step diagnostics:

```text
Arc 1/main:
  negative_pct = 0.0
  zero_pct     = 0.0
  tiny_pct     = 0.0
  du_median    = 0.0003665924
  du_p99       = 0.0003670757

Arc 2/sub:
  negative_pct = 0.0
  zero_pct     = 0.0
  tiny_pct     = 0.0
  du_median    = 0.0003665924
  du_p99       = 0.0003670757
```

The previous measured Arc 2 shrink was:

```text
Arc 1/main median U span = 0.17550468
Arc 2/sub median U span  = 0.17479706
delta                    ~= 0.4%
```

That defect is gone in the live evaluated mesh.

### Live State Kept

```text
UV Random U = 0.0
U Stride Per Warp End = 0.17396614
U Stride Per Weft Pick = 0.17396614
Texture Scale U = 1.0
Texture Scale V = 1.0
Sub Texture Scale V = 1.0
Arc 1 V Padding = 0.012
Alpha remap low/high = 0.10 / 0.78
Alpha gamma = 1.0
```

### Saved Files / Docs

Saved live Blender file:

```text
Codex_ParametricWeave.blend
```

Updated docs:

```text
docs/BlenderFixes/README.md
docs/BlenderFixes/architecture.md
docs/BlenderFixes/geometry_nodes_guide.md
docs/TextureResolutionFix/README.md
docs/TextureResolutionFix/action_plan.md
docs/TextureResolutionFix/diagnostic_validation.md
```

Updated rebuild note:

```text
scripts/build_flat_arc1_rebuild.py
  documents deterministic same-strand U and explicitly rejects rebuilding the
  old nearest-surface Arc 2 U sampler.
```

### Viewport Capture

```text
runtime/texture_resolution_live_corrected_tests/current_live_preview_deterministic_same_strand_u.png
```

### Verification

```text
python3 -m py_compile backend/app/render_jobs.py backend/tests/test_render_jobs.py backend/app/blender_live.py backend/app/blender_sync.py scripts/build_flat_arc1_rebuild.py
python3 -m unittest backend.tests.test_render_jobs backend.tests.test_blender_live backend.tests.test_blender_sync
git diff --check -- backend/app/render_jobs.py backend/tests/test_render_jobs.py backend/app/blender_live.py backend/app/blender_sync.py scripts/build_flat_arc1_rebuild.py docs/TextureResolutionFix/README.md docs/TextureResolutionFix/action_plan.md docs/TextureResolutionFix/diagnostic_validation.md docs/TextureResolutionFix/phase_log.md docs/BlenderFixes/README.md docs/BlenderFixes/architecture.md docs/BlenderFixes/geometry_nodes_guide.md
```

Result:

```text
34 tests passed.
diff whitespace check passed.
```

---

## Phase 1.7 - Material Defaults And RGBA Alpha Colorspace Fix

Date: 2026-06-04

### User Change Reviewed

The user manually tested a material-default change in the live Blender file:

```text
Alpha texture colorspace = Non-Color
Principled Roughness     = 1.0
Principled Sheen Weight  = 0.5
```

Live readback showed this was only partially applied:

```text
FabricStudioMaterial_01_08a7db9d6113
  roughness = 1.0
  sheen     ~= 0.5
  diffuse   = sRGB RGBA UDIM image
  alpha     = separate Non-Color RGBA UDIM image

FabricStudioMaterial_02_d866f49b8b2d
  roughness = 0.72
  sheen     = 0.0
  diffuse   = sRGB RGBA UDIM image
  alpha     = same sRGB image datablock as diffuse
```

### Root Cause In The Generator

The render-job material generator shared one Blender image datablock for RGBA
diffuse and RGBA alpha:

```text
diffuse_tex.image = rgba_image
alpha_tex.image   = rgba_image
```

That means setting the alpha texture to `Non-Color` is not stable. Blender
stores colorspace on the image datablock, not on the texture node. If diffuse
and alpha share one image, the image can be either `sRGB` or `Non-Color`, not
both.

### Code Fix

Updated generated preview material defaults:

```text
DEFAULT_PREVIEW_MATERIAL_ROUGHNESS = 1.0
DEFAULT_PREVIEW_MATERIAL_SHEEN     = 0.5
```

Updated both direct RGBA paths:

```text
UDIM RGBA:
  diffuse image = <material>_RGBA_UDIM        colorspace sRGB
  alpha image   = <material>_RGBA_Alpha_UDIM  colorspace Non-Color

single RGBA:
  diffuse image = <material>_RGBA        colorspace sRGB
  alpha image   = <material>_RGBA_Alpha  colorspace Non-Color
```

Changed `ensure_image(...)` to load with `check_existing=False` when creating a
new named image datablock. This prevents Blender from returning the already
loaded diffuse image for the alpha path just because the file path is the same.

Updated plain/live draft material creation in `backend/app/blender_sync.py` so
web-draft materials use the same roughness and sheen defaults.

### Live Blender Patch

Applied the same defaults to the open Blender scene and saved:

```text
Codex_ParametricWeave.blend
```

Readback after save:

```text
FabricStudioMaterial_01_059e1c0937b5
FabricStudioMaterial_01_08a7db9d6113
FabricStudioMaterial_01_e59d738c7c1f
FabricStudioMaterial_02_d866f49b8b2d

roughness        = 1.0
sheen            = 0.5
diffuse image    = RGBA_UDIM, sRGB
alpha image      = RGBA_Alpha_UDIM, Non-Color
same_image       = false
```

`WebDraftMaterial` also reads back:

```text
roughness = 1.0
sheen     = 0.5
```

Save state:

```text
bpy.data.is_dirty = False
```

### Verification

```text
python3 -m py_compile backend/app/render_jobs.py backend/app/blender_sync.py backend/tests/test_render_jobs.py backend/tests/test_blender_sync.py
python3 -m unittest backend.tests.test_render_jobs backend.tests.test_blender_sync backend.tests.test_blender_live
```

Result:

```text
34 tests passed.
```
