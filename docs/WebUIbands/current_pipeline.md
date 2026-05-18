# Current band pipeline (2026-05-16)

Two independent passes, two different algorithms.

## Pass 1 — pre-inpaint per-thread (Stage 2)

**Entry point:** `POST /api/multithread/process` in
[backend/app/yarnseamless_routes.py:518-706](../../backend/app/yarnseamless_routes.py#L518-L706).

For each detected thread strip `i`:

1. `dual_alpha_pipeline` produces `thread_{i}_alpha.png` (uint8 L mask).
2. `binary_closing` with a `1 × 100` horizontal structure fills hair-gap
   dropouts so the per-row coverage doesn't fragment ([yarnseamless_routes.py:636-640](../../backend/app/yarnseamless_routes.py#L636-L640)).
3. **Core band**: two parallel detectors in
   [backend/app/yarnseamless/multithread_flow/solid_band.py](../../backend/app/yarnseamless/multithread_flow/solid_band.py):
   - **Approach C** (`approach_c_longest_run`) — per-row longest True run.
     Row qualifies if longest run / image-width > `COVERAGE_THRESHOLD = 0.85`.
     Returns the longest contiguous run of qualifying rows.
   - **Approach D** (`approach_d_combined_smoothed`) — weighted sum
     `0.2·mean + 0.2·max + 0.3·coverage + 0.3·run_frac`, smoothed by a
     5-tap moving average, threshold `SCORE_THRESHOLD = 0.85`.
   - A and B (coverage fraction, morphological opening) are computed in
     `solid_band.py` as CLI exploration approaches but **not** called by the
     web route.
4. **Fiber extents**: `compute_fiber_extents_y` walks the raw (un-closed)
   `alpha_arr` outward from the C-band core. A row qualifies as "in strand"
   when its visible-pixel count is ≥ `max(3, 0.05 × peak_visible_count)`.
   Same walker is used twice — once seeded from C, once from D.
5. Visualisations: `thread_{i}_c_visualization.png` (1-px red lines for core)
   and `thread_{i}_d_visualization.png`.

**Per-thread output schema** (one entry per thread in `summary.json`):

```json
{
  "index": 0,
  "c_band": { "top_y": int, "bottom_y": int, "height": int,
              "fiber_top_y": int, "fiber_bot_y": int },
  "d_band": { ... same shape ... },
  "width_samples": [{ "x", "top_y", "bottom_y", "width_px", "width_mm" }, ...]
}
```

`width_samples` is computed from the C-band only and is 5 evenly-spaced
horizontal probes used by the front-end dimensions readout.

## Where Pass 1 is consumed

| Consumer | Code | Use |
|---|---|---|
| **MTI alignment** | [MultiThreadImageEditor.tsx:163-222](../../frontend/src/components/yarnseamless/MultiThreadImageEditor.tsx#L163-L222) | `chosenBand()` picks C unless its `top_y < 0`, else D. `yOffset_i = round((h_i / 2) − band_centre_i)` clamped to ±300. |
| **MTI review overlay** | same file, `'review'` view | Draws the two red core lines on each leveled thread. |
| **/export `width` field** | [yarnseamless_routes.py:1422-1442](../../backend/app/yarnseamless_routes.py#L1422-L1442) | `unified_top = round(avg(c_band.top_y + frag_y))`, same for bottom. Quantises the assembled core to per-thread C estimates. |
| **MFE solid-band overlay** | [MultiFragmentEditor.tsx:1488-1512](../../frontend/src/components/yarnseamless/MultiFragmentEditor.tsx#L1488-L1512) | Two dashed-red horizontal lines on the assembled preview. |
| **Auto mask rect** | [MultiFragmentEditor.tsx:30-70](../../frontend/src/components/yarnseamless/MultiFragmentEditor.tsx#L30-L70) | `detectThreadBand` (its own per-row content-density walk on the leveled RGB — NOT the alpha) → mask height. Independent of C/D, just confusingly similar. |
| **threads_solid_band metadata** | [yarnseamless_routes.py:1490-1496](../../backend/app/yarnseamless_routes.py#L1490-L1496) | Diagnostic-only copy of per-thread c_band / d_band into `export_metadata.json`. Not pushed to Blender. |

## Pass 2 — post-inpaint on assembled alpha (save-to-library)

**Entry point:** `POST /api/multithread/save-to-library` →
`save_to_library()` in [backend/app/yarnseamless/yarn_library.py:333-555](../../backend/app/yarnseamless/yarn_library.py#L333-L555).

Inputs:

- `export_assembled_rgba.png` (RGB = predicted foreground, A = alpha matte) and
  `export_assembled_alpha.png` (just the L mask).
- `export_metadata.json` — provides `width.top_y_in_export` and
  `width.bottom_y_in_export` (which themselves are Pass-1 averages, see above).

Flow:

1. `compute_fiber_bands(alpha_arr, core_top, core_bot)` —
   [yarn_library.py:61-133](../../backend/app/yarnseamless/yarn_library.py#L61-L133).
   - Counts per-row visible pixels (`alpha > 5`).
   - Picks `floor = max(3, 0.05 × peak_visible_count)`.
   - Walks **outward only** from the provided `core_top` / `core_bot`,
     extending while neighbouring rows are still visible.
   - Returns `bands_px = {core, fiber_top, fiber_bot}` and the normalised
     V-ranges in Blender convention (V=0 bottom).
2. Builds the `metadata.blender` block — texture_world_width_m, Arc 1/Arc 2
   socket scalars, and Phase 3g halo fractions
   (`top_halo_frac = fiber_top_h / total_h`,
    `bot_halo_frac = fiber_bot_h / total_h`).

**Two-pass coupling:** Pass 2's core values are inherited verbatim from Pass 1
via `width.top_y_in_export` / `width.bottom_y_in_export`. So the final yarn
metadata's `core_v_min/max` is only as good as the average of per-thread C/D
approaches. The final assembled alpha is read but only to walk *outside* the
already-fixed core boundaries.

## Why the user wants this reorganised

> "We have to make both the bands processing after we do the inpainting and
> finalise the image."

Concretely:

1. Stop quantising the core to pre-inpaint per-thread C/D averages. The
   assembled alpha is the source of truth — measure both core and fibers on it.
2. Replace the two-algorithm split (C/D for core, visible-pixel walk for
   fibers) with one consistent FWHM density walk that returns all three bands
   from a single pass.
3. Keep Pass 1 only as a lightweight alignment helper — MTI still needs *some*
   per-thread band-centre estimate before the user can review and offset, but
   downstream metadata stops using it.
