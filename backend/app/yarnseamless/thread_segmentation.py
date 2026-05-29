"""Segmentation-first yarn/thread detection and alpha cleanup.

This module is intentionally independent from the older brightness-peak split
logic.  It builds a foreground probability image by modelling the scan
background first, then uses that probability for both column detection and
per-thread alpha cleanup.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage, signal

from . import dual_alpha_pipeline as dap
from . import band_detect


@dataclass
class ThreadCandidate:
    x_center: int
    x0: int
    x1: int
    width: int
    score: float
    peak_score: float
    peak_density: float
    continuity: float
    accepted: bool = True
    failure_reason: str | None = None


@dataclass
class ThreadDetectionResult:
    peaks: list[int]
    profile: np.ndarray
    foreground_score: np.ndarray
    foreground_mask: np.ndarray
    normalized_u8: np.ndarray
    row_density_p95: float
    foreground_separation: float
    bg_rgb: list[float]
    candidates: list[ThreadCandidate]
    rejected_candidates: list[ThreadCandidate]
    failure_reason: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "peaks": [int(p) for p in self.peaks],
            "row_density_p95": float(self.row_density_p95),
            "foreground_separation": float(self.foreground_separation),
            "bg_rgb": [float(v) for v in self.bg_rgb],
            "failure_reason": self.failure_reason,
            "candidates": [asdict(c) for c in self.candidates],
            "rejected_candidates": [asdict(c) for c in self.rejected_candidates],
        }


@dataclass
class AlphaSegmentationResult:
    alpha_u8: np.ndarray
    foreground_score: np.ndarray
    foreground_mask: np.ndarray
    normalized_u8: np.ndarray
    quality: dict[str, Any]


def _luma(arr: np.ndarray) -> np.ndarray:
    a = arr.astype(np.float32)
    return (0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]).astype(np.float32)


def _smooth_1d(values: np.ndarray, window: int) -> np.ndarray:
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


def _robust_high_norm(values: np.ndarray) -> np.ndarray:
    arr = np.asarray(values, dtype=np.float32)
    med = float(np.median(arr))
    mad = float(np.median(np.abs(arr - med)))
    scale = max(mad * 1.4826, float(arr.std()) * 0.12, 1e-4)
    return np.clip((arr - med) / (scale * 4.0), 0.0, 1.0).astype(np.float32)


def _sample_rows(img_rgb: np.ndarray, *, max_rows: int = 1600, max_pixels: int = 7_000_000) -> tuple[np.ndarray, int]:
    H, W = img_rgb.shape[:2]
    rows_by_pixels = max(96, int(max_pixels // max(1, W)))
    target_rows = max(96, min(max_rows, rows_by_pixels, H))
    step = max(1, int(np.ceil(H / float(target_rows))))
    return img_rgb[::step], step


def _robust_background_rgb(sample_rgb: np.ndarray, *, border_only: bool = False) -> np.ndarray:
    if border_only:
        H, W = sample_rgb.shape[:2]
        band_y = max(3, min(24, H // 8))
        band_x = max(3, min(24, W // 8))
        chunks = [
            sample_rgb[:band_y].reshape(-1, 3),
            sample_rgb[-band_y:].reshape(-1, 3),
            sample_rgb[:, :band_x].reshape(-1, 3),
            sample_rgb[:, -band_x:].reshape(-1, 3),
        ]
        flat = np.concatenate(chunks, axis=0).astype(np.float32)
    else:
        flat = sample_rgb.reshape(-1, 3).astype(np.float32)

    rough = np.median(flat, axis=0)
    dist = np.linalg.norm(flat - rough[None, :], axis=1)
    keep = dist <= np.percentile(dist, 65)
    if int(keep.sum()) < 50:
        keep = dist <= np.percentile(dist, 85)
    if int(keep.sum()) < 50:
        return rough.astype(np.float32)
    return np.median(flat[keep], axis=0).astype(np.float32)


def _foreground_score(
    img_rgb: np.ndarray,
    *,
    border_background: bool = False,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, float, list[float], dict[str, float]]:
    """Return (score, mask, normalized_u8, separation, bg_rgb, metrics)."""
    bg_rgb = _robust_background_rgb(img_rgb, border_only=border_background)
    arr = img_rgb.astype(np.float32)
    luma = _luma(img_rgb)
    bg_luma = float(0.2126 * bg_rgb[0] + 0.7152 * bg_rgb[1] + 0.0722 * bg_rgb[2])

    rgb_dist = np.linalg.norm(arr - bg_rgb[None, None, :], axis=2) / (255.0 * np.sqrt(3.0))
    luma_dist = np.abs(luma - bg_luma) / 255.0

    centered = arr - luma[..., None]
    bg_centered = bg_rgb - bg_luma
    chroma_dist = np.linalg.norm(centered - bg_centered[None, None, :], axis=2) / (255.0 * np.sqrt(3.0))

    raw = np.maximum.reduce([
        rgb_dist.astype(np.float32),
        (1.35 * luma_dist).astype(np.float32),
        (1.8 * chroma_dist).astype(np.float32),
    ])

    # Lab distance makes similar-luminance colour changes pop, but can be
    # memory-heavy, so it is a contributor rather than the only signal.
    try:
        lab = dap.srgb_u8_to_lab(img_rgb)
        bg_lab = dap.srgb_u8_to_lab(bg_rgb.reshape(1, 1, 3).astype(np.uint8))[0, 0]
        de = np.linalg.norm(lab - bg_lab[None, None, :], axis=2).astype(np.float32)
        raw = np.maximum(raw, np.clip(de / 55.0, 0.0, 1.0))
    except Exception:
        pass

    flat = raw.reshape(-1)
    bg_hi = float(np.percentile(flat, 72.0))
    fg_hi = float(np.percentile(flat, 99.65))
    med = float(np.median(flat))
    mad = float(np.median(np.abs(flat - med)))
    fg_hi = max(fg_hi, med + 7.0 * max(mad * 1.4826, 1e-4), bg_hi + 0.018)
    score = np.clip((raw - bg_hi) / max(fg_hi - bg_hi, 1e-5), 0.0, 1.0).astype(np.float32)
    score = ndimage.gaussian_filter(score, sigma=(0.6, 0.45))

    weak = score >= 0.22
    strong = score >= 0.52
    labels, n = ndimage.label(weak, structure=np.ones((3, 3), dtype=bool))
    if n > 0 and strong.any():
        keep_labels = np.unique(labels[strong])
        keep_labels = keep_labels[keep_labels != 0]
        mask = np.isin(labels, keep_labels)
    else:
        mask = weak
    mask = ndimage.binary_closing(mask, structure=np.ones((5, 3), dtype=bool))
    mask = ndimage.binary_opening(mask, structure=np.ones((2, 1), dtype=bool))

    bg_values = raw[~mask] if (~mask).any() else flat
    fg_values = raw[mask] if mask.any() else flat[-1:]
    separation = float(np.percentile(fg_values, 70) - np.percentile(bg_values, 90))
    normalized = (score * 255.0).clip(0, 255).astype(np.uint8)
    metrics = {
        "raw_bg_hi": bg_hi,
        "raw_fg_hi": fg_hi,
        "raw_median": med,
        "raw_mad": mad,
    }
    return score, mask.astype(bool), normalized, separation, [float(v) for v in bg_rgb], metrics


def _per_col_longest_run_fraction(mask: np.ndarray) -> np.ndarray:
    H, W = mask.shape
    out = np.zeros(W, dtype=np.float32)
    for x in range(W):
        col = mask[:, x]
        if not col.any():
            continue
        padded = np.concatenate(([False], col, [False]))
        diffs = np.diff(padded.astype(np.int8))
        starts = np.where(diffs == 1)[0]
        ends = np.where(diffs == -1)[0]
        out[x] = float((ends - starts).max()) / float(max(1, H))
    return out


def _runs_from_bool(flags: np.ndarray) -> list[tuple[int, int]]:
    flags = np.asarray(flags, dtype=bool)
    if not flags.any():
        return []
    padded = np.concatenate(([False], flags, [False]))
    diffs = np.diff(padded.astype(np.int8))
    starts = np.where(diffs == 1)[0]
    ends = np.where(diffs == -1)[0] - 1
    return [(int(a), int(b)) for a, b in zip(starts, ends)]


def _merge_runs(runs: list[tuple[int, int]], merge_gap: int) -> list[tuple[int, int]]:
    if not runs:
        return []
    merged: list[tuple[int, int]] = []
    cur0, cur1 = runs[0]
    for x0, x1 in runs[1:]:
        if x0 - cur1 <= merge_gap:
            cur1 = x1
        else:
            merged.append((cur0, cur1))
            cur0, cur1 = x0, x1
    merged.append((cur0, cur1))
    return merged


def _candidate_from_run(
    x0: int,
    x1: int,
    profile: np.ndarray,
    density: np.ndarray,
    continuity: np.ndarray,
) -> ThreadCandidate:
    xs = np.arange(x0, x1 + 1)
    weights = np.maximum(profile[x0:x1 + 1], 1e-6)
    center = int(round(float((xs * weights).sum() / weights.sum())))
    peak_score = float(profile[x0:x1 + 1].max())
    peak_density = float(density[x0:x1 + 1].max())
    cont = float(continuity[x0:x1 + 1].max())
    score = float(0.55 * peak_score + 0.25 * peak_density + 0.20 * cont)
    return ThreadCandidate(
        x_center=center,
        x0=int(x0),
        x1=int(x1),
        width=int(x1 - x0 + 1),
        score=score,
        peak_score=peak_score,
        peak_density=peak_density,
        continuity=cont,
    )


def _rank_candidates(
    candidates: list[ThreadCandidate],
    n_threads: int | None,
    width: int,
) -> tuple[list[ThreadCandidate], list[ThreadCandidate]]:
    accepted: list[ThreadCandidate] = []
    rejected: list[ThreadCandidate] = []
    edge_margin = max(4, int(round(width * 0.004)))
    max_width = max(32, int(round(width * 0.075)))

    for cand in candidates:
        reason = None
        if cand.x_center < edge_margin or cand.x_center > width - 1 - edge_margin:
            reason = "candidate touches scanner edge"
        elif cand.width > max_width:
            reason = "candidate is too wide for a separate thread"
        elif cand.continuity < 0.18 and not (
            cand.peak_score >= 0.85 and cand.score >= 0.50 and cand.continuity >= 0.10
        ) and not (
            cand.peak_score >= 0.95 and cand.score >= 0.55 and cand.continuity >= 0.03
        ):
            reason = "candidate lacks vertical continuity"
        elif cand.peak_score < 0.16:
            reason = "candidate foreground score is too weak"
        elif cand.score < 0.18:
            reason = "candidate combined score is too weak"

        if reason:
            cand.accepted = False
            cand.failure_reason = reason
            rejected.append(cand)
        else:
            accepted.append(cand)

    if n_threads is None:
        deduped: list[ThreadCandidate] = []
        min_sep = max(8, width // 64)
        for cand in sorted(accepted, key=lambda c: c.score, reverse=True):
            if all(abs(cand.x_center - prev.x_center) >= min_sep for prev in deduped):
                deduped.append(cand)
            else:
                cand.accepted = False
                cand.failure_reason = "duplicate ridge for same thread"
                rejected.append(cand)
        accepted = deduped
        accepted.sort(key=lambda c: c.x_center)
        rejected.sort(key=lambda c: c.x_center)
        return accepted, rejected

    pool = sorted(candidates, key=lambda c: c.score, reverse=True)
    selected: list[ThreadCandidate] = []
    min_sep = max(10, width // max(1, n_threads * 4))
    for cand in pool:
        if len(selected) >= n_threads:
            break
        if cand.x_center < edge_margin or cand.x_center > width - 1 - edge_margin:
            continue
        if cand.width > max_width:
            continue
        if cand.continuity < 0.02 or cand.peak_score < 0.07:
            continue
        if all(abs(cand.x_center - prev.x_center) >= min_sep for prev in selected):
            cand.accepted = True
            cand.failure_reason = None
            selected.append(cand)

    selected_ids = {id(c) for c in selected}
    final_rejected: list[ThreadCandidate] = []
    for cand in candidates:
        if id(cand) in selected_ids:
            continue
        if cand.accepted:
            cand.accepted = False
            cand.failure_reason = "not selected for requested thread count"
        final_rejected.append(cand)
    selected.sort(key=lambda c: c.x_center)
    final_rejected.sort(key=lambda c: c.x_center)
    return selected, final_rejected


def detect_threads(img_rgb: np.ndarray, n_threads: int | None = None) -> ThreadDetectionResult:
    """Detect vertical yarn threads from a segmentation foreground map."""
    sample, row_step = _sample_rows(img_rgb)
    score, mask, normalized, separation, bg_rgb, _metrics = _foreground_score(sample)
    Hs, W = score.shape

    # Wide woven fabric/plaid creates horizontal foreground bands.  A real
    # separated-thread scan should have low foreground coverage in every row.
    row_density = mask.mean(axis=1).astype(np.float32)
    row_density_p95 = float(np.percentile(row_density, 95)) if row_density.size else 0.0

    density = mask.mean(axis=0).astype(np.float32)
    qscore = np.percentile(score, 88, axis=0).astype(np.float32)
    continuity = _per_col_longest_run_fraction(mask)

    density_n = _robust_high_norm(density)
    continuity_n = np.clip(continuity / max(0.15, float(continuity.max(initial=0.0))), 0.0, 1.0)
    profile = np.maximum.reduce([
        qscore,
        density_n,
        0.75 * continuity_n,
    ]).astype(np.float32)
    profile = _smooth_1d(profile, max(7, W // 360))

    peak = float(profile.max(initial=0.0))
    med = float(np.median(profile))
    mad = float(np.median(np.abs(profile - med)))
    threshold = max(0.12, 0.18 * peak, med + 1.0 * max(mad * 1.4826, 1e-4))
    col_flags = profile >= threshold
    merge_gap = max(6, int(round(W * 0.014)))
    if n_threads:
        merge_gap = min(merge_gap, max(8, W // max(1, n_threads * 8)))
    runs = _merge_runs(_runs_from_bool(col_flags), merge_gap)
    candidates = [_candidate_from_run(x0, x1, profile, density, continuity) for x0, x1 in runs]

    # A fuzzy yarn can turn into one broad foreground component because its
    # hairs bridge nearby ridges.  Add narrow ridge candidates from inside wide
    # components; the ranking pass below will keep only globally consistent
    # centers and reject the broad support component.
    wide_floor = max(80, int(round(W * 0.055)))
    ridge_candidates: list[ThreadCandidate] = []
    for cand in candidates:
        if cand.width <= wide_floor or cand.peak_score <= 0:
            continue
        sub = profile[cand.x0:cand.x1 + 1]
        ridge_height = max(0.38 if n_threads is not None else 0.72, cand.peak_score * 0.38)
        if n_threads is not None:
            ridge_distance = max(32, int(round(W / float(max(8, n_threads * 6)))))
        else:
            ridge_distance = max(32, int(round(W / float(max(8, 8 * 2)))))
        local_peaks, _props = signal.find_peaks(
            sub,
            distance=ridge_distance,
            prominence=max(0.004, float(profile.std()) * 0.025),
            height=ridge_height,
        )
        half = max(8, min(64, int(round(W * 0.014))))
        for lp in local_peaks:
            p = int(cand.x0 + int(lp))
            lo = max(0, p - half)
            hi = min(W - 1, p + half)
            if any(
                abs(p - existing.x_center) <= half and existing.width <= wide_floor
                for existing in candidates + ridge_candidates
            ):
                continue
            ridge_candidates.append(_candidate_from_run(lo, hi, profile, density, continuity))
    candidates.extend(ridge_candidates)

    # Expected-count mode gets one extra low-threshold peak pass.  This finds
    # very pale/fuzzy third threads without making auto mode hallucinate them.
    if n_threads is not None and len(candidates) < n_threads:
        min_dist = max(8, W // max(1, n_threads * 4))
        peaks, _props = signal.find_peaks(
            profile,
            distance=min_dist,
            prominence=max(0.015, float(profile.std()) * 0.08),
        )
        for p in peaks:
            p = int(p)
            local_peak = float(profile[p])
            if any(c.x0 <= p <= c.x1 for c in candidates):
                continue
            lo = p
            hi = p
            floor = max(0.045, local_peak * 0.32)
            while lo > 0 and profile[lo - 1] >= floor:
                lo -= 1
            while hi < W - 1 and profile[hi + 1] >= floor:
                hi += 1
            candidates.append(_candidate_from_run(lo, hi, profile, density, continuity))

    accepted, rejected = _rank_candidates(candidates, n_threads, W)
    failure_reason = None
    aspect = float(img_rgb.shape[0]) / float(max(1, img_rgb.shape[1]))
    if row_density_p95 > 0.18:
        failure_reason = "scan looks like woven fabric or plaid, not separated vertical yarn threads"
        accepted = []
    elif not accepted and aspect < 2.5 and len(rejected) >= 3:
        failure_reason = "scan looks like woven fabric or plaid, not separated vertical yarn threads"
    elif n_threads is not None and len(accepted) < n_threads:
        failure_reason = f"detected {len(accepted)} usable thread(s), expected {n_threads}"
    elif n_threads is None and not accepted:
        failure_reason = "no usable vertical yarn threads detected"

    return ThreadDetectionResult(
        peaks=[int(c.x_center) for c in accepted],
        profile=profile.astype(np.float32),
        foreground_score=score.astype(np.float32),
        foreground_mask=mask.astype(bool),
        normalized_u8=normalized,
        row_density_p95=row_density_p95,
        foreground_separation=float(separation),
        bg_rgb=bg_rgb,
        candidates=accepted,
        rejected_candidates=rejected,
        failure_reason=failure_reason,
    )


def _keep_thread_components(mask: np.ndarray, score: np.ndarray, *, horizontal: bool) -> np.ndarray:
    H, W = mask.shape
    labels, n = ndimage.label(mask, structure=np.ones((3, 3), dtype=bool))
    if n == 0:
        return np.zeros_like(mask, dtype=bool)

    kept = np.zeros_like(mask, dtype=bool)
    slices = ndimage.find_objects(labels)
    min_long = 0.18 * (W if horizontal else H)
    min_area = max(25, int(mask.size * 0.00003))
    strong = score >= 0.52
    for idx, slc in enumerate(slices, start=1):
        if slc is None:
            continue
        ys, xs = slc
        h = ys.stop - ys.start
        w = xs.stop - xs.start
        area = int((labels[slc] == idx).sum())
        long_span = w if horizontal else h
        touches_strong = bool((strong[slc] & (labels[slc] == idx)).any())
        if area >= min_area and long_span >= min_long and touches_strong:
            kept[labels == idx] = True
    if not kept.any():
        # Last-resort fallback: keep the largest strong-touching component.
        best_idx = 0
        best_area = 0
        for idx, slc in enumerate(slices, start=1):
            if slc is None:
                continue
            component = labels[slc] == idx
            if not (strong[slc] & component).any():
                continue
            area = int(component.sum())
            if area > best_area:
                best_idx = idx
                best_area = area
        if best_idx:
            kept[labels == best_idx] = True
    return kept


def _connected_visible_support(
    alpha_u8: np.ndarray,
    *,
    core_mask: np.ndarray | None = None,
    alpha_eps: int = 5,
    bridge_px: int | None = None,
) -> np.ndarray:
    """Keep only visible alpha connected to the thick thread body.

    Scanner fog can leave low alpha everywhere.  A plain row-density walk sees
    that as false hair, while a strict FWHM band misses real long fibers.  This
    keeps the old useful behaviour: seed from the thick/core alpha, bridge tiny
    gaps along the yarn direction, then retain only connected visible strands.
    """
    alpha = np.asarray(alpha_u8, dtype=np.uint8)
    weak_values = alpha[(alpha > int(alpha_eps)) & (alpha < 64)]
    adaptive_eps = int(alpha_eps)
    if weak_values.size >= 100:
        adaptive_eps = max(adaptive_eps, int(min(24, np.percentile(weak_values, 92))))
    visible = alpha > adaptive_eps
    if not visible.any():
        return np.zeros_like(visible, dtype=bool)

    if core_mask is None:
        strong_cut = max(80, int(np.percentile(alpha[visible], 88)))
        core_mask = alpha >= strong_cut
    else:
        core_mask = np.asarray(core_mask, dtype=bool)
    if not core_mask.any():
        core_mask = alpha >= max(40, int(np.percentile(alpha[visible], 75)))
    if not core_mask.any():
        return visible

    if bridge_px is None:
        bridge_px = max(7, min(61, alpha.shape[1] // 140))
    bridged = ndimage.binary_closing(
        visible,
        structure=np.ones((3, int(bridge_px)), dtype=bool),
    )
    labels, n = ndimage.label(bridged, structure=np.ones((3, 3), dtype=bool))
    if n == 0:
        return np.zeros_like(visible, dtype=bool)
    touching = np.unique(labels[core_mask])
    touching = touching[touching != 0]
    if touching.size == 0:
        return visible & core_mask
    connected = np.isin(labels, touching)
    return connected & visible


def _connected_fiber_extents_y(
    alpha_u8: np.ndarray,
    core_top_y: int,
    core_bottom_y: int,
    *,
    alpha_eps: int = 5,
    coverage_frac: float = 0.05,
    min_row_px: int = 3,
) -> tuple[int, int, np.ndarray]:
    if alpha_u8 is None or core_top_y < 0 or core_bottom_y < 0:
        empty = np.zeros_like(alpha_u8, dtype=bool) if alpha_u8 is not None else np.zeros((0, 0), dtype=bool)
        return int(core_top_y), int(core_bottom_y), empty
    alpha = np.asarray(alpha_u8, dtype=np.uint8)
    H, _W = alpha.shape
    cy0 = int(max(0, min(H - 1, core_top_y)))
    cy1 = int(max(0, min(H - 1, core_bottom_y)))
    seed = np.zeros_like(alpha, dtype=bool)
    seed[cy0:cy1 + 1, :] = alpha[cy0:cy1 + 1, :] >= 80
    if not seed.any():
        seed[cy0:cy1 + 1, :] = alpha[cy0:cy1 + 1, :] > int(alpha_eps)
    connected = _connected_visible_support(alpha, core_mask=seed, alpha_eps=alpha_eps)
    visible_count = connected.sum(axis=1)
    peak = int(visible_count.max()) if visible_count.size else 0
    if peak <= 0:
        return cy0, cy1, connected
    floor = max(int(min_row_px), int(round(float(coverage_frac) * peak)))
    in_strand = visible_count >= floor
    fty0 = cy0
    while fty0 > 0 and in_strand[fty0 - 1]:
        fty0 -= 1
    fby1 = cy1
    while fby1 < H - 1 and in_strand[fby1 + 1]:
        fby1 += 1
    return int(fty0), int(fby1), connected


def _per_row_longest_run(binary: np.ndarray) -> np.ndarray:
    H, _W = binary.shape
    out = np.zeros(H, dtype=np.int32)
    for y in range(H):
        row = binary[y]
        if not row.any():
            continue
        padded = np.concatenate(([False], row, [False]))
        diffs = np.diff(padded.astype(np.int8))
        starts = np.where(diffs == 1)[0]
        ends = np.where(diffs == -1)[0]
        out[y] = int((ends - starts).max())
    return out


def _run_containing_or_nearest(flags: np.ndarray, anchor: int) -> tuple[int, int]:
    runs = _runs_from_bool(flags)
    if not runs:
        return -1, -1
    for y0, y1 in runs:
        if y0 <= anchor <= y1:
            return int(y0), int(y1)
    best = min(runs, key=lambda r: min(abs(anchor - r[0]), abs(anchor - r[1])))
    return int(best[0]), int(best[1])


def _detect_connected_core_band(alpha_u8: np.ndarray) -> dict[str, Any]:
    """Find the solid/core thickness band from the connected thick alpha body.

    Whole-row density alone can be fooled by long disconnected scanner haze or
    red-card spill bands. This seeds from the high-alpha body, keeps visible
    alpha connected to that body, then finds the peak-relative vertical core
    run from connected high-alpha rows.
    """
    alpha = np.asarray(alpha_u8, dtype=np.uint8)
    H, W = alpha.shape
    visible = alpha > 4
    if not visible.any():
        return {
            "top_y": -1,
            "bottom_y": -1,
            "height": -1,
            "connected_visible": np.zeros_like(alpha, dtype=bool),
            "score": np.zeros(H, dtype=np.float32),
            "metrics": {
                "strong_cut": 0,
                "peak_score": 0.0,
                "peak_row": -1,
                "threshold": 0.0,
                "connected_peak_density": 0.0,
            },
        }

    values = alpha[visible]
    strong_cut = int(max(80, min(220, round(float(np.percentile(values, 88))))))
    core_seed = alpha >= strong_cut
    if int(core_seed.sum()) < max(12, W // 30):
        strong_cut = int(max(56, min(180, round(float(np.percentile(values, 78))))))
        core_seed = alpha >= strong_cut
    if not core_seed.any():
        core_seed = alpha >= max(32, int(np.percentile(values, 70)))

    connected = _connected_visible_support(alpha, core_mask=core_seed, alpha_eps=5)
    if not connected.any():
        connected = visible

    strong = connected & (alpha >= strong_cut)
    if int(strong.sum()) < max(12, W // 30):
        fallback_cut = int(max(40, min(strong_cut, round(float(np.percentile(alpha[connected], 72))))))
        strong = connected & (alpha >= fallback_cut)
        strong_cut = fallback_cut
    if not strong.any():
        strong = connected

    longest = _per_row_longest_run(strong).astype(np.float32)
    counts = strong.sum(axis=1).astype(np.float32)
    connected_counts = connected.sum(axis=1).astype(np.float32)
    alpha_mass = (alpha.astype(np.float32) * connected.astype(np.float32)).sum(axis=1)
    mean_alpha = np.divide(
        alpha_mass,
        np.maximum(connected_counts, 1.0),
        out=np.zeros_like(alpha_mass, dtype=np.float32),
        where=connected_counts > 0,
    ) / 255.0

    longest_n = longest / max(1.0, float(longest.max(initial=0.0)))
    counts_n = counts / max(1.0, float(counts.max(initial=0.0)))
    score = (0.62 * longest_n + 0.28 * counts_n + 0.10 * mean_alpha).astype(np.float32)
    if H >= 5:
        score = _smooth_1d(score, 5)

    peak_score = float(score.max(initial=0.0))
    if peak_score <= 0:
        cy0 = cy1 = -1
        threshold = 0.0
        peak_row = -1
    else:
        peak_row = int(np.argmax(score))
        threshold = max(0.22, peak_score * 0.48)
        cy0, cy1 = _run_containing_or_nearest(score >= threshold, peak_row)
        if cy0 >= 0 and cy1 - cy0 <= 1:
            cy0, cy1 = _run_containing_or_nearest(score >= max(0.16, peak_score * 0.34), peak_row)

    connected_peak_density = float((strong.sum(axis=1) / max(1, W)).max(initial=0.0))
    return {
        "top_y": int(cy0),
        "bottom_y": int(cy1),
        "height": int(cy1 - cy0 + 1) if cy0 >= 0 and cy1 >= cy0 else -1,
        "connected_visible": connected,
        "score": score.astype(np.float32),
        "metrics": {
            "strong_cut": int(strong_cut),
            "peak_score": float(peak_score),
            "peak_row": int(peak_row),
            "threshold": float(threshold),
            "connected_peak_density": connected_peak_density,
        },
    }


def segment_thread_alpha(
    img_rgb: np.ndarray,
    base_alpha_u8: np.ndarray | None = None,
    *,
    horizontal: bool = True,
) -> AlphaSegmentationResult:
    """Clean alpha for a single leveled thread image.

    The returned matte is crisp because the segmentation gates noisy background
    pixels instead of globally blurring the alpha.  If `base_alpha_u8` is
    provided, its wispy detail is preserved inside the segmentation support.
    """
    score, mask, normalized, separation, bg_rgb, _metrics = _foreground_score(
        img_rgb,
        border_background=True,
    )
    if horizontal:
        close_w = max(9, min(151, img_rgb.shape[1] // 80))
        close_shape = (3, close_w)
    else:
        close_h = max(9, min(151, img_rgb.shape[0] // 80))
        close_shape = (close_h, 3)
    mask = ndimage.binary_closing(mask, structure=np.ones(close_shape, dtype=bool))
    mask = _keep_thread_components(mask, score, horizontal=horizontal)
    support = ndimage.binary_dilation(mask, structure=np.ones((5, 5), dtype=bool), iterations=1)

    seg_alpha = (np.power(np.clip(score, 0.0, 1.0), 0.72) * 255.0).clip(0, 255).astype(np.uint8)
    seg_alpha[~mask] = 0

    if base_alpha_u8 is None:
        alpha = seg_alpha
    else:
        base = np.asarray(base_alpha_u8, dtype=np.uint8)
        if base.shape != score.shape:
            h = min(base.shape[0], score.shape[0])
            w = min(base.shape[1], score.shape[1])
            base = base[:h, :w]
            seg_alpha = seg_alpha[:h, :w]
            support = support[:h, :w]
            mask = mask[:h, :w]
            normalized = normalized[:h, :w]
            score = score[:h, :w]
        core_seed = (base >= 100) | (mask & (score >= 0.70))
        connected_support = _connected_visible_support(base, core_mask=core_seed, alpha_eps=5)
        support = support | connected_support
        gated = np.where(support, base, 0).astype(np.uint8)
        alpha = gated

    alpha = np.where(alpha >= 4, alpha, 0).astype(np.uint8)
    alpha = _despeckle_alpha(alpha, min_area=max(20, int(alpha.size * 0.00002)), low=5)

    bg_alpha = alpha[~support] if (~support).any() else np.array([0], dtype=np.uint8)
    fg_alpha = alpha[mask] if mask.any() else np.array([0], dtype=np.uint8)
    density = (alpha > 127).mean(axis=1 if horizontal else 0).astype(np.float32)
    quality = {
        "algorithm": "segmentation_gated_alpha_v2",
        "foreground_separation": float(separation),
        "background_rgb": [float(v) for v in bg_rgb],
        "background_alpha_p95": float(np.percentile(bg_alpha, 95)),
        "foreground_alpha_p50": float(np.percentile(fg_alpha, 50)),
        "peak_density": float(density.max(initial=0.0)),
        "failure_reason": None,
    }
    if quality["peak_density"] <= 0.01:
        quality["failure_reason"] = "alpha support is empty"
    elif quality["foreground_alpha_p50"] < 40:
        quality["failure_reason"] = "foreground alpha is too weak"

    return AlphaSegmentationResult(
        alpha_u8=alpha,
        foreground_score=score.astype(np.float32),
        foreground_mask=mask.astype(bool),
        normalized_u8=normalized,
        quality=quality,
    )


def _despeckle_alpha(alpha_u8: np.ndarray, *, min_area: int, low: int = 5) -> np.ndarray:
    mask = alpha_u8 >= low
    if not mask.any():
        return alpha_u8
    labels, n = ndimage.label(mask, structure=np.ones((3, 3), dtype=bool))
    if n == 0:
        return alpha_u8
    areas = np.bincount(labels.ravel())
    keep = areas >= int(min_area)
    keep[0] = False
    return np.where(keep[labels], alpha_u8, 0).astype(np.uint8)


def detect_band_quality(alpha_u8: np.ndarray) -> dict[str, Any]:
    """Return legacy-compatible band dicts plus explicit quality metrics."""
    alpha = np.asarray(alpha_u8, dtype=np.uint8)
    density = (alpha > 127).mean(axis=1).astype(np.float32)
    peak = float(density.max(initial=0.0))
    if peak <= 0.005:
        empty = {"top_y": -1, "bottom_y": -1, "height": -1, "fiber_top_y": -1, "fiber_bot_y": -1}
        return {
            "c_band": empty.copy(),
            "d_band": empty.copy(),
            "quality": {
                "algorithm": "fwhm_density_walk",
                "peak_density": peak,
                "core_width": 0,
                "continuity": 0.0,
                "failure_reason": "no visible alpha band",
            },
            "raw": None,
        }

    raw = band_detect.detect_bands(alpha)
    core = _detect_connected_core_band(alpha)
    cy0, cy1 = int(core["top_y"]), int(core["bottom_y"])
    if cy0 < 0 or cy1 < cy0:
        cy0, cy1 = raw["bands_px"]["core"]
    fty0, fby1, connected_visible = _connected_fiber_extents_y(alpha, cy0, cy1)
    band = {
        "top_y": int(cy0),
        "bottom_y": int(cy1),
        "height": int(cy1 - cy0 + 1),
        "fiber_top_y": int(fty0),
        "fiber_bot_y": int(fby1),
    }
    rows = density >= max(peak * 0.5, 1e-6)
    continuity = float(band["height"] / max(1, int(rows.sum()))) if rows.any() else 0.0
    connected_visible_count = connected_visible.sum(axis=1) if connected_visible.size else np.zeros(0, dtype=np.int64)
    connected_peak = int(connected_visible_count.max()) if connected_visible_count.size else 0
    core_metrics = core.get("metrics", {})
    failure_reason = None
    if band["height"] <= 1:
        failure_reason = "band core is too thin"
    elif max(peak, float(core_metrics.get("connected_peak_density", 0.0))) < 0.08:
        failure_reason = "band foreground coverage is very low"

    return {
        "c_band": band.copy(),
        "d_band": band.copy(),
        "quality": {
            "algorithm": "connected_core_peak_band_v1",
            "peak_density": peak,
            "core_width": int(band["height"]),
            "fiber_top_height": int(max(0, cy0 - fty0)),
            "fiber_bot_height": int(max(0, fby1 - cy1)),
            "connected_visible_peak_px": connected_peak,
            "connected_core_peak_score": float(core_metrics.get("peak_score", 0.0)),
            "connected_core_threshold": float(core_metrics.get("threshold", 0.0)),
            "connected_core_alpha_cut": int(core_metrics.get("strong_cut", 0)),
            "raw_fwhm_core": [int(v) for v in raw["bands_px"]["core"]],
            "continuity": continuity,
            "failure_reason": failure_reason,
        },
        "raw": raw,
    }


def save_detection_debug_images(
    img_rgb: np.ndarray,
    result: ThreadDetectionResult,
    out_dir: str | Path,
    *,
    max_height: int = 2400,
) -> dict[str, str]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    files: dict[str, str] = {}

    sample_h, sample_w = result.normalized_u8.shape
    scale_y = max(1.0, img_rgb.shape[0] / float(max_height))
    thumb = Image.fromarray(img_rgb).convert("RGB")
    if thumb.height > max_height:
        thumb = thumb.resize((max(1, int(round(thumb.width / scale_y))), max_height), Image.Resampling.BILINEAR)

    overlay = thumb.copy()
    draw = ImageDraw.Draw(overlay)
    sx = overlay.width / float(img_rgb.shape[1])
    for cand in result.candidates:
        x = int(round(cand.x_center * sx))
        draw.line([(x, 0), (x, overlay.height - 1)], fill=(0, 255, 0), width=3)
        x0 = int(round(cand.x0 * sx))
        x1 = int(round(cand.x1 * sx))
        draw.rectangle([(x0, 0), (x1, overlay.height - 1)], outline=(0, 200, 255), width=2)
    for cand in result.rejected_candidates:
        x = int(round(cand.x_center * sx))
        draw.line([(x, 0), (x, overlay.height - 1)], fill=(255, 140, 0), width=2)
    p = out / "segmentation_overlay.png"
    overlay.save(p)
    files["segmentation_overlay"] = p.name

    normalized = Image.fromarray(result.normalized_u8, mode="L")
    if normalized.height != overlay.height:
        normalized = normalized.resize((overlay.width, overlay.height), Image.Resampling.BILINEAR)
    p = out / "segmentation_normalized.png"
    normalized.save(p)
    files["segmentation_normalized"] = p.name

    mask_img = Image.fromarray((result.foreground_mask.astype(np.uint8) * 255), mode="L")
    if mask_img.height != overlay.height:
        mask_img = mask_img.resize((overlay.width, overlay.height), Image.Resampling.NEAREST)
    p = out / "segmentation_mask.png"
    mask_img.save(p)
    files["segmentation_mask"] = p.name

    heat = np.zeros((*result.normalized_u8.shape, 3), dtype=np.uint8)
    heat[..., 0] = result.normalized_u8
    heat[..., 1] = np.clip(result.normalized_u8.astype(np.int16) // 2 + result.foreground_mask.astype(np.int16) * 120, 0, 255)
    heat[..., 2] = 255 - result.normalized_u8
    heat_img = Image.fromarray(heat, mode="RGB")
    if heat_img.height != overlay.height:
        heat_img = heat_img.resize((overlay.width, overlay.height), Image.Resampling.BILINEAR)
    p = out / "segmentation_heatmap.png"
    heat_img.save(p)
    files["segmentation_heatmap"] = p.name
    return files


def save_thread_alpha_debug(
    result: AlphaSegmentationResult,
    out_dir: str | Path,
    prefix: str,
) -> dict[str, str]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    files: dict[str, str] = {}
    p = out / f"{prefix}_segmentation_alpha.png"
    Image.fromarray(result.alpha_u8, mode="L").save(p)
    files["segmentation_alpha"] = p.name
    p = out / f"{prefix}_segmentation_mask.png"
    Image.fromarray((result.foreground_mask.astype(np.uint8) * 255), mode="L").save(p)
    files["segmentation_mask"] = p.name
    p = out / f"{prefix}_segmentation_normalized.png"
    Image.fromarray(result.normalized_u8, mode="L").save(p)
    files["segmentation_normalized"] = p.name
    return files
