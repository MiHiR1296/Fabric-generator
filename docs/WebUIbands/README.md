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
| 1 | [current_pipeline.md](current_pipeline.md) | Today's flow after the 2026-05-29 repairs: connected-core per-thread bands for review/alignment, plus assembled-alpha export bands for saved Blender metadata. |
| 2 | [target_pipeline.md](target_pipeline.md) | Historical cut-over plan for the single FWHM-density detector. Kept for context; later work added connected-core refinements for per-thread red bands. |
| 3 | [yarnseamless_reference.md](yarnseamless_reference.md) | The reference implementation from `/Users/mihirbotle/Desktop/Impetus/3D Fabric/YarnSeamless/yarnseamless/band_segmenter.py:detect_bands` — what makes it better than the current C/D approaches. |
| 4 | [change_log.md](change_log.md) | One entry per edit. Append at the top. |

## TL;DR

**Current (updated 2026-05-29):**

```
Stage 2 (multithread/process) — PRE-INPAINT, per-thread:
  alpha_arr → thread_segmentation.segment_thread_alpha
            → connected thick-core row scoring
            → c_band/d_band   (same connected-core top/bottom Y)
            → connected visible-fiber walk
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

Historical issues this doc tracks:

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

**Current target:** assembled-alpha metadata remains measured on the final export,
while per-thread red review bands use connected-core detection so disconnected
haze or background rows cannot steal the visible core-thickness bracket.

See `target_pipeline.md` for the cut-over plan.

For the full 2026-05-29 yarn scan processing log, including RGBA/background
cleanup and rotation changes, read
[../YarnScanProcessing/phase_log.md](../YarnScanProcessing/phase_log.md).

## How to update these docs

- Add a Phase entry to `change_log.md` on the same hour as the code change.
- If band metadata shape changes (e.g. a new field in `metadata.blender`), also
  update `docs/putting-it-together/data_contract.md` — the producer/consumer
  contract lives there.
- If the consumer (Blender side) gains a new socket, mirror to
  `docs/BlenderFixes/` and link from this README.
