"""Achromatic-F closed-form matting for the multi-thread web flow.

This module is consumed by lama_server.py (`/api/multithread/process` and
`/api/multithread/regenerate-alpha`). It replaces the legacy
`alpha_pipeline.run()` calls with a closed-form solver derived in
`2bgpics/red_estimation.py` and `2bgpics/dual_estimation.py`.

Self-contained (only depends on numpy, PIL, scipy). The relevant pieces
of `2bgpics/two_bg_solve.py` (sub-pixel registration + cubic-spline shift)
are inlined so we never have to mess with sys.path at import time.
"""
from __future__ import annotations

import numpy as np
from PIL import Image
from scipy.ndimage import shift as ndimage_shift
from scipy.signal import fftconvolve

# === Constants ===
SHIFT_THRESHOLD_PX = 3.0          # halt threshold for two-image registration

# Auto-clean-patch detector defaults
PATCH_W = 400
PATCH_H = 400
N_PATCHES = 4
DEV_THRESHOLDS_U8 = [20, 30, 50, 80]   # try in order; relax if no clean patches
CLEAN_FRAC = 0.999
STRIDE = 100


# === sRGB ↔ linear (IEC 61966-2-1) ===
def srgb_to_linear(x):
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(x):
    x = np.clip(x, 0, None)
    return np.where(x <= 0.0031308, 12.92 * x, 1.055 * np.power(x, 1 / 2.4) - 0.055)


# === Auto-detect clean (thread-free) patches & sample B ===
def auto_sample_B(I_srgb_u8, patch_w=PATCH_W, patch_h=PATCH_H,
                  n_patches=N_PATCHES, clean_frac=CLEAN_FRAC, stride=STRIDE):
    """Pick `n_patches` thread-free patches anywhere in the image and return
    (B_linear, samples_lin, picks, threshold_used).

    Strategy (matches 2bgpics/grey_thread/red_estimation.py):
      1. Robust rough B = per-channel median across all pixels.
      2. Per-pixel deviation = ‖I - B_rough‖ in 8-bit Euclidean units.
      3. bg_mask = deviation < THRESHOLD; sliding-window over an integral
         image; keep windows where ≥CLEAN_FRAC of pixels are bg.
      4. Greedy spatial-diversity selection.
      5. Final B = mean of selected patches in linear RGB.

    Raises RuntimeError if no clean patches at any threshold."""
    H, W, _ = I_srgb_u8.shape
    arr = I_srgb_u8.astype(np.float32)
    B_rough = np.median(arr.reshape(-1, 3), axis=0)
    dev = np.linalg.norm(arr - B_rough, axis=2)
    target = patch_h * patch_w
    candidates = []
    threshold_used = None
    for thr in DEV_THRESHOLDS_U8:
        bg_mask = dev < thr
        integral = np.zeros((H + 1, W + 1), dtype=np.int64)
        integral[1:, 1:] = bg_mask.astype(np.int64).cumsum(0).cumsum(1)
        for y in range(0, H - patch_h + 1, stride):
            for x in range(0, W - patch_w + 1, stride):
                n_bg = (integral[y + patch_h, x + patch_w] - integral[y, x + patch_w]
                        - integral[y + patch_h, x] + integral[y, x])
                if n_bg >= target * clean_frac:
                    candidates.append((x, y, int(n_bg)))
        if candidates:
            threshold_used = thr
            break

    if not candidates:
        raise RuntimeError(
            f"No clean (thread-free) patches found at any threshold up to "
            f"{DEV_THRESHOLDS_U8[-1]}. Image may be too cluttered or B sampling failed."
        )

    candidates.sort(key=lambda t: -t[2])
    min_dist_sq = (max(patch_w, patch_h) * 1.5) ** 2
    picks = []
    for x, y, n in candidates:
        if all((cx - x) ** 2 + (cy - y) ** 2 > min_dist_sq for cx, cy, _ in picks):
            picks.append((x, y, n))
            if len(picks) >= n_patches:
                break

    samples_lin = []
    for x, y, _ in picks:
        patch_u8 = I_srgb_u8[y:y + patch_h, x:x + patch_w, :]
        patch_lin = srgb_to_linear(patch_u8.astype(np.float64) / 255.0)
        samples_lin.append(patch_lin.mean(axis=(0, 1)))
    samples_lin = np.array(samples_lin)
    B_lin = samples_lin.mean(axis=0)
    return B_lin, samples_lin, picks, int(threshold_used)


# === Closed-form achromatic-F (single scan) ===
def closed_form_alpha_red(I_srgb_u8, B_red_lin):
    """Single-scan matting: I = α·f + (1−α)·B, F achromatic.

    NOTE: function name says "red" for historical reasons but the math is
    colour-agnostic. Pass any flat-bg colour as B (linear RGB 3-vector).

    Per pixel, 3 equations / 2 unknowns; closed-form 2×2 LS.
    Returns H×W uint8 alpha [0, 255]."""
    a, _f = closed_form_alpha_and_f(I_srgb_u8, B_red_lin)
    return (a * 255).round().astype(np.uint8)


def closed_form_alpha_and_f(I_srgb_u8, B_lin):
    """Same closed-form solve but returns BOTH α (float [0,1]) and f
    (achromatic foreground brightness, float [0,1]).

    f is recovered from u = α·f via f = u/α (clamped). Useful when the caller
    wants to use f as the foreground colour at composite time (e.g. inside
    LaMa-inpainted regions where the captured-RGB is a thread+bg mixture
    that would leak bg colour into composites)."""
    I = srgb_to_linear(I_srgb_u8.astype(np.float64) / 255.0)
    B = np.asarray(B_lin, dtype=np.float64).reshape(3)
    sumB = float(B.sum())
    ssqB = float((B * B).sum())
    det = 3.0 * ssqB - sumB ** 2
    inv_AtA = (1.0 / det) * np.array([[ssqB, sumB], [sumB, 3.0]])
    D = I - B
    b1 = D.sum(axis=-1)
    b2 = -(B * D).sum(axis=-1)
    u = inv_AtA[0, 0] * b1 + inv_AtA[0, 1] * b2     # α·f
    a = inv_AtA[1, 0] * b1 + inv_AtA[1, 1] * b2     # α
    a = np.clip(a, 0.0, 1.0)
    eps = 1e-3
    f = np.where(a > eps, u / np.maximum(a, eps), 0.0)
    f = np.clip(f, 0.0, 1.0)
    return a, f


def recover_rgb_foreground_from_alpha(
    I_srgb_u8,
    alpha_u8,
    B_lin,
    *,
    min_alpha: float = 1.0 / 255.0,
    fill_thresh: int = 15,
    stabilize_low_alpha: bool = True,
    stabilize_below_u8: int = 96,
    core_alpha_u8: int = 180,
    source_blend_start_u8: int | None = None,
    preserve_source_above_u8: int | None = None,
):
    """Recover a chromatic foreground using an already-computed alpha matte.

    The alpha solvers in this module intentionally assume an achromatic
    foreground for stability, but the exported RGBA should preserve the yarn's
    actual colour. Given I = alpha * F + (1-alpha) * B, solve F per RGB channel.
    """
    I = srgb_to_linear(I_srgb_u8.astype(np.float64) / 255.0)
    B = np.asarray(B_lin, dtype=np.float64).reshape(3)
    alpha = np.asarray(alpha_u8, dtype=np.float64)
    if alpha.max(initial=0.0) > 1.0:
        alpha = alpha / 255.0
    alpha = np.clip(alpha, 0.0, 1.0)

    denom = np.maximum(alpha[..., None], float(min_alpha))
    F_lin = (I - (1.0 - alpha[..., None]) * B) / denom
    F_lin = np.clip(F_lin, 0.0, 1.0)
    F_u8 = (linear_to_srgb(F_lin) * 255).clip(0, 255).astype(np.uint8)

    if stabilize_low_alpha:
        alpha_u8_arr = (alpha * 255.0).round().astype(np.uint8)
        core = alpha_u8_arr >= int(core_alpha_u8)
        low = (alpha_u8_arr > int(round(min_alpha * 255.0))) & (alpha_u8_arr < int(stabilize_below_u8))
        if core.any() and low.any():
            core_rgb = np.median(F_u8[core].reshape(-1, 3), axis=0).astype(np.float32)
            w = np.clip(alpha_u8_arr.astype(np.float32) / float(max(1, stabilize_below_u8)), 0.0, 1.0)
            w = (w ** 4)[..., None]
            mixed = F_u8.astype(np.float32) * w + core_rgb[None, None, :] * (1.0 - w)
            F_u8[low] = mixed[low].clip(0, 255).astype(np.uint8)

    if preserve_source_above_u8 is not None:
        alpha_u8_arr = (alpha * 255.0).round().astype(np.uint8)
        source_rgb = np.asarray(I_srgb_u8, dtype=np.uint8)
        high = alpha_u8_arr >= int(preserve_source_above_u8)
        F_u8[high] = source_rgb[high]
        if source_blend_start_u8 is not None:
            start = int(source_blend_start_u8)
            stop = int(preserve_source_above_u8)
            if stop > start:
                mid = (alpha_u8_arr >= start) & (alpha_u8_arr < stop)
                if mid.any():
                    w = ((alpha_u8_arr.astype(np.float32) - float(start)) / float(stop - start))
                    w = np.clip(w, 0.0, 1.0)[..., None]
                    mixed = F_u8.astype(np.float32) * (1.0 - w) + source_rgb.astype(np.float32) * w
                    F_u8[mid] = mixed[mid].clip(0, 255).astype(np.uint8)

    transparent = alpha <= float(min_alpha)
    canvas_fill = I_srgb_u8.max(axis=2) <= int(fill_thresh)
    F_u8[transparent | canvas_fill] = 0
    return F_u8


def sample_local_B_from_borders(I_srgb_u8, band: int = 6, fill_thresh: int = 15):
    """Sample the bg colour from the top + bottom band rows of the crop.
    Excludes canvas-fill pixels (rgb_max ≤ fill_thresh). Returns linear-RGB
    3-vector or None if not enough samples.

    Use when the local bg colour drifts from the globally-sampled B (e.g.
    LaMa output: it draws a "red enough" bg but the actual RGB drifts)."""
    H, W = I_srgb_u8.shape[:2]
    band = min(band, H // 2)
    if band <= 0:
        return None
    top = I_srgb_u8[:band].reshape(-1, 3)
    bot = I_srgb_u8[-band:].reshape(-1, 3)
    pix = np.concatenate([top, bot], axis=0)
    pix = pix[pix.max(axis=1) > fill_thresh]
    if pix.shape[0] < 50:
        return None
    pix_lin = srgb_to_linear(pix.astype(np.float64) / 255.0)
    return np.median(pix_lin.reshape(-1, 3), axis=0)


# === Method K: Lab chroma-only α + Mahalanobis bg gate ===
#
# Why this exists (vs the RGB-space closed_form_alpha_and_f above):
#
#   In Lab the achromatic-F prior F=(L_f, 0, 0) DECOUPLES the matting equations:
#     I.L = α·L_f + (1-α)·B.L     ← contains both α and L_f
#     I.a = (1-α)·B.a              ← contains ONLY α  (F.a = 0 for grey)
#     I.b = (1-α)·B.b              ← contains ONLY α  (F.b = 0 for grey)
#
#   So α can be solved directly from the chroma channels — without ever
#   touching L_f. This is more numerically stable than the RGB version where
#   all 3 channels mix α and f together in a 2-D LS. Empirically gives
#   +2 to +48 % more visible halo wisps than RGB closed-form on our scans.
#
#   The Mahalanobis gate on the 2-D (a*, b*) chroma cluster cleanly classifies
#   bg pixels (statistically inside the cluster → α=0 forced) without ever
#   eating halo (real halo desaturates → falls outside the gate).
#
# Caveat: Lab is non-linear so the matting equation is approximate here.
# Negligible for α < 0.5 (the wispy region where we care most).

# D65 reference white & sRGB→XYZ matrix
_LAB_M = np.array([[0.4124564, 0.3575761, 0.1804375],
                   [0.2126729, 0.7151522, 0.0721750],
                   [0.0193339, 0.1191920, 0.9503041]])
_LAB_XN, _LAB_YN, _LAB_ZN = 0.95047, 1.0, 1.08883
_LAB_DELTA = 6.0 / 29.0


def srgb_u8_to_lab(arr_u8):
    """sRGB u8 (H, W, 3) → CIELab D65 via XYZ. Manual; no skimage dependency."""
    rgb = np.clip(arr_u8.astype(np.float64) / 255.0, 0.0, 1.0)
    rgb_lin = srgb_to_linear(rgb)
    with np.errstate(divide="ignore", over="ignore", invalid="ignore"):
        xyz = rgb_lin @ _LAB_M.T
    xyz = np.nan_to_num(xyz, nan=0.0, posinf=1.0, neginf=0.0)
    xyz_n = xyz / np.array([_LAB_XN, _LAB_YN, _LAB_ZN])
    fT = np.where(xyz_n > _LAB_DELTA ** 3,
                  np.cbrt(xyz_n),
                  xyz_n / (3 * _LAB_DELTA ** 2) + 4.0 / 29.0)
    L = 116 * fT[..., 1] - 16
    a_ = 500 * (fT[..., 0] - fT[..., 1])
    b_ = 200 * (fT[..., 1] - fT[..., 2])
    return np.stack([L, a_, b_], axis=-1)


def sample_edge_bg_cluster(leveled_u8, N=5, n_sigma=3.0):
    """Estimate the bg colour as a CLUSTER (mean + covariance) by sampling
    the top N and bottom N rows of a leveled thread strip + sigma-clipping.

    Geometric guarantee: in our scans, the thread is centred vertically, so
    rows 0..N and rows H-N..H are bg-only (no halo, no thread). σ-clip at
    n_sigma handles rare cases where a stray fibre touches the edge.

    Returns:
      B_lab_mean   — (3,) mean in CIELab (L*, a*, b*)
      B_lab_cov    — (3, 3) covariance matrix in CIELab
      B_lin_mean   — (3,) mean in linear RGB (for compatibility with
                     existing call sites that expect linear B vector)
      n_kept       — int, number of samples used

    Raises ValueError if fewer than 1000 valid samples survive.
    """
    H, W, _ = leveled_u8.shape
    if H < 2 * N:
        raise ValueError(f"image too short for edge sampling: H={H}, need ≥ {2*N}")
    top = leveled_u8[:N].reshape(-1, 3)
    bot = leveled_u8[-N:].reshape(-1, 3)
    samples_srgb = np.concatenate([top, bot], axis=0)

    # σ-clip in linear RGB (1 pass)
    samples_lin = srgb_to_linear(samples_srgb.astype(np.float64) / 255.0)
    med = np.median(samples_lin, axis=0)
    sigma = np.std(samples_lin, axis=0)
    keep = ((np.abs(samples_lin[:, 0] - med[0]) <= n_sigma * sigma[0]) &
            (np.abs(samples_lin[:, 1] - med[1]) <= n_sigma * sigma[1]) &
            (np.abs(samples_lin[:, 2] - med[2]) <= n_sigma * sigma[2]))
    samples_srgb_clean = samples_srgb[keep]
    samples_lin_clean = samples_lin[keep]
    n_kept = int(keep.sum())
    if n_kept < 1000:
        raise ValueError(f"too few clean bg samples after σ-clip: {n_kept} < 1000")

    samples_lab = srgb_u8_to_lab(samples_srgb_clean)
    return (samples_lab.mean(axis=0),
            np.cov(samples_lab, rowvar=False),
            samples_lin_clean.mean(axis=0),
            n_kept)


def closed_form_alpha_and_f_lab_gated(
    leveled_u8,
    B_lab_mean=None,
    B_lab_cov=None,
    chi2_thresh=13.82,
    return_cluster=False,
    fallback_B_lin=None,
):
    """Method K — Lab chroma-only α + 2D Mahalanobis gate.

    Pipeline:
      1. If cluster not supplied, sample it from the image's edge rows
         (sample_edge_bg_cluster).
      2. For each pixel, solve α from a*/b* chroma alone:
            α_a = 1 - I.a / B.a_mean
            α_b = 1 - I.b / B.b_mean
            α   = (|B.a|·α_a + |B.b|·α_b) / (|B.a| + |B.b|)
      3. Apply 2D Mahalanobis gate in (a*, b*): if d² < chi2_thresh, α := 0.
         Default chi2_thresh = 13.82 = χ²(2, 99.9%).
      4. Force α = 0 on canvas-fill (rgb_max ≤ 15).
      5. Recover L_f from the L equation, convert back to grey linear RGB,
         then to sRGB u8 for the F output.

    Defensive fallback: if edge sampling fails (image too short, or fewer
    than 1000 clean samples), falls back to closed_form_alpha_and_f using
    fallback_B_lin (caller must provide if there's any chance of failure).

    Returns:
      alpha_u8       — (H, W) uint8 α
      F_rgb_u8       — (H, W, 3) uint8 achromatic grey foreground
      [if return_cluster=True, also returns B_lab_mean, B_lab_cov]
    """
    H, W = leveled_u8.shape[:2]

    # --- Step 1: get the cluster (auto-sample if not supplied) ---
    if B_lab_mean is None or B_lab_cov is None:
        try:
            B_lab_mean, B_lab_cov, _, _ = sample_edge_bg_cluster(leveled_u8)
        except ValueError as e:
            print(f"[Method K] edge sampling failed ({e}); falling back to Method A")
            if fallback_B_lin is None:
                raise
            a_u8 = closed_form_alpha_red(leveled_u8, fallback_B_lin)
            _, f_lin = closed_form_alpha_and_f(leveled_u8, fallback_B_lin)
            f_srgb = (linear_to_srgb(f_lin) * 255).clip(0, 255).astype(np.uint8)
            F_rgb_u8 = np.stack([f_srgb] * 3, axis=-1)
            if return_cluster:
                return a_u8, F_rgb_u8, None, None
            return a_u8, F_rgb_u8

    # --- Step 2: Lab chroma-only α solve ---
    leveled_lab = srgb_u8_to_lab(leveled_u8)
    I_L = leveled_lab[..., 0]
    I_a = leveled_lab[..., 1]
    I_b = leveled_lab[..., 2]
    wa = abs(B_lab_mean[1])
    wb = abs(B_lab_mean[2])
    alpha_J = ((wa * (1.0 - I_a / B_lab_mean[1]) +
                wb * (1.0 - I_b / B_lab_mean[2]))
               / max(wa + wb, 1e-9))
    alpha_J = np.clip(alpha_J, 0.0, 1.0)

    # --- Step 3: 2D Mahalanobis bg gate in (a*, b*) ---
    chroma_cov = B_lab_cov[1:, 1:]
    inv_chroma_cov = np.linalg.inv(chroma_cov + np.eye(2) * 1e-8)
    D_chroma = np.stack([I_a - B_lab_mean[1], I_b - B_lab_mean[2]], axis=-1)
    d2 = np.einsum('hwi,ij,hwj->hw', D_chroma, inv_chroma_cov, D_chroma)
    inside_chroma_cluster = d2 < chi2_thresh
    alpha = alpha_J.copy()
    alpha[inside_chroma_cluster] = 0.0

    # --- Step 4: canvas-fill safety ---
    cf = leveled_u8.max(axis=2) <= 15
    alpha[cf] = 0.0
    alpha_u8 = (alpha * 255).round().astype(np.uint8)

    # --- Step 5: recover L_f → grey RGB ---
    L_f = np.where(alpha > 1e-3,
                   (I_L - (1 - alpha) * B_lab_mean[0]) / np.maximum(alpha, 1e-3),
                   0.0)
    L_f = np.clip(L_f, 0, 100)
    fy_inv = (L_f + 16) / 116
    Y_norm = np.where(fy_inv > _LAB_DELTA,
                      fy_inv ** 3,
                      3 * _LAB_DELTA ** 2 * (fy_inv - 4.0 / 29.0))
    f_lin = np.clip(Y_norm, 0, 1)
    f_srgb = (linear_to_srgb(f_lin) * 255).clip(0, 255).astype(np.uint8)
    F_rgb_u8 = np.stack([f_srgb] * 3, axis=-1)

    if return_cluster:
        return alpha_u8, F_rgb_u8, B_lab_mean, B_lab_cov
    return alpha_u8, F_rgb_u8


def closed_form_alpha_hybrid_lab_luma(
    leveled_u8,
    B_lin,
    *,
    luma_floor: int = 100,
    return_cluster: bool = False,
):
    """Single-scan matte robust to background-card colour changes.

    Method K is chroma-driven, which is excellent for coloured yarn on a
    coloured card but weak for black/grey yarn on grey cards where the signal
    is mostly luminance.  Add only the strong closed-form luminance core so
    band detection has a continuous body row without admitting low-level
    background fog into the saved alpha.
    """
    alpha_lab_u8, _F_unused, B_lab_mean, B_lab_cov = (
        closed_form_alpha_and_f_lab_gated(
            leveled_u8,
            return_cluster=True,
            fallback_B_lin=B_lin,
        )
    )
    try:
        a_luma, _f_unused = closed_form_alpha_and_f(leveled_u8, B_lin)
        if not np.isfinite(a_luma).all():
            raise FloatingPointError("non-finite luminance alpha")
        alpha_luma_u8 = (a_luma * 255).round().astype(np.uint8)
    except Exception as e:
        print(f"[hybrid-alpha] luminance fallback skipped ({e})")
        alpha_luma_u8 = np.zeros_like(alpha_lab_u8, dtype=np.uint8)

    alpha_luma_u8 = np.where(
        alpha_luma_u8 >= int(luma_floor),
        alpha_luma_u8,
        0,
    ).astype(np.uint8)
    alpha_u8 = np.maximum(alpha_lab_u8, alpha_luma_u8)
    if return_cluster:
        return alpha_u8, B_lab_mean, B_lab_cov
    return alpha_u8


# === Closed-form achromatic-F (dual scan) ===
def closed_form_alpha_dual(I_red_srgb_u8, I_cyan_srgb_u8, B_red_lin, B_cyan_lin):
    """Dual-scan matting: 6 equations / 2 unknowns under achromatic F.

    Both inputs MUST be the same shape (caller is responsible for alignment).
    Returns H×W uint8 alpha."""
    if I_red_srgb_u8.shape != I_cyan_srgb_u8.shape:
        raise ValueError(
            f"shape mismatch: red={I_red_srgb_u8.shape} cyan={I_cyan_srgb_u8.shape}")
    Ir = srgb_to_linear(I_red_srgb_u8.astype(np.float64) / 255.0)
    Ic = srgb_to_linear(I_cyan_srgb_u8.astype(np.float64) / 255.0)
    Br = np.asarray(B_red_lin, dtype=np.float64).reshape(3)
    Bc = np.asarray(B_cyan_lin, dtype=np.float64).reshape(3)

    sumBr = float(Br.sum()); sumBc = float(Bc.sum())
    ssqBr = float((Br * Br).sum()); ssqBc = float((Bc * Bc).sum())
    SumB = sumBr + sumBc
    SsqB = ssqBr + ssqBc
    det = 6.0 * SsqB - SumB ** 2
    inv_AtA = (1.0 / det) * np.array([[SsqB, SumB], [SumB, 6.0]])

    Dr = Ir - Br
    Dc = Ic - Bc
    b1 = Dr.sum(axis=-1) + Dc.sum(axis=-1)
    b2 = -((Br * Dr).sum(axis=-1) + (Bc * Dc).sum(axis=-1))

    a = inv_AtA[1, 0] * b1 + inv_AtA[1, 1] * b2
    a = np.clip(a, 0.0, 1.0)
    return (a * 255).round().astype(np.uint8)


# === Sub-pixel registration (inlined from 2bgpics/two_bg_solve.py) ===
def estimate_xy_shift(a, b, sample_h=1024):
    """Estimate sub-pixel (dy, dx) shift between two images via FFT
    cross-correlation on a centred horizontal strip + parabolic refinement.
    Returns (dy, dx) such that b ≈ shift(a, dy, dx)."""
    H, W = a.shape[:2]
    y0 = max(0, H // 2 - sample_h // 2)
    y1 = min(H, y0 + sample_h)
    A = a[y0:y1].astype(np.float32).mean(axis=2)
    B = b[y0:y1].astype(np.float32).mean(axis=2)
    A -= A.mean(); B -= B.mean()
    corr = fftconvolve(A, B[::-1, ::-1], mode="same")
    py, px = np.unravel_index(corr.argmax(), corr.shape)
    cy, cx = corr.shape[0] // 2, corr.shape[1] // 2

    def parabolic_offset(v_minus, v_zero, v_plus):
        denom = (v_minus - 2 * v_zero + v_plus)
        if abs(denom) < 1e-9: return 0.0
        return float((v_minus - v_plus) / (2 * denom))

    sub_dy = 0.0
    if 0 < py < corr.shape[0] - 1:
        sub_dy = parabolic_offset(corr[py - 1, px], corr[py, px], corr[py + 1, px])
    sub_dx = 0.0
    if 0 < px < corr.shape[1] - 1:
        sub_dx = parabolic_offset(corr[py, px - 1], corr[py, px], corr[py, px + 1])

    return float(py - cy + sub_dy), float(px - cx + sub_dx)


def shift_image_subpixel(img_u8, dy, dx):
    """Apply a fractional 2-D shift to an RGB image (cubic spline)."""
    if abs(dy) < 1e-6 and abs(dx) < 1e-6:
        return img_u8
    shifted = np.empty_like(img_u8, dtype=np.float64)
    for c in range(img_u8.shape[2]):
        shifted[..., c] = ndimage_shift(img_u8[..., c].astype(np.float64),
                                        shift=(dy, dx), order=3,
                                        mode="reflect", prefilter=True)
    return shifted.clip(0, 255).astype(np.uint8)


def estimate_and_apply_xy_shift(I_ref_u8, I_other_u8, halt_threshold_px=SHIFT_THRESHOLD_PX):
    """Sub-pixel-align I_other to I_ref. Returns (I_other_aligned, dx, dy).
    Raises RuntimeError if the shift exceeds halt_threshold_px."""
    dy, dx = estimate_xy_shift(I_ref_u8, I_other_u8)
    if abs(dx) > halt_threshold_px or abs(dy) > halt_threshold_px:
        raise RuntimeError(
            f"Two scans are misaligned by dx={dx:+.2f}px, dy={dy:+.2f}px "
            f"(threshold {halt_threshold_px}px). Re-scan with the rig held in place."
        )
    if abs(dx) < 0.01 and abs(dy) < 0.01:
        return I_other_u8, dx, dy
    return shift_image_subpixel(I_other_u8, -dy, -dx), dx, dy


# === Apply the same level_and_crop transform to a second image ===
def apply_level_transform(img_arr, angle_deg, bbox):
    """Mirror the rotate+crop done by alpha_pipeline.level_and_crop, given the
    angle_deg and bbox it returned. Lets a second scan be co-aligned to the
    first scan's leveled coordinate system.

    angle_deg, bbox are exactly what alpha_pipeline.level_and_crop returns in
    its `level_meta` dict — see multithread_flow/alpha_pipeline.py:209-284."""
    if abs(angle_deg) > 1e-3:
        pil = Image.fromarray(img_arr).rotate(
            angle_deg, resample=Image.BICUBIC, expand=True, fillcolor=(0, 0, 0)
        )
        img_arr = np.asarray(pil)
    if bbox is not None:
        x0, y0, x1, y1 = bbox
        img_arr = img_arr[y0:y1, x0:x1]
    return img_arr
