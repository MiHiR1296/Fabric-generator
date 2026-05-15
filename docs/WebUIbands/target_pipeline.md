# Target band pipeline

Single source of truth: **the assembled alpha matte, after inpainting and
finalisation**. One detector, one pass, three bands.

## Flow

```
Stage 2 (multithread/process) — PRE-INPAINT, per-thread:
  alpha_arr → solid_band C/D → c_band/d_band (core only)
  Used ONLY for: MTI alignment yOffset estimate, MTI review overlay.
  NOT used for: width metadata, blender V-bands, save-to-library.

MFE inpaint + assemble + regenerate alpha:
  unchanged.

POST-INPAINT (regenerate-alpha completes OR save-to-library entry):
  export_assembled_alpha.png
    → band_detect.detect_bands(alpha, core_frac=0.5, fiber_frac=0.02)
    → bands_px {core, fiber_top, fiber_bot}      ← one pass
    → bands_v_norm (Blender V=0 bottom)
    → metadata.blender.{ core_v_min/max, fiber_top_v_min, fiber_bot_v_max,
                         top_halo_frac, bot_halo_frac }
    → export_metadata.width   ← derived from the new core, not Pass-1 averages
```

## Concrete cut-over points

### 1. New module: `backend/app/yarnseamless/band_detect.py`

Pure function, no Flask/FastAPI imports, importable from both
`yarnseamless_routes.py` and `yarn_library.py`. Mirrors
[band_segmenter.detect_bands](yarnseamless_reference.md):

```python
def detect_bands(
    alpha_u8: np.ndarray,
    *,
    core_frac: float = 0.5,
    fiber_frac: float = 0.02,
    smooth_taps: int = 7,
) -> dict:
    """Returns {bands_px, bands_v_norm, thickness_px, params}.
    Same shape as yarn_library.compute_fiber_bands, so the consumer is
    drop-in compatible."""
```

Return-shape parity with the existing `compute_fiber_bands` is the key — every
downstream consumer reads `bands_px.core` / `fiber_top` / `fiber_bot` and
`bands_v_norm.*`, so a drop-in replacement keeps the `metadata.blender` block
identical except for the now-better numbers.

### 2. Replace `compute_fiber_bands` call in `yarn_library.save_to_library`

[backend/app/yarnseamless/yarn_library.py:405-409](../../backend/app/yarnseamless/yarn_library.py#L405-L409):

```python
# BEFORE
if isinstance(core_top, int) and isinstance(core_bot, int):
    with Image.open(alpha_src) as alpha_im:
        alpha_arr = np.asarray(alpha_im.convert("L"))
    bands = compute_fiber_bands(alpha_arr, core_top, core_bot)

# AFTER
with Image.open(alpha_src) as alpha_im:
    alpha_arr = np.asarray(alpha_im.convert("L"))
bands = detect_bands(alpha_arr)
```

Stop reading `core_top` / `core_bot` from `export_metadata.json`. The new
detector computes core itself.

### 3. Recompute `export_metadata.width` from the new core

In `/api/multifragment/export-final` ([yarnseamless_routes.py:1410-1499](../../backend/app/yarnseamless_routes.py#L1410-L1499)):

```python
# BEFORE: average Pass-1 c_bands across fragments
tops, bots = [], []
for j, f_meta in enumerate(fragments):
    ...
    tops.append(frag_y + cb["top_y"])
    bots.append(frag_y + cb["bottom_y"])
unified_top = round(sum(tops) / len(tops))
unified_bot = round(sum(bots) / len(bots))

# AFTER: read the assembled alpha and run the new detector once
alpha_path = sdir / "assembled_alpha.png"   # produced by regenerate-alpha
if alpha_path.exists():
    alpha_arr = np.asarray(Image.open(alpha_path).convert("L"))
    bands = detect_bands(alpha_arr)
    core = bands["bands_px"]["core"]
    unified_top, unified_bot = int(core[0]), int(core[1])
    unified_width_px = unified_bot - unified_top + 1
else:
    unified_top = unified_bot = unified_width_px = None
```

This also means **export now depends on regenerate-alpha**. The UI already
runs regenerate-alpha before export in the happy path, but we should fail
loudly (HTTP 409 with a clear message) if `assembled_alpha.png` is missing
rather than silently falling back to Pass-1 averages.

### 4. Keep Pass 1 as alignment helper

[backend/app/yarnseamless/multithread_flow/solid_band.py](../../backend/app/yarnseamless/multithread_flow/solid_band.py)
and the per-thread C/D calls in [yarnseamless_routes.py:641-660](../../backend/app/yarnseamless_routes.py#L641-L660)
stay. `c_band` / `d_band` are still in `summary.json` per thread because:

- MTI needs band-centres before the user can review (chicken-and-egg with
  inpaint).
- The `thread_{i}_c_visualization.png` overlays drive the MTI review screen.

What changes: `width_samples` (used for the dimensions card in MFE) becomes a
**preview-only** approximation. The authoritative width comes from the
post-inpaint pass in step 3.

### 5. Drop `threads_solid_band` from `metadata.blender`'s parent

`export_metadata.threads_solid_band` is already diagnostic-only. Leave it.
But mark it as such in [data_contract.md](../putting-it-together/data_contract.md)
so future readers don't think it feeds Blender.

## Risks / open questions

- **Wraparound region for `assembled_alpha.png`.** Right now the export
  excludes the wrap join (the `N-1` join is `is_wraparound_excluded_from_export`).
  If `assembled_alpha.png` includes the wrap and `export_assembled_alpha.png`
  excludes it, the new detector must run on whichever file matches what the
  exported RGBA covers. Today `save_to_library` reads `export_assembled_alpha.png`
  — verify that's the trimmed one before flipping the export route to read the
  same.
- **`compute_fiber_bands` is still imported elsewhere?** Quick grep before
  removal — `yarn_library.py` is the only producer; consumers read the
  resulting JSON, not the function.
- **MTI alignment quality.** If pre-inpaint C/D drift far from the
  post-inpaint truth, the user sees fragments misaligned at first load. They
  can still slide them, but a known regression. If it bites, port `detect_bands`
  into Pass 1 too (run it on the per-thread alpha BEFORE binary closing — the
  density walk handles dropouts itself via smoothing).

## Phasing

Land in three small PRs, in this order:

1. **Phase A — add `band_detect.py`**, plus a unit test that pins return-shape
   parity vs `compute_fiber_bands` on a synthetic alpha. No callers yet.
2. **Phase B — switch `save_to_library`** to call the new detector. The
   `metadata.blender` block is now driven entirely by the post-inpaint alpha.
   `export_metadata.width` still uses Pass-1 averages; that's the next phase.
3. **Phase C — switch `/api/multifragment/export-final`** to compute
   `unified_top` / `unified_bot` from the new detector on `assembled_alpha.png`.
   Pass 1's `c_band` / `d_band` keep flowing into MTI alignment but no longer
   influence the saved width.

Each phase is independently reversible.
