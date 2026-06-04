# Texture Resolution Fix

## Purpose

This folder tracks the investigation and fix plan for the mismatch between the
crisp yarn texture visible in Blender's Image Editor and the noticeably blurry
result when that same texture is mapped onto the parametric weave geometry.

The earlier write-up of this folder concluded that the active issue was a 20
percent U-sampling skew from a stale root `Texture Scale U = 0.8`. That drift
is real and worth fixing, but additional user testing has shown the symptom is
larger than a 20 percent skew can produce:

```text
texture in Image Editor:   crisp
texture mapped on a plane: crisp
texture mapped on weave:   hazy / blurry, fine detail missing
```

This document is now structured around that observation. The problem is almost
certainly not in the image on disk and not in how Blender loads it. It is in
what happens between the loaded image and what each rendered pixel actually
samples once the texture rides the curved, undulating, narrow-on-screen yarn
strands.

## Latest Status - 2026-06-04

The current confirmed correction is:

```text
Do not change the final Arc 2/sub-strand scale combiner.
Do not set Sub Texture Scale V to 0.0.
Do not replace the combiner with Texture + is_sub * (Sub - Texture).
```

The deeper Blender docs and checkpoint say the approved Arc 2 state is:

```text
Texture Scale V     = 1.0
Sub Texture Scale V = 1.0
Texture Offset V     = 0.0
Sub Texture Offset V = 0.0
Arc 2 Match Arc 1 V Rate = false
Arc 2 free-flow halo path active
```

The earlier `Sub Texture Scale V = 0.0` test was diagnostic only: it made the
texture look a little clearer by reducing how much vertical source band Arc 2
sampled, but it broke the intended Arc 2 halo interpretation. The later
`Texture + is_sub * (Sub - Texture)` graph rewrite was also rejected because it
downgraded Arc 2 texture mapping.

Current code/docs state:

```text
backend/app/blender_live.py          pins Sub Texture Scale V = 1.0
backend/app/blender_sync.py          sets Sub Texture Scale V = 1.0
backend/app/blender_sync.py          sets preview roughness 1.0, sheen 0.5
backend/app/render_jobs.py           inserts FabricStudioAlphaRemap by default; curve is opt-in
backend/app/render_jobs.py           loads RGBA diffuse as sRGB and RGBA alpha as separate Non-Color image
backend/app/render_jobs.py           sets generated preview roughness 1.0, sheen 0.5
scripts/build_flat_arc1_rebuild.py   rebuild default is Sub Texture Scale V = 1.0
scripts/build_flat_arc1_rebuild.py   final V combiner restored to Texture + is_sub*Sub
live Blender MCP scene               restored to the previous Arc 2 scale wiring
live Blender MCP scene               current FabricStudio materials use separate Non-Color alpha images
```

Validation:

```text
python3 -m unittest backend.tests.test_render_jobs backend.tests.test_blender_live backend.tests.test_blender_sync
Ran 34 tests - OK
```

Remaining work:

```text
1. Preserve the approved Arc 2 free-flow halo graph.
2. Review the live Blender diagnostic setup:
   alpha remap low/high = 0.10 / 0.78, gamma = 1.0.
   Arc 2 deterministic same-strand U is active.
3. Keep the old nearest-surface transfer disabled/muted; it was replaced
   because it caused endpoint shrink / plateau artifacts.
4. Keep geometry-density work as a quality preset, not the first fix.
```

### Phase 1.2 - Alpha Curve Validated Live (2026-06-04)

Item 2 above is now validated against the running scene. A Math POWER node
was inserted on Material 1 only, between `FabricStudioAlphaNode.Alpha` and
`Principled BSDF.Alpha`, then removed. The viewport before/after delta was
larger than any geometry-density, render-resolution, or texture-interpolation
change tested in earlier phases. Full trace, sockets read, and visual results
are in [phase_log.md Phase 1.2](phase_log.md).

Phase 1.4 refined this from a gamma-only curve into a two-step alpha cleanup.
Phase 1.5 then reduced the default strength after visual review showed the
first remap made Arc2 too noisy/opaque:

```text
FabricStudioAlphaRemap:
  From Min = 0.10
  From Max = 0.78
  Clamp / smoother-step range

FabricStudioAlphaCurve:
  POWER gamma = 1.0 by default, so the curve step is skipped unless opted in
```

Production patch landed in `backend/app/render_jobs.py` inside
`ensure_texture_preview_material`, gated by `WEAVE_ALPHA_REMAP_ENABLED` and
`WEAVE_ALPHA_REMAP_LOW`, `WEAVE_ALPHA_REMAP_HIGH`, and
`WEAVE_ALPHA_CURVE_GAMMA`. See
[action_plan.md Phase A-2](action_plan.md) for the exact diff and acceptance
criteria.

The alpha-curve fix is independent of the Arc 2 V combiner choice. It
operates on the per-pixel alpha value after sampling and does not change
which V rows are sampled. Whichever V graph the team standardises on
(current free-flow halo or the historical formulas), the alpha boost is
additive and reversible.

Phase details and render outputs are logged in [phase_log.md](phase_log.md),
especially Phase 0.9, Phase 1.0, Phase 1.1, Phase 1.2, and Phase 1.3. The older
geometry-first, `Sub Texture Scale V = 0.0`, and absolute-sub-scale formula
sections are preserved as investigation history but are superseded by this
status.

## 2026-06-03 Diagnostic Validation Update

See [diagnostic_validation.md](diagnostic_validation.md) for the complete
validation pass. The key corrections are:

1. The asset pipeline is clean. All scanned runtime assets match metadata,
   and tiled RGBA assets stitch back to the source with `maxdiff = 0`.
2. `/api/blender/push-project-bandmeta` already restores root
   `Texture Scale U` to `1.0` for `Parametric Weave knotty`.
3. `/api/blender/push-bandmeta` does not repair stale root
   `Texture Scale U`, so pinning `("Texture Scale U", 1.0)` there is still
   correct hygiene.
4. The live graph does not expose `Ply Resolution`; that earlier proposal is
   legacy graph vocabulary and should not be implemented for the current
   graph.
5. The valid V-density lever is `PW Profile - Mesh Line Count` plus `Offset`
   together. `31 / 1/30` gives 31 V samples; `61 / 1/60` gives 61 V samples.
6. `Thread Subdivisions` is a valid U-density lever. It doubles mesh size
   when doubled, so it should be owned by quality presets rather than pinned
   into every metadata-only push.

## Confirmed Facts (Do Not Re-Investigate)

These were established in `phase_log.md` Phase 0 and have not changed:

1. The active source image is full resolution.

   ```text
   runtime/yarn_assets/059e1c0937b5/rgba.png  47058 x 607
   ```

2. The UDIM tiles Blender uses reconstruct the source pixel-for-pixel.

   ```text
   stitched 3 tiles = 47058 x 607
   max channel diff vs source = 0
   ```

3. The active material reads from the RGBA UDIM image, not the atlas, not the
   Cycles-safe downscale.

   ```text
   FabricStudioDiffuseNode  source=TILED  3 tiles  interpolation=Linear  extension=CLIP
   Phase 0 historical readback: FabricStudioAlphaNode used the same image
   Phase 1.7 current default:  FabricStudioAlphaNode uses a separate Non-Color image datablock
   ```

4. The saved blend has root `Texture Scale U = 0.8` against a checkpoint of
   `1.0`. This is a real drift (worth fixing), but moves the effective U
   sampling by only ~20 percent.

5. The frontend never resizes pixels before sending to Blender. It sends file
   paths.

Conclusion: the source file, the on-disk tiles, the in-Blender image data, and
the live UV-mapping math are all carrying the full original resolution. The
blur appears somewhere between "the image is loaded full res" and "the pixel
is shaded".

## Viewport-Side Symptom (Phase 0.6 Update)

After the initial pixel-budget analysis was written, the user confirmed:

```text
The texture is blurry in the viewport itself, not only in rendered output.
The plane-vs-strand A/B in the same viewport shows: plane sharp, strand
blurry.
```

This was important at the time because it changed which mechanisms could be
the cause. Phase 0.8 and Phase 0.9 later tested this geometry lead directly;
the geometry renders improved sampling density but did not solve the haze.
The current lead is the sub-strand V mapping bug plus alpha softness.

```text
- Cycles MIP filter math (the previous lead hypothesis) cannot explain a
  viewport-only symptom. The viewport uses the GPU's hardware sampler with
  EEVEE / Solid / Material-Preview shading, not Cycles' offline filter.
- The blur is therefore happening before or instead of Cycles' MIP step.
- The most plausible mechanism left is UV interpolation across a too-coarse
  strand mesh, NOT texture filter selection.
```

### The Geometry Lead

The first geometry draft used the older `Ply Resolution` vocabulary from
legacy `Weave From Draft` paths. The validation pass corrected that for the
current live graph:

```text
current graph: Parametric Weave knotty
U density:     Thread Subdivisions = 8
V density:     PW Profile - Mesh Line Count = 31
V domain:      PW Profile - Mesh Line Offset = 1/30
```

The current V profile is therefore 31 samples around the active profile, not
a `Ply Resolution = 5` pentagon. That is better than the earlier assumption,
but still coarse enough to plausibly blur a narrow, curved, fiber-detailed
strand in the viewport.

At a 3200 px render with 80 warp threads:

```text
strand screen width:      ~40 px
visible front face:       ~20 px
profile V samples:        31 around the profile
texture V coordinate:     linearly interpolated between profile samples
```

The GPU sampler does its job — it correctly samples the texture at the
interpolated UV — but the *UV itself* is linearly interpolated between a
tiny number of vertices, so the texture lookup positions are quantized.
High-V detail in the source image is destroyed by this interpolation step,
not by the texture filter.

A flat plane in the same viewport has dense quad subdivision (Blender
defaults to a fine subdivision; even a default plane is 1 quad per pixel
when subdivided once or twice), so its UVs vary smoothly with screen
position. Same image, completely different sampling positions.

### Why This Fits The Observation

```text
1. Image Editor: shows raw image. No UV. Sharp.      -> consistent
2. Plane in viewport: dense UVs, fine sampling.      -> sharp (consistent)
3. Strand in viewport: narrow curved profile with
   31 profile samples and sparse U resampling.        -> blurry (consistent)
4. Increase profile V steps and Thread Subdivisions. -> predicts sharper detail
```

This was tested in the geometry render matrix. It remains useful for final
quality presets, but it was not the primary cause of the user-visible haze.

### What This Does NOT Eliminate

```text
- Cycles MIP downsampling at final render still applies on top of the
  geometry fix. Even with infinite mesh density, the V-wrap pixel budget
  caps how much detail can fit on a 40 px wide strand.
- The Socket_97 = 0.8 drift is still real and still worth fixing.
- The atlas resampling risk on the >16 yarn material path is still real.
```

So the geometry fix moves the viewport from "blurry haze" to "sharp at
preview resolution", and the render-side fixes from the rest of this doc
move the final render from "lower-than-source MIP" to "matched-to-budget".
Both are needed for the full chain to behave; the geometry fix is just
where the largest visible win lives.

## The Real Question

Why is the same RGBA image sharp on a plane but blurry on the weave?

That comparison rules out:

- File downscale (same file)
- Loading-path issues (same loader)
- Cycles single-image cap (same image; UDIM bypass is identical)
- Viewport GL_MAX_TEXTURE_SIZE (same image; would affect plane too)
- Source rgba.png having missing detail (visible in Image Editor)
- Texture node interpolation alone (would affect plane too)

It points at one of three things, possibly all:

A. **Strand mesh subdivision is too coarse** (historical lead after Phase 0.6):
   the current graph has `Thread Subdivisions = 8` and 31 profile V samples.
   UV is linearly interpolated between those samples, so high-frequency
   texture detail can be weakened at the UV lookup, before the texture filter
   gets a chance to help. This is the only one of the three that can explain
   a viewport-only symptom. Phase 0.8 showed this is not sufficient as the
   primary fix.

D. **Sub-strand V over-sampling diagnostic** (Phase 0.9, retracted as final fix in Phase 1.2):
   `Sub Texture Scale V = 1.0` was being added on top of
   `Texture Scale V = 1.0`, doubling the sub-strand V sample span and mixing
   blank/low-alpha rows into the yarn. Reducing that span improved sharpness,
   but changing the final sub-scale combiner damaged Arc 2. The next valid
   place to work is the existing Arc 2 Top/Core/Bot / HaloFlow V mapping.

E. **Alpha opacity softness** (confirmed in Phase 0.9):
   the input contains the fine fiber/twist detail, but soft translucent alpha
   suppresses it after filtering on curved strands. A hard threshold proves
   the detail is present but is too visually harsh, so the next fix should be
   a tunable alpha curve.

B. **Sampling-rate limit on the curved strand**: each strand occupies very few
   screen pixels at preview resolution, so the texture filter is forced to
   sample from a heavily reduced MIP level even though every source texel is
   present in memory. Applies most strongly in Cycles renders.

C. **UV / surface-curvature interaction**: even with an arc-length unwrap that
   prevents geometric stretch, the curved tube has high screen-space
   derivatives, especially in V (around the cylinder). Those derivatives drive
   MIP selection and on a curved strand they are dramatically larger than on a
   flat plane. Applies most strongly in Cycles renders.

For a viewport-only blur, (A) is the lead. (B) and (C) become the lead once
(A) is fixed and we are talking about the final rendered output.

The next sections walk through the math behind these and the discriminating
tests that tell us which one dominates.

## The Pixel-Budget Math

Numbers from `phase_log.md` Phase 0, applied to the current preview render.

### U direction (along the strand)

```text
texture width (source):                  47058 px
effective repeats per strand (now):       0.168
effective repeats per strand (fixed U):   0.210
preview render width:                     3200 px
visible strand U length on screen:       ~3200 px (strand runs across the frame)
```

So one strand displays roughly `0.168 * 47058 = 7906` source pixels stretched
across `~3200` screen pixels. That is a `2.47x` downsample on U. Trilinear
filtering picks roughly MIP level 1, sampling from a half-resolution copy.
Some detail is lost but the U direction is not the worst offender.

If the Socket_97 fix is applied, the per-strand source pixel budget rises to
`9882 / 3200 = 3.09x` downsample — still in MIP 1 territory. Even with the U
fix, U-direction blur reduction is incremental, not transformative.

### V direction (around the strand cylinder)

```text
texture height (source):                  607 px
warp_threads = weft_threads:              80
strand screen width at 3200 render:      ~40 px wide (3200 / 80)
visible cylinder half:                   ~20 px
```

The V axis wraps the cylinder. From the camera, only roughly half the cylinder
is visible (the front). So 607 source pixels in V are mapped to roughly 20
screen pixels of visible front face.

```text
V downsample ratio:  ~30x
likely MIP level:    ~5
effective V detail:  ~19 px out of 607
```

This is the dominant blur source on the strand. The image data is there, but
the texture filter has no choice — at 30x undersampling, anti-aliasing
literally requires reading from a near-bottom MIP.

A plane that fills the frame has roughly `3200 / 1 = 3200` screen pixels per
texture pass in both U and V. Downsample ratios are tiny, MIP 0 wins, and the
image looks like the source.

This is the most parsimonious explanation for "sharp on plane, blurry on
strand".

### Conclusion From The Math

Restoring `Texture Scale U = 1.0` moves U by 20 percent. It does not change
the V direction at all. If the user-reported blur is dominated by V wrap, the
Socket_97 fix is correct hygiene but visually almost invisible.

The dominant levers are:

1. More screen pixels per strand (higher render resolution, or tile render
   mode, or closer camera).
2. Lower V undersampling (larger strand thickness on screen, or thinner
   visible region of the strand, or different aspect of V texture detail).
3. Cycles texture filter behavior (interpolation, MIP, extension).

## Hypotheses And Discriminating Tests

Each hypothesis below comes with a test that produces a different observable.
The point is to stop arguing about which hypothesis is "right" and instead run
two or three short experiments that pin it down.

### H1. Screen pixels per strand are the limit

Claim:

```text
At 3200 x 3200 render with ~80 warp threads, each strand is too narrow on
screen to allow any high-frequency texture detail through, regardless of how
many texels the source has.
```

Test:

```text
1. Render once at 3200 (baseline).
2. Render the same scene at 8192 via WEAVE_PREVIEW_RENDER_RESOLUTION=8192.
3. Render the same scene with tile_render_mode (already exists), which
   renders fabric in 4 tiles each up to 8192 — effective sampling density
   roughly 2.5x higher than baseline.
```

Expected if H1 is the cause:

```text
Detail returns roughly proportional to render-pixels-per-strand.
The 8192 render looks visibly sharper than 3200.
The tile render looks visibly sharper than 8192 single render.
```

Expected if H1 is not the cause:

```text
8192 and tile render look the same as 3200 in terms of fine detail per
strand.
```

### H2. V-wrap MIP selection on the cylinder

Claim:

```text
Even with full pixel budget, wrapping a 607 px tall texture around a narrow
visible cylinder face forces a high MIP level for V sampling.
```

Test:

```text
1. Keep render resolution at 3200.
2. Set the Image Texture node interpolation to Closest in the parametric
   weave material (raw texel readback, no MIP filtering blur).
3. Render and compare to Linear baseline.
```

Expected if H2 is the cause:

```text
Closest output is much sharper (and visibly aliased / dithery on the V
direction), confirming the filter is hiding visible texels.
```

Note: aliased Closest output is diagnostic only. Production output stays on
Linear or Cubic; the test just proves the filter, not the file, is removing
detail.

### H3. Surface curvature spikes derivatives

Claim:

```text
The undulation amplitude (Amplitude socket = 0.005, Arc 1 V Padding = 0.008)
and the arc unwrap leave the geometry curved in 3D world space. Even with
arc-length parameterization, screen-space dU/dx and dV/dx still spike at
grazing-angle bands across the strand. Those spikes drive local MIP
selection up.
```

Test:

```text
1. In Blender, swap the ParametricWeave material onto a temporary flat
   subdivided plane sized to match a single strand at the same camera
   distance.
2. Render at the same 3200 resolution.
3. Compare strand-region detail vs the curved-strand render.
```

Expected if H3 is the cause:

```text
Flat surrogate plane shows substantially more detail than the curved strand
at the same pixel coverage. Difference cannot be explained by H1 alone.
```

### H4. Geometry density / curve subdivision is too low

Claim:

```text
If the geometry-nodes-generated strand mesh has too few subdivisions, UVs
between vertices interpolate linearly and high-frequency texture detail
falls on flat interpolated regions instead of curved sampling. The visual
result reads as smeared detail.
```

Test:

```text
Inspect the ParametricWeave evaluated mesh density. The relevant socket in
the modifier is the resolution / subdivision parameter for warp and weft
curves. Verify both are at recommended values from the checkpoint.
```

Expected if H4 is the cause:

```text
Increasing strand subdivision visibly sharpens texture detail with no
change to source or filter.
```

### H5. Socket_97 U-scale drift (the original hypothesis)

Claim:

```text
Root Texture Scale U = 0.8 reduces U sampling density by 20 percent vs the
documented checkpoint of 1.0.
```

Test:

```text
Restore Socket_97 to 1.0, re-render at 3200, compare.
```

Expected if H5 alone is the cause:

```text
A roughly 20 percent improvement in U-direction visible detail. Nothing
about V-direction blur changes.
```

In practice this fix is necessary hygiene but is unlikely to make the
"completely downsized" symptom go away on its own.

## Why The Earlier Plan Is Necessary But Not Sufficient

The earlier action plan correctly identified:

1. The Socket_97 drift in the saved blend.
2. The risk of the atlas fallback resizing inputs.
3. The risk of bandmeta-only live pushes leaving stale sockets in place.
4. The need for a diagnostic endpoint.

All four items remain valuable. None of them explain "sharp on plane, blurry
on strand at the same render resolution and same texture file". That symptom
is consistent with sampling-bandwidth limits on the curved geometry, not with
file or load corruption.

So this revised plan keeps the earlier items as defensive hygiene and adds
new phases focused on actually moving the visible needle.

## Files To Watch

```text
backend/app/yarn_assets.py
  MAX_CYCLES_TEXTURE_DIMENSION = 16384
  ensure_cycles_tiled_rgba_texture_set(...)   -- UDIM split, no downscale
  _ensure_cycles_safe_texture(...)            -- only used when no RGBA path
backend/app/render_jobs.py
  build_headless_render_script(...)           -- single-pass preview
  _run_tile_render_job(...)                   -- high-detail tiled path
  DEFAULT_PREVIEW_RENDER_RESOLUTION = 3200
backend/app/blender_live.py
  PINNED_FOOTGUN_SOCKETS                      -- pins neutral V defaults,
                                                 including Sub Texture Scale V = 1.0
backend/app/blender_sync.py
  Texture Scale U handling and Sub Texture Scale V setup default
Codex_ParametricWeave.blend                   -- saved root U currently 0.8
docs/CHECKPOINT_2026-05-19.md                 -- expects root U = 1.0
```

## Acceptance Criteria

The fix is accepted when the following are all true:

1. The plane-vs-strand A/B at the same render resolution shows the strand
   matching or near-matching the plane in visible texture detail.
2. The strand region at preview resolution shows clearly resolved yarn texture
   features, not a uniform haze.
3. The Socket_97 drift is fixed in the saved blend and pinned in the live
   bandmeta push, so the U-scale skew cannot silently return.
4. The render job payload reports which sampling path was used
   (single-pass / tile-render / atlas-fallback) and at what render resolution,
   so future complaints of blur can be diagnosed in one call.
5. Documentation distinguishes between:

   ```text
   source texture resolution
   in-Blender image data resolution
   UV mapping density
   screen pixels per strand
   MIP / filter level chosen per shading pixel
   final render resolution
   ```
