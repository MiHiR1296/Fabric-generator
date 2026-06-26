# Verification Matrix

| Area | Check |
|---|---|
| Backend | `python3 -m unittest backend.tests.test_hook_sync` |
| Backend | `python3 -m unittest backend.tests.test_blender_sync backend.tests.test_render_jobs` |
| Frontend | `npm run test:unit` from `frontend/` |
| Frontend | `npm run build` from `frontend/` |
| Blender | `HookDraft_Live` exists and has `stitch_code`, `chain_id`, `chain_u_index`, `chain_material_id` |
| Blender | `ProceduralHook > Hook > Procedural Hook` remains the active target |
| Blender | `ProceduralHook` stores `hook_visual_mode=generated_data_driven_production` |
| Blender | `_hook_build_spec_json` exists and reports `visualReference.role=calibration_reference_only` |
| Blender | evaluated `ProceduralHook` has nonzero generated geometry and `uv_scaled` |
| Blender | dense hook preset emits connected strip components, not one component per active cell |
| Blender | sparse smoke preset keeps holes and emits material indices 0/1 |
| Blender | hook material sockets accept Material 1..16 metadata |
| Regression | `ParametricWeave` still points at `Parametric Weave knotty.001` |

## 2026-06-18 Verification Notes

- `/api/blender/sync-hook-project` verified with:
  - 7 x 37 dense pattern: rows/columns read back correctly.
  - 15 x 21 sparse pattern: empty cells preserved in `HookDraft_Live`.
  - 15 x 21 two-material pattern: material slots `[0, 1]` reported.
  - final 15 x 21 standard baseline: generated mesh output source `Inputs`.
- Final live readback:
  - `driverCount = 0`.
  - `HookDraft_Live` faces: `315`.
  - `HookDraft_Live` attributes include `stitch_code`, `chain_id`,
    `chain_u_index`, `chain_material_id`, `course_id`, and `wale_id`.
  - Evaluated `ProceduralHook`: `194370` vertices / `194040` faces.
  - Pre-V2 look sockets: `Row=15`, `Columns=21`,
    `Texture Scale U=1.06`, `Texture Scale V=0.93`,
    `Texture Offset V=-0.44`.
- Screenshots captured:
  - `/tmp/hook_sync_project_7x37_fixed.png`
  - `/tmp/hook_sparse_15x21.png`
  - `/tmp/hook_two_material_15x21.png`
  - `/tmp/hook_final_generated_standard_15x21.png`

## 2026-06-18 Look-Dev Update

- New default frontend hook preset: `Balanced Interlock`, 16 x 18, generated
  starter pattern with 252 active cells and 36 empty/open cells.
- Live Blender readback after sync:
  - `driverCount = 0`.
  - `HookDraft_Live` faces: `288`.
  - Evaluated `ProceduralHook`: `156376` vertices / `155232` faces.
  - Look sockets: `Row=16`, `Columns=18`, `Leg Width=0.62`,
    `Loop Height=1.86`, `Handle Scale=0.72`, `Half Tube Radius=0.19`,
    `Texture Scale U=0.92`, `Texture Scale V=0.78`,
    `Texture Offset V=-0.36`.
- Screenshot captured:
  - `/tmp/hook_balanced_interlock_16x18.png`

## 2026-06-18 Live Modifier Control Fix

- Manual Blender socket smoke test after `/sync-hook` installed live controls:
  - `Loop Height=3.25` and `Half Tube Radius=0.32` updated the generated live
    pattern settings and changed evaluated mesh Z span from `0.145` to `0.214`.
  - `Row=7` and `Columns=11` rebuilt `HookDraft_Live` to `77` faces and the
    evaluated hook mesh to `41624` vertices / `41272` faces.
  - Restored baseline: `Row=16`, `Columns=18`, `Leg Width=0.62`,
    `Loop Height=1.86`, `Handle Scale=0.72`, `Half Tube Radius=0.19`.
  - Final readback: live-control timer registered, `driverCount=0`,
    evaluated hook mesh `156376` vertices / `155232` faces.
- Screenshot captured:
  - `/tmp/hook_live_controls_restored_16x18.png`

## 2026-06-18 Visual Archetype Repair

- Reference screenshot from the old pre-V2 object:
  - `/tmp/hook_pre_v2_reference.png`
- Replaced the generated construction from row-wise V strips to
  `interlocking_vertical_wales`.
- Final dense classic wale readback:
  - `Row=15`, `Columns=21`.
  - `Leg Width=0.95`, `Loop Height=2.05`, `Handle Scale=0.72`,
    `Half Tube Radius=0.18`, `Curve Resolution=12`, `Tube Resolution=13`.
  - `HookDraft_Live` faces: `315`.
  - Evaluated `ProceduralHook`: `295113` vertices / `294840` faces.
  - Components: `21`, matching one continuous wale per column for the dense
    15 x 21 baseline.
- Manual Blender socket smoke test after the visual repair:
  - Shape controls changed live settings and rebuilt the mesh to
    `136269` vertices / `136080` faces.
  - `Row=8`, `Columns=12` rebuilt `HookDraft_Live` to `96` faces and the
    hook mesh to `41580` vertices / `41472` faces.
- Screenshots captured:
  - `/tmp/hook_classic_wale_pass1.png`
  - `/tmp/hook_classic_wale_pass2_wider.png`
  - `/tmp/hook_classic_wale_final_15x21.png`

## 2026-06-20 Native Visual Lock

- Superseded by the intent-pipeline correction below. These notes are retained
  as visual-reference history only.
- Current visible hook object is a fresh native Pre-V2 `ProceduralHook` object.
- Object/modifier names remain stable:
  - `ProceduralHook`
  - modifier `Hook`
  - node group `Procedural Hook`, marked with
    `hook_native_visual_baseline=True`
- Patched backend hook sync behavior:
  - Native Pre-V2 visual groups keep their own Geometry Nodes output.
  - Generated bridge mesh output is used only for non-native hook groups.
  - Native mode installs a lightweight refresh timer so modifier socket changes
    trigger a viewport/evaluated-geometry refresh without replacing the native
    Geometry Nodes output.
- Visual checks:
  - Current bad generated bridge screenshot:
    `/tmp/hook_shape_current_20260620.png`
  - Fresh native baseline:
    `/tmp/hook_fresh_native_baseline.png`
  - Deliberately changed controls after modifier refresh:
    `/tmp/hook_native_control_changed_after_refresh.png`
  - Restored desired baseline:
    `/tmp/hook_final_restored_desired_shape_20260620.png`
  - Final locked saved state:
    `/tmp/hook_final_native_pre_v2_locked_20260620.png`
  - Native refresh timer changed-control proof:
    `/tmp/hook_native_refresh_timer_changed_20260620.png`
  - Final locked state after refresh timer restore:
    `/tmp/hook_final_native_pre_v2_locked_after_refresh_20260620.png`
- Final desired baseline values:
  - `Row=15`, `Columns=21`, `Pattern Scale=0.07`
  - `Leg Width=0.67`, `Loop Height=2.2`, `Handle Scale=0.6`
  - `Leg Z Offset=0.218`, `Half Tube Radius=0.25`
  - `Curve Resolution=7`, `Tube Resolution=11`
  - `Texture Scale U=1.06`, `Texture Scale V=0.93`,
    `Texture Offset V=-0.44`, `Texture Side Flatten=0`

## 2026-06-20 Intent Pipeline Correction

- Production rule:
  - Pre-V2 is a calibration reference only.
  - `/sync-hook` and `/sync-hook-project` must return a `buildSpec`.
  - The active `ProceduralHook` output must be generated from the pattern data.
- Required live readback:
  - `hook_visual_mode = generated_data_driven_production`
  - `hook_visual_reference_role = pre_v2_calibration_reference_only`
  - `_hook_build_spec_json.visualReference.role = calibration_reference_only`
  - `HookDraft_Live` rows/columns match the frontend pattern.
  - evaluated `ProceduralHook` has nonzero mesh attributes including
    `uv_scaled`, `chain_id`, `chain_u_index`, and `material_id`.
