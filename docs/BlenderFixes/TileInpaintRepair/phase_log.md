# Phase log - tile inpaint repair

> **Read this if** you want to know what has been investigated, tested, changed, or deliberately left untouched for the two-pass inpaint seam repair path. Append-only. Each phase should record Motivation / Diagnosis / Plan or Fix / Verification / What was NOT done.

---

## Phase 0 - start two-pass seam-repair test track

**Date**: 2026-05-26

### Motivation

The zero-guard paste-only tile creator proved that the visible cross is not caused by alpha gaps, overlap blending, or Python averaging. It is a rendered edge/rim inside the tile image. The user proposed using the existing yarn inpainting workflow to repair the cross after the renders are placed next to each other.

The user also correctly identified that one inpaint pass is not enough for a true tileable output. A complete texture needs:

1. repair the center cross created by the initial `2 x 2` paste
2. offset the image so the four outer corners meet at the center
3. repair that wraparound cross
4. offset the repaired image back

### Diagnosis

Current repo inspection found reusable infrastructure:

- `backend/app/yarnseamless_routes.py`
  - `GET /api/lama/health`
  - `POST /api/lama/inpaint`
  - lazy `big-lama.pt` loading through `ensure_model_loaded()`
- `frontend/src/lib/yarnseamless/multiStitch.ts`
  - existing image + mask + LaMa join workflow
- `backend/vendor/yarn_pipeline/seamless_converter.py`
  - older reference implementation that tiles an image, masks seams, and inpaints horizontal/vertical directions
- `backend/app/render_jobs.py`
  - current tile export job and `_stitch_tile_grid(...)` paste-only insertion point

The current LaMa health endpoint is reachable:

```text
GET http://127.0.0.1:8000/api/lama/health
-> {"status":"ok","device":"not-loaded","model":"big-lama","model_path":null}
```

The model file exists locally:

```text
Fabric-generator-tryon/backend/vendor/yarn_pipeline/big-lama.pt
/Users/mihirbotle/Desktop/Impetus/3D Fabric/yarnseamless UI/big-lama.pt
```

### Plan

Create a focused docs track before implementation:

```text
docs/BlenderFixes/TileInpaintRepair/
  README.md
  architecture.md
  phase_log.md
  lessons.md
```

First test should use the current best scratch tile:

```text
/Users/mihirbotle/Desktop/Impetus/3D Fabric/yarnseamless UI/Tiling Generator/
  NormalCamera_Ortho2975_PasteOnly_2x2_1200.png
```

Proposed first proof script:

```text
input paste-only image
build binary center-cross mask
run LaMa inpaint on center cross
roll result by half width and half height
build the same center-cross mask
run LaMa inpaint on offset cross
roll back
save final repaired tile
save masks and intermediate images
```

### Verification

- New docs folder created.
- Architecture records the two-pass center/offset repair design.
- Phase log records current baseline, known files, and the intended first proof.
- No implementation was run in this phase.

### What was NOT done

- Did not change backend code.
- Did not change frontend code.
- Did not edit or save the Blender file.
- Did not run the LaMa model on the tile image yet.
- Did not replace the existing tile export output with an inpainted result.

### Lesson

For texture tileability, the offset pass is not optional. Repairing only the center cross makes the preview look better, but the finished image can still show a seam when the whole repaired texture is tiled again.

---

## Phase 1 - backend utility and first r32/r48 outputs

**Date**: 2026-05-26

### Motivation

The user asked to set up the inpaint seam-repair test and produce outputs in the `Tiling Generator` folder. The first proof needed to be reusable enough to become backend job code later, but still controlled enough to evaluate before changing the frontend tile button.

### Diagnosis

The current `2.975` paste-only image is a `2400 x 2400` RGBA file:

```text
NormalCamera_Ortho2975_PasteOnly_2x2_1200.png
```

The seam coordinates are known:

```text
center seam x = 1200
center seam y = 1200
```

The existing LaMa model path resolves and runs on MPS:

```text
[lama] Using MPS (Apple GPU)
[lama] Loading big-lama from .../big-lama.pt
```

### Fix

Added a backend utility:

```text
backend/app/tile_inpaint_repair.py
```

It provides:

- procedural center-cross masks
- wrap-offset image rolling
- paste-only retile previews
- two-pass repair:
  - Pass A: inpaint center cross
  - Pass B: roll by half width/height, inpaint wraparound cross, roll back
- CLI entrypoint for controlled experiments
- debug outputs for masks, crops, pass outputs, and final retile preview

Added lightweight tests:

```text
backend/tests/test_tile_inpaint_repair.py
```

### Outputs

Created two repair variants:

```text
NormalCamera_Ortho2975_InpaintTileable_r32_2x2_1200.png
NormalCamera_Ortho2975_InpaintTileable_r48_2x2_1200.png
```

Created retile previews:

```text
NormalCamera_Ortho2975_Inpaint_r32_final_retiled_2x2.png
NormalCamera_Ortho2975_Inpaint_r48_final_retiled_2x2.png
```

Created comparison sheets:

```text
NormalCamera_Ortho2975_InpaintComparison_CenterCross.png
NormalCamera_Ortho2975_InpaintComparison_RetiledWrap.png
```

The `r48` variant uses a wider mask and removes the seam more strongly. The `r32` variant repaints less but leaves more seam evidence.

Outer-edge strip comparison:

```text
original paste-only:
  top/bottom avg 19.14
  left/right avg 15.12

r32:
  top/bottom avg 13.77
  left/right avg 15.05

r48:
  top/bottom avg 13.25
  left/right avg 12.66
```

### Verification

Ran:

```bash
cd Fabric-generator-tryon/backend
.venv/bin/python -m unittest tests.test_tile_inpaint_repair
```

Result:

```text
Ran 4 tests in 0.001s
OK
```

Manual visual inspection:

- center cross is substantially reduced in `r48`
- retiled preview no longer shows the hard plus-shaped border
- `r48` is visibly softer in the repaired band than the original weave
- `r32` preserves more detail but leaves more seam

### What was NOT done

- Did not wire inpaint repair into `/api/blender/render-project-tiles` yet.
- Did not change frontend controls.
- Did not change tile count defaults.
- Did not edit or save the Blender file.
- Did not optimize for `3 x 3` or `4 x 3` seam grids yet.

### Lesson

The two-pass method works as a repair concept on the current gray fabric sample. The next question is product policy: whether to make the frontend tile export default to a `2 x 2` repair flow, or generalize the mask system to repair all internal seams for `3 x 3` and `4 x 3` outputs.

---

## Phase 2 - tighter r12 mask test

**Date**: 2026-05-26

### Motivation

The first `r32` and `r48` tests repaired the seam, but the user correctly noted that the cross mask was too wide. A tighter pass should repaint less of the weave and preserve more of the rendered thread detail.

### Diagnosis

The same two-pass center/offset method can use a much smaller mask:

```text
seam_radius_px = 12
context_px = 640
```

This still gives LaMa a broad context crop around the seam, but only asks it to replace a narrow 24 px band.

### Fix

Ran the existing utility with `--seam-radius 12`:

```bash
cd Fabric-generator-tryon/backend
.venv/bin/python -m app.tile_inpaint_repair \
  "/Users/mihirbotle/Desktop/Impetus/3D Fabric/yarnseamless UI/Tiling Generator/NormalCamera_Ortho2975_PasteOnly_2x2_1200.png" \
  "/Users/mihirbotle/Desktop/Impetus/3D Fabric/yarnseamless UI/Tiling Generator/NormalCamera_Ortho2975_InpaintTileable_r12_2x2_1200.png" \
  --debug-dir "/Users/mihirbotle/Desktop/Impetus/3D Fabric/yarnseamless UI/Tiling Generator" \
  --prefix NormalCamera_Ortho2975_Inpaint_r12 \
  --seam-radius 12 \
  --context 640
```

### Outputs

Created:

```text
NormalCamera_Ortho2975_InpaintTileable_r12_2x2_1200.png
NormalCamera_Ortho2975_Inpaint_r12_final_retiled_2x2.png
NormalCamera_Ortho2975_Inpaint_r12_summary.json
NormalCamera_Ortho2975_InpaintComparison_CenterCross_r12_r32_r48.png
NormalCamera_Ortho2975_InpaintComparison_RetiledWrap_r12_r32_r48.png
```

Outer-edge strip comparison:

```text
original paste-only:
  top/bottom avg 19.14
  left/right avg 15.12

r12:
  top/bottom avg 15.14
  left/right avg 16.69

r32:
  top/bottom avg 13.77
  left/right avg 15.05

r48:
  top/bottom avg 13.25
  left/right avg 12.66
```

### Verification

Manual visual inspection:

- `r12` preserves more original weave detail than `r32` or `r48`
- center cross is less harsh than the original
- seam removal is not as complete as `r48`
- left/right metric is slightly worse than the original, so this setting is not a universal win

### What was NOT done

- Did not change the repair utility.
- Did not wire any mask width into the frontend.
- Did not pick a final default.
- Did not edit or save Blender.

### Lesson

The useful mask width is a visual tradeoff, not a monotonic metric. `r12` looks more natural and preserves detail; `r48` is stronger at seam removal. The likely best value may be between them, such as `r16`, `r20`, or `r24`.

---

## Phase 3 - r12 color-match test

**Date**: 2026-05-26

### Motivation

The user noticed that the `r12` inpainted seam was not only repairing geometry detail; it was also shifting color, making the seam read like a darker yarn. This is especially visible with a tight mask because LaMa can fill the narrow band with plausible thread texture that does not match the surrounding rendered color.

### Diagnosis

The color shift is a post-inpaint artifact, not a Blender paste gap. The `r12` mask is narrow enough to preserve detail, but the model still invents RGB values inside the masked band. If those values skew darker than the nearby fabric, the seam becomes a dark thread line even when the hard cross shape is reduced.

### Fix

Added an internal color-matching pass to `backend/app/tile_inpaint_repair.py`:

- keep the original LaMa result as the structure source
- build a local ring around the masked pixels
- match the inpainted masked pixels toward the mean/std color of the surrounding original crop
- expose it as CLI-only/internal tuning with `--color-match`

This is not intended as a frontend user control. It is a quality knob for the tile repair pipeline.

Ran:

```bash
cd Fabric-generator-tryon/backend
.venv/bin/python -m app.tile_inpaint_repair \
  "/Users/mihirbotle/Desktop/Impetus/3D Fabric/yarnseamless UI/Tiling Generator/NormalCamera_Ortho2975_PasteOnly_2x2_1200.png" \
  "/Users/mihirbotle/Desktop/Impetus/3D Fabric/yarnseamless UI/Tiling Generator/NormalCamera_Ortho2975_InpaintTileable_r12_color05_2x2_1200.png" \
  --debug-dir "/Users/mihirbotle/Desktop/Impetus/3D Fabric/yarnseamless UI/Tiling Generator" \
  --prefix NormalCamera_Ortho2975_Inpaint_r12_color05 \
  --seam-radius 12 \
  --context 640 \
  --color-match 0.5
```

Also tested full-strength color matching:

```text
--color-match 1.0
```

### Outputs

Created:

```text
NormalCamera_Ortho2975_InpaintTileable_r12_color05_2x2_1200.png
NormalCamera_Ortho2975_Inpaint_r12_color05_final_retiled_2x2.png
NormalCamera_Ortho2975_Inpaint_r12_color05_summary.json
NormalCamera_Ortho2975_InpaintTileable_r12_color_2x2_1200.png
NormalCamera_Ortho2975_Inpaint_r12_color_final_retiled_2x2.png
NormalCamera_Ortho2975_Inpaint_r12_color_summary.json
NormalCamera_Ortho2975_InpaintComparison_r12_color_sweep.png
NormalCamera_Ortho2975_InpaintComparison_r12_color_sweep_retiled.png
```

### Verification

Manual visual inspection:

- raw `r12` preserves detail but can read as a dark yarn/seam line
- `r12 + color-match 0.5` reduces the dark-yarn feel while staying close to the raw inpaint structure
- `r12 + color-match 1.0` pushes color harder toward the neighboring yarn, which can help the dark line but may overcorrect local contrast
- the structural seam is still faintly present at `r12`; color matching fixes color drift, not every seam shape

Ran:

```bash
cd Fabric-generator-tryon/backend
.venv/bin/python -m unittest tests.test_tile_inpaint_repair
```

Result:

```text
Ran 5 tests
OK
```

### What was NOT done

- Did not make color matching a frontend control.
- Did not pick the final default for production.
- Did not edit or save Blender.
- Did not wire this experimental option into the tile render endpoint yet.

### Lesson

For tight masks, color consistency and structure consistency are separate problems. `r12` can preserve weave geometry while still creating a visible color seam. A local color-match pass is useful, but the best default may be a combination of slightly wider mask radius and moderate color matching rather than maximum strength.

---

## Phase 4 - r6 color-match test and 2x2 output correction

**Date**: 2026-05-26

### Motivation

The user requested an even tighter mask:

```text
seam_radius_px = 6
color_match_strength = 1.0
```

The user also pointed out that the `final_retiled` preview was misleading. The repaired artifact is already a `2 x 2` assembly. Repeating it again creates a `4 x 4` source-tile layout, which is useful only as a diagnostic and should not be treated as the current working output.

### Fix

Ran `r6` with full color matching and no repeated preview:

```bash
cd Fabric-generator-tryon/backend
.venv/bin/python -m app.tile_inpaint_repair \
  "/Users/mihirbotle/Desktop/Impetus/3D Fabric/yarnseamless UI/Tiling Generator/NormalCamera_Ortho2975_PasteOnly_2x2_1200.png" \
  "/Users/mihirbotle/Desktop/Impetus/3D Fabric/yarnseamless UI/Tiling Generator/NormalCamera_Ortho2975_InpaintTileable_r6_color_2x2_1200.png" \
  --debug-dir "/Users/mihirbotle/Desktop/Impetus/3D Fabric/yarnseamless UI/Tiling Generator" \
  --prefix NormalCamera_Ortho2975_Inpaint_r6_color \
  --seam-radius 6 \
  --context 640 \
  --color-match 1.0 \
  --no-retile-preview
```

Updated `backend/app/tile_inpaint_repair.py` so repeated previews are opt-in:

```text
--retile-preview
```

When enabled, the filename now uses:

```text
*_diagnostic_repeated_2x2.png
```

This avoids implying that a repeated `4 x 4` diagnostic is the final `2 x 2` tile output.

### Outputs

Created:

```text
NormalCamera_Ortho2975_InpaintTileable_r6_color_2x2_1200.png
NormalCamera_Ortho2975_Inpaint_r6_color_summary.json
NormalCamera_Ortho2975_InpaintComparison_2x2_r6_color.png
```

The summary records:

```json
"seam_radius_px": 6,
"color_match_strength": 1.0,
"final_retile_preview_path": null
```

### Verification

Manual visual inspection:

- `r6 color 1.0` preserves the most original image area
- the cross structure is still very visible because the repaired band is only 12 px wide
- this is tighter than the actual seam artifact, so it is probably too narrow for a final setting
- the output remains the real `2 x 2` working image, with no generated `4 x 4` repeat preview

### What was NOT done

- Did not delete older `final_retiled` diagnostic files from previous tests.
- Did not make `r6` the production default.
- Did not change the frontend.
- Did not edit or save Blender.

### Lesson

`r6` is useful as a lower-bound test, but it is likely too narrow for this fabric seam. Also, preview naming matters: repeating an already assembled `2 x 2` repair image creates a `4 x 4` diagnostic, not a new final output.

---

## Phase 5 - production tile export wiring

**Date**: 2026-05-26

### Motivation

The user selected `r12 + color-match 1.0` as the closest result and asked to finalize the flow in the backend and frontend. The user also called out that the repair step creates many intermediate images and JSON files during experiments, but an end user should only receive the final output image.

### Fix

Backend:

- `render-project-tiles` now normalizes to the finalized calibrated flow:
  - `tileCount = 4`
  - `columns = 2`
  - `rows = 2`
  - `tileResolution = 1200`
  - `guardThreads = 0`
  - `variationStrength = 0`
- after Blender renders the four source tiles, the backend stitches them to a temporary raw image
- it then runs `repair_tile_with_two_pass_inpaint(...)` with:
  - `seam_radius_px = 12`
  - `context_px = 640`
  - `color_match_strength = 1.2`
  - `save_debug_outputs = False`
  - `save_retile_preview = False`
- normal tile jobs clean up intermediate tile renders, tile scripts, atlas files, raw stitched image, logs, and debug files
- set `WEAVE_KEEP_TILE_DEBUG=1` to keep intermediates for debugging

Frontend:

- removed the tile render-count selector
- the user now gets one tile button for the calibrated 2x2 repaired texture
- resolution, guard, variation, and inpaint tuning remain internal

### Verification

Added tests for:

- quiet inpaint repair mode saving only the final output
- backend tile option normalization to the 2x2 production flow
- existing mask/roll/paste and stitch helpers

### What was NOT done

- Did not delete older scratch files from previous manual experiments in `Tiling Generator/`.
- Did not make `r12` or color strength user-facing controls.
- Did not edit or save Blender.

### Lesson

Once a seam-repair setting becomes the product default, it should not behave like a research script. Debug artifacts must be opt-in, and the frontend should expose a single end-user action that returns the final texture.

---

## Phase 6 - slight color-match overdrive

**Date**: 2026-05-26

### Motivation

The user observed that `r12 + color-match 1.0` was closest, but the cross still read slightly dark. They suggested trying a little more color correction, around `1.2`.

### Fix

Changed the color-match clamp from `0..1` to `0..1.5`, so values above `1.0` intentionally over-drive the local color match instead of being silently treated as `1.0`.

Production default changed to:

```text
seam_radius_px = 12
color_match_strength = 1.2
```

### Output

Manual sample:

```text
NormalCamera_Ortho2975_InpaintTileable_r12_color12_2x2_1200.png
NormalCamera_Ortho2975_InpaintComparison_2x2_r12_color12.png
```

### Lesson

`1.0` means exact local color match. A slightly higher value can be useful when the model still produces a dark seam after exact matching, but this should stay a small overdrive rather than a user-facing control.

---

## Phase 7 - frontend source-tile artifact view

**Date**: 2026-05-26

### Motivation

The user noted that the issue is not just color; the repaired area also needs to be clearer. To know where clarity is being lost, the frontend should show the four Blender renders used to build the final `2 x 2` repaired output.

### Fix

Backend:

- each tile job now copies the four source renders into `source_tiles/`
- job snapshots include `tileSourceImageUrls`
- new route serves each source render:

```text
GET /api/blender/render-jobs/{job_id}/tile-sources/{source_index}
```

- normal cleanup keeps:
  - final repaired output
  - four source renders
- normal cleanup still removes:
  - tile render scripts
  - tile stdout/stderr logs
  - raw stitched image
  - atlas/temp debug folders

Frontend:

- tile preview now shows the final repaired texture first
- below it, the four Blender source renders appear as a compact diagnostic strip

### Lesson

Clarity needs to be diagnosed before tuning. If the four source renders are sharp but the final output is soft, the inpaint/detail pass needs tuning. If the four source renders are already soft, the problem is in Blender render/camera/material settings rather than the seam repair step.
