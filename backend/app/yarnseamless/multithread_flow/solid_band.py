"""Detect the solid (opaque) band of the thread, separated from semi-
transparent fur above and below. Implements four straight-line approaches
(A, B, C, D) and saves one visualization per approach.

Run from this directory:
    python3 solid_band.py                                    # uses defaults
    python3 solid_band.py --input roated_white.jpg --out-dir output_rotated_white
"""
import argparse
import json
import os
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

import alpha_pipeline


# Defaults (overridden by CLI flags)
INPUT_PATH = "histogram_change20260428_14281977.jpg"
ALPHA_PATH = "histogram_change20260428_14281977_alpha.png"
OUT_DIR = "outputs"

# A pixel is "fully opaque" if its alpha is at or above this.
ALPHA_THRESHOLD = 200
# A row counts as "solid" only if at least this fraction of its pixels are
# opaque (or, for D, its weighted score exceeds this). Tightened to 0.85
# so the brackets only enclose the truly continuous solid core, not
# fur-dominated rows.
COVERAGE_THRESHOLD = 0.85
SCORE_THRESHOLD = 0.85
# Horizontal kernel width for B's morphological opening. Wide enough that
# only spans of horizontally-continuous opaque pixels survive.
OPENING_KERNEL_W = 1000
# Vertical moving-average window for D's smoothed score.
SMOOTH_TAPS = 5


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def longest_true_run(rows):
    """Return (start, end_inclusive, length) of the longest contiguous True
    run in a 1D bool array. Returns (-1, -1, 0) if no True values."""
    if not rows.any():
        return -1, -1, 0
    padded = np.concatenate(([False], rows, [False]))
    diffs = np.diff(padded.astype(np.int8))
    starts = np.where(diffs == 1)[0]
    ends = np.where(diffs == -1)[0]
    lengths = ends - starts
    i = int(np.argmax(lengths))
    return int(starts[i]), int(ends[i] - 1), int(lengths[i])


def per_row_longest_run(binary):
    """For each row of a 2D bool array, return the longest run of consecutive
    True values. Returns 1D int array of length H."""
    H, W = binary.shape
    out = np.zeros(H, dtype=np.int32)
    for r in range(H):
        row = binary[r]
        if not row.any():
            continue
        padded = np.concatenate(([False], row, [False]))
        diffs = np.diff(padded.astype(np.int8))
        starts = np.where(diffs == 1)[0]
        ends = np.where(diffs == -1)[0]
        out[r] = int((ends - starts).max())
    return out


# ---------------------------------------------------------------------------
# Approaches
# ---------------------------------------------------------------------------

def approach_a_coverage_fraction(alpha):
    binary = alpha >= ALPHA_THRESHOLD
    coverage = binary.mean(axis=1).astype(np.float32)
    solid_rows = coverage > COVERAGE_THRESHOLD
    top, bottom, _ = longest_true_run(solid_rows)
    return {"top_y": top, "bottom_y": bottom}


def approach_b_morphological_opening(alpha):
    """Binarize, morphologically open with a wide horizontal kernel, then
    keep only rows whose surviving coverage exceeds the threshold. Eliminates
    fur clumps that aren't horizontally continuous over the full image."""
    binary = alpha >= ALPHA_THRESHOLD
    structure = np.ones((1, OPENING_KERNEL_W), dtype=bool)
    opened = ndimage.binary_opening(binary, structure=structure)
    if not opened.any():
        return {"top_y": -1, "bottom_y": -1}
    coverage = opened.mean(axis=1).astype(np.float32)
    solid_rows = coverage > COVERAGE_THRESHOLD
    top, bottom, _ = longest_true_run(solid_rows)
    return {"top_y": top, "bottom_y": bottom}


def approach_c_longest_run(alpha):
    binary = alpha >= ALPHA_THRESHOLD
    H, W = binary.shape
    longest = per_row_longest_run(binary)
    run_frac = longest.astype(np.float32) / float(W)
    solid_rows = run_frac > COVERAGE_THRESHOLD
    top, bottom, _ = longest_true_run(solid_rows)
    return {"top_y": top, "bottom_y": bottom}


def approach_d_combined_smoothed(alpha):
    H, W = alpha.shape
    binary = alpha >= ALPHA_THRESHOLD

    mean_sig = alpha.mean(axis=1).astype(np.float32) / 255.0
    max_sig = alpha.max(axis=1).astype(np.float32) / 255.0
    coverage = binary.mean(axis=1).astype(np.float32)
    longest = per_row_longest_run(binary)
    run_frac = longest.astype(np.float32) / float(W)

    score = (0.2 * mean_sig
             + 0.2 * max_sig
             + 0.3 * coverage
             + 0.3 * run_frac)
    kernel = np.ones(SMOOTH_TAPS, dtype=np.float32) / SMOOTH_TAPS
    smoothed = np.convolve(score, kernel, mode="same")

    solid_rows = smoothed > SCORE_THRESHOLD
    top, bottom, _ = longest_true_run(solid_rows)
    return {"top_y": top, "bottom_y": bottom}


# Phase 3g — outer-extent walk (the fiber/halo band, rows 2 & 3 of the 4-band model).
# Phase 3g(v2, 2026-05-14) — switched from FWHM density walk to a visible-pixel
# walk per user request: "the top most visible pixel will be the top band, and
# same for the bot the lowest most visible pixel in the alpha is where the
# lowest band should be". The old walk binarised at alpha > 127, which excluded
# the hair pixels (typically alpha 20–80) and produced extents barely wider than
# the core. The new walk uses alpha > ALPHA_VISIBLE_EPS with a small per-row
# minimum count to reject single-pixel noise, then expands outward from the
# core boundaries while neighbouring rows are still visible.
ALPHA_VISIBLE_EPS = 5         # per-pixel visibility threshold (alpha > eps)
COVERAGE_FRAC = 0.05          # row qualifies when visible-count > frac × peak
MIN_ROW_VISIBLE_PX = 3        # absolute safety floor (tiny images)


def compute_fiber_extents_y(alpha_u8, core_top_y, core_bottom_y, *,
                            alpha_eps=ALPHA_VISIBLE_EPS,
                            coverage_frac=COVERAGE_FRAC,
                            min_row_px=MIN_ROW_VISIBLE_PX):
    """Return (fiber_top_y, fiber_bot_y) — outermost rows still showing visible
    hair, walking contiguously outward from the core.

    Threshold = max(min_row_px, coverage_frac × peak_visible_count). Picking a
    fraction of peak (not an absolute count) is what makes this work for wide
    images with low-amplitude matting noise on every row.

    Pre-inpaint per-thread use only. The authoritative post-inpaint detector
    is `app.yarnseamless.band_detect.detect_bands`.
    """
    if alpha_u8 is None or core_top_y < 0 or core_bottom_y < 0:
        return int(core_top_y), int(core_bottom_y)
    H, _W = alpha_u8.shape
    visible_count = (alpha_u8 > alpha_eps).sum(axis=1)
    peak = int(visible_count.max()) if visible_count.size else 0
    floor = max(int(min_row_px), int(round(coverage_frac * peak)))
    in_strand = visible_count >= floor
    cy0 = int(max(0, min(H - 1, core_top_y)))
    cy1 = int(max(0, min(H - 1, core_bottom_y)))
    fty0 = cy0
    while fty0 > 0 and in_strand[fty0 - 1]:
        fty0 -= 1
    fby1 = cy1
    while fby1 < H - 1 and in_strand[fby1 + 1]:
        fby1 += 1
    return int(fty0), int(fby1)


# ---------------------------------------------------------------------------
# Visualization
# ---------------------------------------------------------------------------

def save_visualization(key, top_y, bottom_y, base_rgb, out_dir=None,
                       line_width=1, suffix="_visualization"):
    """Draw two thin red horizontal lines at `top_y`/`bottom_y` on a copy of
    `base_rgb` and save to <out_dir>/<key><suffix>.png.
    `line_width` is the on-image pixel width (default 1 for max precision)."""
    target_dir = out_dir if out_dir is not None else OUT_DIR
    img = Image.fromarray(base_rgb).convert("RGB")
    draw = ImageDraw.Draw(img)
    H, W = base_rgb.shape[:2]
    for y in (top_y, bottom_y):
        if y < 0:
            continue
        y_clamped = max(0, min(H - 1, int(y)))
        draw.line([(0, y_clamped), (W - 1, y_clamped)],
                  fill=(255, 0, 0), width=line_width)
    img.save(os.path.join(target_dir, f"{key}{suffix}.png"))


def build_leveled_rgb():
    """Run alpha-pipeline preprocess (orientation + level + crop) on the
    raw input so the resulting RGB shares y-coordinates with the alpha
    mask we're analyzing."""
    leveled_path = os.path.join(OUT_DIR, "leveled_input.png")
    alpha_pipeline.preprocess(INPUT_PATH, leveled_path, preset="auto",
                              orientation="auto", level=True)
    return np.asarray(Image.open(leveled_path).convert("RGB"))


def ensure_alpha():
    """Generate the alpha file via alpha_pipeline.run if it's missing."""
    if not os.path.exists(ALPHA_PATH):
        print(f"[info] {ALPHA_PATH} not found - generating from {INPUT_PATH}")
        meta = alpha_pipeline.run(INPUT_PATH, ALPHA_PATH, preset="auto",
                                  orientation="auto", level=True)
        print(f"[info] alpha_pipeline meta: {json.dumps(meta)}")
    return np.asarray(Image.open(ALPHA_PATH).convert("L"))


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--input", default=INPUT_PATH,
                   help="Path to source RGB image.")
    p.add_argument("--alpha", default=None,
                   help="Path to alpha mask (auto-derived from --input if "
                        "omitted; generated if missing).")
    p.add_argument("--out-dir", default=OUT_DIR,
                   help="Directory for all outputs (created if missing).")
    return p.parse_args()


def main():
    global INPUT_PATH, ALPHA_PATH, OUT_DIR
    args = parse_args()
    INPUT_PATH = args.input
    OUT_DIR = args.out_dir
    if args.alpha:
        ALPHA_PATH = args.alpha
    else:
        stem = os.path.splitext(os.path.basename(INPUT_PATH))[0]
        ALPHA_PATH = os.path.join(OUT_DIR, f"{stem}_alpha.png")

    os.makedirs(OUT_DIR, exist_ok=True)
    alpha = ensure_alpha()
    base_rgb = build_leveled_rgb()

    if base_rgb.shape[:2] != alpha.shape:
        raise RuntimeError(
            f"Leveled input {base_rgb.shape[:2]} doesn't match alpha "
            f"{alpha.shape}. The alpha mask must come from the same "
            f"preprocess pass.")

    results = {
        "a": approach_a_coverage_fraction(alpha),
        "b": approach_b_morphological_opening(alpha),
        "c": approach_c_longest_run(alpha),
        "d": approach_d_combined_smoothed(alpha),
    }

    summary = {}
    for key, res in results.items():
        save_visualization(key, res["top_y"], res["bottom_y"], base_rgb)
        summary[key] = {
            "top_y": res["top_y"],
            "bottom_y": res["bottom_y"],
            "solid_height": (res["bottom_y"] - res["top_y"]
                             if res["bottom_y"] >= 0 else -1),
        }

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
