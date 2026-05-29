# Yarn Scan Processing

This folder documents the yarn-scan processing work done on 2026-05-29:
thread detection, per-thread rotation/leveling, alpha cleanup, RGBA export,
background spill removal, and the core-thickness band used by Blender.

Read this before changing:

| file | what it covers |
|---|---|
| [phase_log.md](phase_log.md) | Detailed chronological log of the investigation, decisions, code changes, sample metrics, and verification commands. |

## Current Pipeline Summary

The current processing path is:

1. `/api/multithread/process` loads the scan and samples the card/background
   color.
2. `thread_segmentation.detect_threads` detects vertical thread columns from a
   foreground probability map, not brightness peaks alone.
3. Each thread crop is rotated to horizontal in
   `multithread_flow/alpha_pipeline.py`. Every measured nonzero angle is now
   corrected; sub-degree tilts are no longer skipped.
4. `dual_alpha_pipeline` produces a base alpha.
5. `thread_segmentation.segment_thread_alpha` gates that alpha through cleaned
   foreground support and connected visible yarn strands.
6. `thread_segmentation.detect_band_quality` computes the red core-thickness
   band from the connected thick alpha body.
7. `/api/multithread/regenerate-alpha` and `/api/multithread/export` build the
   final RGBA strip.
8. RGBA export uses source stitched RGB plus natural material alpha, then
   subtracts detected background-color chroma from semitransparent fringe.
9. Runtime/library assets prefer full-resolution `rgba.png` and RGBA UDIM
   tiles. Separate albedo/alpha files are not the render source.

## Important Principles

- **Do not boost the core alpha/RGB.** The old core boost made the center look
  edited and blocky in zoomed RGBA previews.
- **Do not save or render blurred albedo fallbacks for this path.** Blender
  should use the crisp RGBA strip or RGBA UDIM tiles.
- **Do rotate tiny angles.** A 0.5 degree tilt is enough to make row-based
  bands look wrong.
- **Core band means thick connected yarn body, not any long alpha row.**
  Haze/fuzz/background rows can be longer than the true core and must not own
  the red bracket.
- **Background cleanup removes color, not alpha.** Red-card spill is removed by
  subtracting the card chroma from fringe RGB while keeping alpha intact.

## Canonical Sample Used During This Pass

The main acceptance sample for this session was:

- source session: `runtime/debug/multithread_image/20260529_035408_350`
- active asset: `runtime/yarn_assets/0448639d212b`
- library entry: `../yarn_library/20260529_035614_c4ecd7`
- reprocessed rotation/band session: `runtime/debug/multithread_image/20260529_130625_379`

Useful QA sheets generated during the work:

- `/tmp/current_rgba_bg_removed_chroma_subtract.jpg`
- `/tmp/rotation_band_fix_old_vs_new.jpg`

These are temporary local files, not repo artifacts.
