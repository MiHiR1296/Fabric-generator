"""FWHM density-walk band detector — one pass, three bands.

Ported from `YarnSeamless/yarnseamless/band_segmenter.py:detect_bands`. Runs on
the post-inpaint assembled alpha matte and returns the same dict shape as the
old `yarn_library.compute_fiber_bands`, so save_to_library can call it as a
drop-in replacement.

Why this exists: the previous flow computed the core from PRE-inpaint per-thread
approach C/D in solid_band.py (rigid 0.85 coverage threshold, brittle on noisy
or wide scans, returns -1 on failure), averaged those across threads to get the
unified core, and only then walked outward for the fiber halos on the assembled
alpha. This detector measures all three bands on the same image with one
peak-relative algorithm so a single failed thread can't quantise what Blender
sees. See docs/WebUIbands/ for the full rationale.
"""
from __future__ import annotations

from typing import Any

import numpy as np
from scipy import ndimage


def _largest_run(boolean_1d: np.ndarray) -> tuple[int | None, int | None]:
    """(start, end) inclusive of the longest True-run, or (None, None) if all False."""
    if not boolean_1d.any():
        return None, None
    labels, _ = ndimage.label(boolean_1d)
    sizes = np.bincount(labels.ravel())
    sizes[0] = 0
    best = int(np.argmax(sizes))
    idx = np.where(labels == best)[0]
    return int(idx.min()), int(idx.max())


def detect_bands(
    alpha_u8: np.ndarray,
    *,
    core_frac: float = 0.5,
    fiber_frac: float = 0.02,
    smooth_taps: int = 7,
) -> dict[str, Any]:
    """Detect core + top fiber + bottom fiber bands from an alpha matte.

    Algorithm:
      1. density[y] = fraction of pixels in row y with alpha > 0.5 (i.e. > 127/255)
      2. box-smooth density with a `smooth_taps`-wide kernel (default 7) so
         single-pixel dropouts don't fragment the longest core run
      3. core = largest contiguous run where density >= core_frac × peak
         (FWHM at core_frac=0.5)
      4. fiber walks outward from each core boundary while density >= fiber_frac
         × peak, contiguously

    Returns the same shape as the legacy `compute_fiber_bands` so consumers
    (`save_to_library`, the `metadata.blender` builder) don't need to change.
    """
    if alpha_u8.ndim != 2:
        raise ValueError(f"alpha_u8 must be 2D HxW, got shape {alpha_u8.shape}")
    H, W = alpha_u8.shape

    a = alpha_u8.astype(np.float32) / 255.0
    density = (a > 0.5).mean(axis=1).astype(np.float32)
    if H >= smooth_taps and smooth_taps > 1:
        k = np.ones(smooth_taps, dtype=np.float32) / float(smooth_taps)
        density = np.convolve(density, k, mode="same")

    peak = float(density.max()) if density.size else 0.0
    if peak <= 0:
        cy0, cy1 = 0, max(0, H - 1)
        fty0, fby1 = cy0, cy1
        core_thresh = fiber_thresh = 0.0
    else:
        core_thresh = core_frac * peak
        fiber_thresh = fiber_frac * peak

        core_y0, core_y1 = _largest_run(density >= core_thresh)
        if core_y0 is None:
            peak_row = int(np.argmax(density))
            core_y0 = max(0, peak_row - 1)
            core_y1 = min(H - 1, peak_row + 1)
        cy0, cy1 = int(core_y0), int(core_y1)

        above_fiber = density >= fiber_thresh
        fty0 = cy0
        while fty0 > 0 and above_fiber[fty0 - 1]:
            fty0 -= 1
        fby1 = cy1
        while fby1 < H - 1 and above_fiber[fby1 + 1]:
            fby1 += 1

    return {
        "bands_px": {
            "core":      [cy0, cy1],
            "fiber_top": [fty0, cy0],
            "fiber_bot": [cy1, fby1],
        },
        "bands_v_norm": {
            "_convention": "blender (V=0 bottom, V=1 top)",
            "core":      [1.0 - cy1 / H, 1.0 - cy0 / H],
            "fiber_top": [1.0 - cy0 / H, 1.0 - fty0 / H],
            "fiber_bot": [1.0 - fby1 / H, 1.0 - cy1 / H],
        },
        "thickness_px": {
            "core_height":      int(cy1 - cy0 + 1),
            "fiber_top_height": int(cy0 - fty0),
            "fiber_bot_height": int(fby1 - cy1),
        },
        "params": {
            "algorithm": "fwhm_density_walk",
            "core_frac": core_frac,
            "fiber_frac": fiber_frac,
            "smooth_taps": smooth_taps,
            "peak_density": peak,
            "core_thresh": float(core_thresh),
            "fiber_thresh": float(fiber_thresh),
        },
    }
