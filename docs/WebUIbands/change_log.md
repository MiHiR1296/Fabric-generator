# WebUI bands — change log

Append new entries **at the top**. One entry per edit. Date format = YYYY-MM-DD.

---

## 2026-05-29 — Connected-core per-thread bands + sub-degree rotation

The yarn scan processing repair is documented in full at
[../YarnScanProcessing/phase_log.md](../YarnScanProcessing/phase_log.md).
Band-specific summary:

- `alpha_pipeline.level_and_crop` no longer skips sub-degree tilt. Default
  `min_rotate_deg` changed from `1.0` to `0.0`, with a tiny `1e-6` guard so
  exactly zero does not resample.
- `dual_alpha_pipeline.apply_level_transform` now mirrors the first scan's
  rotate/crop with `BICUBIC` resampling for two-background processing.
- `thread_segmentation.detect_band_quality` now uses
  `connected_core_peak_band_v1` for per-thread `c_band` / `d_band`.
- The new core detector seeds from high-alpha connected yarn body, scores rows
  by longest connected run + count + mean alpha, and selects the peak-relative
  core run around the strongest row.
- Raw FWHM output is still preserved in `band_quality.raw_fwhm_core` for
  debugging, but it no longer owns the red review bracket when disconnected
  haze/background rows are stronger than the real core.

Regression tests added:

- `test_level_and_crop_rotates_subdegree_tilt`
- `test_band_quality_uses_connected_thick_core_not_disconnected_haze_band`

Sample reprocess:

- source session: `20260529_035408_350`
- new session: `20260529_130625_379`
- corrected tilts: `0.561`, `0.120`, `0.488` degrees
- new bands: `197-216`, `241-258`, `272-287`
- QA sheet: `/tmp/rotation_band_fix_old_vs_new.jpg`

## 2026-05-16 — Phase A + B + C landed

Single FWHM detector now owns post-inpaint bands end-to-end. Pre-inpaint
per-thread `solid_band` C/D still drives MTI alignment only.

**Phase A — new module: [backend/app/yarnseamless/band_detect.py](../../backend/app/yarnseamless/band_detect.py).**
- `detect_bands(alpha_u8, core_frac=0.5, fiber_frac=0.02, smooth_taps=7)`.
- Algorithm: per-row coverage at α > 0.5 → 7-tap box smooth → largest run ≥
  50% of peak = core → outward walk while ≥ 2% of peak = fibers.
- Returns the same shape (`bands_px`, `bands_v_norm`, `thickness_px`, `params`)
  that the legacy `compute_fiber_bands` produced, so downstream
  `metadata.blender` builders are drop-in.

**Phase B — `yarn_library.save_to_library`** now calls `detect_bands(alpha_arr)`
instead of `compute_fiber_bands(alpha_arr, core_top, core_bot)`. Stopped
reading `width.top_y_in_export` / `bottom_y_in_export` from `export_metadata.json`
— the assembled alpha is the source of truth and the detector finds the core
itself. The legacy `compute_fiber_bands` function was removed entirely (no
fallback path).

**Phase C — `/api/multifragment/export` (the export-final route in
yarnseamless_routes.py)** now runs `detect_bands` on `export_assembled_alpha.png`
to compute `width.top_y_in_export` / `bottom_y_in_export`. The pre-inpaint
loop that averaged Pass-1 per-thread `c_band` tops/bots is gone. **Hard-fails
with HTTP 409** if `export_assembled_alpha.png` doesn't exist — the user must
run Regenerate Alpha before Export. No fallback.

**Behavioural shift to watch for:**
- Halos will be measured tighter than before. Old `compute_fiber_bands` used
  `alpha > 5` (any visible pixel), new `detect_bands` uses `alpha > 0.5`
  (≥ ~50% opaque) for the density signal, then walks while density ≥ 2%
  of peak. Result: only the denser part of the hair counts as halo. If
  rendered fabric ends up with too-thin halos, lower `fiber_frac` (e.g.
  0.005) or rework the detector to use a two-threshold scheme (high for
  core density, low for fiber visibility).
- `threads_solid_band` block in `export_metadata.json` is unchanged but is
  now strictly diagnostic — it no longer influences anything downstream.

**Files touched:**
- new: `backend/app/yarnseamless/band_detect.py`
- edit: `backend/app/yarnseamless/yarn_library.py` (added import, removed
  `compute_fiber_bands`, swapped call in `save_to_library`)
- edit: `backend/app/yarnseamless_routes.py` (added import, rewired width
  computation in the export route, added 409 guard)
- edit: `backend/app/yarnseamless/multithread_flow/solid_band.py` (refreshed
  stale comment that pointed at the removed function)

## 2026-05-16 — doc folder seeded

- Created `docs/WebUIbands/` with:
  - `README.md` — entry point + TL;DR of current vs target.
  - `current_pipeline.md` — two-pass map (pre-inpaint per-thread C/D in
    `solid_band.py`; post-inpaint visible-pixel fiber walk in
    `yarn_library.compute_fiber_bands`).
  - `yarnseamless_reference.md` — the FWHM density-walk port target from
    `YarnSeamless/yarnseamless/band_segmenter.py:detect_bands`.
  - `target_pipeline.md` — three-phase cut-over plan (add detector, switch
    save-to-library, switch export-final). Pass 1 stays only as MTI alignment
    helper.

No code changes yet. Next: Phase A — drop in `backend/app/yarnseamless/band_detect.py`.
