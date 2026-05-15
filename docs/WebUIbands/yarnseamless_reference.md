# YarnSeamless reference detector

Reference implementation lives at
`/Users/mihirbotle/Desktop/Impetus/3D Fabric/YarnSeamless/yarnseamless/band_segmenter.py`
in `detect_bands` (lines 50-111).

This is the algorithm we are porting in. It returns **core + both fibers** in
one pass against a single alpha matte.

## Algorithm

```python
def detect_bands(alpha_u8, core_frac=0.5, fiber_frac=0.02) -> dict:
    H, W = alpha_u8.shape
    a = alpha_u8.astype(np.float32) / 255.0

    # 1. per-row coverage at half-alpha threshold
    density = (a > 0.5).mean(axis=1).astype(np.float32)

    # 2. mild box smooth so single-pixel dropouts don't fragment the run
    if H >= 9:
        k = np.ones(7, dtype=np.float32) / 7
        density = np.convolve(density, k, mode="same")

    peak = float(density.max())
    core_thresh  = core_frac  * peak   # FWHM at 0.5 = half-max
    fiber_thresh = fiber_frac * peak   # 2% of peak = noise floor

    # 3. core = LARGEST contiguous run above core_thresh
    above_core = density >= core_thresh
    core_y0, core_y1 = _largest_run(above_core)   # scipy.ndimage.label

    # 4. fibers = walk outward from core boundaries until density drops
    #    below fiber_thresh
    above_fiber = density >= fiber_thresh
    fiber_top_y0 = core_y0
    while fiber_top_y0 > 0 and above_fiber[fiber_top_y0 - 1]:
        fiber_top_y0 -= 1
    fiber_bot_y1 = core_y1
    while fiber_bot_y1 < H - 1 and above_fiber[fiber_bot_y1 + 1]:
        fiber_bot_y1 += 1

    return {
        "core_v_range_px":      [core_y0, core_y1],
        "fiber_top_v_range_px": [fiber_top_y0, core_y0],
        "fiber_bot_v_range_px": [core_y1, fiber_bot_y1],
    }
```

## Why this is better than the current C/D + visible-pixel-walk pair

| Property | Current C (`approach_c_longest_run`) | Current D (`approach_d_combined_smoothed`) | Reference `detect_bands` |
|---|---|---|---|
| Core decision rule | per-row longest True run / W > 0.85 | weighted score > 0.85 | FWHM: row >= 50% of peak coverage |
| Threshold type | absolute (0.85) | absolute (0.85) | **relative to peak** — adapts to per-yarn density |
| Smoothing | none on rows; 5-tap on score (D only) | 5-tap MA on score | 7-tap box on row density |
| Fiber detection | not in C/D — done by separate `compute_fiber_extents_y` | same | **same pass** — single density curve, two thresholds |
| Failure mode | `top_y = -1` when no row meets 0.85, forcing D fallback | usually fires when C fails but inherits the rigid 0.85 floor | degrades gracefully — peak%-relative threshold always finds *some* core |
| Background noise | brittle: a single missing pixel in a row kills the longest-run >= 0.85 | smoothed but still binary | density>0.5 binary then smoothed; tolerates dropouts |
| Wide-image bias | OK | OK | works the same — `density` is a fraction, not an absolute count |

The peak-relative thresholds are the key win. A scan with thin sub-alpha noise
above/below the strand will still produce a clean core because the core rows
have density ~1.0 while noise rows have density ~0.05. A scan with a thicker
halo will widen the fiber bands automatically because `fiber_frac × peak` is
self-scaling.

The `_largest_run` (via `scipy.ndimage.label`) also has the same semantics as
the current C/D's `longest_true_run` helper — both return the longest True run.

## Tunables — defaults transfer cleanly

| Parameter | Reference default | Notes |
|---|---|---|
| `core_frac` | 0.5 | True FWHM. Higher (0.6-0.7) for a tighter core. |
| `fiber_frac` | 0.02 | 2% of peak. Lower catches more wisps. |

For the Fabric-generator port we keep the same two parameters and expose them
as `process()` keyword args so MTI / save-to-library can pass overrides if a
specific yarn needs it (no UI knob yet — start with the defaults).

## What we do NOT port

- `detect_twist_period` (FFT-based ply-twist period along U). Not used by
  Fabric-generator today. Add as a separate phase if needed.
- `normal_from_luma`, `roughness_from_luma`, overlay drawing. Fabric-generator
  has its own normal/roughness path in the Blender material; we only need the
  band ranges.

## File mapping (port plan)

| Source (yarnseamless) | Destination (Fabric-generator-tryon) |
|---|---|
| `band_segmenter.detect_bands` | new helper in `backend/app/yarnseamless/band_detect.py` (or fold into `yarn_library.py` next to `compute_fiber_bands` and deprecate the old one) |
| `band_segmenter._largest_run` | inline; tiny helper |

The pre-inpaint per-thread C/D code in `multithread_flow/solid_band.py` stays
in place for MTI alignment only — it doesn't need to change to land the
post-inpaint switch.
