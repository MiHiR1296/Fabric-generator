# Action Plan

## Goal

Make the parametric weave render preserve the fidelity that is already
visible in the source RGBA file when the same file is shown in Blender's
Image Editor or mapped onto a flat plane. Today the strand-region detail in
the preview render is much softer than the underlying texels justify.

## 2026-06-04 Correction

This document is a phase log and planning aid, not the final truth. The
current source of truth is the live Blender graph, evaluated attributes, and
render A/Bs.

Rejected ideas:

```text
Do not set Sub Texture Scale V to 0.0 as the production fix.
Do not rewrite the final V scale as Texture + is_sub * (Sub - Texture).
```

The user reported that both of those paths break / degrade Arc 2. Live graph
readback was restored to the approved additive combiner:

```text
Texture Scale V     = 1.0
Sub Texture Scale V = 1.0
v_scale             = Texture Scale V + is_sub_strand * Sub Texture Scale V
```

New live diagnostic findings:

```text
1. Arc 1 V Padding is not the Arc 2 blur/stretch cause.
   Changing 0.012 -> 0.008 -> 0.004 -> 0.002 -> 0.0 leaves Arc 2
   uv_scaled.y ranges unchanged.

2. Same-Strand U Transfer is a real Arc 2 mapping suspect, but it must not be
   removed outright.
   Current transfer: 0.292% zero U steps, 0.019% reversed U steps on sampled
   Arc 2 slices.
   Bypassed transfer: 0% zero / tiny / reversed U steps, but the visual result
   is unrealistic because Arc 2 loses Arc 1 texture continuity.
   Deterministic same-strand U: Arc 2 follows the Arc 1/base yarn U stream
   without nearest-surface lookup. Arc 1 and Arc 2 U spans now match exactly
   in the evaluated mesh.

3. The dominant visible haze is alpha/material blending.
   The source RGBA is full resolution, but the material was feeding the raw
   alpha directly into Principled Alpha. A two-step alpha cleanup first
   removes the low-alpha haze band, then applies a mild curve to expose more
   strand/fiber detail without changing UVs.
```

Updated priority:

```text
Phase A-1: keep Sub Texture Scale V = 1.0 and keep the restored additive
           final V combiner.
Phase A-2: ship a tunable alpha remap + curve in the material generator.
Phase A-3: replace nearest-surface Same-Strand U Transfer with deterministic
           same-yarn Arc 1 -> Arc 2 U continuity.
Phase A-4: keep geometry density / interpolation as quality presets, not the
           primary fix.
```

## How This Plan Differs From The Previous One

The previous plan started from the assumption that fixing the root
`Texture Scale U = 0.8` drift would meaningfully restore visible detail.
After the plane-vs-strand A/B (texture is sharp on a plane, blurry on the
weave — Phase 0.5) and the viewport-confirmation report (blur is visible in
the viewport itself, not only in Cycles renders — Phase 0.6), that fix is
reclassified as defensive hygiene rather than the primary lever.

The previous ordering was:

```text
Phase A0 (geometry):    bump strand mesh density (the most likely fix).
Phase A1-A3 (diagnostic): if A0 does not fully resolve it, prove which
                          remaining lever moves the picture.
Phase B (hygiene):      keep the drift fixes from the previous plan.
Phase C (high-detail):  make the high-detail render paths the default
                        wherever a high-fidelity preview is the user goal.
Phase D (clarity):      make the render path and resolution observable in
                        the UI so future blur reports are diagnosable in
                        one screen.
```

## Historical Phase A0 - Geometry Density Probe

Owner: Blender file + backend + frontend

Status update:

```text
Demoted after Phase 0.8/0.9 diagnostics.
Geometry density is still a useful quality lever, but it did not resolve the
hazy renders by itself. Do Phase A-1 and A-2 first.
```

## Phase A-1 - Fix Sub-Strand V Over-Scaling

Owner: backend + Blender rebuild script + working `.blend`

Status:

```text
Retracted as a production fix after user visual review.
The diagnostic was useful because it proved the V scale path changes Arc 2
sharply, but the final formula below is not approved. Keep the restored live
graph formula:

v_scale = Texture Scale V + is_sub_strand * Sub Texture Scale V
```

Problem:

```text
Sub Texture Scale V is intended to be an absolute Arc 2/sub-strand scale, but
the graph was treating it as an additive delta:

v_scale = is_sub_strand * Sub Texture Scale V + Texture Scale V
```

Therefore:

```text
Texture Scale V = 1.0, Sub Texture Scale V = 1.0 -> sub V scale = 2.0
```

This made sub-strands sample `uv_scaled.y = 0.4028..0.6005`, far wider than
the detected yarn band.

Correct formula:

```text
v_scale = Texture Scale V + is_sub_strand * (Sub Texture Scale V - Texture Scale V)
```

With the corrected graph and `Sub Texture Scale V = 1.0`, live Blender reads:

```text
main uv_scaled.y = 0.45917..0.54248  span 0.08331
sub  uv_scaled.y = 0.45140..0.55025  span 0.09885
```

Code already updated:

```text
backend/app/blender_live.py
backend/app/blender_sync.py
scripts/build_flat_arc1_rebuild.py
backend/tests/test_blender_live.py
backend/tests/test_blender_sync.py
```

Remaining action:

```text
Regenerate or update the working Blender file so its saved default and current
node graph use the corrected absolute sub-scale formula.
```

Acceptance:

```text
After a full setup push and a metadata-only push, live Blender reads back:
Texture Scale V = 1.0
Sub Texture Scale V = 1.0
Sub Texture Offset V = 0.0

The evaluated graph must still show the narrowed sub-strand V span, proving
the formula no longer doubles Arc 2.
```

Render check:

```text
Compare:
runtime/texture_resolution_v_mapping_tests/20260604_020718/
  00_current_original_subdelta1.png
  01_original_subdelta0.png
  04_alpha_boost_subdelta0.png
```

## Phase A-2 - Add A Tunable Alpha Opacity Curve

Owner: backend render material generator

Status as of 2026-06-04: validated in live Blender via the Phase 1.2 A/B test.
Lead production fix. See [phase_log.md Phase 1.2](phase_log.md) for the full
trace, scene baseline readback, and viewport before/after.

### Evidence

Phase 0.9 saved-render edge metric:

```text
original alpha render edge_mean:          3.43
alpha boost sqrt render edge_mean:        4.47
hard alpha threshold render edge_mean:    6.91
rgb bleed with original alpha edge_mean:  3.43
```

Phase 1.2 live viewport A/B (same scene, same camera, Material 1 only):

```text
baseline (no curve):
  Yarn surface reads as gray haze. Twist direction not visible. Halo bleeds
  into strand body.

alpha = pow(alpha, 0.5):
  Yarn twist direction clearly readable. Crevices defined. Halo preserved
  but no longer mushy. Gray haze largely removed.

alpha = pow(alpha, 0.35):
  Stronger effect. Diagonal twist sharply visible per strand. No cut-out
  artifacts. Halo still soft.
```

Live A/B nodes were removed after the test; scene was restored to its
Phase 1.1 state.

### Why The Alpha Remap Works

```text
Source RGBA has the yarn body in a narrow ~36 px V core band with
semi-transparent fiber tails on either side (alpha ~ 0.15..0.30).
Linear texture filtering blends those low-alpha pixels across the strand's
screen pixels, producing gray haze that drowns out twist contrast.

The live fix does not change which pixels are sampled. It maps very low
alpha to zero, maps the useful yarn/fiber range back to 0..1 with a smooth
Map Range, then applies a mild POWER curve. This keeps the anti-aliased
fiber edge, but stops the broad translucent halo from washing out the yarn
twist detail.
```

### Production Patch (Validated)

Single-point change in [backend/app/render_jobs.py](../../backend/app/render_jobs.py)
inside `ensure_texture_preview_material(...)`: route the selected alpha output
through `link_alpha_to_shader(...)` instead of linking directly to
`Principled BSDF.Alpha`.

```python
# Before
alpha_output = alpha_tex.outputs['Alpha'] if (use_rgba_tiled or use_rgba_single) else alpha_tex.outputs['Color']
links.new(alpha_output, shader.inputs['Alpha'])

# After
alpha_output = alpha_tex.outputs['Alpha'] if (use_rgba_tiled or use_rgba_single) else alpha_tex.outputs['Color']
link_alpha_to_shader(nodes, links, alpha_output, shader.inputs['Alpha'])
```

Properties:

```text
Default enabled:    WEAVE_ALPHA_REMAP_ENABLED = true
Low cleanup:        WEAVE_ALPHA_REMAP_LOW = 0.10
Useful range top:   WEAVE_ALPHA_REMAP_HIGH = 0.78
Default curve:      WEAVE_ALPHA_CURVE_GAMMA = 1.0

Nodes:
  FabricStudioAlphaRemap  ShaderNodeMapRange, clamp, smootherstep if available
  FabricStudioAlphaCurve  ShaderNodeMath POWER, only created when gamma != 1.0

Off switch:
  WEAVE_ALPHA_REMAP_ENABLED=0 restores the direct alpha link.

Optional sharper curve:
  WEAVE_ALPHA_CURVE_GAMMA=0.75 or lower keeps the low/high remap and boosts
  mid-alpha fibers. Visual review showed this can become too noisy on Arc 2,
  so it is not the default.
```

The same patch covers both the headless render path and the app-driven
`/api/blender/push-project-bandmeta` live setup path, because that endpoint
calls `build_headless_render_script(..., render_still=False)` and uses the same
`ensure_texture_preview_material` materializer. The older
`/api/blender/push-bandmeta` endpoint only writes modifier metadata and does
not create or refresh material nodes.

### Acceptance

```text
1. Live setup leaves active materials with FabricStudioAlphaRemap between
   FabricStudioAlphaNode.Alpha and Principled BSDF.Alpha. FabricStudioAlphaCurve
   may exist only when gamma is not 1.0.
2. WEAVE_ALPHA_REMAP_ENABLED=0 restores the previous direct-link behavior
   without code changes, so before/after A/B remains trivial.
3. WEAVE_ALPHA_CURVE_GAMMA=1.0 disables only the POWER step; this is the
   current default after Arc 2 visual review.
4. Render preview at 3200 retains the alpha-cleanup detail (not just viewport).
5. No regression on yarns whose alpha is already crisp; in those cases use
   environment overrides or future per-asset settings to relax the remap.
```

### Optional Follow-Ups After Landing

```text
- Add explicit alpha remap fields to the render settings JSON so per-render
  or per-asset overrides do not require env vars.
- Expose a UI control in the Render Panel as a "Yarn Crispness" slider mapped
  to low/high/gamma presets.
- Consider per-asset defaults from bandMeta once enough yarns are tested.
```

## Phase A-3 - Geometry Density Quality Preset Details

Owner: Blender file + backend + frontend

This is now a quality-preset phase, not the lead fix. The user has confirmed
the blur is visible in the viewport itself and is geometry-specific: the same
material is sharp on a plane and blurry on the weave. The actual running graph is
`Parametric Weave knotty`, and the diagnostic validation found an important
correction:

```text
Do not use Ply Resolution as the current fix lever.
The live Parametric Weave knotty graph does not expose that socket.
```

The current graph has two real density levers:

```text
U direction: Thread Subdivisions
V direction: PW Profile - Mesh Line Count + Offset together
```

Baseline live mesh:

```text
Thread Subdivisions = 8
PW Profile - Mesh Line Count = 31
PW Profile - Mesh Line Offset = 1 / 30

vertices = 4,300,800
faces    = 4,089,600
v_around unique values = 31
```

### A0.1 - Manual V-Density Probe

Steps:

1. Open `Codex_ParametricWeave.blend`.
2. Select `ParametricWeave`, open the `Weave` node group.
3. Find `PW Profile - Mesh Line`.
4. Change Count and Offset together:

```text
current:  Count = 31, Offset = 1/30
probe:    Count = 61, Offset = 1/60
```

5. Keep `Texture Scale U = 1.0`.
6. Refresh the viewport and compare the same strand crop.

Acceptance:

```text
Strand viewport detail visibly improves when V profile steps increase.
The profile domain remains 0..1.
```

Important:

```text
Count-only is invalid. A naive Count 31 -> 61 while keeping Offset 1/30
pushes the profile domain to 0..2 and does not produce the intended V
sampling result.
```

Validated mechanical result:

```text
Count 31 / Offset 1/30 -> 4.30M vertices, 31 V samples
Count 61 / Offset 1/60 -> 7.37M vertices, 61 V samples
```

### A0.2 - Manual U-Density Probe

`Thread Subdivisions` is exposed and works, but it is expensive:

```text
Thread Subdivisions = 4   -> 2,150,400 vertices / 2,041,600 faces
Thread Subdivisions = 8   -> 4,300,800 vertices / 4,089,600 faces
Thread Subdivisions = 16  -> 8,601,600 vertices / 8,185,600 faces
Thread Subdivisions = 32  -> 17,203,200 vertices / 16,377,600 faces
```

Start with:

```text
Thread Subdivisions: 8 -> 16
```

Acceptance:

```text
U-direction strand detail improves enough to justify the mesh cost.
```

### A0.3 - First Visual Matrix

Run the smallest useful matrix before code changes:

```text
baseline:  V=31, Thread=8
balanced:  V=61, Thread=16
high:      V=61, Thread=24
extreme:   V=91, Thread=24    (only if performance allows)
```

For every row, capture:

```text
viewport screenshot
3200 preview render
same strand crop rectangle
vertex / face count
```

Acceptance:

```text
We know the smallest V/U density pair that fixes the viewport blur.
```

### A0.4 - Expose Profile V Steps As A Render Override

Owner: Blender graph + backend

Add a current-graph socket:

```text
Profile V Steps
```

It must drive both:

```text
PW Profile - Mesh Line Count  = Profile V Steps
PW Profile - Mesh Line Offset = 1 / (Profile V Steps - 1)
```

Files likely involved:

```text
scripts/build_flat_arc1_rebuild.py
backend/app/blender_sync.py
backend/app/render_jobs.py
backend/app/main.py
```

Acceptance:

```text
The backend can set V profile density without manual node edits and without
breaking the profile's 0..1 domain.
```

### A0.5 - Quality Preset Mapping

Owner: backend + frontend

Tie geometry-density sockets to quality tiers after the matrix picks the
smallest acceptable values:

```text
draft     -> Profile V Steps = 31, Thread Subdivisions = 8,  render 3200
high      -> Profile V Steps = 61, Thread Subdivisions = 16, render 6400
seamless  -> Profile V Steps = 61, Thread Subdivisions = 24, tile render
```

Acceptance:

```text
Picking a quality tier changes geometry density and render resolution
together, with no manual .blend editing required.
```

### A0.6 - Do Not Pin Density In Metadata-Only Push Yet

`PINNED_FOOTGUN_SOCKETS` should pin safety defaults, not force expensive
geometry on every metadata-only color/material push. Pinning
`Thread Subdivisions = 16` or a future `Profile V Steps = 61` should wait
until the quality tier design is implemented.

Acceptance:

```text
Metadata-only pushes repair dangerous texture-state drift, but quality
selection owns geometry density.
```

## Phase A1 - Plane Vs Strand A/B Render

Owner: Blender + backend (one-off experiment)

Steps:

1. In the live Blender scene, duplicate `ParametricWeave` and replace its
   modifier output with a flat subdivided plane sized to roughly match a
   single strand at the same camera distance. Apply the active
   `FabricStudioMaterial_01_<asset>` material to that plane.
2. Render the original ParametricWeave and the plane surrogate at the same
   resolution (3200) and same samples.
3. Compare strand-region pixel detail side by side.

Acceptance:

```text
We have visual evidence of how much of the blur comes from the geometry
itself versus from the render-resolution / pixel-budget limit.
```

This is the single most useful experiment to run before changing any code,
because every code change below depends on which hypothesis dominates.

## Phase A2 - Resolution Sweep

Owner: backend env var

Steps:

1. Render the same draft at the three resolutions:

   ```text
   WEAVE_PREVIEW_RENDER_RESOLUTION=3200
   WEAVE_PREVIEW_RENDER_RESOLUTION=6400
   WEAVE_PREVIEW_RENDER_RESOLUTION=8192
   ```

2. Trigger one tile render via the existing
   `submit_project_tile_render_job(...)` path. That renders the fabric in
   four tiles at up to 8192 each and stitches.
3. Crop the same strand region from all four outputs and compare.

Acceptance:

```text
We know whether the strand blur is bounded by render-pixels-per-strand
(if so, larger renders are visibly sharper) or by something else (if so,
larger renders give the same visible detail).
```

## Phase A3 - Filter And MIP A/B

Owner: backend env var + Image Texture node setting

Steps:

1. Render with `WEAVE_TEXTURE_INTERPOLATION=Linear` (current default).
2. Render with `WEAVE_TEXTURE_INTERPOLATION=Closest`.
3. Render with `WEAVE_TEXTURE_INTERPOLATION=Cubic`.

Acceptance:

```text
We know whether the filter step is suppressing visible texels (Closest is
sharper + aliased) or whether the missing detail is upstream of the filter
(Closest is also blurry).
```

These three experiments together answer the question: is the visible blur a
sampling-rate limit, a filter selection, or geometry undersampling.

## Phase B1 - Reset The Saved Blend Baseline

Owner: Blender file

Files:

```text
Codex_ParametricWeave.blend
docs/CHECKPOINT_2026-05-19.md
```

Steps:

1. Back up the current blend file.
2. Set `ParametricWeave > Weave > Texture Scale U` (`Socket_97`) to `1.0`.
3. Save the blend.
4. Background-mode read back and confirm:

```text
Socket_97 = 1.0
```

Acceptance:

```text
Saved blend matches docs/CHECKPOINT_2026-05-19.md for Socket_97.
```

This will improve U sampling density by ~20 percent. It will not change V
direction sampling.

## Phase B2 - Pin Root Texture Scale U In The Live Bandmeta Push

Owner: backend live Blender sync

Files:

```text
backend/app/blender_live.py
backend/tests/test_blender_live.py
```

Steps:

1. Add to `PINNED_FOOTGUN_SOCKETS`:

```python
("Texture Scale U", 1.0),
```

2. Add or update a test asserting that entry is present.
3. Run:

```bash
cd backend
python3 -m unittest tests.test_blender_live tests.test_blender_sync
```

Acceptance:

```text
A bandmeta-only live push cannot leave root Texture Scale U at a stale
value such as 0.8.
```

## Phase B3 - Make Atlas Fallback Explicit

Owner: backend render material payloads

Files:

```text
backend/app/atlas.py
backend/app/render_jobs.py
backend/tests/test_render_jobs.py
```

Steps:

1. Log when atlas preview mode is selected (currently silent in render job
   metadata).
2. Add render job metadata `atlasMode: bool`, `atlasResampled: bool`, and
   the atlas tile width/height.
3. Consider replacing atlas resize with padding when exact pixel
   preservation matters.

Acceptance:

```text
No render silently enters the atlas resampling path.
```

## Phase C1 - Add A Quality Preset Tier For High-Detail Previews

Owner: backend + frontend render panel

The single-pass 3200 render is fine for layout review but is below the
sampling bandwidth needed to show fine yarn texture detail. Users currently
have two ways to get higher quality:

```text
WEAVE_PREVIEW_RENDER_RESOLUTION=8192    (env override, single render)
submit_project_tile_render_job(...)     (tile render path, exists)
```

Neither is a first-class user choice in the UI.

Steps:

1. Add a `previewQuality` field to render requests, with three tiers:

```text
draft      -> 3200, current default
high       -> 8192, single-pass
seamless   -> tile render, current 4-up path
```

2. Plumb through `requestProjectRender(...)` in
   `frontend/src/utils/parserApi.ts`.
3. In `RenderPanel.tsx`, expose the tier as a dropdown and disable
   higher tiers when the GPU does not have enough VRAM for the larger
   render target.

Acceptance:

```text
A user complaining about strand blur in the preview can switch to a
higher tier without editing env vars or calling the tile-render endpoint
directly.
```

## Phase C2 - Optional: Closer Inspection Camera

Owner: backend + frontend

When the user reports "the texture is blurry", they often want a close-up
inspection view, not a higher-res full-frame render. A close-up camera
fundamentally increases screen pixels per strand without paying for an
8192 full-frame render.

Steps:

1. Add a `SeamlessInspectionCamera` (orthographic, very small ortho_scale)
   that focuses on one strand at the active asset.
2. Wire an "Inspect Texture" button in the render panel that fires a small
   render using that camera at 1024 or 2048.

Acceptance:

```text
The user can ask the system to render a single strand at maximum sampling
density to confirm whether the texture detail is reaching the shader.
```

## Phase C3 - Optional: Per-Material V Frequency Tuning

Owner: backend render math + UI

If the V wrap on the cylinder is the dominant downsample (Phase A1/A3 will
confirm), we may want to expose:

```text
Material N Texture Scale V
Material N V Crop or V Stretch
```

Currently V is fixed-scale per-material. If the source RGBA has more V detail
than the cylinder can show, padding/cropping V (instead of wrapping the full
607 px around) may be a better tradeoff. This decision depends on what the
source images actually look like in V.

Acceptance:

```text
We have an intentional policy for V-direction texture coverage rather than
inheriting whatever the source aspect ratio happens to be.
```

This is optional and should not start until Phase A1/A3 evidence justifies
it.

## Phase D1 - Texture Resolution Diagnostic Endpoint

Owner: backend + optional UI

Suggested endpoint:

```text
GET /api/blender/texture-diagnostics
```

Suggested output:

```json
{
  "activeObject": "ParametricWeave",
  "modifier": "Weave",
  "rootTextureScaleU": 1.0,
  "renderPath": "single_pass_3200",
  "previewResolutionPx": 3200,
  "materials": [
    {
      "slot": 0,
      "name": "FabricStudioMaterial_01_059e1c0937b5",
      "imageWidthPx": 47058,
      "imageHeightPx": 607,
      "blenderImageSource": "TILED",
      "udimTileCount": 3,
      "udimTileWidthPx": 15686,
      "interpolation": "Linear",
      "materialTextureScaleU": 0.0753,
      "effectiveRepeatsPerStrand": 0.21,
      "estimatedSourcePixelsPerStrandU": 9882
    }
  ],
  "pixelBudget": {
    "renderPxPerStrandU": 3200,
    "renderPxPerStrandV": 40,
    "uDownsampleRatio": 3.09,
    "vDownsampleRatio": 30.35,
    "expectedDominantBlurAxis": "V"
  }
}
```

The interesting new field vs the previous draft is `pixelBudget`. That is the
single number that explains why the strand looks blurry compared to a plane
at the same camera distance.

Acceptance:

```text
One API call reports source size, in-Blender image data size, UV mapping
scale, per-strand pixel budget, expected dominant blur axis, and the
preview resolution. Future blur complaints can be diagnosed without
running ad hoc MCP scripts.
```

## Phase D2 - Surface Resolution Context In The UI

Owner: frontend render panel

Files:

```text
frontend/src/components/RenderPanel.tsx
frontend/src/utils/parserApi.ts
```

Steps:

1. Show source texture dimensions.
2. Show Blender texture path:

```text
RGBA single
RGBA UDIM
split RGB/alpha
atlas fallback
```

3. Show render preview size and quality tier.
4. Show pixel-budget summary (e.g. `~3200 px/strand U, ~40 px/strand V`).
5. Show root U scale.

Acceptance:

```text
Users can tell whether they are inspecting source texture, the loaded
Blender image, the UV mapping density, or the final render — without
having to read backend logs.
```

## Phase E - Regression Test Scenarios

These are the scenarios the diagnostic and the render paths must handle
correctly:

1. **One wide RGBA yarn (current case, 47058 x 607)**

   ```text
   path: RGBA UDIM
   stitched tiles == source
   root Texture Scale U == 1.0
   ```

2. **One small RGBA yarn (≤ 16384 wide)**

   ```text
   path: RGBA single
   no atlas
   root Texture Scale U == 1.0
   ```

3. **Split RGB/alpha legacy yarn (no RGBA source)**

   ```text
   path: split direct material or split UDIM
   no unintended cycles_safe downscale unless over cap and no RGBA source
   ```

4. **More yarns than MAX_DIRECT_PREVIEW_MATERIALS = 16**

   ```text
   path: atlas mode
   atlasResampled flag reported
   atlas tile width/height reported
   ```

5. **Preview vs source confusion check**

   ```text
   diagnostic reports both preview render size and source texture size as
   separate fields, never conflated.
   ```

## Open Questions

These are decisions the team should make before committing to Phase C and D
implementations:

1. Should the default `previewQuality` be `draft` or `high` once the high
   tier exists? Draft is fast but always blurry on strands; high is slow
   but matches user expectations.
2. Should the V direction get an explicit cylinder-coverage policy
   (Phase C3), or do we accept that round geometry will always lose V
   detail at preview resolution?
3. Should the `.blend` load process run a sanity script that resets
   high-risk sockets to the checkpoint values, removing the entire class
   of "saved blend drifted from checkpoint" bugs?
4. Should `WEAVE_TEXTURE_INTERPOLATION=Closest` be exposed as an
   inspection-only toggle in the UI so users can verify raw texel content
   on demand?
5. Should atlas fallback preserve exact source pixels by padding instead
   of resizing?

## Quick Reference: What To Do When Someone Says "Texture Is Blurry"

1. Confirm the source rgba.png looks sharp in Blender's Image Editor.
2. Run the plane-vs-strand A/B (Phase A1).
3. Bump render resolution (Phase A2). If the strand improves visibly,
   point the user at the `high` or `seamless` quality tier.
4. Flip texture interpolation to Closest (Phase A3). If visible texels
   appear (aliased), confirm filter is the bottleneck.
5. Check the diagnostic (Phase D1) for `pixelBudget.vDownsampleRatio`. If
   it's much larger than `uDownsampleRatio`, V-wrap on the cylinder is
   the dominant blur source and Phase C is the right answer.
