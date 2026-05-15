"""Pure-Python pipeline helpers for batch mode.

These mirror two pieces of pipeline logic that today live only in the React UI:

  * `auto_align_yoffsets`     mirrors MultiThreadImageEditor.jsx:handleNext
                              (band-centre alignment, ~lines 204-222)
  * `build_join_canvas`       mirrors MultiFragmentEditor.jsx:buildJoinCanvasAndMask
                              (strip placement + edge-extension + auto mask rect +
                              1024×1024 crop centred on the seam, ~lines 807-951)

NOTE — temporary duplication: as of 2026-05, the same math also lives in the JS
above. This is the "batch-only quick path" scope from the
noble-painting-aho plan. If you change the math here, change the JS too AND re-run
the pixel-equivalence verification (see `web/test_yarn_pipeline.py`).

PIXEL EQUIVALENCE vs the JS: empirically, max diff vs UI's `full_canvas.png` is
~4-9 grey levels, ALL concentrated in edge-extension rows above/below the strip
content (where the canvas extends past the source frag's height range). Root
cause: the browser canvas's `drawImage` with imageSmoothingEnabled=true does
bilinear filtering on the 1-row-tall stretched source, sampling rows 211+212
(blend) at the boundary; Python broadcast just replicates row 212 exactly. The
diff rows are α=0 in the final composite, so they are invisible in the exported
RGBA / dark-blue images.

No Flask, no HTTP. Functions read/write only the files they're explicitly given.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass

import numpy as np
from PIL import Image


# Constants mirror the JS:
STRIP_WIDTH = 512           # MultiFragmentEditor.jsx:64
LAMA_CROP_SIZE = 1024       # MultiFragmentEditor.jsx:65
DEFAULT_MASK_ZONE_FULL = 512  # JS default = 30 display px / typical viewScale ≈ 0.06 → ~500 full-res px.
                              # We expose this as a parameter; default chosen for batch sensibility.
DEFAULT_MASK_HEIGHT_PAD = 10  # MultiFragmentEditor.jsx:67


# ---------------------------------------------------------------------------
# 1. Band-centre alignment ─ mirrors MultiThreadImageEditor.jsx:handleNext
# ---------------------------------------------------------------------------

def _chosen_band(thread: dict, band_source: str = "c") -> dict | None:
    """Replicates `chosenBand()` from MultiThreadImageEditor.jsx:163.

    'c' uses c_band with auto-fallback to d_band if c_band failed
    (top_y < 0). 'd' forces d_band. 'none' returns None.
    """
    if band_source == "d":
        return thread.get("d_band")
    if band_source == "none":
        return None
    c = thread.get("c_band") or {}
    if c.get("top_y", -1) >= 0:
        return c
    return thread.get("d_band")


def auto_align_yoffsets(summary: dict, band_source: str = "c") -> list[dict]:
    """Compute yOffsets so every thread's band centre lands at the same row.

    Returns a `fragments[]` array of {thread_index, w, h, yOffset, name}
    ready to pass to /assemble or /regenerate-alpha. Mirrors the JS at
    MultiThreadImageEditor.jsx:204-222.

    Math:
        yOffset_i = round((h_i / 2) - bandCentre_i)
        clamped to ±300.

    If a thread has no usable band, its yOffset is 0 and its band-centre
    falls back to h/2 (matches the JS).
    """
    threads = summary.get("threads") or []
    fragments: list[dict] = []
    for t in threads:
        band = _chosen_band(t, band_source)
        leveled_size = t.get("leveled_size") or [0, 0]
        # leveled_size is [W, H]; h_i is the leveled image height
        w, h = int(leveled_size[0]), int(leveled_size[1])
        if band and band.get("top_y", -1) >= 0 and band.get("bottom_y", -1) >= 0:
            band_centre = (band["top_y"] + band["bottom_y"]) / 2.0
        else:
            band_centre = h / 2.0
        own_delta = (h / 2.0) - band_centre
        y_offset = int(round(own_delta))
        if y_offset > 300:
            y_offset = 300
        elif y_offset < -300:
            y_offset = -300
        fragments.append({
            "thread_index": int(t.get("index", -1)),
            "w": w, "h": h,
            "yOffset": y_offset,
            "name": f"thread_{t.get('index', '?')}.png",
        })
    return fragments


# ---------------------------------------------------------------------------
# 2. Per-join canvas build ─ mirrors MultiFragmentEditor.jsx:buildJoinCanvasAndMask
# ---------------------------------------------------------------------------

@dataclass
class JoinCanvasResult:
    full_canvas_path: str       # join_<i>_full_canvas.png on disk
    lama_input_path: str        # join_<i>_lama_input.png on disk
    lama_mask_path: str         # join_<i>_lama_mask.png on disk
    fullW: int
    fullH: int
    cropX: int
    cropY: int
    maskRectFull: dict          # {x, y, w, h}


def _detect_thread_band(img_rgb_arr: np.ndarray) -> dict:
    """Per-row content-density band detector. Returns {y0, y1} (y1 exclusive)
    in image-local rows. Replicates MultiFragmentEditor.jsx:30 (`detectThreadBand`).

    Algorithm: count pixels per row with grey in [25, 230]; find peak row;
    expand y0/y1 while density stays > max(60% of peak, 5% of width).
    """
    if img_rgb_arr.ndim != 3 or img_rgb_arr.shape[2] < 3:
        h = img_rgb_arr.shape[0]
        return {"y0": int(h * 0.4), "y1": int(h * 0.6)}
    h, w = img_rgb_arr.shape[:2]
    grey = img_rgb_arr[..., :3].mean(axis=2)
    mask = (grey > 25) & (grey < 230)
    row_counts = mask.sum(axis=1)
    peak_row = int(np.argmax(row_counts))
    peak_count = int(row_counts[peak_row])
    if peak_count == 0:
        return {"y0": int(h * 0.4), "y1": int(h * 0.6)}
    threshold = max(peak_count * 0.60, w * 0.05)
    y0 = peak_row
    while y0 > 0 and row_counts[y0 - 1] >= threshold:
        y0 -= 1
    y1 = peak_row
    while y1 < h - 1 and row_counts[y1 + 1] >= threshold:
        y1 += 1
    return {"y0": int(y0), "y1": int(y1 + 1)}


def _paste_strip_with_edge_extend(canvas: np.ndarray, frag_arr: np.ndarray,
                                  *, sL_or_R: int, side: str, fy: int) -> None:
    """Place `frag_arr` strip into `canvas` (in-place), edge-extending the top
    and bottom rows vertically so nothing above/below is left black.

    Replicates the canvas drawImage(...) sequence in
    MultiFragmentEditor.jsx:840-857 (left strip) and :850-857 (right strip).

    side='left'  → strip is the RIGHTMOST `sL_or_R` cols of frag_arr,
                    pasted into canvas[:, 0 : sL_or_R].
    side='right' → strip is the LEFTMOST  `sL_or_R` cols of frag_arr,
                    pasted into canvas[:, fullW - sL_or_R : fullW].
                    (Caller controls full canvas width via the canvas they pass.)
    """
    fH, fW = frag_arr.shape[:2]
    s = min(sL_or_R, fW)
    canvas_H, canvas_W = canvas.shape[:2]

    if side == "left":
        strip = frag_arr[:, fW - s : fW]
        dest_x0, dest_x1 = 0, s
    elif side == "right":
        strip = frag_arr[:, 0 : s]
        dest_x0 = canvas_W - s
        dest_x1 = canvas_W
    else:
        raise ValueError(f"side must be 'left' or 'right', got {side!r}")

    # Edge-extend ABOVE: rows 0..fy filled with the strip's top row.
    if fy > 0:
        top_row = strip[0:1, :, :]        # shape (1, s, C)
        canvas[0:fy, dest_x0:dest_x1] = np.broadcast_to(top_row, (fy, s, strip.shape[2]))

    # Edge-extend BELOW: rows fy+fH..canvas_H filled with the strip's bottom row.
    bot_start = fy + fH
    if bot_start < canvas_H:
        bot_row = strip[fH - 1 : fH, :, :]   # shape (1, s, C)
        canvas[bot_start:canvas_H, dest_x0:dest_x1] = np.broadcast_to(
            bot_row, (canvas_H - bot_start, s, strip.shape[2]))

    # The actual strip content, clipped to canvas bounds.
    y0c = max(0, fy);  y1c = min(canvas_H, fy + fH)
    y0a = y0c - fy;    y1a = y0a + (y1c - y0c)
    if y1c > y0c:
        canvas[y0c:y1c, dest_x0:dest_x1] = strip[y0a:y1a]


def _crop_1024_edge_extend(src: np.ndarray, *, cropX: int, cropY: int,
                           cropSize: int = LAMA_CROP_SIZE) -> np.ndarray:
    """Take a `cropSize × cropSize` view of `src` centred at (cropX, cropY).
    If the crop overlaps the canvas edges, edge-extend top/bottom rows to fill.

    Replicates `cropTo1024` in MultiFragmentEditor.jsx:905-935.
    """
    fH, fW = src.shape[:2]
    channels = 1 if src.ndim == 2 else src.shape[2]
    if src.ndim == 2:
        out = np.zeros((cropSize, cropSize), dtype=src.dtype)
    else:
        out = np.zeros((cropSize, cropSize, channels), dtype=src.dtype)

    sx = max(0, cropX)
    sy = max(0, cropY)
    sx_end = min(fW, cropX + cropSize)
    sy_end = min(fH, cropY + cropSize)
    sw = sx_end - sx
    sh = sy_end - sy
    if sw <= 0 or sh <= 0:
        return out

    # Edge-extend top: rows above the src — fill with src's top row at the
    # same column range.
    if cropY < 0:
        top_row = src[0:1, sx:sx_end]   # (1, sw, C) or (1, sw)
        rows_to_fill = -cropY
        out[0:rows_to_fill, sx - cropX : sx - cropX + sw] = np.broadcast_to(
            top_row, ((rows_to_fill,) + top_row.shape[1:]))

    # Edge-extend bottom.
    if cropY + cropSize > fH:
        overflow = (cropY + cropSize) - fH
        bot_row = src[fH - 1 : fH, sx:sx_end]
        out[fH - cropY : fH - cropY + overflow, sx - cropX : sx - cropX + sw] = \
            np.broadcast_to(bot_row, ((overflow,) + bot_row.shape[1:]))

    # In-bounds content
    out[sy - cropY : sy - cropY + sh, sx - cropX : sx - cropX + sw] = \
        src[sy:sy_end, sx:sx_end]

    return out


def build_join_canvas(
    *,
    mt_dir: str,
    sdir: str,
    fragments: list[dict],
    join_idx: int,
    strip_w: int = STRIP_WIDTH,
    mask_zone_w: int = DEFAULT_MASK_ZONE_FULL,
    mask_height_pad: int = DEFAULT_MASK_HEIGHT_PAD,
    mask_height_override: int | None = None,
    lama_crop_size: int = LAMA_CROP_SIZE,
    paint_mask_png_path: str | None = None,
) -> JoinCanvasResult:
    """Build the per-join full canvas + 1024×1024 LaMa input crop + mask.

    Mirrors MultiFragmentEditor.jsx:buildJoinCanvasAndMask. All dimensions
    are in FULL-RES pixels.

    Args:
        mt_dir: path to debug/multithread_image/<mt_sid>/ — reads
                thread_<thread_index>_leveled.png for both adjacent fragments.
        sdir:   path to debug/multifragment/<sid>/   — writes
                join_<join_idx>_full_canvas.png, _lama_input.png, _lama_mask.png.
        fragments: array as returned by `auto_align_yoffsets` (must have
                'thread_index' and 'yOffset' at minimum).
        join_idx: 0..N-1; bridges fragment[join_idx] and fragment[(join_idx+1) % N].
        strip_w, mask_zone_w, mask_height_pad, lama_crop_size: see JS constants.
        mask_height_override: if given (full-res px), overrides the auto
                detected_h + pad height. Mirrors `maskHeightOverride` in JS.
        paint_mask_png_path: optional path to an OR-merge mask (white where
                the user painted). Pasted onto the auto rect. Batch normally
                omits this; UI will set it when the user used the paint tool.

    Returns: JoinCanvasResult.
    """
    N = len(fragments)
    if N < 2:
        raise ValueError(f"need >= 2 fragments, got {N}")
    left_idx = join_idx
    right_idx = (join_idx + 1) % N

    left_meta = fragments[left_idx]
    right_meta = fragments[right_idx]

    def _leveled_path(meta: dict) -> str:
        tidx = meta.get("thread_index")
        if tidx is None:
            raise ValueError(f"fragment {meta} missing thread_index")
        return os.path.join(mt_dir, f"thread_{int(tidx)}_leveled.png")

    left_path = _leveled_path(left_meta)
    right_path = _leveled_path(right_meta)
    if not os.path.exists(left_path):
        raise FileNotFoundError(left_path)
    if not os.path.exists(right_path):
        raise FileNotFoundError(right_path)

    left_arr = np.asarray(Image.open(left_path).convert("RGB"))
    right_arr = np.asarray(Image.open(right_path).convert("RGB"))
    left_H, left_W = left_arr.shape[:2]
    right_H, right_W = right_arr.shape[:2]

    sL = min(strip_w, left_W)
    sR = min(strip_w, right_W)
    fullW = sL + sR
    fullH = max(left_H, right_H)
    junctionX = sL

    leftYOffset = int(left_meta.get("yOffset", 0) or 0)
    rightYOffset = int(right_meta.get("yOffset", 0) or 0)
    leftY = round((fullH - left_H) / 2 + leftYOffset)
    rightY = round((fullH - right_H) / 2 + rightYOffset)

    # ---- Full per-join canvas with strips + edge-extension ----
    full_canvas = np.zeros((fullH, fullW, 3), dtype=np.uint8)
    _paste_strip_with_edge_extend(full_canvas, left_arr,
                                  sL_or_R=sL, side="left",  fy=leftY)
    _paste_strip_with_edge_extend(full_canvas, right_arr,
                                  sL_or_R=sR, side="right", fy=rightY)

    # ---- Auto mask rect ----
    half_mask = mask_zone_w / 2.0
    maskLeft = max(0, int(np.floor(junctionX - half_mask)))
    maskRight = min(fullW, int(np.ceil(junctionX + half_mask)))

    lc = _detect_thread_band(left_arr)
    rc = _detect_thread_band(right_arr)
    lYCenter = leftY + (lc["y0"] + lc["y1"]) / 2.0
    rYCenter = rightY + (rc["y0"] + rc["y1"]) / 2.0
    centerY = (lYCenter + rYCenter) / 2.0
    detectedH = max(lc["y1"] - lc["y0"], rc["y1"] - rc["y0"])
    autoH = detectedH + mask_height_pad
    mh = mask_height_override if mask_height_override is not None else autoH
    my = max(0, int(round(centerY - mh / 2)))
    mh_clipped = min(int(round(mh)), fullH - my)

    full_mask = np.zeros((fullH, fullW), dtype=np.uint8)
    full_mask[my : my + mh_clipped, maskLeft:maskRight] = 255

    # Optional paint-mask OR-merge (size must match the per-join canvas)
    if paint_mask_png_path and os.path.exists(paint_mask_png_path):
        pm = np.asarray(Image.open(paint_mask_png_path).convert("L"))
        if pm.shape == full_mask.shape:
            full_mask = np.maximum(full_mask, pm)
        else:
            # Resize to fullH × fullW with nearest neighbour (preserves binary).
            pm_pil = Image.fromarray(pm).resize((fullW, fullH), Image.NEAREST)
            full_mask = np.maximum(full_mask, np.asarray(pm_pil))

    # ---- 1024×1024 LaMa input crop centred on (junctionX, centerY) ----
    cropX = int(round(junctionX - lama_crop_size / 2))
    cropY = int(round(centerY - lama_crop_size / 2))
    crop_canvas = _crop_1024_edge_extend(full_canvas, cropX=cropX, cropY=cropY,
                                         cropSize=lama_crop_size)
    crop_mask = _crop_1024_edge_extend(full_mask, cropX=cropX, cropY=cropY,
                                       cropSize=lama_crop_size)

    # ---- Persist ----
    os.makedirs(sdir, exist_ok=True)
    fc_path = os.path.join(sdir, f"join_{join_idx}_full_canvas.png")
    li_path = os.path.join(sdir, f"join_{join_idx}_lama_input.png")
    lm_path = os.path.join(sdir, f"join_{join_idx}_lama_mask.png")
    Image.fromarray(full_canvas, mode="RGB").save(fc_path)
    Image.fromarray(crop_canvas, mode="RGB").save(li_path)
    Image.fromarray(crop_mask, mode="L").save(lm_path)

    return JoinCanvasResult(
        full_canvas_path=fc_path,
        lama_input_path=li_path,
        lama_mask_path=lm_path,
        fullW=fullW, fullH=fullH,
        cropX=cropX, cropY=cropY,
        maskRectFull={
            "x": maskLeft, "y": my,
            "w": maskRight - maskLeft,
            "h": mh_clipped,
        },
    )


# ---------------------------------------------------------------------------
# Convenience: load a multithread session's summary.json
# ---------------------------------------------------------------------------

def load_summary(mt_dir: str) -> dict:
    sp = os.path.join(mt_dir, "summary.json")
    if not os.path.exists(sp):
        raise FileNotFoundError(sp)
    with open(sp) as f:
        return json.load(f)
