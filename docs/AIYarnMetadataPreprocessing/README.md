# AI Yarn Metadata Preprocessing

This folder documents the experimental metadata path for AI-generated yarn
images. The scanned-yarn pipeline remains the production priority and source of
truth. Nothing in this folder changes the scanned-yarn detector, the UI, or the
Blender file.

The immediate goal is to make AI-generated RGBA yarn strips usable enough for
visual experiments by creating better `metadata.json` files before they enter
the existing `yarn_library/<yarn_id>/` contract.

## Why This Exists

The first AI yarn batch had plausible-looking `measurements*.json` files, but
those files did not match how the Blender material system consumes yarn data:

- `c_band` was too narrow or used a different height convention.
- `d_band` often ignored loose/wispy fibers.
- The source images had no trustworthy scanner DPI provenance.
- The images were short and tall compared with scanned yarn strips.
- The standard scanned-yarn FWHM detector made some AI cores too wide, which
  left too little useful V range for Arc 2 fiber detail.

That produced renders where the yarn looked stretched along U and where Arc 2
appeared under-scaled or visually absent.

## Current Experimental Rule

For AI-generated RGBA strips only:

1. Treat the AI JSON as provenance, not as authoritative render metadata.
2. Read source dimensions and alpha directly from the PNG.
3. Detect a stricter high-alpha dense core for Arc 1.
4. Detect a wider low-alpha contiguous support range for Arc 2.
5. Write an explicit `blender.texture_scale_u` so the runtime does not fall
   back to scanned-yarn auto scale.
6. Keep declared DPI only as metadata-scale provenance until a real physical
   calibration is chosen.

The current accepted experimental strategy is:

```text
Arc 1 core:
  largest contiguous row run where row_density(alpha > 224)
  is at least 95% of that density profile's peak.

Arc 2 support:
  contiguous row support around the core where row_density(alpha > 5)
  is at least 2% of image width.

U scale:
  alpha_equivalent_width_px = sum((alpha / 255) ** 1.5) / image_width_px
  core_only_u = core_height_px / (image_height_px * 0.6)
  alpha_mass_u = alpha_equivalent_width_px / (image_height_px * 0.6)
  texture_scale_u = min(max(core_only_u, alpha_mass_u), core_only_u * 2.0)
```

The `0.6` value is the current Arc 1 physical-equivalent span in the
Parametric Weave graph. It is already used throughout the existing yarn
metadata/Blender handoff as `ARC1_V_AROUND_SPAN`.

The current U-scale strategy is:

```text
ai_alpha_mass_equivalent_width_v2
```

The previous dense-core-only U scale is kept in metadata as
`texture_scale_u_previous_core_only` for comparison.

## What Was Created So Far

The first AI batch came from:

```text
/Users/mihirbotle/Desktop/Impetus/3D Fabric/FabricGenerator_ExternalAssets_2026-05-16/ai_yarn
```

Generated library entries:

```text
yarn_library/20260611_100000_a10000  AI Yarn 01
yarn_library/20260611_100001_a10001  AI Yarn 02
yarn_library/20260611_100002_a10002  AI Yarn 03
yarn_library/20260611_100003_a10003  AI Yarn 04
yarn_library/20260611_100004_a10004  AI Yarn 05
yarn_library/20260611_100005_a10005  AI Yarn 06
```

Runtime diagnostics:

```text
runtime/ai_yarn_sanity/ai_yarn_sanity_report.json
runtime/ai_yarn_sanity/ai_yarn_v_band_overlay_after_arc2_fix.png
runtime/ai_yarn_sanity/blender_after_ai_arc2_v_band_fix.png
```

The first follow-up single-image test came from:

```text
/Users/mihirbotle/Desktop/Impetus/3D Fabric/FabricGenerator_ExternalAssets_2026-05-16/001_frayed_alpha_outputs
```

Generated library entry:

```text
yarn_library/20260611_110000_af0001  AI Frayed 001
```

Runtime diagnostics:

```text
runtime/ai_yarn_sanity/001_frayed/detector_summary.json
runtime/ai_yarn_sanity/001_frayed/001_frayed_detector_overlay.png
runtime/ai_yarn_sanity/001_frayed/001_frayed_sanity_report.json
runtime/ai_yarn_sanity/001_frayed/blender_after_001_frayed_push.png
```

External corrected metadata copies:

```text
/Users/mihirbotle/Desktop/Impetus/3D Fabric/FabricGenerator_ExternalAssets_2026-05-16/ai_yarn/corrected_metadata
/Users/mihirbotle/Desktop/Impetus/3D Fabric/FabricGenerator_ExternalAssets_2026-05-16/001_frayed_alpha_outputs/corrected_metadata
```

## Read In This Order

1. [methodology.md](methodology.md) - the algorithm and reasoning.
2. [batch_2026-06-11.md](batch_2026-06-11.md) - what happened on the first AI batch.
3. [batch_2026-06-11_001_frayed.md](batch_2026-06-11_001_frayed.md) - single-image follow-up using the same process.
4. [u_scale_v2_2026-06-11.md](u_scale_v2_2026-06-11.md) - stricter U-scale retry and automation.
5. [metadata_contract.md](metadata_contract.md) - fields written for `metadata.json`.
6. [ingestion_runbook.md](ingestion_runbook.md) - repeatable steps for the next sample batch.
7. [phase_log.md](phase_log.md) - chronological log of the experiment.

## Non-Goals

- Do not change the scanned-yarn metadata path yet.
- Do not change the Blender file for this experiment.
- Do not expose this in the UI until the metadata process is stable.
- Do not treat the AI image DPI as physically trusted unless future input
  generation supplies calibrated physical scale.
