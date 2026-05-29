# Yarn Scan Processing Phase Log

Append-only engineering log for yarn scan processing, RGBA export, alpha,
rotation, and band detection. Entries use Symptom / Diagnosis / Fix /
Verification so future debugging can start from facts rather than memory.

---

## 2026-05-29 - Robust Detection, Natural RGBA, Background Spill Removal, Rotation, And Connected Core Bands

### Context

User was testing Epson thread scans, especially red-card scans with white yarn.
The UI/RGBA preview and Blender render showed several related problems:

- Threads were sometimes missed when background color changed.
- Processed RGBA looked visibly edited compared with the original scan.
- Blue/color yarns could become grey/black after alpha/RGBA recovery.
- A red/pink halo appeared around yarn fibers because the card/background
  color leaked into semitransparent foreground pixels.
- Blender could not render a 47053 x 1019 texture as a single image because
  Cycles rejects textures over 16384 px in either dimension.
- The code was saving albedo/alpha files even though the crisp `rgba.png` was
  the desired render source.
- Thread crops with tiny rotations were not corrected, so red core bands looked
  misplaced.
- The core-thickness band could lock onto the wrong alpha rows instead of the
  actual thick yarn body.

### Main Files Touched

- `backend/app/yarnseamless/thread_segmentation.py`
- `backend/app/yarnseamless/multithread_flow/split_threads.py`
- `backend/app/yarnseamless/multithread_flow/alpha_pipeline.py`
- `backend/app/yarnseamless/dual_alpha_pipeline.py`
- `backend/app/yarnseamless_routes.py`
- `backend/app/yarn_assets.py`
- `backend/app/yarnseamless/yarn_library.py`
- `backend/app/render_jobs.py`
- `frontend/src/components/yarnseamless/MultiFragmentEditor.tsx`
- `scripts/dev_services.sh`
- tests:
  - `backend/tests/test_thread_segmentation.py`
  - `backend/tests/test_yarnseamless_routes.py`
  - `backend/tests/test_yarn_assets.py`
  - `backend/tests/test_yarn_library.py`
  - `backend/tests/test_render_jobs.py`

### Phase 1 - Segmentation-First Thread Detection

#### Symptom

The old splitter could fail or report low confidence when threads were on a
different colored background. Some scans visibly had three separated threads,
but the detector missed one or split duplicate edges as separate threads.

#### Diagnosis

Brightness peaks alone were not reliable. A yarn can be dark, light, blue, or
low contrast relative to the card. The detector needed to model the background
first, then detect foreground probability from RGB/Lab/chroma/luma separation.

#### Fix

Added `backend/app/yarnseamless/thread_segmentation.py` with:

- robust background estimation from low-foreground/border regions;
- foreground scoring from RGB distance, luminance distance, chroma distance,
  and Lab distance where available;
- hysteresis-style weak/strong cleanup;
- connected component filtering;
- column profiles based on foreground density, high-percentile score, and
  longest continuous runs;
- candidate quality metadata and rejection reasons.

`split_threads.py` now routes through `thread_segmentation.detect_threads`
through `detect_thread_layout`, while older callers can still use
`detect_thread_columns`.

#### Verification

Added synthetic tests for:

- dark threads after background color change;
- weak chroma threads with similar luma;
- duplicate edge peaks around one thick thread;
- fabric/plaid rejection;
- local Epson fixture scans in `testingv1_cheques` when available.

### Phase 2 - Stop Editing The RGBA Core

#### Symptom

Zooming into `rgba.png` showed hard edited slabs/pixelation in the yarn core.
The original scan had visible texture detail, but the processed RGBA center
looked flattened. User identified "core boost" as the main source of the
processed look.

#### Diagnosis

Several places were forcing high alpha/core pixels to 255 or replacing
foreground values. This made the core look binary and destroyed subtle scan
detail. Blender then faithfully rendered the edited texture.

#### Fix

Removed the known core-boost paths:

- `yarnseamless_routes._material_alpha_from_matte` now only zeros numerical
  dust below alpha 4 and preserves natural matte values.
- Removed `core_whitefill` from `multithread_flow/alpha_pipeline.py`.
- Removed segmentation alpha overwrite/boosts in `thread_segmentation.py`.

The canonical RGBA path is now:

- stitched/source RGB;
- natural material alpha;
- no core RGB recovery;
- no forced opaque center boost.

#### Verification

For the active sample asset `runtime/yarn_assets/0448639d212b`:

- `rgba.png` stayed full resolution at 47053 x 1019.
- alpha remained byte-for-byte identical when only RGB spill cleanup changed.
- high-alpha yarn pixels were protected in later cleanup passes.

### Phase 3 - Prefer Full-Resolution RGBA And RGBA UDIM Tiles

#### Symptom

Blender failed with:

```text
Texture exceeds maximum allowed size of 16384 x 16384
requested: 47053 x 1019
```

The RGBA strip looked crisp, while split albedo looked blurry. The user asked
why we were saving albedo/alpha if render should use RGBA.

#### Diagnosis

Cycles has a per-texture dimension cap. Downscaling or blurred albedo fallbacks
made Blender look softer than the RGBA preview. The correct path is to keep the
single crisp `rgba.png` as the source and split it into full-resolution UDIM U
tiles for Blender.

#### Fix

`yarn_assets.py`, `yarn_library.py`, and render payload code now prefer RGBA:

- library/runtime entries keep `rgba.png` as the source;
- render texture mode becomes `rgba_tiled` when width exceeds the Cycles cap;
- tile pattern is `cycles_tiled/rgba_<UDIM>.png`;
- albedo/alpha split files are not kept for the canonical library/runtime
  path.

For the active asset:

- source: `runtime/yarn_assets/0448639d212b/rgba.png`
- tiles:
  - `cycles_tiled/rgba_1001.png`
  - `cycles_tiled/rgba_1002.png`
  - `cycles_tiled/rgba_1003.png`

#### Verification

`asset.json` for `0448639d212b` used:

- `sourceFilename: "rgba.png"`
- `renderTextureMode: "rgba_tiled"`
- `renderRgbaTilePattern: "cycles_tiled/rgba_<UDIM>.png"`

The material payload reported `texture_mode: "udim_rgba_tiled"`.

### Phase 4 - Background/Red Spill Removal In RGBA

#### Symptom

After keeping natural RGB, red-card spill remained around semitransparent
fibers. Desaturation helped, but some pink/red hue remained in yarn fringe.
User wanted no background color in the yarn.

#### Diagnosis

The spill is not one exact RGB value. It is a family of background-colored
pixels:

- dark red card shades;
- light red card shades;
- red mixed into white/grey yarn fringe;
- luma-changed versions of the same background chroma.

General desaturation removed some red, but left residual background chroma in
alpha fringe pixels. Deleting those pixels would remove fine fibers, so the
right operation is color cleanup while preserving alpha.

#### Fix

Added `_desaturate_background_spill_rgb` in `yarnseamless_routes.py`.

The final method:

1. Estimate background color from saved `B_red_linear` or low-alpha pixels.
2. Convert the background to sRGB.
3. Build a background hue/chroma family by removing luma from RGB and comparing
   each pixel's chroma direction to the background chroma direction.
4. Build a color gate from:
   - distance to the card color;
   - background hue family alignment;
   - red-excess when the card is red.
5. Keep cleanup strong through transparent/semitransparent fringe.
6. Fade cleanup only near opaque yarn alpha.
7. Subtract the projected background chroma component from RGB.
8. Apply a small neutral mix for pixels that are almost exactly card-family.
9. Do not change alpha.

This is wired into both RGBA creation paths:

- `/api/multithread/regenerate-alpha` Stage C;
- `_build_export_set`, used by `/api/multithread/export`.

#### Candidate Loop And Metrics

Several candidates were compared:

- simple exact background desaturation;
- broader hue-family desaturation;
- background-chroma subtraction;
- background-chroma subtraction with late alpha fade.

Chosen method: late-fade background-chroma subtraction.

For sample `20260529_035408_350` with background sRGB approximately:

```json
[161.53, 56.05, 57.40]
```

Final residual metrics in affected fringe:

```json
{
  "bg_projection_p95": 3.64,
  "bg_projection_mean": 0.75,
  "red_excess_p95": 2.0,
  "red_excess_mean": -0.26
}
```

Practical interpretation: red/card chroma is nearly gone from the visible
fringe.

#### QA Images

Temporary local QA sheets generated:

- `/tmp/current_rgba_bg_spill_desaturated.jpg`
- `/tmp/current_rgba_bg_spill_desaturated_stronger.jpg`
- `/tmp/current_rgba_bg_spill_desaturated_more.jpg`
- `/tmp/rgba_cleanup_candidate_latefade.jpg`
- `/tmp/current_rgba_bg_removed_chroma_subtract.jpg`

Visual rating after final pass: about 9.5/10 on the sample. The remaining fine
fibers read neutral/white instead of pink.

#### Tests

Added `backend/tests/test_yarnseamless_routes.py` covering:

- low-alpha red card spill is removed;
- high-alpha yarn core stays unchanged;
- blue/green yarn colors are protected;
- dark red, light red, and red-mixed pale fringe are caught;
- semitransparent red fringe is cleaned while opaque yarn stays protected.

### Phase 5 - Sub-Degree Rotation Is Mandatory

#### Symptom

Thread crops were still slightly tilted. User noted that even 0.5 degrees or
1 degree cannot be skipped because band detection and visual alignment depend
on the yarn being perfectly horizontal.

#### Diagnosis

`multithread_flow/alpha_pipeline.level_and_crop` had:

```python
min_rotate_deg=1.0
```

and skipped any angle below that threshold. That meant many real thread tilts
were measured but not corrected.

#### Fix

Changed `min_rotate_deg` default to `0.0` and corrected every measured nonzero
angle:

```python
if abs(angle_deg) > max(1e-6, float(min_rotate_deg)):
    rotate(...)
```

Also changed `dual_alpha_pipeline.apply_level_transform` to use `BICUBIC`, so
two-background secondary scans mirror the same leveling quality.

#### Verification

Reprocessed the sample scan through the backend into session:

```text
runtime/debug/multithread_image/20260529_130625_379
```

Measured and corrected tilts:

| thread | tilt corrected |
|---|---:|
| 0 | 0.561 deg |
| 1 | 0.120 deg |
| 2 | 0.488 deg |

Added test:

- `test_level_and_crop_rotates_subdegree_tilt`

### Phase 6 - Connected-Core Band Detector

#### Symptom

The red core-thickness bands were sometimes not placed on the actual thick yarn
body. They could be too wide or drift toward alpha/haze rows.

#### Diagnosis

The old density/FWHM band detector can be fooled by any long row with enough
alpha coverage. A disconnected haze band or scanner/background artifact can
have a wider row run than the real yarn core. The core band needs to be derived
from the connected thick alpha component, not just whole-row density.

#### Fix

Added `_detect_connected_core_band` in `thread_segmentation.py`:

1. Find visible alpha.
2. Seed from high-alpha yarn body.
3. Keep only visible alpha connected to that thick seed.
4. Score each row by:
   - longest connected high-alpha run;
   - high-alpha count;
   - mean connected alpha.
5. Smooth the row score.
6. Select the peak-relative run around the strongest core row.
7. Use this as both `c_band` and `d_band` for the current route.

`detect_band_quality` still reports the old raw FWHM core under
`quality.raw_fwhm_core` for debugging.

#### Verification

Synthetic regression:

- A long disconnected semitransparent row band is present above the true core.
- Raw FWHM chooses the wrong disconnected band.
- Connected-core detector chooses the actual thick center.

Test:

- `test_band_quality_uses_connected_thick_core_not_disconnected_haze_band`

Sample reprocess results:

| thread | old c_band | new c_band | new core width |
|---|---:|---:|---:|
| 0 | 200-241 | 197-216 | 20 px |
| 1 | 246-284 | 241-258 | 18 px |
| 2 | 541-570 | 272-287 | 16 px |

Temporary QA sheet:

- `/tmp/rotation_band_fix_old_vs_new.jpg`

The thread 2 shift is expected: the previous crop/band placement was wrong
after rotation/cropping drift; the new band is on the thick visible yarn body
in the reprocessed leveled frame.

### Phase 7 - Dev Service Control Script

#### Symptom

During iteration, backend/frontend restarts were frequent and manual process
cleanup was error-prone.

#### Fix

Added `scripts/dev_services.sh` with:

```bash
./scripts/dev_services.sh start
./scripts/dev_services.sh stop
./scripts/dev_services.sh restart
./scripts/dev_services.sh status
./scripts/dev_services.sh logs
```

Defaults:

- backend: `http://127.0.0.1:8000`
- frontend: `http://127.0.0.1:5180`

The script stores PID files in `runtime/dev-services` and logs in
`runtime/logs`.

### Verification Commands

Backend checks used during the final pass:

```bash
backend/.venv/bin/python -m unittest \
  backend/tests/test_thread_segmentation.py \
  backend/tests/test_yarnseamless_routes.py \
  backend/tests/test_yarn_assets.py \
  backend/tests/test_yarn_library.py \
  backend/tests/test_render_jobs.py \
  backend/tests/test_dual_alpha_pipeline.py
```

Final result:

```text
Ran 47 tests
OK
```

Dev services restarted successfully:

```text
Backend:  http://127.0.0.1:8000
Frontend: http://127.0.0.1:5180
```

### Current Operating Notes

- Reprocess scans after the rotation/band changes; old sessions will still show
  old `thread_*_leveled.png` and old red-band overlays.
- Inspect `thread_i_c_visualization.png` for core bracket placement.
- Inspect `summary.json -> threads[i].band_quality`:
  - `algorithm` should be `connected_core_peak_band_v1`;
  - `raw_fwhm_core` is only diagnostic;
  - `connected_core_alpha_cut` records the high-alpha seed threshold.
- For RGBA color review, composite `rgba.png` on a dark background and inspect
  semitransparent hairs. The center should retain original scan texture.
- For Blender, use `rgba.png` or RGBA UDIM tiles. Avoid judging the render from
  old blurred albedo outputs.

### Known Risks / Follow-Ups

- Background-chroma subtraction is tuned for red-card white/grey yarns and
  protected by hue/chroma gates for blue/green yarn. Keep adding real colored
  yarn fixtures before making it more aggressive.
- Connected-core band detection intentionally reports a tighter core than old
  FWHM density. If Blender needs a wider visual core later, widen in Blender
  metadata/padding, not by letting haze own the measured core.
- The active sample was reprocessed manually for QA. Future UI runs will use the
  new code automatically, but existing debug sessions are historical artifacts.
