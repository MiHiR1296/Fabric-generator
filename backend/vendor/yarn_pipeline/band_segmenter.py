"""
Band segmenter — Phase 2 of the 2-arc UV pipeline.

Given a yarn image already processed by `yarn_pipeline.py` (so the thread is
horizontal, centered, and we have an alpha matte), split it into two
V-bands for the procedural-weave knotty geometry node group:

    - core band  : the thick body of the yarn (Arc 1 samples this)
    - fiber band : the wispy halo above + below the core (Arc 2 samples this)

Outputs per yarn (under {output_dir}/{name}/):

    normal.png       normal map (luma -> sobel)    — RGB
    roughness.png    inverse-luma roughness        — L
    overlay.png      QA visualization              — RGB
    meta.json        band V-ranges + Blender Map Range recipes for both arcs

The Blender material samples the original (rgb, alpha) directly; per-arc
V-band selection is done by a Map Range node using values from meta.json.
No band-cropped PNGs are written — they would just duplicate data already
present in the source pair.

CLI:

    # Single pair
    python band_segmenter.py RGB ALPHA OUTPUT_DIR
        [--core-frac 0.5] [--fiber-frac 0.02] [--normal-strength 4.0]

    # Batch (pairs by basename: foo_seamless.png + foo_alpha.png -> foo)
    python band_segmenter.py --batch RGB_DIR ALPHA_DIR OUTPUT_DIR
"""
import argparse
import json
import os
import re
import sys
from typing import Optional

import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy import ndimage

import alpha_pipeline  # reuse luma() + row_thread_score()


# ---------------------------------------------------------------------------
# Band detection
# ---------------------------------------------------------------------------

def detect_bands(alpha_u8: np.ndarray, core_frac: float = 0.5,
                 fiber_frac: float = 0.02) -> dict:
    """Find core + fiber V-bands from an alpha matte.

    `core_frac`  — fraction of peak per-row density that defines the core
                   band (FWHM-like; default 0.5 ~= half-max).
    `fiber_frac` — noise floor below which we stop calling pixels "fiber".

    Returns a dict with pixel and normalized V-ranges plus the per-row
    density curve used (for QA / debugging).
    """
    H, W = alpha_u8.shape
    a = (alpha_u8.astype(np.float32) / 255.0)
    density = (a > 0.5).mean(axis=1).astype(np.float32)
    # mild smooth so single-pixel dropouts don't fragment the core run
    if H >= 9:
        k = np.ones(7, dtype=np.float32) / 7
        density = np.convolve(density, k, mode="same")

    peak = float(density.max())
    if peak <= 0:
        # degenerate — no thread; whole image is "core"
        return {
            "density": density.tolist(),
            "peak_density": 0.0,
            "core_v_range_px": [0, H - 1],
            "fiber_top_v_range_px": [0, 0],
            "fiber_bot_v_range_px": [H - 1, H - 1],
        }

    core_thresh = core_frac * peak
    fiber_thresh = fiber_frac * peak

    # Core band = LARGEST contiguous run above core_thresh
    above_core = density >= core_thresh
    core_y0, core_y1 = _largest_run(above_core)
    if core_y0 is None:
        # fallback: peak row + 1px each side
        peak_row = int(np.argmax(density))
        core_y0 = max(0, peak_row - 1)
        core_y1 = min(H - 1, peak_row + 1)

    # Fiber bands = above/below core, until density drops below fiber_thresh
    above_fiber = density >= fiber_thresh
    # walk up from core_y0
    fiber_top_y0 = core_y0
    while fiber_top_y0 > 0 and above_fiber[fiber_top_y0 - 1]:
        fiber_top_y0 -= 1
    # walk down from core_y1
    fiber_bot_y1 = core_y1
    while fiber_bot_y1 < H - 1 and above_fiber[fiber_bot_y1 + 1]:
        fiber_bot_y1 += 1

    return {
        "density": density.tolist(),
        "peak_density": peak,
        "core_v_range_px": [int(core_y0), int(core_y1)],
        "fiber_top_v_range_px": [int(fiber_top_y0), int(core_y0)],
        "fiber_bot_v_range_px": [int(core_y1), int(fiber_bot_y1)],
        "core_thresh": float(core_thresh),
        "fiber_thresh": float(fiber_thresh),
    }


def _largest_run(boolean_1d: np.ndarray):
    """Return (start, end) inclusive of the longest True-run, or (None, None)."""
    if not boolean_1d.any():
        return None, None
    labels, n = ndimage.label(boolean_1d)
    sizes = np.bincount(labels.ravel())
    sizes[0] = 0
    best = int(np.argmax(sizes))
    idx = np.where(labels == best)[0]
    return int(idx.min()), int(idx.max())


# ---------------------------------------------------------------------------
# Twist period detection (along U)
# ---------------------------------------------------------------------------

def detect_twist_period(rgb_u8: np.ndarray, alpha_u8: np.ndarray,
                        core_y0: int, core_y1: int,
                        min_twists: int = 4) -> dict:
    """FFT-based ply-twist period detection along the strand's length axis.

    Strand ply twists produce a quasi-periodic luma oscillation along U at
    the core centerline. Finding the dominant FFT bin tells us:
      * twists_in_image_width  (how many twists across the full image)
      * twist_period_px         (image_width / twists)

    Algorithm:
      1. Take the core band (alpha-weighted average across V).
      2. Detrend (subtract mean) and apply a Hann window.
      3. rfft -> magnitude spectrum.
      4. Ignore DC + first `min_twists` bins (rules out smooth gradients).
      5. Pick the largest peak; report its frequency, period, and
         a confidence = (peak - local_mean) / peak.
    """
    y = (0.2126 * rgb_u8[..., 0] + 0.7152 * rgb_u8[..., 1]
         + 0.0722 * rgb_u8[..., 2]).astype(np.float32)
    band = y[core_y0:core_y1 + 1]
    a = (alpha_u8[core_y0:core_y1 + 1].astype(np.float32) / 255.0)

    # Alpha-weighted column mean along V (so background noise above/below
    # the core doesn't poison the FFT).
    weights_sum = a.sum(axis=0)
    weighted = (band * a).sum(axis=0) / np.maximum(weights_sum, 1e-6)

    # Skip columns with no thread coverage (start/end edges)
    valid = weights_sum > (a.shape[0] * 0.2)
    if valid.sum() < 64:
        return {"twist_period_px": None, "twists_in_image_width": None,
                "confidence": 0.0, "note": "insufficient core coverage"}

    signal = weighted[valid].astype(np.float64)
    n = signal.size
    signal = signal - signal.mean()
    # Hann window reduces spectral leakage from the finite-length signal
    window = 0.5 - 0.5 * np.cos(2 * np.pi * np.arange(n) / max(1, n - 1))
    signal *= window

    spectrum = np.abs(np.fft.rfft(signal))
    if spectrum.size <= min_twists + 2:
        return {"twist_period_px": None, "twists_in_image_width": None,
                "confidence": 0.0, "note": "signal too short"}

    spectrum[:min_twists + 1] = 0  # kill DC + low freq

    peak_bin = int(np.argmax(spectrum))
    if peak_bin == 0 or spectrum[peak_bin] <= 0:
        return {"twist_period_px": None, "twists_in_image_width": None,
                "confidence": 0.0, "note": "no dominant peak"}

    # In a Hann-windowed rfft of length n on a `valid`-sample signal,
    # peak_bin = number of full cycles across the windowed signal.
    # Scale back to full image width:
    image_width = rgb_u8.shape[1]
    twists_in_valid = float(peak_bin)
    twists_in_image = twists_in_valid * image_width / n

    period_px = image_width / max(twists_in_image, 1e-6)

    # Confidence: peak prominence vs immediate neighborhood (excluding self)
    nb_radius = max(2, peak_bin // 8)
    lo = max(1, peak_bin - nb_radius)
    hi = min(spectrum.size, peak_bin + nb_radius + 1)
    neighborhood = np.concatenate([spectrum[lo:peak_bin], spectrum[peak_bin + 1:hi]])
    peak_val = float(spectrum[peak_bin])
    if neighborhood.size > 0 and peak_val > 0:
        confidence = float((peak_val - neighborhood.mean()) / peak_val)
    else:
        confidence = 0.0

    # Top 5 candidate periods (in case primary is wrong)
    top5_bins = np.argsort(spectrum)[-5:][::-1]
    top5 = []
    for b in top5_bins:
        if b <= 0 or spectrum[b] <= 0:
            continue
        t = float(b) * image_width / n
        top5.append({"twists_in_image": round(t, 2),
                     "period_px": round(image_width / max(t, 1e-6), 2),
                     "magnitude": round(float(spectrum[b]), 1)})

    return {
        "twist_period_px": round(float(period_px), 2),
        "twists_in_image_width": round(float(twists_in_image), 2),
        "confidence": round(confidence, 3),
        "top_5_candidates": top5,
        "fft_window_size": int(n),
    }


# ---------------------------------------------------------------------------
# Map generation
# ---------------------------------------------------------------------------

def normal_from_luma(rgb_u8: np.ndarray, alpha_u8: Optional[np.ndarray] = None,
                     strength: float = 4.0) -> np.ndarray:
    """Cheap normal map from luma-as-height. Sobel gradients, encoded RGB.

    Background pixels (where alpha is ~0) are flattened to neutral normal
    (128, 128, 255) so they don't bleed bogus shading into the material.
    """
    h = alpha_pipeline.luma(rgb_u8.astype(np.float32)) / 255.0
    # mild blur to denoise scanner texture before differentiating
    pil = Image.fromarray((h * 255).astype(np.uint8)).filter(
        ImageFilter.GaussianBlur(radius=1.2))
    h = np.asarray(pil, dtype=np.float32) / 255.0

    sobel_x = ndimage.sobel(h, axis=1) * strength
    sobel_y = ndimage.sobel(h, axis=0) * strength
    nx = -sobel_x
    ny = -sobel_y
    nz = np.ones_like(nx)
    norm = np.sqrt(nx * nx + ny * ny + nz * nz)
    nx, ny, nz = nx / norm, ny / norm, nz / norm

    rgb = np.stack([
        ((nx * 0.5) + 0.5) * 255.0,
        ((ny * 0.5) + 0.5) * 255.0,
        ((nz * 0.5) + 0.5) * 255.0,
    ], axis=-1)
    rgb = np.clip(rgb, 0, 255).astype(np.uint8)

    if alpha_u8 is not None:
        bg = (alpha_u8 < 8)[..., None]
        flat = np.array([128, 128, 255], dtype=np.uint8)
        rgb = np.where(bg, flat, rgb)
    return rgb


def roughness_from_luma(rgb_u8: np.ndarray, alpha_u8: Optional[np.ndarray] = None,
                        rough_at_dark: float = 0.85,
                        rough_at_bright: float = 0.45) -> np.ndarray:
    """Placeholder roughness: darker pixels are rougher than highlights.

    Mid-grey ~= mid roughness. Background forced to 1.0 (full rough — won't
    matter once the band-cropped material masks it out, but keeps the file
    stand-alone-usable).
    """
    y = alpha_pipeline.luma(rgb_u8.astype(np.float32)) / 255.0
    rough = rough_at_dark + (rough_at_bright - rough_at_dark) * y
    rough = np.clip(rough, 0.0, 1.0)
    out = (rough * 255.0).astype(np.uint8)
    if alpha_u8 is not None:
        out = np.where(alpha_u8 < 8, 255, out).astype(np.uint8)
    return out


# ---------------------------------------------------------------------------
# Per-band crops + overlays
# ---------------------------------------------------------------------------

def make_overlay(rgb_u8: np.ndarray, bands: dict) -> np.ndarray:
    """RGB visualization: original + horizontal lines marking each band.
    core boundaries drawn cyan, fiber band outer edges drawn magenta."""
    pil = Image.fromarray(rgb_u8.copy()).convert("RGB")
    draw = ImageDraw.Draw(pil)
    W = pil.width
    cy0, cy1 = bands["core_v_range_px"]
    fty0, _ = bands["fiber_top_v_range_px"]
    _, fby1 = bands["fiber_bot_v_range_px"]
    draw.line([(0, cy0), (W - 1, cy0)], fill=(0, 255, 255), width=2)
    draw.line([(0, cy1), (W - 1, cy1)], fill=(0, 255, 255), width=2)
    draw.line([(0, fty0), (W - 1, fty0)], fill=(255, 0, 255), width=1)
    draw.line([(0, fby1), (W - 1, fby1)], fill=(255, 0, 255), width=1)
    return np.asarray(pil)


# ---------------------------------------------------------------------------
# Top-level
# ---------------------------------------------------------------------------

def process(rgb_path: str, alpha_path: str, output_dir: str,
            name: Optional[str] = None,
            core_frac: float = 0.5, fiber_frac: float = 0.02,
            normal_strength: float = 4.0,
            verbose: bool = True) -> dict:
    rgb_img = Image.open(rgb_path)
    if rgb_img.mode == "RGBA":
        rgb_img = rgb_img.convert("RGB")
    elif rgb_img.mode != "RGB":
        rgb_img = rgb_img.convert("RGB")
    rgb = np.asarray(rgb_img)

    alpha_img = Image.open(alpha_path)
    if alpha_img.mode != "L":
        alpha_img = alpha_img.convert("L")
    alpha = np.asarray(alpha_img)

    if alpha.shape != rgb.shape[:2]:
        raise ValueError(
            f"Alpha and RGB sizes mismatch: alpha={alpha.shape} rgb={rgb.shape[:2]}"
            f" (paths: {alpha_path} vs {rgb_path})"
        )

    H, W = alpha.shape
    if name is None:
        name = _derive_name(rgb_path)
    out_dir = os.path.join(output_dir, name)
    os.makedirs(out_dir, exist_ok=True)

    bands = detect_bands(alpha, core_frac=core_frac, fiber_frac=fiber_frac)
    cy0, cy1 = bands["core_v_range_px"]
    fty0, _ = bands["fiber_top_v_range_px"]
    _, fby1 = bands["fiber_bot_v_range_px"]

    twist = detect_twist_period(rgb, alpha, cy0, cy1)

    if verbose:
        print(f"[{name}] {W}x{H}  core=[{cy0},{cy1}] ({cy1 - cy0 + 1}px)"
              f"  fiber_top=[{fty0},{cy0}] ({cy0 - fty0}px)"
              f"  fiber_bot=[{cy1},{fby1}] ({fby1 - cy1}px)")
        if twist.get("twist_period_px"):
            print(f"          twist_period={twist['twist_period_px']}px"
                  f"  twists_in_image={twist['twists_in_image_width']}"
                  f"  confidence={twist['confidence']}")

    # 1. Normal + roughness on the FULL image. Each arc samples its own
    #    V-band from these via the Map Range recipes in meta.json.
    normal = normal_from_luma(rgb, alpha, strength=normal_strength)
    Image.fromarray(normal).save(os.path.join(out_dir, "normal.png"))

    rough = roughness_from_luma(rgb, alpha)
    Image.fromarray(rough).save(os.path.join(out_dir, "roughness.png"))

    # 2. QA overlay
    overlay = make_overlay(rgb, bands)
    Image.fromarray(overlay).save(os.path.join(out_dir, "overlay.png"))

    # 3. Sidecar JSON — Blender Map Range recipes live here. The material
    #    samples (rgb, alpha) directly; per-arc V-band selection is a Map
    #    Range from arc-V [0,1] to image-V [out_min, out_max].
    #
    # IMPORTANT: V is stored in BLENDER convention (V=0 at bottom, V=1 at top).
    # PIL/numpy rows count from the top, so we flip with (1 - row/H).
    # The previously-named "fiber_top" (image rows above the core, lower row
    # indices) becomes the LARGER V band in Blender (above core);
    # "fiber_bot" (rows below core) becomes the SMALLER V band.
    core_v0_n     = 1.0 - cy1 / H        # was cy0/H
    core_v1_n     = 1.0 - cy0 / H        # was cy1/H
    f_top_v0_n    = 1.0 - cy0 / H        # core boundary on top side (lower V → higher V after flip)
    f_top_v1_n    = 1.0 - fty0 / H       # outer top (highest V in image)
    f_bot_v0_n    = 1.0 - fby1 / H       # outer bot (lowest V in image)
    f_bot_v1_n    = 1.0 - cy1 / H        # core boundary on bot side
    meta = {
        "name": name,
        "input": {"rgb": rgb_path, "alpha": alpha_path},
        "image_size_px": [int(W), int(H)],
        "bands_px": {
            "core":      [int(cy0), int(cy1)],
            "fiber_top": [int(fty0), int(cy0)],
            "fiber_bot": [int(cy1), int(fby1)],
        },
        "bands_v_norm": {
            "_convention": "blender (V=0 bottom, V=1 top)",
            "core":      [core_v0_n, core_v1_n],
            "fiber_top": [f_top_v0_n, f_top_v1_n],
            "fiber_bot": [f_bot_v0_n, f_bot_v1_n],
        },
        "thickness_px": {
            "core_height":      int(cy1 - cy0 + 1),
            "fiber_top_height": int(cy0 - fty0),
            "fiber_bot_height": int(fby1 - cy1),
        },
        # Phase 3 reads this. arc-V is the parametric coord along each arc
        # (0 at one strand-edge, 1 at the other). out values are image V
        # (0 = top of source image, 1 = bottom).
        #
        # Arc 1 maps directly to the core band.
        # Arc 2 is wider (radius = main_radius + sub_strand_width). Its V
        # is split into three segments by `r = main_radius / arc2_radius`,
        # so the central `r` fraction of Arc 2 spatially overlaps Arc 1
        # (and samples the core band), while the outer wings sample the
        # fiber halos. The split fractions are computed in the GN graph
        # from the existing sockets — meta.json gives only the band ranges.
        "blender_uv_remap": {
            "source_image": rgb_path,
            "alpha_image":  alpha_path,
            "arc1": {
                "in_min": 0.0, "in_max": 1.0,
                "out_min": core_v0_n, "out_max": core_v1_n,
            },
            "arc2_three_segment": {
                "r_formula": "r = main_radius / (main_radius + sub_strand_width)",
                "top_fiber": {
                    "in_min_expr": "0",
                    "in_max_expr": "(1 - r) / 2",
                    "out_min": f_top_v0_n, "out_max": f_top_v1_n,
                },
                "core": {
                    "in_min_expr": "(1 - r) / 2",
                    "in_max_expr": "(1 + r) / 2",
                    "out_min": core_v0_n, "out_max": core_v1_n,
                },
                "bot_fiber": {
                    "in_min_expr": "(1 + r) / 2",
                    "in_max_expr": "1",
                    "out_min": f_bot_v0_n, "out_max": f_bot_v1_n,
                },
            },
        },
        "twist": twist,
        "outputs": {
            "normal":    os.path.relpath(os.path.join(out_dir, "normal.png")),
            "roughness": os.path.relpath(os.path.join(out_dir, "roughness.png")),
            "overlay":   os.path.relpath(os.path.join(out_dir, "overlay.png")),
        },
        "params": {
            "core_frac": core_frac,
            "fiber_frac": fiber_frac,
            "normal_strength": normal_strength,
        },
    }
    with open(os.path.join(out_dir, "meta.json"), "w") as f:
        json.dump(meta, f, indent=2)

    return meta


def _derive_name(rgb_path: str) -> str:
    """Strip _seamless / _preprocessed / _preproc suffixes for the output name."""
    base = os.path.splitext(os.path.basename(rgb_path))[0]
    return re.sub(r"_(seamless|preprocessed|preproc)$", "", base)


def _pair_dir(rgb_dir: str, alpha_dir: str):
    """Yield (rgb_path, alpha_path, base_name) by matching basename stems.
    Strips known suffixes so foo_seamless.png pairs with foo_alpha.png."""
    rgb_files = {}
    for f in os.listdir(rgb_dir):
        if not f.lower().endswith((".png", ".jpg", ".jpeg", ".tif", ".tiff")):
            continue
        stem = re.sub(r"_(seamless|preprocessed|preproc)$",
                      "", os.path.splitext(f)[0])
        rgb_files[stem] = os.path.join(rgb_dir, f)

    for f in os.listdir(alpha_dir):
        if not f.lower().endswith((".png", ".jpg", ".jpeg")):
            continue
        stem = re.sub(r"_(alpha|matte)$", "", os.path.splitext(f)[0])
        if stem in rgb_files:
            yield rgb_files[stem], os.path.join(alpha_dir, f), stem


def _main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--batch", action="store_true",
                    help="Treat first two positional args as RGB and ALPHA directories.")
    ap.add_argument("rgb", help="RGB image path (or RGB dir if --batch).")
    ap.add_argument("alpha", help="Alpha image path (or ALPHA dir if --batch).")
    ap.add_argument("output_dir", help="Output root. Per-yarn folder is created beneath.")
    ap.add_argument("--core-frac", type=float, default=0.5,
                    help="Density fraction (of peak) defining the core band edge. "
                         "Higher = tighter core. Default 0.5 (FWHM).")
    ap.add_argument("--fiber-frac", type=float, default=0.02,
                    help="Density fraction defining the outer fiber edge. "
                         "Lower = catches more wisps. Default 0.02.")
    ap.add_argument("--normal-strength", type=float, default=4.0)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    if args.batch:
        results = []
        for rgb_p, alpha_p, name in _pair_dir(args.rgb, args.alpha):
            meta = process(rgb_p, alpha_p, args.output_dir, name=name,
                           core_frac=args.core_frac, fiber_frac=args.fiber_frac,
                           normal_strength=args.normal_strength,
                           verbose=not args.quiet)
            results.append({"name": name, "meta": meta})
        print(json.dumps({"count": len(results),
                          "names": [r["name"] for r in results]}))
        return

    meta = process(args.rgb, args.alpha, args.output_dir,
                   core_frac=args.core_frac, fiber_frac=args.fiber_frac,
                   normal_strength=args.normal_strength,
                   verbose=not args.quiet)
    print(json.dumps({"name": meta["name"], "out_dir": os.path.dirname(
        meta["outputs"]["overlay"])}))


if __name__ == "__main__":
    try:
        _main()
    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)
