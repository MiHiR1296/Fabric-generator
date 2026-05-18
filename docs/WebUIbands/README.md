# WebUI bands — yarn band detection in Fabric-generator-tryon

How the wizard finds the top/bottom extents of the **yarn thread core** and the
two **fiber halos** (the fuzzy hair above and below the core). This is the
input that drives:

- **MTI alignment** — fragments are centred so each thread's band-centre lands at
  the same row.
- **Width measurement** — width_mm / width_px shown in the dimensions card.
- **Per-yarn Arc 1 / Arc 2 V-band sockets in Blender** — `metadata.blender.core_v_min/max`,
  `fiber_top_v_min`, `fiber_bot_v_max`, plus the Phase 3g halo fractions.

Read in this order:

| # | file | what it covers |
|---|---|---|
| 1 | [current_pipeline.md](current_pipeline.md) | Today's flow: 4 approaches A/B/C/D in `solid_band.py` running PRE-inpaint per-thread, plus `compute_fiber_bands` walking POST-inpaint on assembled alpha. Code paths and call-graph. |
| 2 | [target_pipeline.md](target_pipeline.md) | Where we're going: single FWHM-density `detect_bands` running POST-inpaint on the assembled alpha. Pre-inpaint per-thread bands only kept for alignment and per-thread review overlays. |
| 3 | [yarnseamless_reference.md](yarnseamless_reference.md) | The reference implementation from `/Users/mihirbotle/Desktop/Impetus/3D Fabric/YarnSeamless/yarnseamless/band_segmenter.py:detect_bands` — what makes it better than the current C/D approaches. |
| 4 | [change_log.md](change_log.md) | One entry per edit. Append at the top. |

## TL;DR

**Current (2026-05-16):**

```
Stage 2 (multithread/process) — PRE-INPAINT, per-thread:
  alpha_arr → binary_closing(1×100) → approach_c_longest_run / approach_d_combined_smoothed
            → c_band/d_band   (core top/bottom Y)
            → compute_fiber_extents_y (alpha visible-pixel walk)
            → c_band.fiber_top_y / fiber_bot_y
  Used by: MTI yOffset alignment, /export width_meta, save-to-library width
           field, blender_uv_remap inputs (indirectly via core_top/bottom).

POST-INPAINT (save-to-library):
  export_assembled_alpha.png + core_top_y_in_export/core_bot_y_in_export
            → yarn_library.compute_fiber_bands (visible-pixel walk, peak%-of-floor)
            → bands_px.core / fiber_top / fiber_bot
            → metadata.blender.{core_v_min/max, fiber_top_v_min, fiber_bot_v_max,
               top_halo_frac, bot_halo_frac}
```

Two issues this doc tracks:

1. **Core boundaries come from pre-inpaint per-thread approach C** (rigid 0.85
   coverage threshold). On a noisy / wide / multi-thread scan, C frequently
   returns `top_y < 0` and we fall back to D (combined smoothed score) — fine,
   but the bands drift with the per-thread crop, and the unified core_top/bot in
   `export_metadata.width` is just `round(avg(tops)), round(avg(bots))` across
   fragments. The final assembled core is therefore quantised to per-thread C/D
   guesses, not measured on the assembled alpha.

2. **Two different algorithms own "core" and "fibers"** — C/D approaches own the
   core, `compute_fiber_bands` owns the fibers. They don't agree on density
   semantics (binary > threshold vs visible-pixel walk with peak%-of-floor).

**Target:** one FWHM density walk (ported from yarnseamless `band_segmenter.detect_bands`)
runs once on the final assembled alpha and returns `{core, fiber_top, fiber_bot}`
in one pass. Pre-inpaint C/D stay only as **alignment helpers** for MTI (yOffsets
need *some* band-centre estimate before the user can review). The save-to-library
fiber walk is replaced by the new detector; the unified width field in
`export_metadata` is recomputed against the new core too.

See `target_pipeline.md` for the cut-over plan.

## How to update these docs

- Add a Phase entry to `change_log.md` on the same hour as the code change.
- If band metadata shape changes (e.g. a new field in `metadata.blender`), also
  update `docs/putting-it-together/data_contract.md` — the producer/consumer
  contract lives there.
- If the consumer (Blender side) gains a new socket, mirror to
  `docs/BlenderFixes/` and link from this README.
