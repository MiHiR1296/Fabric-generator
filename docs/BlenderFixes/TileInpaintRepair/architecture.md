# Architecture - tile inpaint repair

> **Read this if** you are about to implement or test two-pass inpainting on Blender tile exports.

## Problem Statement

The current zero-guard tile export can paste renders next to each other with no image blending:

```text
tile_01.png | tile_02.png
------------+------------
tile_03.png | tile_04.png
```

That removes uncertainty from the stitcher, but a visible cross remains. The cross is not an empty gap. It is the rendered finite fabric edge landing at the tile boundary and then repeating.

Because the seam position is deterministic, it can be masked procedurally.

## Existing Pieces We Can Reuse

| Layer | Existing file | Relevance |
|---|---|---|
| LaMa endpoint | `backend/app/yarnseamless_routes.py` | `POST /api/lama/inpaint` already accepts image + mask and returns an inpainted PNG data URI. |
| LaMa model loader | `backend/app/yarnseamless_routes.py` | `ensure_model_loaded()` loads the shared `big-lama.pt` model once. |
| Vendor seamless reference | `backend/vendor/yarn_pipeline/seamless_converter.py` | Already does a similar horizontal-then-vertical seam inpaint for yarn images. |
| Frontend join workflow | `frontend/src/lib/yarnseamless/multiStitch.ts` | Shows the browser-side pattern: build mask, call LaMa, paste result back. |
| Tile export job | `backend/app/render_jobs.py` | `_stitch_tile_grid(...)` is the natural insertion point after paste-only assembly. |
| Tile repair utility | `backend/app/tile_inpaint_repair.py` | Current controlled test utility: builds masks, runs two-pass LaMa repair, saves intermediates and retile preview. |

The cleanest implementation is backend-side after paste-only assembly. The browser should not need to upload a `2400 x 2400` image back to the server after Blender already produced it.

## Desired Pipeline

```text
POST /api/blender/render-project-tiles
        |
        v
render N Blender tiles
        |
        v
paste-only assembly
        |
        v
two-pass seam repair
        |
        v
runtime/render_jobs/<job_id>/tile_export.png
```

For the first proof, use a single source tile pasted `2 x 2`:

```text
NormalCamera_Ortho2975_Source_1200.png
  -> NormalCamera_Ortho2975_PasteOnly_2x2_1200.png
  -> center-cross inpaint
  -> offset-cross inpaint
  -> repaired tileable output
```

The current test utility can be run directly:

```bash
cd Fabric-generator-tryon/backend
.venv/bin/python -m app.tile_inpaint_repair \
  "/Users/mihirbotle/Desktop/Impetus/3D Fabric/yarnseamless UI/Tiling Generator/NormalCamera_Ortho2975_PasteOnly_2x2_1200.png" \
  "/Users/mihirbotle/Desktop/Impetus/3D Fabric/yarnseamless UI/Tiling Generator/NormalCamera_Ortho2975_InpaintTileable_r48_2x2_1200.png" \
  --debug-dir "/Users/mihirbotle/Desktop/Impetus/3D Fabric/yarnseamless UI/Tiling Generator" \
  --prefix NormalCamera_Ortho2975_Inpaint_r48 \
  --seam-radius 48 \
  --context 640
```

## Two-Pass Method

### Pass A - center cross

Input is the pasted image.

```text
width = 2400
height = 2400
tile_w = 1200
tile_h = 1200

mask vertical band:
  x = tile_w - seam_radius ... tile_w + seam_radius

mask horizontal band:
  y = tile_h - seam_radius ... tile_h + seam_radius
```

Then inpaint the masked cross.

### Pass B - wraparound cross

The outer borders are also future seams. To expose them to LaMa with context on both sides:

```text
rolled = roll(pass_a_output, dx = width / 2, dy = height / 2)
```

Now the old four corners meet in the middle of the image. Generate the same center-cross mask and inpaint again.

Finally:

```text
final = roll(pass_b_output, dx = -width / 2, dy = -height / 2)
```

This is the pass that makes the finished texture more tileable when repeated again.

## Mask Shape

The mask can be procedural. We do not need AI detection for the first test because the seam coordinates are known.

Recommended first parameters:

```text
seam_radius_px: 12 to 48
mask_shape: binary cross
mask_blur: none for LaMa input; optional dilation before threshold
```

The existing endpoint thresholds the mask to binary, so any feathering will become binary unless the backend repair path calls the model directly with custom preprocessing. For the first test, treat masks as binary.

## Crop Or Full-Image Inpaint

Avoid sending the entire `2400 x 2400` image in one call unless quick testing proves it is stable on the current machine.

Preferred repair implementation:

```text
for vertical seam:
  crop a vertical window around x = center
  split along y into overlapping chunks if needed
  inpaint masked pixels
  paste crop back

for horizontal seam:
  crop a horizontal window around y = center
  split along x into overlapping chunks if needed
  inpaint masked pixels
  paste crop back
```

At the cross intersection, the second direction will see pixels already repaired by the first direction. This is acceptable for the first proof. If artifacts appear, repair the central square as a third crop after the two line passes.

## Integration Options

### Option A - call `/api/lama/inpaint`

Pros:

- fastest test path
- uses the exact existing endpoint
- no duplicate model code

Cons:

- requires base64 encode/decode
- awkward from inside a backend render job
- job would HTTP-call its own FastAPI server

Good for manual proof scripts and frontend experiments.

### Option B - backend direct helper

Pros:

- best fit for render jobs
- avoids HTTP loopback and base64 overhead
- can save debug crops/masks/results directly into the render job folder

Cons:

- needs refactoring the LaMa call from route-local code into a helper function
- must avoid circular imports between `render_jobs.py` and `yarnseamless_routes.py`

Best production shape:

```text
backend/app/lama_inpaint.py
  ensure_model_loaded()
  inpaint_pil(image, mask) -> PIL.Image

backend/app/yarnseamless_routes.py
  route wrapper around helper

backend/app/render_jobs.py
  direct helper call for seam repair
```

## Alpha / RGBA Policy

The current LaMa endpoint converts input to RGB. For fabric tile exports this is probably acceptable if the final output is RGB texture only.

If the final tile export must preserve alpha:

- inpaint RGB only
- keep original alpha unchanged if it is fully opaque
- if alpha has visible seam damage, repair alpha separately with a simpler blur/fill or a second inpaint pass

Current diagnostic images are opaque, so RGB-only repair is fine for the first test.

## Output Files For The First Test

Recommended names in `Tiling Generator/`:

```text
NormalCamera_Ortho2975_PasteOnly_2x2_1200.png
NormalCamera_Ortho2975_InpaintPassA_CenterCross.png
NormalCamera_Ortho2975_InpaintPassB_OffsetCross.png
NormalCamera_Ortho2975_InpaintTileable_2x2_1200.png
NormalCamera_Ortho2975_InpaintMask_CenterCross.png
NormalCamera_Ortho2975_InpaintMask_OffsetCross.png
```

For backend job integration, save debug outputs under:

```text
runtime/render_jobs/<job_id>/tile_repair/
  paste_only.png
  pass_a_mask.png
  pass_a_output.png
  pass_b_rolled_input.png
  pass_b_mask.png
  pass_b_rolled_output.png
  final_unrolled.png
```

## Success Criteria

First proof succeeds if:

- center cross is materially reduced
- image still looks like woven fabric, not smeared paint
- final image can be tiled `2 x 2` again without a new hard border
- repair does not visibly destroy the herringbone/draft rhythm around the seam

It does not need to solve every possible material in the first proof. It only needs to prove the architecture on the current gray fabric test.

## What This Does Not Replace

This does not replace graph-level tileability.

Blender-side boundary contracts still matter for a clean procedural solution. Inpaint repair is a pragmatic post-render layer for the current product workflow:

```text
make the visually obvious seam acceptable now
keep future geometry-node edge contracts possible later
```
