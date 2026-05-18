"""
Unified yarn-alpha pipeline with bg-detection + preset selection.

Replaces the split between alpha_fit.py (white bg -> auto-invert) and
alpha_fit_black_bg.py (black bg -> no invert). The core processing stages
are identical; only a handful of knobs change per preset, so we keep one
pipeline and pick the preset up-front.

Entry points:
  * classify(img_rgb)           -> (preset_name, confidence, signals)
  * detect_orientation(img_rgb) -> ("horizontal"|"vertical", ratio)
  * run(src, dst, preset=None, overrides=None) -> dict of meta/outputs
  * CLI: python alpha_pipeline.py <input> <output> [--preset auto|white_bg|black_bg]
         [--bp FLOAT] [--wp FLOAT] [--gamma FLOAT] [--hardcut-cutoff INT]
         [--orientation auto|horizontal|vertical]
    Prints a single JSON line to stdout with preset/confidence/paths.

The final output always has the hardcut applied (translucent tail zeroed
below `hardcut_cutoff`). No separate "_hardcut" variant is written.
Output is always written with the thread running horizontally.
"""
import argparse
import json
import sys
import numpy as np
from PIL import Image, ImageFilter
from scipy import ndimage


# ---------------------------------------------------------------------------
# Core stages (shared across presets)
# ---------------------------------------------------------------------------

def luma(img_rgb):
    r, g, b = img_rgb[..., 0], img_rgb[..., 1], img_rgb[..., 2]
    return (0.2126 * r + 0.7152 * g + 0.0722 * b).astype(np.float32)


def levels(y, bp, wp, gamma=1.0):
    n = (y - bp) / max(1.0, (wp - bp))
    n = np.clip(n, 0.0, 1.0)
    if gamma != 1.0:
        n = np.power(n, 1.0 / gamma)
    return (n * 255.0).astype(np.uint8)


def row_thread_score(y_work, smooth_rows=15):
    row_mean = y_work.mean(axis=1)
    row_peak = np.percentile(y_work, 99, axis=1)

    def norm(x):
        lo = float(np.percentile(x, 20))
        hi = float(x.max())
        return np.clip((x - lo) / max(1.0, hi - lo), 0.0, 1.0)

    score = 0.25 * norm(row_mean) + 0.75 * norm(row_peak)
    if smooth_rows > 1:
        k = np.ones(smooth_rows, dtype=np.float32) / smooth_rows
        score = np.convolve(score, k, mode="same")
    return score.astype(np.float32)


def detect_thread_rows(y_work, thresh=0.20):
    return row_thread_score(y_work) > thresh


def compute_bp_wp(y_work):
    thread_mask = detect_thread_rows(y_work)
    h = y_work.shape[0]
    n_thread = int(thread_mask.sum())
    if n_thread < 3 or n_thread > h * 0.9:
        bp = float(np.percentile(y_work, 78.75))
        wp = float(np.percentile(y_work, 95.0))
    else:
        bg_pix = y_work[~thread_mask, :].ravel()
        th_pix = y_work[thread_mask, :].ravel()
        bp = float(np.percentile(bg_pix, 90.0))
        wp = float(np.percentile(th_pix, 70.0))
    if wp - bp < 40:
        wp = bp + 40
    return bp, wp, n_thread


def hysteresis_clean(alpha_u8, low=18, high=70):
    weak = alpha_u8 >= low
    strong = alpha_u8 >= high
    labels, n = ndimage.label(weak, structure=np.ones((3, 3), dtype=np.uint8))
    if n == 0:
        return np.zeros_like(alpha_u8)
    keep_labels = np.unique(labels[strong])
    keep_labels = keep_labels[keep_labels != 0]
    mask = np.isin(labels, keep_labels)
    return np.where(mask, alpha_u8, 0).astype(np.uint8)


def bg_row_clamp(alpha_u8, row_score, score_lo=0.02, score_hi=0.15, floor=0.35, sharpness=1.0):
    denom = max(1e-6, float(score_hi - score_lo))
    w = np.clip((row_score - score_lo) / denom, 0.0, 1.0)
    if sharpness != 1.0:
        w = np.power(w, sharpness)
    w = floor + (1.0 - floor) * w
    out = alpha_u8.astype(np.float32) * w[:, None]
    return np.clip(out, 0, 255).astype(np.uint8)


def core_whitefill(alpha_u8, bright_thresh=230, row_min_frac=0.10,
                   feather_sigma=10, strength=1.0):
    bright = alpha_u8 >= bright_thresh
    if not bright.any():
        return alpha_u8
    H, W = alpha_u8.shape
    row_bright = bright.sum(axis=1)
    thread_rows = row_bright >= (row_min_frac * W)
    if not thread_rows.any():
        return alpha_u8
    row_mask = thread_rows[:, None]
    bright_in_body = bright & row_mask

    has_bright_col = bright_in_body.any(axis=0)
    first_idx = np.argmax(bright_in_body, axis=0)
    last_idx = H - 1 - np.argmax(bright_in_body[::-1], axis=0)
    row_idx = np.arange(H)[:, None]
    filled = (row_idx >= first_idx[None, :]) & (row_idx <= last_idx[None, :]) & has_bright_col[None, :]
    filled = filled & row_mask

    mask_u8 = (filled.astype(np.uint8) * 255)
    pil = Image.fromarray(mask_u8).filter(ImageFilter.GaussianBlur(radius=feather_sigma))
    w = np.asarray(pil, dtype=np.float32) / 255.0
    a = alpha_u8.astype(np.float32)
    out = a + w * (255.0 - a) * strength
    return np.clip(out, 0, 255).astype(np.uint8)


def kill_bg_ccs(alpha_u8, bright_thresh=230, row_min_frac=0.10, low=10):
    bright = alpha_u8 >= bright_thresh
    H, W = alpha_u8.shape
    row_bright = bright.sum(axis=1)
    thread_rows = row_bright >= (row_min_frac * W)
    if not thread_rows.any():
        return alpha_u8
    mask = alpha_u8 >= low
    if not mask.any():
        return alpha_u8
    labels, n = ndimage.label(mask, structure=np.ones((3, 3), dtype=np.uint8))
    if n == 0:
        return alpha_u8
    thread_row_labels = labels[thread_rows, :]
    touching = np.unique(thread_row_labels)
    touching = touching[touching != 0]
    keep_mask = np.isin(labels, touching)
    return np.where(keep_mask, alpha_u8, 0).astype(np.uint8)


def hard_low_cut(alpha_u8, cutoff=40):
    return np.where(alpha_u8 >= cutoff, alpha_u8, 0).astype(np.uint8)


def despeckle(alpha_u8, min_area=30, low=10):
    mask = alpha_u8 >= low
    if not mask.any():
        return alpha_u8
    labels, n = ndimage.label(mask, structure=np.ones((3, 3), dtype=np.uint8))
    if n == 0:
        return alpha_u8
    areas = np.bincount(labels.ravel())
    keep = areas >= min_area
    keep[0] = False
    keep_mask = keep[labels]
    return np.where(keep_mask, alpha_u8, 0).astype(np.uint8)


def speckle_snap(alpha_u8, blur_sigma=6, threshold=25):
    pil = Image.fromarray(alpha_u8).filter(ImageFilter.GaussianBlur(radius=blur_sigma))
    local_avg = np.asarray(pil, dtype=np.float32)
    keep = (local_avg > threshold).astype(np.float32)
    soft = np.clip((local_avg - threshold * 0.5) / (threshold * 0.5), 0.0, 1.0)
    weight = np.maximum(keep, soft)
    out = alpha_u8.astype(np.float32) * weight
    return np.clip(out, 0, 255).astype(np.uint8)


# ---------------------------------------------------------------------------
# Level & crop: rotate so the thread's centerline is flat-horizontal, then
# crop so left-most and right-most thread pixels are at equal distance from
# top and bottom (thread vertically centered in the frame).
#
# The line fit uses ONLY the "thick core" of the thread (high-percentile
# luma + morphological opening + largest connected component) so wispy
# fuzz and stray fibers don't drag the angle. The crop is keyed to that
# same core mask — wisps are allowed to poke outside the crop, not drive it.
# ---------------------------------------------------------------------------

def _core_mask(y_work, core_percentile=90, open_iters=2):
    """Binary mask of the thread's thick core.
    y_work = luma in 'work space' (bright thread on dark bg)."""
    thresh = float(np.percentile(y_work, core_percentile))
    m = y_work >= thresh
    if open_iters > 0:
        m = ndimage.binary_opening(m, structure=np.ones((3, 3), dtype=bool),
                                   iterations=open_iters)
    labels, n = ndimage.label(m, structure=np.ones((3, 3), dtype=bool))
    if n == 0:
        return np.zeros_like(m, dtype=bool)
    sizes = np.bincount(labels.ravel())
    sizes[0] = 0
    return labels == int(np.argmax(sizes))


def level_and_crop(img_rgb, invert=False, pad_ratio=0.25, core_percentile=90):
    """Rotate to flat-horizontal + vertically center the thread body.

    Returns (cropped_rgb, meta). If no core CC can be found the input is
    returned unchanged with angle=0, bbox=None.
    """
    y = luma(img_rgb)
    yw = (255.0 - y) if invert else y

    core = _core_mask(yw, core_percentile=core_percentile)
    if not core.any():
        return img_rgb, {"angle_deg": 0.0, "bbox": None,
                         "thread_height": 0, "cropped": False}

    # Per-column centroid of the core — uses only thick-core pixels, so
    # wispy fibers don't contribute. Line fit through these gives the
    # true thread angle.
    H, W = core.shape
    row_idx = np.arange(H, dtype=np.float32)[:, None]
    col_sum = core.sum(axis=0).astype(np.float32)
    has_col = col_sum > 0
    xs = np.where(has_col)[0].astype(np.float32)
    if xs.size < 20:
        angle_deg = 0.0
    else:
        col_y = (row_idx * core.astype(np.float32)).sum(axis=0) / np.maximum(col_sum, 1e-6)
        ys = col_y[has_col]
        slope, _intercept = np.polyfit(xs, ys, 1)
        # Image y increases downward; PIL.rotate(angle) is CCW when looking
        # at the image. Positive slope (thread goes down-right) needs a
        # CCW rotation to level -> positive angle passed to PIL.
        angle_deg = float(np.degrees(np.arctan(slope)))

    if abs(angle_deg) > 1e-3:
        pil = Image.fromarray(img_rgb).rotate(
            angle_deg, resample=Image.BILINEAR, expand=True, fillcolor=(0, 0, 0)
        )
        rotated = np.asarray(pil)
    else:
        rotated = img_rgb

    # Recompute core on the rotated image for an accurate bbox.
    y2 = luma(rotated)
    yw2 = (255.0 - y2) if invert else y2
    core2 = _core_mask(yw2, core_percentile=core_percentile)
    if not core2.any():
        return rotated, {"angle_deg": round(angle_deg, 3), "bbox": None,
                         "thread_height": 0, "cropped": False}

    ys_any, xs_any = np.where(core2)
    y0, y1 = int(ys_any.min()), int(ys_any.max())
    x0, x1 = int(xs_any.min()), int(xs_any.max())
    thread_height = y1 - y0 + 1
    y_center = (y0 + y1) // 2
    pad = max(8, int(thread_height * pad_ratio))

    Hr, Wr = rotated.shape[:2]
    # Symmetric vertical crop around the centerline: same distance from
    # top and bottom (clamped to image edges).
    half = thread_height // 2 + pad
    half = min(half, y_center, Hr - 1 - y_center)
    crop_y0 = max(0, y_center - half)
    crop_y1 = min(Hr, y_center + half + 1)
    # Horizontal crop: thread's full extent (no extra padding — thread
    # enters left edge and exits right edge).
    crop_x0 = max(0, x0)
    crop_x1 = min(Wr, x1 + 1)

    cropped = rotated[crop_y0:crop_y1, crop_x0:crop_x1]
    return cropped, {
        "angle_deg": round(angle_deg, 3),
        "bbox": [crop_x0, crop_y0, crop_x1, crop_y1],
        "thread_height": int(thread_height),
        "cropped": True,
        "cropped_size": [int(crop_x1 - crop_x0), int(crop_y1 - crop_y0)],
    }


# ---------------------------------------------------------------------------
# Orientation detection (pipeline needs the thread running horizontally)
# ---------------------------------------------------------------------------

def detect_orientation(img_rgb):
    """Return ("horizontal"|"vertical", ratio).

    ratio = (variance along the presumed long axis) /
            (variance across the presumed long axis)
    A thread running horizontally has much higher variance ACROSS rows
    (dark bg rows vs bright thread rows) than along rows (each row is
    fairly uniform once you pick one). We measure both orientations and
    pick whichever gives the larger across/along ratio.

    Aspect ratio alone isn't sufficient — e.g. some cropped horizontal
    samples are actually square-ish but the thread is still horizontal.
    """
    y = luma(img_rgb).astype(np.float32)
    row_mean = y.mean(axis=1)  # per-row mean (varies with vertical position)
    col_mean = y.mean(axis=0)  # per-column mean (varies with horizontal pos)
    row_var = float(np.var(row_mean))
    col_var = float(np.var(col_mean))
    # If thread is horizontal, rows differ a lot (bg vs thread rows) -> row_var high.
    # If thread is vertical, columns differ a lot -> col_var high.
    if row_var >= col_var:
        return "horizontal", row_var / max(1e-6, col_var)
    return "vertical", col_var / max(1e-6, row_var)


# ---------------------------------------------------------------------------
# Background classifier
# ---------------------------------------------------------------------------

def _bimodality_gap(y_work):
    """Separation between thread-row peak and bg-row mean in the given space.
    Higher = cleaner separation (thread is bright, bg is dark)."""
    score = row_thread_score(y_work)
    if score.max() <= 0:
        return 0.0
    thread_mask = score > 0.20
    if not thread_mask.any() or thread_mask.all():
        return 0.0
    th_peak = float(np.percentile(y_work[thread_mask], 95))
    bg_mean = float(y_work[~thread_mask].mean())
    return th_peak - bg_mean


def classify(img_rgb):
    """Pick one of {white_bg, black_bg} by combining four cheap signals.

    Returns (preset, confidence, signals). `confidence` is in [0, 1] —
    the weighted share of signals that voted for the chosen preset.
    Callers should treat confidence < ~0.6 as "unsure; ask user".
    """
    y = luma(img_rgb)
    H, W = y.shape
    ch, cw = max(1, H // 20), max(1, W // 20)

    corners = np.concatenate([
        y[:ch, :cw].ravel(),
        y[:ch, -cw:].ravel(),
        y[-ch:, :cw].ravel(),
        y[-ch:, -cw:].ravel(),
    ])
    corner_median = float(np.median(corners))

    mean_y = float(y.mean())

    gap_bright = _bimodality_gap(y)          # bg is already dark + thread bright
    gap_inv = _bimodality_gap(255.0 - y)     # bg bright -> invert gives thread bright

    gx = np.abs(np.diff(y, axis=1))
    edge_density_top = float(np.mean(gx[:ch, :]))
    edge_density_mid = float(np.mean(gx[H // 3: 2 * H // 3, :]))
    edges_concentrate_center = edge_density_mid > edge_density_top * 1.5

    # 4 weighted votes. Each returns (vote_black_bg, strength in [0,1]).
    votes = []

    # 1. corner brightness: <50 strongly black, >200 strongly white
    strength = min(1.0, abs(corner_median - 128.0) / 100.0)
    votes.append((corner_median < 128.0, strength, "corner_median", corner_median))

    # 2. whole-image mean: same direction as corners but weaker
    strength = min(1.0, abs(mean_y - 128.0) / 80.0)
    votes.append((mean_y < 128.0, strength * 0.7, "mean_luma", mean_y))

    # 3. bimodality: whichever direction gives the larger gap wins
    gap_margin = abs(gap_bright - gap_inv)
    strength = min(1.0, gap_margin / 80.0)
    votes.append((gap_bright >= gap_inv, strength, "bimodality_gap",
                  {"bright": gap_bright, "inverted": gap_inv}))

    # 4. edge-density concentration: real thread rows cluster in the middle.
    #    Only informative if the concentration signal is strong — acts as a
    #    tiebreaker, not a primary signal.
    if edges_concentrate_center:
        # Threads in middle, bg in corners — corners tell us the bg color.
        strength = 0.3
        votes.append((corner_median < 128.0, strength, "edges_center",
                      {"top": edge_density_top, "mid": edge_density_mid}))
    else:
        votes.append((None, 0.0, "edges_center",
                      {"top": edge_density_top, "mid": edge_density_mid}))

    score_black = sum(s for v, s, _, _ in votes if v is True)
    score_white = sum(s for v, s, _, _ in votes if v is False)
    total = score_black + score_white
    if total <= 1e-6:
        preset = "black_bg"  # arbitrary fallback
        confidence = 0.0
    else:
        if score_black >= score_white:
            preset = "black_bg"
            confidence = score_black / total
        else:
            preset = "white_bg"
            confidence = score_white / total

    signals = {
        "corner_median": round(corner_median, 1),
        "mean_luma": round(mean_y, 1),
        "bimodality_gap_bright": round(gap_bright, 1),
        "bimodality_gap_inverted": round(gap_inv, 1),
        "edge_density_top": round(edge_density_top, 2),
        "edge_density_mid": round(edge_density_mid, 2),
        "score_black_bg": round(score_black, 3),
        "score_white_bg": round(score_white, 3),
    }
    return preset, round(confidence, 3), signals


# ---------------------------------------------------------------------------
# Preset registry
# ---------------------------------------------------------------------------
# The pipeline stages are identical across presets. Only `invert` + a couple
# of knobs differ. Keep this tiny so adding a third preset later is obvious.
# `gamma` defaults to 1.8 (close to the historical fit against the 005
# manual reference) — per-preset override is available.

PRESETS = {
    "white_bg": {
        "invert": True,
        "gamma": 1.8,
        "hysteresis": {"low": 18, "high": 70},
        "row_clamp": {"score_lo": 0.02, "score_hi": 0.15, "floor": 0.35, "sharpness": 1.0},
        "speckle": {"blur_sigma": 6, "threshold": 25},
        "whitefill": {"bright_thresh": 230, "row_min_frac": 0.35, "feather_sigma": 4, "strength": 1.0},
        "despeckle": {"min_area": 30, "low": 10},
        "kill_bg": {"bright_thresh": 230, "row_min_frac": 0.10, "low": 10},
        "hardcut": 40,
    },
    "black_bg": {
        "invert": False,
        "gamma": 1.8,
        "hysteresis": {"low": 18, "high": 70},
        "row_clamp": {"score_lo": 0.02, "score_hi": 0.15, "floor": 0.35, "sharpness": 1.0},
        "speckle": {"blur_sigma": 6, "threshold": 25},
        "whitefill": {"bright_thresh": 230, "row_min_frac": 0.35, "feather_sigma": 4, "strength": 1.0},
        "despeckle": {"min_area": 30, "low": 10},
        "kill_bg": {"bright_thresh": 230, "row_min_frac": 0.10, "low": 10},
        "hardcut": 40,
    },
}


def _deep_merge(base, override):
    """Merge `override` onto a copy of `base` (one level deep for nested dicts)."""
    out = {k: (dict(v) if isinstance(v, dict) else v) for k, v in base.items()}
    if not override:
        return out
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k].update(v)
        else:
            out[k] = v
    return out


# ---------------------------------------------------------------------------
# Top-level run
# ---------------------------------------------------------------------------

def preprocess(src_path, dst_path, preset=None, orientation="auto", level=True):
    """Run only the preprocess stages: orientation rotate + level + crop.
    Writes a leveled/cropped RGB image. No alpha is produced.

    This is the first step of the full yarn pipeline; it produces the RGB
    source that "make seamless" then consumes. Classification is used only
    to pick the correct `invert` flag for the core detection — no alpha
    stages run.
    """
    img = np.asarray(Image.open(src_path).convert("RGB"))

    if orientation == "auto":
        detected_orientation, orient_ratio = detect_orientation(img)
    else:
        detected_orientation = orientation
        orient_ratio = None
    if detected_orientation == "vertical":
        img = np.rot90(img, k=-1)

    chosen_preset, confidence, signals = classify(img)
    active_preset = preset if (preset and preset != "auto") else chosen_preset
    if active_preset not in PRESETS:
        raise ValueError(f"Unknown preset: {active_preset}")

    if level:
        img, level_meta = level_and_crop(img, invert=PRESETS[active_preset]["invert"])
    else:
        level_meta = {"angle_deg": 0.0, "bbox": None, "thread_height": 0, "cropped": False}

    Image.fromarray(img).save(dst_path)
    return {
        "auto_preset": chosen_preset,
        "active_preset": active_preset,
        "confidence": confidence,
        "signals": signals,
        "orientation": detected_orientation,
        "orientation_ratio": round(float(orient_ratio), 2) if orient_ratio is not None else None,
        "level": level_meta,
        "output": dst_path,
    }


def run(src_path, dst_path, preset=None, overrides=None, orientation="auto", level=True):
    img = np.asarray(Image.open(src_path).convert("RGB"))

    # Normalize to horizontal (thread runs left-to-right) before processing.
    # Output is always written horizontally.
    if orientation == "auto":
        detected_orientation, orient_ratio = detect_orientation(img)
    else:
        detected_orientation = orientation
        orient_ratio = None
    if detected_orientation == "vertical":
        img = np.rot90(img, k=-1)  # 90° clockwise -> vertical becomes horizontal

    chosen_preset, confidence, signals = classify(img)
    if preset and preset != "auto":
        active_preset = preset
        auto_preset = chosen_preset
    else:
        active_preset = chosen_preset
        auto_preset = chosen_preset

    if active_preset not in PRESETS:
        raise ValueError(f"Unknown preset: {active_preset}")

    cfg = _deep_merge(PRESETS[active_preset], overrides or {})

    # Level (flatten) + crop using the thick-core centerline. This runs
    # on the RGB image before any alpha stages, so BP/WP/hysteresis all
    # see a properly-centered thread.
    if level:
        img, level_meta = level_and_crop(img, invert=cfg["invert"])
    else:
        level_meta = {"angle_deg": 0.0, "bbox": None, "thread_height": 0,
                      "cropped": False}

    y = luma(img)
    yw = (255.0 - y) if cfg["invert"] else y

    # Optional manual BP/WP overrides. If not provided, auto-compute.
    if "bp" in cfg and "wp" in cfg and cfg["bp"] is not None and cfg["wp"] is not None:
        bp, wp = float(cfg["bp"]), float(cfg["wp"])
        n_thread = -1
    else:
        bp, wp, n_thread = compute_bp_wp(yw)

    score = row_thread_score(yw, smooth_rows=15)
    out = levels(yw, bp, wp, cfg["gamma"])
    out = hysteresis_clean(out, **cfg["hysteresis"])
    out = bg_row_clamp(out, score, **cfg["row_clamp"])
    out = speckle_snap(out, **cfg["speckle"])
    out = core_whitefill(out, **cfg["whitefill"])
    out = despeckle(out, **cfg["despeckle"])
    out = kill_bg_ccs(out, **cfg["kill_bg"])
    out = hard_low_cut(out, cutoff=int(cfg["hardcut"]))
    Image.fromarray(out).save(dst_path)

    return {
        "auto_preset": auto_preset,
        "active_preset": active_preset,
        "confidence": confidence,
        "signals": signals,
        "orientation": detected_orientation,
        "orientation_ratio": round(float(orient_ratio), 2) if orient_ratio is not None else None,
        "level": level_meta,
        "bp": round(float(bp), 2),
        "wp": round(float(wp), 2),
        "gamma": cfg["gamma"],
        "hardcut_cutoff": int(cfg["hardcut"]),
        "thread_rows": int(n_thread),
        "output": dst_path,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("output")
    ap.add_argument("--preset", choices=["auto", "white_bg", "black_bg"], default="auto")
    ap.add_argument("--bp", type=float, default=None, help="Manual black point override")
    ap.add_argument("--wp", type=float, default=None, help="Manual white point override")
    ap.add_argument("--gamma", type=float, default=None, help="Manual gamma override")
    ap.add_argument("--hardcut-cutoff", type=int, default=None,
                    help="Cutoff for the final hardcut stage (0-255). Default per preset.")
    ap.add_argument("--orientation", choices=["auto", "horizontal", "vertical"], default="auto",
                    help="Input orientation. 'vertical' rotates 90° CW so thread is horizontal.")
    ap.add_argument("--no-level", action="store_true",
                    help="Skip the level+crop step (thread centerline leveling).")
    ap.add_argument("--preprocess-only", action="store_true",
                    help="Run only orientation + level + crop. Output is an RGB image, not an alpha.")
    ap.add_argument("--classify-only", action="store_true",
                    help="Run only the classifier, don't write output")
    args = ap.parse_args()

    if args.classify_only:
        img = np.asarray(Image.open(args.input).convert("RGB"))
        preset, confidence, signals = classify(img)
        print(json.dumps({"auto_preset": preset, "confidence": confidence, "signals": signals}))
        return

    if args.preprocess_only:
        meta = preprocess(args.input, args.output,
                          preset=args.preset,
                          orientation=args.orientation,
                          level=not args.no_level)
        print(json.dumps(meta))
        return

    overrides = {}
    if args.bp is not None:
        overrides["bp"] = args.bp
    if args.wp is not None:
        overrides["wp"] = args.wp
    if args.gamma is not None:
        overrides["gamma"] = args.gamma
    if args.hardcut_cutoff is not None:
        overrides["hardcut"] = args.hardcut_cutoff

    meta = run(args.input, args.output,
               preset=args.preset,
               overrides=overrides or None,
               orientation=args.orientation,
               level=not args.no_level)
    print(json.dumps(meta))


if __name__ == "__main__":
    try:
        _main()
    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)
