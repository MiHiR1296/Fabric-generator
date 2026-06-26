# Ingestion Runbook For Future AI Batches

Use this runbook when a new batch of AI-generated yarn samples arrives.

The purpose is to solidify the process before adding UI support. Until then,
the process should be repeatable, logged, and conservative.

## Preconditions

Inputs should include one RGBA image per yarn. Optional AI measurement JSON may
be included, but it is treated as provenance only.

Expected input examples:

```text
some_batch/
  tinted_rgba.png
  measurements.json
  tinted_rgba (1).png
  measurements (1).json
```

If the input naming changes, record the pairing rules in the batch log.

## Step 1: Inventory Files

Record:

- source folder,
- image filenames,
- measurement filenames,
- PNG dimensions,
- embedded DPI if present,
- whether the AI JSON image size matches the PNG.

Do not proceed if a measurement file claims a different image size unless the
reason is understood and recorded.

## Step 2: Generate Diagnostic Overlay

For each image, create an overlay showing:

- original AI core from JSON, if present,
- scanned-detector core, if tested,
- final AI dense core,
- final AI Arc 2 support.

Use a light background under the RGBA so sparse alpha fibers are visible.

The overlay is not optional. It is the fastest way to catch a bad Arc 1/Arc 2
split.

## Step 3: Compute AI Bands

Current experimental detector:

```text
CORE_ALPHA_THRESHOLD = 224
CORE_DENSITY_FRACTION = 0.95
ARC2_ALPHA_THRESHOLD = 5
ARC2_ROW_DENSITY = 0.02
ARC1_V_AROUND_SPAN = 0.6
```

Dense core:

```text
row_density = mean(alpha > 224, axis=x)
core = largest_run(row_density >= max(row_density) * 0.95)
```

Arc 2:

```text
support = mean(alpha > 5, axis=x) >= 0.02
outer_top = walk upward from core_top while support is true
outer_bot = walk downward from core_bottom while support is true
```

U scale:

```text
alpha_equivalent_width_px = sum((alpha / 255) ** 1.5) / image_width_px
core_only_u = core_height_px / (image_height_px * 0.6)
alpha_mass_u = alpha_equivalent_width_px / (image_height_px * 0.6)
texture_scale_u = min(max(core_only_u, alpha_mass_u), core_only_u * 2.0)
```

## Step 4: Write Metadata

For each yarn:

1. Create `yarn_library/<yarn_id>/`.
2. Copy source RGBA to `rgba.png`.
3. Create `input_thumb.jpg`.
4. Write `metadata.json`.
5. Update `yarn_library/index.json`.
6. Copy the corrected metadata to the source batch's `corrected_metadata/`
   folder for external review.

Every AI metadata file must include:

```text
source.kind = "ai_generated_rgba"
params.algorithm = "ai_high_alpha_core_full_support_arc2"
blender.v_band_strategy = "ai_dense_core_plus_full_alpha_support_arc2"
blender.texture_scale_u_strategy = "ai_alpha_mass_equivalent_width_v2"
ai_sanity_check
```

## Step 5: Import Into Runtime Assets

Import each library yarn through the existing backend import function or API so
runtime assets get:

- `runtime/yarn_assets/<asset_id>/rgba.png`,
- PBR maps,
- `asset.json`,
- `renderTextureMode`.

For small AI images, `renderTextureMode` will usually be `rgba_single`.

This is fine. A single image material uses a simpler node graph than UDIM
scanned yarns, but the important scale values live in the Geometry Nodes
modifier sockets.

## Step 6: Restart Backend If Needed

The backend caches runtime assets in memory. If files were edited directly on
disk, restart services before API validation:

```text
scripts/dev_services.sh restart
```

## Step 7: Validate API

Check the running backend:

```text
curl -fsS http://127.0.0.1:8000/api/yarn/assets
```

Confirm for each AI yarn:

- label is present,
- status is `ready`,
- `bandMeta.width` matches final core,
- `bandMeta.bands_px` matches report,
- `bandMeta.blender.texture_scale_u` is explicit,
- `bandMeta.blender.v_band_strategy` is the AI strategy.

## Step 8: Push To Blender

Push the batch assets:

```text
POST /api/blender/push-bandmeta
{
  "yarnAssetIds": ["..."],
  "target_object_name": "ParametricWeave",
  "modifier_name": "Weave"
}
```

Then read back:

```text
Material N Texture Scale U
Material N Arc 1 V Min
Material N Arc 1 V Max
Material N Arc 2 V Min
Material N Arc 2 V Max
```

The readback must match the metadata values within Blender float precision.

## Step 9: Visual Review

Capture:

- studio screenshot showing AI yarn cards,
- Blender viewport screenshot after metadata push,
- optional render-preview output if a draft/pattern is selected.

Review for:

- Arc 1 core alignment,
- Arc 2 fiber visibility,
- U stretching,
- overly thick/thin visual scale,
- loss of alpha detail.

## Step 10: Log The Batch

Create a new file:

```text
docs/AIYarnMetadataPreprocessing/batch_YYYY-MM-DD.md
```

Include:

- source path,
- source file table,
- final library/runtime IDs,
- original vs final band table,
- U scale table,
- validation commands,
- artifact paths,
- open questions.

## Acceptance Criteria

A batch is acceptable for AI experimentation when:

- metadata does not rely on AI JSON bands,
- PNG dimensions match metadata dimensions,
- Arc 1 core is visually centered on the dense body,
- Arc 2 extents include visible loose fibers,
- U scale is explicit and non-auto,
- API reports ready runtime assets,
- Blender socket readback matches metadata,
- tests still pass.

## Stop Conditions

Stop and inspect manually if:

- alpha is missing or fully opaque,
- rows contain multiple disconnected yarn bodies,
- source image contains a woven fabric instead of a single yarn strip,
- core detector locks onto a stray dense fiber instead of the main body,
- Arc 2 support reaches the full image height due to noise,
- generated image has no coherent left-to-right yarn direction.
