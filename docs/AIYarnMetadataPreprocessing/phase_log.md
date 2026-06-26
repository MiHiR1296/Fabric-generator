# Phase Log

## Phase 0 - Scope And Guardrails

Goal: document and harden a separate metadata path for AI-generated yarn images.

Guardrails:

- scanned yarns remain priority,
- no UI changes yet,
- no Blender file changes,
- all AI metadata edits are experimental,
- every batch must be logged before implementation work.

## Phase 1 - Source Inspection

Inputs:

```text
/Users/mihirbotle/Desktop/Impetus/3D Fabric/FabricGenerator_ExternalAssets_2026-05-16/ai_yarn
```

Findings:

- six RGBA images,
- six measurement JSON files,
- image dimensions in JSON matched PNG dimensions,
- generated band metadata did not match visible alpha/fiber support,
- no trustworthy embedded scanner DPI.

Decision:

- use AI JSON only as provenance,
- use PNG alpha as the metadata source of truth.

## Phase 2 - Initial Library Import

Created six active library entries:

```text
AI Yarn 01..06
```

Created runtime imports so the existing studio and Blender paths could be used
without adding UI code.

Verification:

- backend API listed six AI yarns,
- studio displayed six AI yarn cards,
- Blender accepted a six-material metadata push.

## Phase 3 - Scanned Detector Trial

The first correction used the same `detect_bands(alpha)` method as scanned
yarns. It produced better metadata than the AI JSON, but visual inspection
showed:

- U still looked stretched,
- Arc 1 core could be too wide,
- Arc 2 had too little useful V room for loose AI fibers.

Decision:

- keep scanned detector unchanged for scanned yarns,
- branch AI metadata into a separate detector.

## Phase 4 - Explicit U Scale

Problem:

AI yarns were falling back to scanned-yarn automatic U scale.

Fix:

```text
texture_scale_u = core_v_span / 0.6
```

instead of:

```text
texture_scale_u = core_v_span * 0.6
```

Result:

- Blender socket readback confirmed explicit AI U values,
- U stretch improved,
- Arc 2 V split still needed correction.

## Phase 5 - Arc 2 V-Band Correction

Problem:

For AI images, the FWHM-style core could include too much fuzzy material. This
made Arc 1 dominate the visible strand and made Arc 2 appear small or missing.

Fix:

- Arc 1 core = strict high-alpha dense central run.
- Arc 2 = wider low-alpha contiguous support around that core.

Final strategy:

```text
params.algorithm = "ai_high_alpha_core_full_support_arc2"
blender.v_band_strategy = "ai_dense_core_plus_full_alpha_support_arc2"
```

Verification:

- API served revised bands,
- Blender accepted metadata push,
- direct socket readback matched metadata,
- viewport screenshot captured,
- unit tests passed.

## Phase 6 - Documentation

Created:

```text
docs/AIYarnMetadataPreprocessing/
  README.md
  methodology.md
  metadata_contract.md
  batch_2026-06-11.md
  ingestion_runbook.md
  phase_log.md
```

Purpose:

- preserve exactly what was done,
- define repeatable batch ingestion,
- give future UI implementation a stable target,
- avoid drifting into UI/Blender changes before the metadata process is solid.

## Phase 7 - 001 Frayed Single-Sample Test

Input:

```text
/Users/mihirbotle/Desktop/Impetus/3D Fabric/FabricGenerator_ExternalAssets_2026-05-16/001_frayed_alpha_outputs
```

Finding:

- the source JSON dimensions matched the PNG,
- original `c_band` was `733-787`,
- original `d_band` was only `731-790`,
- visible frayed fiber support extended much farther than the JSON extent.

Generated:

```text
yarn_library/20260611_110000_af0001  AI Frayed 001
runtime/yarn_assets/188e5cd005cb       AI Frayed 001
```

Final AI metadata:

```text
core = 729-791
Arc 2 support = 630-889
texture_scale_u = 0.06727430555555562
```

Validation:

- restarted backend/frontend services,
- confirmed `/api/yarn/library` and `/api/yarn/assets`,
- pushed runtime asset `188e5cd005cb` to Blender,
- direct Blender socket readback matched metadata within float precision,
- captured `runtime/ai_yarn_sanity/001_frayed/blender_after_001_frayed_push.png`.

Decision:

- keep the same AI dense-core/full-support process for the next batch,
- keep writing a batch log before any UI implementation,
- continue leaving scanned-yarn metadata untouched.

## Phase 8 - Stricter AI U Scale And Automation

Problem:

The dense-core U scale still left some AI materials looking slightly stretched
or at risk of squishing when hand-tuned. The value did not account for
semi-transparent visible fiber mass.

Fix:

```text
texture_scale_u_strategy = "ai_alpha_mass_equivalent_width_v2"
```

Rule:

```text
alpha_equivalent_width_px = sum((alpha / 255) ** 1.5) / image_width_px
core_only_u = core_height_px / (image_height_px * 0.6)
alpha_mass_u = alpha_equivalent_width_px / (image_height_px * 0.6)
texture_scale_u = min(max(core_only_u, alpha_mass_u), core_only_u * 2.0)
```

Applied to:

```text
AI Yarn 01..06
AI Frayed 001
```

Runtime asset IDs were preserved:

```text
efcc65258c23 d27089d0f877 c1a3c5b634a3
5c8c2cc4cc00 bdc775fb81e8 3fc9a3e413ef
188e5cd005cb
```

Automation added:

```text
backend/app/ai_yarn_metadata.py
scripts/ai_yarn_metadata.py
POST /api/yarn/ai/import
POST /api/yarn/ai/refresh-u-scale
Step 1 upload view: AI generated yarn block
```

Validation:

```text
cd frontend && npm run build
PYTHONPATH=backend python3 -m unittest backend/tests/test_ai_yarn_metadata.py backend/tests/test_blender_live.py backend/tests/test_yarn_assets.py
```

Result:

```text
frontend build passed
Ran 13 tests
OK
```
