# Lessons — seamless tile mode

> **Read this before** changing the graph or backend to support tileable fabric output.

Each lesson has the Rule, Why, and Concrete example shape used by the main BlenderFixes docs.

---

## Rule 1 — A tileable render needs a boundary contract, not only more random variations.

**Why**: Rendering 4, 9, or 12 slightly different 1k swatches can reduce visible repetition inside the image, but it does not guarantee that any two neighboring edges match. Unconstrained variation creates more possible seams.

**Concrete example**: `Seed`, `Pattern Noise X/Y`, and `UV Random U` can change the look of a swatch. In tile mode, those values must either be periodic at the crop boundary or locked by an edge profile.

---

## Rule 2 — Guard bands should be generated as fabric, not painted on as pixels.

**Why**: The render edge includes shadows, halos, antialiasing, and strand crossings. If geometry stops exactly at the crop, the edge can look cut even when the center pattern repeats.

**Concrete example**: In guarded mode, generate extra warp ends and weft picks outside the final tile, render the larger region, then crop the center tile. The current diagnostic mode uses zero guard and a direct 1200 x 1200 tile render.

---

## Rule 3 — Mesh continuity is necessary but not sufficient.

**Why**: The geometry can wrap perfectly while the texture still jumps. Scanned yarn sampling depends on `u_along`, per-strand U stride, material texture width, and the original yarn strip's own seamlessness.

**Concrete example**: Left and right edge strands may align spatially, but a mismatch in `Material N Texture Scale U`, `U Stride Per Warp End`, or `UV Random U` can still create a visible fiber jump.

---

## Rule 4 — First prove one simple tile before designing a tile set.

**Why**: If one repeat-aligned, low-randomness tile cannot tile cleanly, a larger edge-compatible system will only hide the root issue temporarily.

**Concrete example**: Start with one repeat-aligned crop from an orthographic render. Tile it 3 x 3. Only after that passes should edge types and interior variation be added.

---

## Rule 5 — Normal swatch rendering must remain the baseline.

**Why**: The existing preview workflow is artist-approved and documented. Tile mode is an export variant, not a replacement for the current render preview.

**Concrete example**: Future backend flags should choose between `render-project` normal behavior and a tile export path. Tile-only assumptions should not silently change `make backend-dev-live` preview renders.

---

## Rule 6 — Build the export workflow before pretending the edge contract is solved.

**Why**: The user-facing workflow needs orchestration first: start a backend job, render multiple Blender outputs, stitch them, show the final image. That can be useful for visual review even before graph-level edge profiles exist.

**Concrete example**: Phase 1 added `/api/blender/render-project-tiles`, guarded overscan renders, overlap blending, and frontend preview. It deliberately does not claim Wang-tile compatibility yet.

---

## Rule 7 — Do not expose backend seam-management knobs as material controls.

**Why**: Guard width, tile resolution, and stitching variation are implementation tuning values. Presenting them beside creative material controls makes the UI feel more technical while not helping the user choose a look.

**Concrete example**: Phase 2 hides `guardThreads`, `tileResolution`, and `variationStrength = 0.25`. Phase 7 moved to zero-guard paste-only mode, and Phase 8 sets the hidden tile resolution to 1200.

---

## Rule 8 — Tile output and swatch preview are mutually exclusive display modes.

**Why**: Showing two preview boxes makes one of them look broken or empty. The render step should have one main output area, with the active action deciding which result is visible.

**Concrete example**: Phase 2 adds `activePreviewMode`. Clicking `Render Preview` shows the Blender swatch; clicking `Build Tile Texture` shows the stitched tile texture.
