# Action Plan

## Goal

Make Blender preview output easier to trust and easier to debug by aligning
docs, backend material generation, live metadata pushes, and future quality
controls with the live `.blend`.

The plan deliberately separates low-risk backend fixes from future `.blend`
socket work. The current pass does not rewrite Arc 2 V mapping or mutate the
geometry-node graph.

## Phase 0 - Freeze Live Truth

Status: done for this pass.

Actions:

- Verify Blender MCP on `127.0.0.1:9876`.
- Read `ParametricWeave > Weave > Parametric Weave knotty` sockets.
- Read active FabricStudio material nodes.
- Record missing sockets and material mismatch in [current_state.md](current_state.md).

Reasoning:

The older docs contain real historical value, but they conflict on alpha
remap, Arc 2 U transfer, and pending cleanup. We need one current truth before
any implementation work.

Acceptance:

- `blender_status` succeeds.
- `Texture Scale U = 1.0`.
- deterministic Arc 2 same-strand U is active.
- alpha remap absence is explicitly recorded before patching.

## Phase 1 - Direct Diffuse Alpha In Generated RGBA Materials

Status: supersedes the earlier alpha-remap default after 2026-06-05 visual
review.

Actions:

- Keep RGBA direct preview materials on one diffuse/RGBA image node.
- Link `FabricStudioDiffuseNode.Alpha` directly to `Principled BSDF.Alpha` by default.
- Do not create `RGBA_Alpha` image nodes for RGBA single or RGBA UDIM assets.
- Keep split diffuse/alpha assets on their separate alpha image fallback path.
- Keep `FabricStudioAlphaRemap` and `FabricStudioAlphaCurve` as opt-in A/B tools only.

Defaults:

```text
WEAVE_ALPHA_REMAP_ENABLED = false
WEAVE_ALPHA_REMAP_LOW     = 0.10
WEAVE_ALPHA_REMAP_HIGH    = 0.78
WEAVE_ALPHA_CURVE_GAMMA   = 1.0
```

Reasoning:

The Blender scene now reads better when the generated material uses the alpha
channel already embedded in the diffuse/RGBA scan, with no Map Range boost. The
separate alpha texture and default remap path were useful diagnostics, but they
can drift away from the artist-approved RGBA readback.

Acceptance:

- Generated RGBA script path links `diffuse_tex.outputs['Alpha']` to shader alpha.
- Generated RGBA script path does not create `RGBA_Alpha` / `RGBA_Alpha_UDIM`.
- Env override `WEAVE_ALPHA_REMAP_ENABLED=1` still routes the selected alpha
  output through `FabricStudioAlphaRemap`.
- Split diffuse/alpha fallback assets continue to use `FabricStudioAlphaNode`.

## Phase 2 - Pin Root Texture Scale U In Metadata-Only Live Push

Status: implemented and unit-verified.

Actions:

- Add `("Texture Scale U", 1.0)` to `PINNED_FOOTGUN_SOCKETS` in
  `backend/app/blender_live.py`.
- Add unit coverage in `backend/tests/test_blender_live.py`.

Reasoning:

Full project setup already resets root U for `Parametric Weave knotty`.
Metadata-only `push-bandmeta` did not, so a manual stale value such as `0.8`
could survive exactly where the user expects the push to clean up Blender.

Acceptance:

- Metadata-only pushes pin root `Texture Scale U` to `1.0`.
- Existing V-footgun pins remain unchanged.

## Phase 3 - Add Quality-Controlled Geometry Density

Status: planned, not implemented in this pass.

Actions:

- Add a `Profile V Steps` socket to `Parametric Weave knotty`.
- Drive both profile mesh count and offset together:

```text
PW Profile - Mesh Line Count  = Profile V Steps
PW Profile - Mesh Line Offset = 1 / (Profile V Steps - 1)
```

- Add render quality tiers after visual/performance validation:

```text
draft    -> Profile V Steps 31, Thread Subdivisions 8,  render 3200
high     -> Profile V Steps 61, Thread Subdivisions 16, render 6400
seamless -> Profile V Steps 61, Thread Subdivisions 24, tile render
```

Reasoning:

V-profile density is a real quality lever, but Count-only edits break the
profile domain. It must be controlled as a paired Count/Offset setting and
owned by render quality, not metadata-only pushes.

Acceptance:

- `Profile V Steps = 61` produces 61 unique profile samples.
- Profile domain remains `0..1`.
- The UI/backend can select quality without manual node edits.

## Phase 4 - Preserve Arc 2 Look While Reducing Haze

Status: planned after rejected exact metadata endpoint-fit attempt.

Actions:

- Keep the current Arc 2 free-flow halo graph:

```text
Texture Scale V = 1.0
Sub Texture Scale V = 1.0
PW Band - Arc2 Top.To Min <- PW HaloFlow - Top Outer Free V
PW Band - Arc2 Bot.To Max <- PW HaloFlow - Bot Outer Free V
Math.015 = Texture Scale V + is_sub * Sub Texture Scale V
```

- Treat the metadata silhouette as a diagnostic boundary, not the production
  Arc 2 UV target.
- Next experiments must use crop renders and visual review, not only numeric
  range matching.
- Candidate safer knobs:

```text
alpha_haze_cleanup -> tune alpha remap low/high for Arc 2 haze rows
halo_soft_crop      -> trim only near-zero-alpha rows in material, not UV geometry
debug_heatmaps      -> render uv_scaled.y and alpha overlays before changing graph
```

Reasoning:

The live diagnostic showed current Arc 2 samples about `45.2%` of its vertex
weight outside the metadata Arc 2 silhouette, mostly in low-alpha rows. A
temporary `Sub Texture Scale V = 0.0` narrows final Arc 2 V, but that knob has
prior visual rejection history and should not become the production fix. The
exact metadata endpoint-fit attempt also matched the numbers but damaged the
Arc 2 look and was rejected. The next pass should keep the free-flow shape and
reduce low-alpha haze/material wash without collapsing the halo.

Acceptance:

- Live graph remains on the free-flow Arc 2 path after metadata pushes.
- Crop renders preserve Arc 2 look and feel.
- Any haze reduction is measured against source alpha rows and visual review.
- No mode changes Arc 2 same-strand U.

## Phase 5 - Add Direct Texture World Width Socket

Status: planned, not implemented in this pass.

Actions:

- Add `Texture World Width BU` to the `.blend`.
- Consume existing `bandMeta.blender.texture_world_width_m`.
- Keep old `Image Width Px / Scanner Pixels Per BU` path until parity passes.
- Remove the old divide only after readback confirms identical U stride.

Reasoning:

The producer already computes physical texture width. The live graph still
derives the same value from two older sockets. The new socket reduces wire
surface and removes one avoidable pixel-level intermediate.

Acceptance:

- New direct socket matches old divide within float tolerance.
- U stride values match for current asset `47058 / 62992.16015625`.
- Data contract and Blender live/socket docs are updated.

## Phase 6 - Add Diagnostics And Visibility

Status: planned.

Actions:

- Add `GET /api/blender/texture-diagnostics`.
- Report MCP connection, socket values, active texture mode, alpha-remap state,
  PBR state, atlas fallback, quality tier, and pixel-budget estimates.
- Log atlas fallback in render job metadata.

Reasoning:

Future blur reports should not require ad hoc MCP scripts. One diagnostics
surface should show whether the problem is source pixels, loaded image path,
UV scale, alpha handling, PBR state, atlas fallback, or final render budget.

Acceptance:

- One API call reports the active material/render path.
- Atlas fallback cannot happen silently.
- UI can show enough context for a non-Blender user to understand the preview.
