"""Split a multi-thread scan into N individual thread images and run the
alpha + tilt-correction pipeline on each.

Usage:
    python3 split_threads.py --input 4threads_sprayblackbg.jpg \\
                             --out-dir outputs_4threads --n-threads 4
"""
import argparse
import json
import os
import numpy as np
from PIL import Image, ImageDraw
from scipy import signal

import alpha_pipeline
import solid_band

try:
    from app.yarnseamless import thread_segmentation
except Exception:  # pragma: no cover - CLI fallback from this folder
    thread_segmentation = None


def _smooth_1d(values, window=21):
    arr = np.asarray(values, dtype=np.float32)
    if arr.size == 0:
        return arr
    window = min(int(window), arr.size)
    if window % 2 == 0:
        window -= 1
    if window < 3:
        return arr.copy()
    pad = window // 2
    padded = np.pad(arr, (pad, pad), mode="edge")
    kernel = np.ones(window, dtype=np.float32) / float(window)
    return np.convolve(padded, kernel, mode="valid").astype(np.float32)


def _robust_high_score(values):
    arr = np.asarray(values, dtype=np.float32)
    median = float(np.median(arr))
    mad = float(np.median(np.abs(arr - median)))
    scale = max(mad * 1.4826, float(arr.std()) * 0.15, 1e-3)
    return np.clip((arr - median) / scale, 0.0, None).astype(np.float32)


def _filter_edge_peaks(peaks, props, width, min_dist):
    # Convolution and scanner borders can create strong artificial edge peaks.
    edge_margin = min(max(8, min_dist // 2), max(0, width // 10))
    if edge_margin <= 0 or peaks.size == 0:
        return peaks, props
    keep = (peaks >= edge_margin) & (peaks < width - edge_margin)
    return peaks[keep], {key: val[keep] for key, val in props.items()}


def _merge_nearby_peaks(peaks, profile, min_dist):
    """Collapse double-peaks from the two edges of one thick/fuzzy yarn."""
    peaks = np.sort(np.asarray(peaks, dtype=np.int64))
    if peaks.size <= 1:
        return peaks.astype(int)

    gaps = np.diff(peaks)
    large_gaps = gaps[gaps > min_dist * 1.5]
    typical_gap = float(np.median(large_gaps if large_gaps.size else gaps))
    merge_dist = min(
        max(float(min_dist) * 1.5, typical_gap * 0.28),
        max(80.0, float(profile.size) * 0.04),
    )

    merged = []
    group = [int(peaks[0])]
    for peak in peaks[1:]:
        peak = int(peak)
        if peak - group[-1] <= merge_dist:
            group.append(peak)
        else:
            merged.append(max(group, key=lambda p: float(profile[p])))
            group = [peak]
    merged.append(max(group, key=lambda p: float(profile[p])))
    return np.asarray(merged, dtype=int)


def _thread_column_profile(img_rgb):
    col_rgb = img_rgb.mean(axis=0, dtype=np.float32)
    col_rgb_smooth = np.stack(
        [_smooth_1d(col_rgb[:, c], 21) for c in range(3)],
        axis=1,
    )
    col_luma = (0.2126 * col_rgb_smooth[:, 0]
                + 0.7152 * col_rgb_smooth[:, 1]
                + 0.0722 * col_rgb_smooth[:, 2]).astype(np.float32)
    bg_luma = float(np.median(col_luma))
    bg_rgb = np.median(col_rgb_smooth, axis=0).astype(np.float32)

    mean_score = np.maximum(
        _robust_high_score(np.abs(col_luma - bg_luma)),
        _robust_high_score(np.linalg.norm(col_rgb_smooth - bg_rgb, axis=1)),
    )

    # Full-height means can hide broken or low-density threads.  Sample rows and
    # use a high percentile so a column with intermittent yarn still votes.
    max_sample_rows = 1024
    row_step = max(1, int(np.ceil(img_rgb.shape[0] / float(max_sample_rows))))
    sample = img_rgb[::row_step].astype(np.float32)
    sample_luma = (0.2126 * sample[..., 0]
                   + 0.7152 * sample[..., 1]
                   + 0.0722 * sample[..., 2]).astype(np.float32)
    luma_q = np.percentile(np.abs(sample_luma - bg_luma), 75, axis=0)

    chroma = sample[..., 0] - bg_rgb[0]
    chroma *= chroma
    tmp = sample[..., 1] - bg_rgb[1]
    chroma += tmp * tmp
    tmp = sample[..., 2] - bg_rgb[2]
    chroma += tmp * tmp
    np.sqrt(chroma, out=chroma)
    chroma_q = np.percentile(chroma, 75, axis=0)

    quantile_score = np.maximum(
        _robust_high_score(luma_q),
        _robust_high_score(chroma_q),
    )
    return _smooth_1d(np.maximum(mean_score, quantile_score), 9)


def detect_thread_columns(img_rgb, n_threads=None):
    """Find x-positions of vertical threads via contrast-aware peak detection.

    If `n_threads` is given, returns the top-N peaks by prominence (sorted by x).
    If `n_threads` is None, returns ALL peaks above the prominence floor
    (auto-detect — the count is whatever the image actually has).
    Returns (peak_xs, detection_profile).

    Older scans used bright yarn on dark cards, so luma maxima were enough.
    Cheque scans can contain dark or saturated yarn on a light/coloured card,
    where the thread is a luma trough or mostly a chroma change.  We therefore
    score each column by deviation from the scan background in both luma and
    RGB column colour.
    """
    if thread_segmentation is not None:
        layout = thread_segmentation.detect_threads(img_rgb, n_threads)
        if layout.failure_reason:
            raise RuntimeError(layout.failure_reason)
        return np.asarray(layout.peaks, dtype=int), layout.profile

    detection_profile = _thread_column_profile(img_rgb)
    W = detection_profile.size
    # For min_dist, assume up to ~16 threads when auto-detecting.
    nt_for_dist = n_threads if n_threads else 16
    min_dist = max(20, W // (nt_for_dist * 4))
    prom_floor = max(0.6, float(detection_profile.std()) * 0.25)
    peaks, props = signal.find_peaks(detection_profile, distance=min_dist,
                                     prominence=prom_floor)
    peaks, props = _filter_edge_peaks(peaks, props, W, min_dist)
    peaks = _merge_nearby_peaks(peaks, detection_profile, min_dist)
    if n_threads is None:
        # Auto: return everything found, sorted left-to-right.
        return np.sort(peaks), detection_profile
    if len(peaks) < n_threads:
        for relaxed_prom in (prom_floor * 0.5, prom_floor * 0.25, 0.1, 0.03):
            peaks, props = signal.find_peaks(
                detection_profile,
                distance=min_dist,
                prominence=relaxed_prom,
            )
            peaks, props = _filter_edge_peaks(peaks, props, W, min_dist)
            peaks = _merge_nearby_peaks(peaks, detection_profile, min_dist)
            if len(peaks) >= n_threads:
                break
    if len(peaks) < n_threads:
        raise RuntimeError(
            f"Detected only {len(peaks)} thread peaks, expected at least "
            f"{n_threads}. Try a lower thread count or improve scan contrast.")
    top_idx = np.argsort(detection_profile[peaks])[-n_threads:]
    return np.sort(peaks[top_idx]), detection_profile


def detect_thread_layout(img_rgb, n_threads=None):
    """Return the full segmentation-first detection result.

    Kept separate from `detect_thread_columns` so the web route can report QA
    metadata while older callers continue to receive `(peaks, profile)`.
    """
    if thread_segmentation is None:
        peaks, profile = detect_thread_columns(img_rgb, n_threads)
        return {
            "peaks": [int(p) for p in peaks],
            "profile": profile,
            "failure_reason": None,
        }
    return thread_segmentation.detect_threads(img_rgb, n_threads)


def split_into_strips(img_rgb, peaks):
    """Slice into N strips, each centered on a peak with width = median peak
    spacing. Returns list of (x0, x1, strip_array)."""
    H, W = img_rgb.shape[:2]
    if len(peaks) > 1:
        spacing = float(np.median(np.diff(peaks)))
    else:
        spacing = float(W)
    half = int(round(spacing / 2.0))

    strips = []
    for p in peaks:
        x0 = max(0, int(p) - half)
        x1 = min(W, int(p) + half)
        strips.append((x0, x1, img_rgb[:, x0:x1]))
    return strips


def save_detection_overlay(img_rgb, peaks, strips, out_path):
    overlay = Image.fromarray(img_rgb).convert("RGB").copy()
    draw = ImageDraw.Draw(overlay)
    H, W = img_rgb.shape[:2]
    for p in peaks:
        draw.line([(int(p), 0), (int(p), H - 1)], fill=(0, 255, 0), width=8)
    for x0, x1, _ in strips:
        for x in (x0, x1):
            x_clamped = max(0, min(W - 1, x))
            draw.line([(x_clamped, 0), (x_clamped, H - 1)],
                      fill=(255, 0, 0), width=4)
    overlay.save(out_path)


def process_multi_thread_scan(input_path, out_dir, n_threads=4, verbose=True):
    """Top-level entry point. Splits the input scan into N threads and runs
    the alpha + tilt + solid-band-detection pipeline on each.

    Writes to <out_dir>:
        detection_overlay.png         - input with peak/strip boundaries drawn
        raw_strips/thread_<i>.png     - raw vertical slices
        thread_<i>_leveled.png        - oriented horizontal + tilt-corrected
                                        + cropped RGB
        thread_<i>_alpha.png          - alpha mask for the leveled image
        thread_<i>_c_visualization.png- leveled image + 1-px red top/bottom
                                        lines from approach C
        thread_<i>_d_visualization.png- same with approach D
        summary.json                  - all per-thread metadata

    Returns the summary dict (also written to summary.json). Per-thread
    fields:
        index             - 0..n_threads-1
        x_range           - [x0, x1] in original image coords
        raw_size          - [W, H] of the sliced strip
        orientation       - 'vertical' or 'horizontal' (always 'vertical'
                            for these scans, which are then rotated 90 CW)
        tilt_angle_deg    - residual tilt corrected by alpha_pipeline
        leveled_size      - [W, H] after orientation + level + crop
        auto_preset       - 'black_bg' or 'white_bg' chosen by classifier
        preset_confidence - 0..1
        c_band            - {top_y, bottom_y, height} from approach C, or
                            {top_y: -1, bottom_y: -1, height: -1} if C
                            failed (no row hit the strict threshold)
        d_band            - same shape, from approach D
    """
    os.makedirs(out_dir, exist_ok=True)
    raw_dir = os.path.join(out_dir, "raw_strips")
    os.makedirs(raw_dir, exist_ok=True)

    img = np.asarray(Image.open(input_path).convert("RGB"))
    H, W = img.shape[:2]
    if verbose:
        print(f"[info] input: {W}x{H}")

    peaks, _ = detect_thread_columns(img, n_threads)
    if verbose:
        print(f"[info] detected thread x-positions: {peaks.tolist()}")

    strips = split_into_strips(img, peaks)
    save_detection_overlay(img, peaks, strips,
                           os.path.join(out_dir, "detection_overlay.png"))

    summary = {
        "input": input_path,
        "input_size": [W, H],
        "peaks": [int(p) for p in peaks],
        "threads": [],
    }

    for i, (x0, x1, strip) in enumerate(strips):
        raw_path = os.path.join(raw_dir, f"thread_{i}.png")
        Image.fromarray(strip).save(raw_path)
        if verbose:
            print(f"[thread {i}] x={x0}-{x1} ({x1-x0}px wide, "
                  f"{strip.shape[0]}px tall)")

        leveled_path = os.path.join(out_dir, f"thread_{i}_leveled.png")
        alpha_pipeline.preprocess(raw_path, leveled_path, preset="auto",
                                  orientation="auto", level=True)

        alpha_path = os.path.join(out_dir, f"thread_{i}_alpha.png")
        meta = alpha_pipeline.run(raw_path, alpha_path, preset="auto",
                                  orientation="auto", level=True)

        alpha_arr = np.asarray(Image.open(alpha_path).convert("L"))
        leveled_arr = np.asarray(Image.open(leveled_path).convert("RGB"))
        if thread_segmentation is not None:
            band_result = thread_segmentation.detect_band_quality(alpha_arr)
            c_res = band_result["c_band"]
            d_res = band_result["d_band"]
        else:
            c_res = solid_band.approach_c_longest_run(alpha_arr)
            d_res = solid_band.approach_d_combined_smoothed(alpha_arr)
        solid_band.save_visualization(
            f"thread_{i}", c_res["top_y"], c_res["bottom_y"],
            leveled_arr, out_dir=out_dir, line_width=1,
            suffix="_c_visualization")
        solid_band.save_visualization(
            f"thread_{i}", d_res["top_y"], d_res["bottom_y"],
            leveled_arr, out_dir=out_dir, line_width=1,
            suffix="_d_visualization")

        def band_dict(res):
            t, b = res["top_y"], res["bottom_y"]
            return {"top_y": t, "bottom_y": b,
                    "height": b - t if b >= 0 else -1}

        summary["threads"].append({
            "index": i,
            "x_range": [x0, x1],
            "raw_size": [strip.shape[1], strip.shape[0]],
            "orientation": meta["orientation"],
            "tilt_angle_deg": meta["level"].get("angle_deg"),
            "leveled_size": meta["level"].get("cropped_size"),
            "auto_preset": meta["auto_preset"],
            "preset_confidence": meta["confidence"],
            "c_band": band_dict(c_res),
            "d_band": band_dict(d_res),
        })
        if verbose:
            print(f"  -> orient={meta['orientation']}, "
                  f"tilt={meta['level'].get('angle_deg')} deg, "
                  f"leveled={meta['level'].get('cropped_size')}")
            print(f"  -> band C: y={c_res['top_y']}-{c_res['bottom_y']}, "
                  f"band D: y={d_res['top_y']}-{d_res['bottom_y']}")

    with open(os.path.join(out_dir, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)

    if verbose:
        print(f"\n[done] outputs in {out_dir}/")
    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--n-threads", type=int, default=4)
    args = ap.parse_args()
    process_multi_thread_scan(args.input, args.out_dir, args.n_threads)


if __name__ == "__main__":
    main()
