"""Yarnseamless routes — FastAPI port of `yarnseamless/web/lama_server.py`.

Faithful port of the yarn workflow endpoints. The matting flow (SAM2/ViTMatte
single-image) and the batch-mode helpers (auto-align / build-join / run-all)
are intentionally NOT ported here — they are not used by the wizard.

Endpoints exposed:

  GET  /api/lama/health
  POST /api/lama/inpaint
  POST /api/multithread/upload
  POST /api/multithread/process
  GET  /api/multithread/file/{session_id}/{filename}
  GET  /api/multifragment/file/{session_id}/{filename}
  POST /api/multithread/assemble
  POST /api/multithread/regenerate-alpha
  POST /api/multithread/export
  POST /api/multithread/save-to-library

Routing matches the original Flask paths so the React components ported from
yarnseamless need no fetch-URL changes. Internal compute imports come from
`app.yarnseamless.*` (Phase 2a).

Model loading: lazy via `ensure_model_loaded()` and also via the FastAPI
lifespan hook in `main.py`. Fallback chain for the LaMa weights:
  1. `BIG_LAMA_MODEL_PATH` or `LAMA_MODEL` env var
  2. `<yarnseamless UI>/big-lama.pt`              (local shared artifact)
  3. `backend/vendor/yarn_pipeline/big-lama.pt`   (local reconstruction target)
  4. `~/.cache/torch/hub/checkpoints/big-lama.pt`
  5. `seamless_converter.ensure_bundled_model_path()` if chunk files exist
"""
from __future__ import annotations

import base64
import io
import json
import os
import re
import secrets
import shutil
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import torch
from fastapi import APIRouter, Body, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from PIL import Image

try:
    from simple_lama_inpainting.utils import prepare_img_and_mask
except ImportError:  # pragma: no cover
    from simple_lama_inpainting.utils.util import prepare_img_and_mask

# The yarnseamless compute modules. Importing the package triggers the
# multithread_flow/__init__.py sys.path trick so bare imports inside
# `split_threads.py` / `solid_band.py` keep resolving (they import
# `alpha_pipeline`).
from . import yarnseamless  # noqa: F401 — keep import for side effects
from .yarnseamless import band_detect as _band_detect
from .yarnseamless import dual_alpha_pipeline as _dap
from .yarnseamless import thread_segmentation as _seg
from .yarnseamless import yarn_library as _yarn_library
from .yarnseamless.multithread_flow import alpha_pipeline as _ap
from .yarnseamless.multithread_flow import solid_band as _sb
from .yarnseamless.multithread_flow import split_threads as _split_threads
from .runtime_paths import (
    MULTIFRAG_DEBUG_DIR,
    MULTITHREAD_OUTPUT_DIR,
    PROJECT_ROOT,
    UPLOADS_DIR,
    YARN_LIBRARY_ROOT,
    ensure_runtime_dirs,
)


# Allow PIL to open arbitrarily large scans (250 MB TIFFs are normal).
Image.MAX_IMAGE_PIXELS = None
# MPS fallback for ops not supported on Apple GPU.
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")


# ===========================================================================
# Model state
# ===========================================================================
# Loaded once on first /api/lama/inpaint call OR via lifespan hook on startup.
# Globals are module-level (not threaded through every handler) because every
# route reads them and Flask did the same thing.

device: torch.device | None = None
model: Any = None
MODEL_PATH: Path | None = None


def _resolve_model_path() -> Path | None:
    """Search the candidate model paths in order. None if not found."""
    for env_name in ("BIG_LAMA_MODEL_PATH", "LAMA_MODEL"):
        env_path = os.environ.get(env_name)
        if env_path:
            candidate = Path(env_path).expanduser().resolve()
            if candidate.exists() and candidate.is_file():
                return candidate

    candidates: list[Path] = [
        PROJECT_ROOT.parent / "big-lama.pt",
        PROJECT_ROOT / "backend" / "vendor" / "yarn_pipeline" / "big-lama.pt",
        Path.home() / ".cache" / "torch" / "hub" / "checkpoints" / "big-lama.pt",
    ]
    for c in candidates:
        if c.exists() and c.is_file():
            return c
    return None


def ensure_model_loaded() -> None:
    """Idempotent loader. Discovers the weights, picks MPS/CPU, JIT-loads, warmup."""
    global device, model, MODEL_PATH
    if model is not None:
        return

    MODEL_PATH = _resolve_model_path()
    if MODEL_PATH is None:
        # Last resort: ask the vendor seamless_converter to reconstruct from chunks.
        vendor_root = PROJECT_ROOT / "backend" / "vendor" / "yarn_pipeline"
        if str(vendor_root) not in sys.path:
            sys.path.insert(0, str(vendor_root))
        try:
            from seamless_converter import ensure_bundled_model_path  # type: ignore
            reconstructed = ensure_bundled_model_path()
            MODEL_PATH = Path(reconstructed)
        except Exception as e:  # pragma: no cover
            print(f"[lama] vendor reconstruct failed: {e}")
            traceback.print_exc()

    if MODEL_PATH is None or not MODEL_PATH.exists():
        raise RuntimeError(
            "big-lama.pt not found. Set BIG_LAMA_MODEL_PATH or LAMA_MODEL, or place "
            "the file at <yarnseamless UI>/big-lama.pt, "
            "backend/vendor/yarn_pipeline/big-lama.pt, or "
            "~/.cache/torch/hub/checkpoints/big-lama.pt. Vendor chunk "
            "reconstruction is also attempted when chunk files are present."
        )

    if torch.backends.mps.is_available():
        device = torch.device("mps")
        print("[lama] Using MPS (Apple GPU)")
    else:
        device = torch.device("cpu")
        print("[lama] Using CPU")

    print(f"[lama] Loading big-lama from {MODEL_PATH}...")
    model = torch.jit.load(str(MODEL_PATH), map_location="cpu")
    model.eval()
    model.to(device)

    # Warmup so the first user request doesn't pay the JIT compile cost.
    dummy_img = Image.fromarray(np.zeros((256, 256, 3), dtype=np.uint8))
    dummy_mask = Image.fromarray(np.zeros((256, 256), dtype=np.uint8))
    img_t, mask_t = prepare_img_and_mask(dummy_img, dummy_mask, device)
    with torch.inference_mode():
        model(img_t, mask_t)
    if device.type == "mps":
        torch.mps.synchronize()
    print("[lama] Warmup done.")


# ===========================================================================
# Helpers (same shape as lama_server.py)
# ===========================================================================

_SAFE_SESSION_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_SAFE_FILENAME_RE = re.compile(r"^[A-Za-z0-9_-]+\.[A-Za-z0-9]+$")


def _new_session_id() -> str:
    """Replicates yarnseamless's matting_pipeline.new_session_id()."""
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]


def _decode_image(data_uri_or_base64: str) -> Image.Image:
    """Decode a data URI or raw base64 string to PIL Image."""
    if data_uri_or_base64.startswith("data:"):
        _, encoded = data_uri_or_base64.split(",", 1)
    else:
        encoded = data_uri_or_base64
    raw = base64.b64decode(encoded)
    return Image.open(io.BytesIO(raw))


def _encode_image(pil_img: Image.Image) -> str:
    """Encode PIL Image to PNG data URI."""
    buf = io.BytesIO()
    pil_img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f"data:image/png;base64,{b64}"


def _multithread_session_dir(session_id: str) -> Path:
    if not session_id or not _SAFE_SESSION_RE.match(session_id):
        raise HTTPException(status_code=400, detail="Invalid session_id")
    p = (MULTITHREAD_OUTPUT_DIR / session_id).resolve()
    try:
        p.relative_to(MULTITHREAD_OUTPUT_DIR.resolve())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid path")
    return p


def _trim_and_pad_no_wraparound(src_path: str, out_path: str, *, strip_w: int) -> None:
    """Roll the wraparound join from the right edge of `assembled` to span both
    edges of `export`. Same total width. Works on any channel count (RGB / L /
    RGBA) because `assembled_*.png` already has the LaMa-aware join images
    pasted into its wraparound region."""
    a = np.asarray(Image.open(src_path))
    Ww = a.shape[1]
    middle = a[:, : Ww - 2 * strip_w]
    right_block = a[:, Ww - 2 * strip_w : Ww - strip_w]  # left half of wrap
    left_block = a[:, Ww - strip_w : Ww]                 # right half of wrap
    out_arr = np.concatenate([left_block, middle, right_block], axis=1)
    Image.fromarray(out_arr).save(out_path)


def _estimate_background_linear_for_export(
    rgb_u8: np.ndarray,
    alpha_u8: np.ndarray,
    fallback_b_lin: np.ndarray | None = None,
) -> np.ndarray | None:
    if fallback_b_lin is not None:
        arr = np.asarray(fallback_b_lin, dtype=np.float64)
        if arr.shape == (3,) and np.isfinite(arr).all():
            return arr

    rgb = np.asarray(rgb_u8, dtype=np.uint8)
    alpha = np.asarray(alpha_u8, dtype=np.uint8)
    non_canvas = rgb.max(axis=2) > 20
    candidates = (alpha <= 2) & non_canvas
    if int(candidates.sum()) < 256:
        candidates = (alpha <= 24) & non_canvas
    if int(candidates.sum()) < 256:
        return None
    bg_srgb = np.median(rgb[candidates].reshape(-1, 3), axis=0).astype(np.float64) / 255.0
    return _dap.srgb_to_linear(bg_srgb)


def _smoothstep(edge0: float, edge1: float, x: np.ndarray) -> np.ndarray:
    denom = max(1e-6, float(edge1 - edge0))
    t = np.clip((x - edge0) / denom, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def _desaturate_background_spill_rgb(
    rgb_pil: Image.Image,
    alpha_pil: Image.Image,
    *,
    background_linear: np.ndarray | None = None,
) -> Image.Image:
    """Desaturate scan-card coloured spill while preserving yarn RGB detail.

    This is intentionally much narrower than foreground recovery: it estimates
    the scan-card colour, builds a hue/chroma family for lighter and darker
    variants of that colour, then subtracts only that background-colour chroma
    from fringe pixels. High-alpha yarn pixels keep the original scan RGB.
    """
    rgb_u8 = np.asarray(rgb_pil.convert("RGB"), dtype=np.uint8)
    alpha_u8 = np.asarray(alpha_pil.convert("L"), dtype=np.uint8)
    b_lin = _estimate_background_linear_for_export(rgb_u8, alpha_u8, background_linear)
    if b_lin is None:
        return Image.fromarray(rgb_u8, mode="RGB")

    try:
        bg_srgb = (_dap.linear_to_srgb(np.asarray(b_lin, dtype=np.float64)) * 255.0).clip(0, 255)
        rgb = rgb_u8.astype(np.float32)
        alpha = alpha_u8.astype(np.float32)

        # Exact-ish colour range around the card/background. This catches the
        # actual card pixels plus simple darker/lighter scanner variants.
        dist = np.linalg.norm(rgb - bg_srgb.astype(np.float32)[None, None, :], axis=2)
        close_to_bg = 1.0 - _smoothstep(12.0, 145.0, dist)

        # Broader hue family around the background. By comparing chroma after
        # removing luma, light red, dark red, and red-tinted yarn fringe all
        # map back to the same card-colour direction without catching blue/green
        # yarns.
        luma_scalar = 0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]
        rgb_chroma = rgb - luma_scalar[..., None]
        bg_luma = float(0.2126 * bg_srgb[0] + 0.7152 * bg_srgb[1] + 0.0722 * bg_srgb[2])
        bg_chroma = bg_srgb.astype(np.float32) - bg_luma
        bg_chroma_norm = max(1e-6, float(np.linalg.norm(bg_chroma)))
        chroma_norm = np.linalg.norm(rgb_chroma, axis=2)
        bg_chroma_3 = bg_chroma.astype(np.float32)[None, None, :]
        hue_alignment = (
            np.sum(rgb_chroma * bg_chroma_3, axis=2)
            / np.maximum(1e-6, chroma_norm * bg_chroma_norm)
        )
        hue_family = (
            _smoothstep(-0.12, 0.58, hue_alignment)
            * _smoothstep(0.3, 22.0, chroma_norm)
        )

        bg_red_excess = float(bg_srgb[0] - max(bg_srgb[1], bg_srgb[2]))
        if bg_red_excess > 20.0:
            red_excess = rgb[..., 0] - np.maximum(rgb[..., 1], rgb[..., 2])
            hue_like_bg = _smoothstep(1.5, max(14.0, bg_red_excess * 0.42), red_excess)
            colour_gate = np.maximum.reduce((close_to_bg, hue_family, hue_like_bg * 0.95))
        else:
            colour_gate = np.maximum(close_to_bg, hue_family)

        # Keep cleanup strong through the whole transparent/semitransparent
        # fringe and fade only right before opaque yarn. The center/core remains
        # untouched, but red card spill in fine strands is removed completely.
        edge_gate = 1.0 - _smoothstep(236.0, 252.0, alpha)
        strength = np.clip(colour_gate * edge_gate * 1.45, 0.0, 1.0)

        projection = np.maximum(0.0, np.sum(rgb_chroma * bg_chroma_3 / bg_chroma_norm, axis=2))
        chroma_clean = (
            rgb_chroma
            - (bg_chroma_3 / bg_chroma_norm) * projection[..., None] * strength[..., None]
        )
        out = luma_scalar[..., None] + chroma_clean

        # If a pixel is almost exactly the card family, a tiny final neutral mix
        # removes residual red without deleting the strand alpha.
        neutral_strength = np.clip(close_to_bg * edge_gate * 0.35, 0.0, 0.35)
        luma = luma_scalar[..., None]
        out = out * (1.0 - neutral_strength[..., None]) + luma * neutral_strength[..., None]
        return Image.fromarray(out.clip(0, 255).astype(np.uint8), mode="RGB")
    except Exception as exc:
        print(f"[rgba-export] background spill desaturation skipped: {exc}")
        return Image.fromarray(rgb_u8, mode="RGB")


def _summary_background_linear(summary: dict[str, Any] | None) -> np.ndarray | None:
    if not isinstance(summary, dict):
        return None
    raw = summary.get("B_red_linear")
    if raw is None:
        return None
    try:
        arr = np.asarray(raw, dtype=np.float64)
    except Exception:
        return None
    if arr.shape != (3,) or not np.isfinite(arr).all():
        return None
    return arr


def _material_alpha_from_matte(alpha_pil: Image.Image) -> Image.Image:
    """Alpha used by Blender materials: preserve the natural matte."""
    alpha = np.asarray(alpha_pil.convert("L"), dtype=np.uint8)
    material = alpha.copy()
    # Only remove numerical dust from nominally transparent pixels. Do not boost
    # the yarn core to 255: that hard binary alpha was the visible edited slab in
    # zoomed previews and Blender.
    material[material < 4] = 0
    return Image.fromarray(material.astype(np.uint8), mode="L")


def _build_export_set(
    sdir: Path,
    strip_w: int,
    *,
    background_linear: np.ndarray | None = None,
    make_rgba: bool = True,
) -> dict[str, str]:
    """Run _trim_and_pad_no_wraparound for all four assembled outputs that exist,
    plus build the merged RGBA. Returns {kind: filename}."""
    out: dict[str, str] = {}
    for name in (
        "assembled_final.png",
        "assembled_alpha.png",
        "assembled_material_alpha.png",
        "assembled_F.png",
        "assembled_dark_blue.png",
    ):
        src = sdir / name
        if not src.exists():
            continue
        dst = sdir / f"export_{name}"
        base = name.replace("assembled_", "").replace(".png", "")
        try:
            _trim_and_pad_no_wraparound(str(src), str(dst), strip_w=strip_w)
            out[base] = dst.name
        except Exception as e:
            print(f"[export-set] {base} failed: {e}")
    ea = sdir / "export_assembled_alpha.png"
    ema = sdir / "export_assembled_material_alpha.png"
    if ea.exists():
        try:
            material_alpha = _material_alpha_from_matte(Image.open(ea).convert("L"))
            material_alpha.save(ema)
            out["material_alpha"] = ema.name
        except Exception as exc:
            print(f"[export-set] material alpha failed: {exc}")

    # Canonical material preview/export: stitched scan RGB plus natural matte.
    # Keep yarn pixels unprocessed; only neutralize low-alpha background-colour spill.
    ergb = sdir / "export_assembled_final.png"
    ef = sdir / "export_assembled_F.png"
    ea = sdir / "export_assembled_alpha.png"
    alpha_src = ema if ema.exists() else ea
    rgb_src = ergb if ergb.exists() else ef
    if make_rgba and rgb_src.exists() and alpha_src.exists():
        f_pil = Image.open(rgb_src).convert("RGB")
        a_pil = Image.open(alpha_src).convert("L")
        if a_pil.size != f_pil.size:
            ac = Image.new("L", f_pil.size, 0)
            ac.paste(a_pil, (0, 0))
            a_pil = ac
        f_pil = _desaturate_background_spill_rgb(
            f_pil,
            a_pil,
            background_linear=background_linear,
        )
        rgba = Image.merge(
            "RGBA", (f_pil.split()[0], f_pil.split()[1], f_pil.split()[2], a_pil)
        )
        rgba.save(sdir / "export_assembled_rgba.png")
        out["rgba"] = "export_assembled_rgba.png"
    return out


# ===========================================================================
# Router
# ===========================================================================

router = APIRouter()


# --- LaMa health / inpaint ------------------------------------------------

@router.get("/api/lama/health")
async def lama_health() -> dict:
    return {
        "status": "ok",
        "device": str(device) if device else "not-loaded",
        "model": "big-lama",
        "model_path": str(MODEL_PATH) if MODEL_PATH else None,
    }


@router.post("/api/lama/inpaint")
async def lama_inpaint(payload: dict = Body(default_factory=dict)) -> dict:
    image_b64 = payload.get("image")
    mask_b64 = payload.get("mask")
    if not image_b64 or not mask_b64:
        raise HTTPException(status_code=400, detail="Missing image or mask")

    ensure_model_loaded()
    try:
        img_pil = _decode_image(image_b64).convert("RGB")
        mask_pil = _decode_image(mask_b64).convert("L")
        # Ensure mask is strictly binary.
        mask_np = np.array(mask_pil)
        mask_np = ((mask_np > 127) * 255).astype(np.uint8)
        mask_pil = Image.fromarray(mask_np)

        print(f"[lama] Input: {img_pil.size}, mask: {mask_pil.size}")
        img_t, mask_t = prepare_img_and_mask(img_pil, mask_pil, device)

        t0 = time.time()
        with torch.inference_mode():
            result = model(img_t, mask_t)
        if device is not None and device.type == "mps":
            torch.mps.synchronize()
        t1 = time.time()

        result_np = result[0].permute(1, 2, 0).detach().cpu().numpy()
        result_np = np.clip(result_np * 255, 0, 255).astype(np.uint8)
        result_pil = Image.fromarray(result_np)

        print(f"[lama] Done in {t1 - t0:.2f}s, output: {result_pil.size}")
        return {"image": _encode_image(result_pil), "time": round(t1 - t0, 2)}
    except Exception as e:
        print(f"[lama] Error: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# --- Upload / Process -----------------------------------------------------

@router.post("/api/multithread/upload")
async def multithread_upload(file: UploadFile = File(...)) -> dict:
    """Persist a raw scan + return a JPEG thumbnail data URI.

    Browser can't render a 250 MB TIFF in an <img> tag. PIL decodes the file
    server-side, produces a ≤1024 px JPEG for preview.
    """
    ensure_runtime_dirs()
    if file is None or not file.filename:
        raise HTTPException(status_code=400, detail="Missing file field")

    orig_name = file.filename
    lower = orig_name.lower()
    if lower.endswith((".tif", ".tiff")):
        ext = ".tif"
    elif lower.endswith((".jpg", ".jpeg")):
        ext = ".jpg"
    elif lower.endswith(".png"):
        ext = ".png"
    else:
        ext = ".png"  # fallback; PIL will sniff by content

    upload_id = secrets.token_hex(8)
    udir = UPLOADS_DIR / upload_id
    udir.mkdir(parents=True, exist_ok=True)
    fpath = udir / f"input{ext}"
    body = await file.read()
    fpath.write_bytes(body)
    size_bytes = fpath.stat().st_size

    try:
        with Image.open(fpath) as im:
            im = im.convert("RGB")
            W, H = im.size
            im.thumbnail((1024, 1024), Image.LANCZOS)
            buf = io.BytesIO()
            im.save(buf, format="JPEG", quality=82)
            b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        thumb = f"data:image/jpeg;base64,{b64}"
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Failed to decode uploaded image: {e}")

    return {
        "upload_id": upload_id,
        "ext": ext,
        "width": W,
        "height": H,
        "size_bytes": size_bytes,
        "thumbnail_data_url": thumb,
    }


@router.post("/api/multithread/process")
async def multithread_process(payload: dict = Body(default_factory=dict)) -> dict:
    """Run the multithread_flow pipeline on an uploaded scan.

    Body: { upload_id?, image?, image2?, upload_id2?, n_threads?, dpi? }
    Returns the same dict written to summary.json plus URLs.
    """
    ensure_runtime_dirs()
    image_b64 = payload.get("image")
    image2_b64 = payload.get("image2")
    upload_id = payload.get("upload_id")
    upload_id2 = payload.get("upload_id2")
    if not image_b64 and not upload_id:
        raise HTTPException(status_code=400, detail="Missing image or upload_id")

    raw_nt = payload.get("n_threads", None)
    if raw_nt in (None, "", 0, "0", "auto"):
        n_threads: int | None = None
    else:
        try:
            n_threads = int(raw_nt)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="n_threads must be an integer 1..16 or 'auto'")
        if n_threads < 1 or n_threads > 16:
            raise HTTPException(status_code=400, detail="n_threads must be between 1 and 16")

    dpi = float(payload.get("dpi", 1600))
    if not (50 <= dpi <= 12800):
        raise HTTPException(status_code=400, detail="dpi must be between 50 and 12800")

    sid = _new_session_id()
    work_dir = MULTITHREAD_OUTPUT_DIR / sid
    work_dir.mkdir(parents=True, exist_ok=True)

    def _decode_and_save(b64: str, label: str) -> tuple[Path, str]:
        if b64.startswith("data:"):
            header, body = b64.split(",", 1)
            if "tiff" in header or "tif" in header:
                ext_ = ".tif"
            elif "jpeg" in header or "jpg" in header:
                ext_ = ".jpg"
            else:
                ext_ = ".png"
        else:
            body = b64
            ext_ = ".png"
        raw = base64.b64decode(body)
        path = work_dir / f"{label}{ext_}"
        path.write_bytes(raw)
        return path, ext_

    def _copy_from_upload(uid: str, label: str) -> tuple[Path, str]:
        if not _SAFE_SESSION_RE.match(uid or ""):
            raise ValueError("Invalid upload_id")
        udir = UPLOADS_DIR / uid
        if not udir.is_dir():
            raise FileNotFoundError(f"upload_id not found: {uid}")
        found = None
        for fn in os.listdir(udir):
            if fn.startswith("input."):
                found = udir / fn
                break
        if not found:
            raise FileNotFoundError(f"upload_id {uid} has no input file")
        ext_ = found.suffix or ".png"
        dst = work_dir / f"{label}{ext_}"
        shutil.copyfile(found, dst)
        return dst, ext_

    try:
        if upload_id:
            input_path, ext = _copy_from_upload(upload_id, "input")
        else:
            input_path, ext = _decode_and_save(image_b64, "input")
        input2_path: Path | None = None
        if upload_id2:
            input2_path, _ = _copy_from_upload(upload_id2, "input2")
        elif image2_b64:
            input2_path, _ = _decode_and_save(image2_b64, "input2")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to decode image: {e}")

    try:
        timings: dict[str, Any] = {}
        t_total = time.time()

        # Stage 0
        t = time.time()
        img_arr = np.asarray(Image.open(input_path).convert("RGB"))
        H, W = img_arr.shape[:2]
        B_red_lin, _samps_r, picks_r, thr_r = _dap.auto_sample_B(img_arr)
        img2_arr = None
        registration_shift_xy_px = None
        B_cyan_lin = None
        if input2_path is not None:
            img2_arr_raw = np.asarray(Image.open(input2_path).convert("RGB"))
            if img2_arr_raw.shape != img_arr.shape:
                raise HTTPException(
                    status_code=400,
                    detail=f"image2 shape {img2_arr_raw.shape} does not match image {img_arr.shape}",
                )
            B_cyan_lin, _samps_c, picks_c, thr_c = _dap.auto_sample_B(img2_arr_raw)
            try:
                img2_arr, dx, dy = _dap.estimate_and_apply_xy_shift(img_arr, img2_arr_raw)
                registration_shift_xy_px = [round(float(dx), 3), round(float(dy), 3)]
            except RuntimeError as e:
                raise HTTPException(status_code=422, detail=str(e))
        timings["sample_b_and_align"] = round(time.time() - t, 2)

        # Stage 1: segmentation-first split
        t = time.time()
        layout = _split_threads.detect_thread_layout(img_arr, n_threads)
        if getattr(layout, "failure_reason", None):
            raise HTTPException(status_code=422, detail=layout.failure_reason)
        layout_peaks = layout["peaks"] if isinstance(layout, dict) else layout.peaks
        peaks = np.asarray(layout_peaks, dtype=int)
        if n_threads is None:
            if len(peaks) < 1:
                raise HTTPException(
                    status_code=422,
                    detail=(f"Auto-detect found only {len(peaks)} thread(s). "
                            "Try a manual count, or check the scan contrast."),
                )
            if len(peaks) > 16:
                raise HTTPException(
                    status_code=422,
                    detail=(f"Auto-detect found {len(peaks)} candidate peaks (max 16). "
                            "Provide an explicit n_threads to disambiguate."),
                )
            n_threads = int(len(peaks))
        strips = _split_threads.split_into_strips(img_arr, peaks)
        if img2_arr is not None:
            strips2 = _split_threads.split_into_strips(img2_arr, peaks)
        _split_threads.save_detection_overlay(
            img_arr, peaks, strips, str(work_dir / "detection_overlay.png")
        )
        segmentation_debug_files: dict[str, str] = {}
        segmentation_summary: dict[str, Any] | None = None
        if hasattr(layout, "to_json"):
            segmentation_summary = layout.to_json()
            try:
                segmentation_debug_files = _seg.save_detection_debug_images(img_arr, layout, work_dir)
            except Exception as _e:
                print(f"[multithread/process] segmentation debug save skipped: {_e}")
        raw_dir = work_dir / "raw_strips"
        raw_dir.mkdir(parents=True, exist_ok=True)
        timings["detect_split"] = round(time.time() - t, 2)

        summary: dict[str, Any] = {
            "input": str(input_path),
            "input_size": [W, H],
            "peaks": [int(p) for p in peaks],
            "threads": [],
            "n_threads": int(len(peaks)),
            "B_red_linear": B_red_lin.tolist(),
            "dpi": dpi,
            "two_image": img2_arr is not None,
        }
        if segmentation_summary is not None:
            summary["segmentation"] = segmentation_summary
        if B_cyan_lin is not None:
            summary["B_cyan_linear"] = B_cyan_lin.tolist()
        if registration_shift_xy_px is not None:
            summary["registration_shift_xy_px"] = registration_shift_xy_px
        if input2_path is not None:
            summary["input2"] = str(input2_path)

        # Stage 2: per-thread leveling + alpha + band
        per_thread_timings = []
        for i, (x0, x1, strip) in enumerate(strips):
            tt: dict[str, Any] = {}
            t = time.time()
            raw_path = raw_dir / f"thread_{i}.png"
            Image.fromarray(strip).save(raw_path)
            if img2_arr is not None:
                Image.fromarray(strips2[i][2]).save(raw_dir / f"thread_{i}_cyan.png")
            tt["save_raw"] = round(time.time() - t, 2)

            t = time.time()
            leveled_path = work_dir / f"thread_{i}_leveled.png"
            preprocess_meta = _ap.preprocess(
                str(raw_path), str(leveled_path), preset="auto",
                orientation="auto", level=True,
            )
            # Inscribed-rectangle crop (eliminates rotation-fill black at corners).
            try:
                leveled = np.asarray(Image.open(leveled_path).convert("RGB"))
                fill = (leveled.max(axis=2) <= 20)
                if fill.any():
                    H_l, W_l, _ = leveled.shape
                    col_idx = np.arange(W_l)
                    first_real = np.where(fill, W_l, col_idx[None, :]).min(axis=1)
                    last_real = np.where(fill, -1, col_idx[None, :]).max(axis=1)
                    best_area = 0
                    best = None
                    for y0_ in range(H_l):
                        if first_real[y0_] >= W_l:
                            continue
                        cum_l = int(first_real[y0_])
                        cum_r = int(last_real[y0_])
                        for y1_ in range(y0_, H_l):
                            if first_real[y1_] >= W_l:
                                break
                            fr = int(first_real[y1_])
                            lr = int(last_real[y1_])
                            if fr > cum_l: cum_l = fr
                            if lr < cum_r: cum_r = lr
                            if cum_r < cum_l: break
                            area = (y1_ - y0_ + 1) * (cum_r - cum_l + 1)
                            if area > best_area:
                                best_area = area
                                best = (y0_, y1_, cum_l, cum_r)
                    if best is not None:
                        y0_, y1_, x0_, x1_ = best
                        cropped = leveled[y0_:y1_ + 1, x0_:x1_ + 1]
                        Image.fromarray(cropped).save(leveled_path)
            except Exception as _e:
                print(f"[inscribed-crop] thread {i} skipped: {_e}")
            tt["preprocess_level"] = round(time.time() - t, 2)

            t = time.time()
            alpha_path = work_dir / f"thread_{i}_alpha.png"
            leveled_rgb_1 = np.asarray(Image.open(leveled_path).convert("RGB"))
            F_rgb_thread = leveled_rgb_1.copy()

            if img2_arr is not None:
                strip2_arr = strips2[i][2]
                detected_orient = preprocess_meta.get("orientation", "horizontal")
                if detected_orient == "vertical":
                    strip2_arr = np.rot90(strip2_arr, k=-1)
                level_meta = preprocess_meta.get("level", {})
                leveled_rgb_2 = _dap.apply_level_transform(
                    strip2_arr,
                    angle_deg=level_meta.get("angle_deg", 0.0),
                    bbox=level_meta.get("bbox"),
                )
                if leveled_rgb_2.shape != leveled_rgb_1.shape:
                    h_min = min(leveled_rgb_1.shape[0], leveled_rgb_2.shape[0])
                    w_min = min(leveled_rgb_1.shape[1], leveled_rgb_2.shape[1])
                    leveled_rgb_1 = leveled_rgb_1[:h_min, :w_min]
                    leveled_rgb_2 = leveled_rgb_2[:h_min, :w_min]
                alpha_arr_u8 = _dap.closed_form_alpha_dual(
                    leveled_rgb_1, leveled_rgb_2, B_red_lin, B_cyan_lin)
                thread_B_lab_mean = None
                thread_B_lab_cov = None
            else:
                try:
                    alpha_arr_u8, thread_B_lab_mean, thread_B_lab_cov = (
                        _dap.closed_form_alpha_hybrid_lab_luma(
                            leveled_rgb_1,
                            B_red_lin,
                            return_cluster=True,
                        )
                    )
                except Exception as _ek:
                    print(f"[multithread/process] thread {i} Method K failed ({_ek}); falling back to Method A")
                    a_lin, _f_lin = _dap.closed_form_alpha_and_f(leveled_rgb_1, B_red_lin)
                    alpha_arr_u8 = (a_lin * 255).round().astype(np.uint8)
                    thread_B_lab_mean = None
                    thread_B_lab_cov = None
            black_fill = (
                (leveled_rgb_1[..., 0] == 0)
                & (leveled_rgb_1[..., 1] == 0)
                & (leveled_rgb_1[..., 2] == 0)
            )
            if black_fill.any():
                alpha_arr_u8[black_fill] = 0
                F_rgb_thread[black_fill] = 0
            alpha_seg_quality: dict[str, Any] | None = None
            alpha_seg_debug_files: dict[str, str] = {}
            try:
                alpha_seg = _seg.segment_thread_alpha(
                    leveled_rgb_1,
                    alpha_arr_u8,
                    horizontal=True,
                )
                alpha_arr_u8 = alpha_seg.alpha_u8
                if black_fill.any():
                    alpha_arr_u8[black_fill] = 0
                    F_rgb_thread[black_fill] = 0
                alpha_seg_quality = alpha_seg.quality
                alpha_seg_debug_files = _seg.save_thread_alpha_debug(
                    alpha_seg,
                    work_dir,
                    f"thread_{i}",
                )
            except Exception as _e_seg:
                print(f"[multithread/process] thread {i} segmentation alpha cleanup skipped: {_e_seg}")
            Image.fromarray(alpha_arr_u8, mode="L").save(alpha_path)
            try:
                Image.fromarray(F_rgb_thread).save(work_dir / f"thread_{i}_F.png")
            except Exception as _eF:
                print(f"[multithread/process] thread {i} F save failed: {_eF}")
            meta = {
                "orientation": preprocess_meta.get("orientation", "horizontal"),
                "level": preprocess_meta.get("level", {}),
                "auto_preset": preprocess_meta.get("auto_preset"),
                "active_preset": preprocess_meta.get("active_preset"),
                "confidence": preprocess_meta.get("confidence"),
            }
            tt["alpha_run"] = round(time.time() - t, 2)

            t = time.time()
            alpha_arr = np.asarray(Image.open(alpha_path).convert("L"))
            leveled_arr = np.asarray(Image.open(leveled_path).convert("RGB"))
            band_result = _seg.detect_band_quality(alpha_arr)
            c_res = band_result["c_band"]
            d_res = band_result["d_band"]
            _sb.save_visualization(
                f"thread_{i}", c_res["top_y"], c_res["bottom_y"], leveled_arr,
                out_dir=str(work_dir), line_width=1, suffix="_c_visualization",
            )
            _sb.save_visualization(
                f"thread_{i}", d_res["top_y"], d_res["bottom_y"], leveled_arr,
                out_dir=str(work_dir), line_width=1, suffix="_d_visualization",
            )
            fiber_top_y_c, fiber_bot_y_c = c_res["fiber_top_y"], c_res["fiber_bot_y"]
            fiber_top_y_d, fiber_bot_y_d = d_res["fiber_top_y"], d_res["fiber_bot_y"]
            tt["band_detect"] = round(time.time() - t, 2)
            tt["total"] = round(sum(v for v in tt.values() if isinstance(v, (int, float))), 2)
            per_thread_timings.append(tt)

            def _band_dict(res, fty, fby):
                tv, bv = res["top_y"], res["bottom_y"]
                return {"top_y": tv, "bottom_y": bv,
                        "height": int(res.get("height", bv - tv if bv >= 0 else -1)),
                        "fiber_top_y": int(fty), "fiber_bot_y": int(fby)}

            H_t, W_t = alpha_arr.shape
            band_top = c_res.get("top_y", -1)
            band_bot = c_res.get("bottom_y", -1)
            width_samples = []
            if band_top >= 0 and band_bot > band_top and W_t >= 5:
                margin = max(50, W_t // 20)
                xs = np.linspace(margin, W_t - 1 - margin, 5).round().astype(int)
                width_px = int(band_bot - band_top + 1)
                width_mm = round(width_px / dpi * 25.4, 4)
                for x_meas in xs:
                    width_samples.append({
                        "x": int(x_meas),
                        "top_y": int(band_top),
                        "bottom_y": int(band_bot),
                        "width_px": width_px,
                        "width_mm": width_mm,
                    })

            selected_candidates = getattr(layout, "candidates", []) if not isinstance(layout, dict) else []
            split_quality = None
            if i < len(selected_candidates):
                cand = selected_candidates[i]
                split_quality = {
                    "x_center": int(cand.x_center),
                    "x0": int(cand.x0),
                    "x1": int(cand.x1),
                    "score": float(cand.score),
                    "peak_score": float(cand.peak_score),
                    "peak_density": float(cand.peak_density),
                    "continuity": float(cand.continuity),
                }
            failure_reason = None
            if alpha_seg_quality and alpha_seg_quality.get("failure_reason"):
                failure_reason = alpha_seg_quality.get("failure_reason")
            if band_result["quality"].get("failure_reason"):
                failure_reason = band_result["quality"].get("failure_reason")

            thread_entry = {
                "index": i,
                "x_range": [x0, x1],
                "raw_size": [strip.shape[1], strip.shape[0]],
                "orientation": meta["orientation"],
                "tilt_angle_deg": meta["level"].get("angle_deg"),
                "leveled_size": meta["level"].get("cropped_size"),
                "auto_preset": meta["auto_preset"],
                "preset_confidence": meta["confidence"],
                "c_band": _band_dict(c_res, fiber_top_y_c, fiber_bot_y_c),
                "d_band": _band_dict(d_res, fiber_top_y_d, fiber_bot_y_d),
                "width_samples": width_samples,
                "segmentation_quality": {
                    "split": split_quality,
                    "alpha": alpha_seg_quality,
                },
                "band_quality": band_result["quality"],
                "foreground_separation": (
                    alpha_seg_quality.get("foreground_separation")
                    if alpha_seg_quality else None
                ),
                "failure_reason": failure_reason,
                "qa_files": alpha_seg_debug_files,
                "timings": tt,
            }
            if thread_B_lab_mean is not None and thread_B_lab_cov is not None:
                thread_entry["B_lab_mean"] = [float(v) for v in thread_B_lab_mean]
                thread_entry["B_lab_cov"] = [[float(v) for v in row] for row in thread_B_lab_cov]
            summary["threads"].append(thread_entry)

        timings["per_thread"] = per_thread_timings
        timings["total"] = round(time.time() - t_total, 2)
        summary["timings"] = timings

        with open(work_dir / "summary.json", "w") as f:
            json.dump(summary, f, indent=2)

        elapsed = timings["total"]
        breakdown = ", ".join(f"t{i}={tt['total']}s" for i, tt in enumerate(per_thread_timings))
        print(f"[multithread] Session {sid}: detect+split={timings['detect_split']}s | {breakdown} | total={elapsed}s")
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Pipeline failed: {e}")

    base_url = f"/api/multithread/file/{sid}"
    summary["session_id"] = sid
    summary["urls"] = {
        "detection_overlay": f"{base_url}/detection_overlay.png",
        "input": f"{base_url}/input{ext}",
    }
    for key, filename in segmentation_debug_files.items():
        summary["urls"][key] = f"{base_url}/{filename}"
    for t_entry in summary.get("threads", []):
        i = t_entry["index"]
        t_entry["urls"] = {
            "leveled": f"{base_url}/thread_{i}_leveled.png",
            "alpha":   f"{base_url}/thread_{i}_alpha.png",
            "c_viz":   f"{base_url}/thread_{i}_c_visualization.png",
            "d_viz":   f"{base_url}/thread_{i}_d_visualization.png",
        }
        for key, filename in (t_entry.get("qa_files") or {}).items():
            t_entry["urls"][key] = f"{base_url}/{filename}"
    summary["elapsed_seconds"] = elapsed
    return summary


# --- Static file serving --------------------------------------------------

@router.get("/api/multithread/file/{session_id}/{filename}")
async def multithread_file(session_id: str, filename: str):
    if not _SAFE_SESSION_RE.match(session_id):
        raise HTTPException(status_code=400, detail="Invalid session_id")
    if not _SAFE_FILENAME_RE.match(filename) or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    sdir = _multithread_session_dir(session_id)
    full = (sdir / filename).resolve()
    try:
        full.relative_to(MULTITHREAD_OUTPUT_DIR.resolve())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid path")
    if not full.exists():
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(str(full))


@router.post("/api/multifragment/save-debug")
async def multifragment_save_debug(payload: dict = Body(default_factory=dict)) -> dict:
    """Persist per-join PNG bundles uploaded as base64 data URIs from the
    React MultiFragmentEditor. Port of yarnseamless's Node server.js handler.

    Body:
      {
        session_id: str,
        files:      { "<filename>": "data:image/png;base64,<...>", ... },
        metadata?:  any  // optional; written as metadata.json
      }

    Returns: { session_id, dir, saved: [names] }
    """
    ensure_runtime_dirs()
    session_id = payload.get("session_id")
    files = payload.get("files") or {}
    metadata = payload.get("metadata")
    if not session_id or not files:
        raise HTTPException(status_code=400, detail="Missing session_id or files")

    # Sanitize same way the original server.js does.
    safe_sid = re.sub(r"[^a-zA-Z0-9_-]", "_", str(session_id))
    if not safe_sid:
        raise HTTPException(status_code=400, detail="Invalid session_id")
    sdir = (MULTIFRAG_DEBUG_DIR / safe_sid).resolve()
    try:
        sdir.relative_to(MULTIFRAG_DEBUG_DIR.resolve())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid path")
    sdir.mkdir(parents=True, exist_ok=True)

    saved: list[str] = []
    try:
        for name, data_uri in files.items():
            safe_name = re.sub(r"[^a-zA-Z0-9_.-]", "_", str(name))
            if not safe_name:
                continue
            # Expect data:<mime>;base64,<payload>
            s = str(data_uri or "")
            m = re.match(r"^data:[^;]+;base64,(.+)$", s)
            if not m:
                continue
            blob = base64.b64decode(m.group(1))
            (sdir / safe_name).write_bytes(blob)
            saved.append(safe_name)
        if metadata is not None:
            (sdir / "metadata.json").write_text(
                json.dumps(metadata, indent=2), encoding="utf-8"
            )
        print(f"[multifrag-debug] Session {safe_sid}: saved {len(saved)} files → {sdir}")
        return {"session_id": safe_sid, "dir": str(sdir), "saved": saved}
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/multifragment/open-debug")
async def multifragment_open_debug(payload: dict = Body(default_factory=dict)) -> dict:
    """Open the multifragment debug folder in Finder (macOS) / Explorer
    (Windows) / xdg-open (Linux). Port of yarnseamless's Node handler."""
    import shutil as _shutil
    import subprocess
    session_id = payload.get("session_id")
    if not session_id:
        raise HTTPException(status_code=400, detail="Missing session_id")
    safe_sid = re.sub(r"[^a-zA-Z0-9_-]", "_", str(session_id))
    if not safe_sid:
        raise HTTPException(status_code=400, detail="Invalid session_id")
    sdir = (MULTIFRAG_DEBUG_DIR / safe_sid).resolve()
    try:
        sdir.relative_to(MULTIFRAG_DEBUG_DIR.resolve())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid path")
    if not sdir.is_dir():
        raise HTTPException(status_code=404, detail="Session folder not found")
    # Pick the right opener for the platform.
    opener = None
    if sys.platform == "darwin":
        opener = "open"
    elif sys.platform.startswith("linux") and _shutil.which("xdg-open"):
        opener = "xdg-open"
    elif sys.platform == "win32":
        opener = "explorer"
    if opener:
        try:
            subprocess.Popen([opener, str(sdir)], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        except Exception as e:
            traceback.print_exc()
    return {"ok": True, "dir": str(sdir)}


@router.get("/api/multifragment/file/{session_id}/{filename}")
async def multifragment_file(session_id: str, filename: str):
    if not _SAFE_SESSION_RE.match(session_id):
        raise HTTPException(status_code=400, detail="Invalid session_id")
    if not _SAFE_FILENAME_RE.match(filename) or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    full = (MULTIFRAG_DEBUG_DIR / session_id / filename).resolve()
    try:
        full.relative_to(MULTIFRAG_DEBUG_DIR.resolve())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid path")
    if not full.exists():
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(str(full))


# --- Assemble -------------------------------------------------------------

@router.post("/api/multithread/assemble")
async def multithread_assemble(payload: dict = Body(default_factory=dict)) -> dict:
    """Server-side assembly via Pillow — no browser canvas-dim limit."""
    sid = payload.get("multifragment_session_id")
    mt_sid = payload.get("multithread_session_id")
    fragments = payload.get("fragments") or []
    strip_w = int(payload.get("strip_width", 512))
    join_usage = payload.get("join_usage") or []
    if not sid or not _SAFE_SESSION_RE.match(sid):
        raise HTTPException(status_code=400, detail="Missing/invalid multifragment_session_id")
    if not fragments:
        raise HTTPException(status_code=400, detail="Missing fragments[]")
    sdir = (MULTIFRAG_DEBUG_DIR / sid).resolve()
    try:
        sdir.relative_to(MULTIFRAG_DEBUG_DIR.resolve())
    except ValueError:
        raise HTTPException(status_code=404, detail="Multifragment session not found")
    if not sdir.is_dir():
        raise HTTPException(status_code=404, detail="Multifragment session not found")

    frag_paths: list[Path] = []
    for f in fragments:
        if f.get("thread_index") is not None and mt_sid and _SAFE_SESSION_RE.match(mt_sid):
            p = MULTITHREAD_OUTPUT_DIR / mt_sid / f"thread_{int(f['thread_index'])}_leveled.png"
        elif f.get("leveled_filename"):
            fname = str(f["leveled_filename"]).replace("..", "")
            p = sdir / fname
        else:
            raise HTTPException(status_code=400, detail=f"Fragment {f.get('name','?')} missing path info")
        if not p.exists():
            raise HTTPException(status_code=404, detail=f"Fragment image not found: {p}")
        frag_paths.append(p)

    join_paths: list[Path] = []
    for i in range(len(fragments)):
        usage = join_usage[i] if i < len(join_usage) else "inpaint"
        fname = f"join_{i}_full_canvas.png" if usage == "skip" else f"join_{i}_pasted_back.png"
        p = sdir / fname
        if not p.exists():
            alt = f"join_{i}_pasted_back.png" if usage == "skip" else f"join_{i}_full_canvas.png"
            p_alt = sdir / alt
            if p_alt.exists():
                p = p_alt
            else:
                raise HTTPException(
                    status_code=404,
                    detail=f"Missing {fname} — re-run Inpaint All Joins first",
                )
        join_paths.append(p)

    try:
        t0 = time.time()
        frag_imgs = [Image.open(p).convert("RGB") for p in frag_paths]
        join_imgs = [Image.open(p).convert("RGB") for p in join_paths]

        N = len(frag_imgs)
        total_h = max(*[im.height for im in frag_imgs], *[im.height for im in join_imgs])
        interior_widths = [max(0, im.width - 2 * strip_w) for im in frag_imgs]
        total_w = sum(interior_widths) + sum(im.width for im in join_imgs)

        out = Image.new("RGB", (total_w, total_h), "black")
        join_x_centers = []
        x = 0
        for j in range(N):
            frag = frag_imgs[j]
            interior = interior_widths[j]
            yo = int(fragments[j].get("yOffset", 0) or 0)
            frag_y = (total_h - frag.height) // 2 + yo
            if interior > 0:
                interior_crop = frag.crop((strip_w, 0, frag.width - strip_w, frag.height))
                out.paste(interior_crop, (x, frag_y))
            x += interior
            jim = join_imgs[j]
            join_y = (total_h - jim.height) // 2
            out.paste(jim, (x, join_y))
            join_x_centers.append(int(x + jim.width // 2))
            x += jim.width

        out_path = sdir / "assembled_final.png"
        out.save(out_path, "PNG")
        elapsed = round(time.time() - t0, 2)
        print(f"[multithread-assemble] {sid}: {total_w}x{total_h} in {elapsed}s")
        return {
            "assembled_url": f"/api/multifragment/file/{sid}/assembled_final.png",
            "w": total_w, "h": total_h,
            "join_x_centers": join_x_centers,
            "time_seconds": elapsed,
        }
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Assembly failed: {e}")


# --- Regenerate alpha ------------------------------------------------------

@router.post("/api/multithread/regenerate-alpha")
async def multithread_regenerate_alpha(payload: dict = Body(default_factory=dict)) -> dict:
    """Per-join + assembled α/F regeneration. Builds assembled_F, RGBA, dark-blue,
    and the no-wraparound export set. See yarnseamless docs/alpha_policy.md."""
    sid = payload.get("multifragment_session_id") or payload.get("session_id")
    mt_sid = payload.get("multithread_session_id")
    fragments = payload.get("fragments") or []
    strip_w = int(payload.get("strip_width", 512))
    make_rgba = bool(payload.get("make_rgba", True))
    join_usage = payload.get("join_usage") or []
    make_dark_blue = bool(payload.get("make_dark_blue", True))
    if not sid or not _SAFE_SESSION_RE.match(sid):
        raise HTTPException(status_code=400, detail="Missing/invalid multifragment_session_id")
    sdir = (MULTIFRAG_DEBUG_DIR / sid).resolve()
    try:
        sdir.relative_to(MULTIFRAG_DEBUG_DIR.resolve())
    except ValueError:
        raise HTTPException(status_code=404, detail="Session not found")
    if not sdir.is_dir():
        raise HTTPException(status_code=404, detail="Session not found")

    from scipy import ndimage as _ndimage  # noqa: F401 — kept for parity with yarnseamless

    # B_red from the multithread session (saved during /process).
    B_red_lin = None
    if mt_sid and _SAFE_SESSION_RE.match(mt_sid):
        mt_summary_path = MULTITHREAD_OUTPUT_DIR / mt_sid / "summary.json"
        if mt_summary_path.exists():
            try:
                with open(mt_summary_path) as fp:
                    mt_summary = json.load(fp)
                if "B_red_linear" in mt_summary:
                    B_red_lin = np.array(mt_summary["B_red_linear"], dtype=np.float64)
            except Exception as e:
                print(f"[regen-alpha] could not read B_red: {e}")

    joins_meta = payload.get("joins") or []
    join_indices = list(range(len(fragments)))

    frag_alpha_paths: list[Path | None] = []
    frag_F_paths: list[Path | None] = []
    for f in fragments:
        idx = f.get("thread_index")
        if idx is not None and mt_sid and _SAFE_SESSION_RE.match(mt_sid):
            ap_p = MULTITHREAD_OUTPUT_DIR / mt_sid / f"thread_{int(idx)}_alpha.png"
            fp_p = MULTITHREAD_OUTPUT_DIR / mt_sid / f"thread_{int(idx)}_F.png"
            frag_alpha_paths.append(ap_p if ap_p.exists() else None)
            frag_F_paths.append(fp_p if fp_p.exists() else None)
        else:
            frag_alpha_paths.append(None)
            frag_F_paths.append(None)

    boxes: list[dict[str, Any]] = []
    for i in join_indices:
        usage = join_usage[i] if i < len(join_usage) else "inpaint"
        out_name = f"join_{i}_alpha.png"
        out_path = sdir / out_name
        t0 = time.time()
        try:
            jmeta = joins_meta[i] if i < len(joins_meta) and joins_meta[i] else None
            if jmeta:
                fullW_j = int(jmeta.get("fullW") or 0)
                fullH_j = int(jmeta.get("fullH") or 0)
            else:
                fullW_j = fullH_j = 0
            if not (fullW_j and fullH_j):
                pb_path = sdir / f"join_{i}_pasted_back.png"
                fc_path = sdir / f"join_{i}_full_canvas.png"
                size_src = pb_path if pb_path.exists() else (fc_path if fc_path.exists() else None)
                if size_src:
                    with Image.open(size_src) as im:
                        fullW_j, fullH_j = im.size
                else:
                    print(f"[regen-alpha] join {i} skipped — no canvas size info")
                    continue

            join_alpha = np.zeros((fullH_j, fullW_j), dtype=np.uint8)
            N_frags = len(fragments)
            left_idx = i
            right_idx = (i + 1) % N_frags
            left_apath = frag_alpha_paths[left_idx] if left_idx < len(frag_alpha_paths) else None
            right_apath = frag_alpha_paths[right_idx] if right_idx < len(frag_alpha_paths) else None

            sL = strip_w
            sR = strip_w

            def _paste_left_strip(canvas, alpha_img, frag_meta):
                if alpha_img is None or frag_meta is None: return
                A = np.asarray(alpha_img.convert("L"))
                fH, fW = A.shape
                use_sL = min(sL, fW)
                yo = int(frag_meta.get("yOffset", 0) or 0)
                fy = (fullH_j - fH) // 2 + yo
                y0c = max(0, fy);                y1c = min(fullH_j, fy + fH)
                y0a = y0c - fy;                  y1a = y0a + (y1c - y0c)
                if y1c > y0c and use_sL > 0:
                    canvas[y0c:y1c, 0:use_sL] = A[y0a:y1a, fW - use_sL: fW]

            def _paste_right_strip(canvas, alpha_img, frag_meta):
                if alpha_img is None or frag_meta is None: return
                A = np.asarray(alpha_img.convert("L"))
                fH, fW = A.shape
                use_sR = min(sR, fW)
                yo = int(frag_meta.get("yOffset", 0) or 0)
                fy = (fullH_j - fH) // 2 + yo
                y0c = max(0, fy);                y1c = min(fullH_j, fy + fH)
                y0a = y0c - fy;                  y1a = y0a + (y1c - y0c)
                if y1c > y0c and use_sR > 0:
                    canvas[y0c:y1c, sL:sL + use_sR] = A[y0a:y1a, 0:use_sR]

            if left_apath:
                with Image.open(left_apath) as la_img:
                    _paste_left_strip(join_alpha, la_img, fragments[left_idx])
            if right_apath:
                with Image.open(right_apath) as ra_img:
                    _paste_right_strip(join_alpha, ra_img, fragments[right_idx])

            def _paste_F_left(canvas, F_img_pil, frag_meta):
                if F_img_pil is None or frag_meta is None: return
                Fa = np.asarray(F_img_pil.convert("RGB"))
                fH, fW = Fa.shape[:2]
                use_sL = min(sL, fW)
                yo = int(frag_meta.get("yOffset", 0) or 0)
                fy = (fullH_j - fH) // 2 + yo
                y0c = max(0, fy); y1c = min(fullH_j, fy + fH)
                y0a = y0c - fy;  y1a = y0a + (y1c - y0c)
                if y1c > y0c and use_sL > 0:
                    canvas[y0c:y1c, 0:use_sL] = Fa[y0a:y1a, fW - use_sL: fW]

            def _paste_F_right(canvas, F_img_pil, frag_meta):
                if F_img_pil is None or frag_meta is None: return
                Fa = np.asarray(F_img_pil.convert("RGB"))
                fH, fW = Fa.shape[:2]
                use_sR = min(sR, fW)
                yo = int(frag_meta.get("yOffset", 0) or 0)
                fy = (fullH_j - fH) // 2 + yo
                y0c = max(0, fy); y1c = min(fullH_j, fy + fH)
                y0a = y0c - fy;  y1a = y0a + (y1c - y0c)
                if y1c > y0c and use_sR > 0:
                    canvas[y0c:y1c, sL:sL + use_sR] = Fa[y0a:y1a, 0:use_sR]

            F_full = np.zeros((fullH_j, fullW_j, 3), dtype=np.uint8)
            left_fpath = frag_F_paths[left_idx] if left_idx < len(frag_F_paths) else None
            right_fpath = frag_F_paths[right_idx] if right_idx < len(frag_F_paths) else None
            if left_fpath:
                with Image.open(left_fpath) as lf_img:
                    _paste_F_left(F_full, lf_img, fragments[left_idx])
            if right_fpath:
                with Image.open(right_fpath) as rf_img:
                    _paste_F_right(F_full, rf_img, fragments[right_idx])

            if usage == "inpaint" and jmeta and jmeta.get("maskRectFull"):
                in_path = sdir / f"join_{i}_pasted_back.png"
                if in_path.exists():
                    try:
                        rect = jmeta["maskRectFull"]
                        rx = int(rect.get("x", 0)); ry = int(rect.get("y", 0))
                        rw = int(rect.get("w", 0)); rh = int(rect.get("h", 0))
                        rx0 = max(0, rx); ry0 = max(0, ry)
                        rx1 = min(fullW_j, rx + rw); ry1 = min(fullH_j, ry + rh)
                        with Image.open(in_path) as pim:
                            pasted = np.asarray(pim.convert("RGB"))
                        sub = pasted[ry0:ry1, rx0:rx1]
                        B_local = _dap.sample_local_B_from_borders(sub, band=6)
                        B_use = B_local if B_local is not None else B_red_lin
                        if B_use is None:
                            legacy_path = str(out_path) + ".tmp_legacy.png"
                            _ap.run(str(in_path), legacy_path, preset="auto",
                                    orientation="horizontal", level=False)
                            with Image.open(legacy_path) as lim:
                                legacy = np.asarray(lim.convert("L"))
                            os.unlink(legacy_path)
                            if legacy.shape == (fullH_j, fullW_j) and rx1 > rx0 and ry1 > ry0:
                                join_alpha[ry0:ry1, rx0:rx1] = legacy[ry0:ry1, rx0:rx1]
                        else:
                            a_lin, _f_lin = _dap.closed_form_alpha_and_f(sub, B_use)
                            a_u8 = (a_lin * 255).astype(np.uint8)
                            cf = sub.max(axis=2) <= 15
                            a_u8[cf] = 0
                            a_u8[a_u8 < 50] = 0
                            join_alpha[ry0:ry1, rx0:rx1] = a_u8
                            F_local = sub.copy()
                            F_local[cf] = 0
                            F_full[ry0:ry1, rx0:rx1] = F_local
                    except Exception as _e:
                        traceback.print_exc()
                        print(f"[regen-alpha] join {i} alpha refresh step failed: {_e}")

            Image.fromarray(F_full).save(sdir / f"join_{i}_F.png")
            Image.fromarray(join_alpha, mode="L").save(out_path)
        except Exception as e:
            traceback.print_exc()
            print(f"[regen-alpha] join {i} failed: {e}")
            continue
        try:
            with Image.open(out_path) as im:
                w, h = im.size
        except Exception:
            w, h = 0, 0
        boxes.append({
            "join_index": i,
            "alpha_url": f"/api/multifragment/file/{sid}/{out_name}",
            "w": w, "h": h,
            "time_seconds": round(time.time() - t0, 2),
        })
        print(f"[regen-alpha] join {i} ({usage}): {w}x{h} in {boxes[-1]['time_seconds']}s")

    # Stage B: assembled alpha
    assembled_alpha_url = None
    assembled_rgba_url = None
    assembled_dark_blue_url = None
    out_w = out_h = 0
    F_assembled = None
    alpha_canvas: Image.Image | None = None
    if fragments:
        try:
            t0 = time.time()
            frag_leveled = []
            frag_alphas = []
            for f in fragments:
                idx = f.get("thread_index")
                if idx is not None and mt_sid and _SAFE_SESSION_RE.match(mt_sid):
                    lp = MULTITHREAD_OUTPUT_DIR / mt_sid / f"thread_{int(idx)}_leveled.png"
                    ap_p = MULTITHREAD_OUTPUT_DIR / mt_sid / f"thread_{int(idx)}_alpha.png"
                else:
                    lp = ap_p = None
                frag_leveled.append(lp if lp and lp.exists() else None)
                frag_alphas.append(ap_p if ap_p and ap_p.exists() else None)

            join_alphas = []
            for i in range(len(fragments)):
                p = sdir / f"join_{i}_alpha.png"
                join_alphas.append(p if p.exists() else None)

            frag_alpha_imgs = [Image.open(p).convert("L") if p else None for p in frag_alphas]
            frag_leveled_imgs = [Image.open(p) if p else None for p in frag_leveled]
            join_alpha_imgs = [Image.open(p).convert("L") if p else None for p in join_alphas]

            interior_widths = []
            for j, fim in enumerate(frag_leveled_imgs):
                if fim is None:
                    interior_widths.append(0)
                else:
                    interior_widths.append(max(0, fim.width - 2 * strip_w))

            heights = [im.height for im in frag_leveled_imgs if im] + [im.height for im in join_alpha_imgs if im]
            out_h = max(heights) if heights else 0
            out_w = sum(interior_widths) + sum(im.width if im else 0 for im in join_alpha_imgs)
            if out_w <= 0 or out_h <= 0:
                raise RuntimeError("Cannot determine output size")

            alpha_canvas = Image.new("L", (out_w, out_h), 0)
            x = 0
            for j in range(len(fragments)):
                fim = frag_leveled_imgs[j]
                aim = frag_alpha_imgs[j]
                jaim = join_alpha_imgs[j]
                interior = interior_widths[j]
                yo = int(fragments[j].get("yOffset", 0) or 0)
                if fim and aim and interior > 0:
                    frag_y = (out_h - fim.height) // 2 + yo
                    interior_a = aim.crop((strip_w, 0, fim.width - strip_w, fim.height))
                    alpha_canvas.paste(interior_a, (x, frag_y))
                x += interior
                if jaim:
                    join_y = (out_h - jaim.height) // 2
                    alpha_canvas.paste(jaim, (x, join_y))
                    x += jaim.width

            alpha_canvas.save(sdir / "assembled_alpha.png", "PNG")
            material_alpha_canvas = _material_alpha_from_matte(alpha_canvas)
            material_alpha_canvas.save(sdir / "assembled_material_alpha.png", "PNG")
            assembled_alpha_url = f"/api/multifragment/file/{sid}/assembled_alpha.png"
            print(f"[regen-alpha] composite alpha {out_w}x{out_h} in {round(time.time()-t0,2)}s")

            # Stage B.5: assembled F by composition
            try:
                tF = time.time()
                F_assembled = np.zeros((out_h, out_w, 3), dtype=np.uint8)
                x = 0
                for j in range(len(fragments)):
                    fim = frag_leveled_imgs[j]
                    interior = interior_widths[j]
                    yo = int(fragments[j].get("yOffset", 0) or 0)
                    if fim and interior > 0:
                        frag_y = (out_h - fim.height) // 2 + yo
                        fF_path = frag_F_paths[j] if j < len(frag_F_paths) else None
                        if fF_path and fF_path.exists():
                            with Image.open(fF_path) as fF_im:
                                fF_arr = np.asarray(fF_im.convert("RGB"))
                            iH, iW = fF_arr.shape[:2]
                            interior_F = fF_arr[:, strip_w: iW - strip_w]
                            y0c = max(0, frag_y); y1c = min(out_h, frag_y + iH)
                            y0a = y0c - frag_y;   y1a = y0a + (y1c - y0c)
                            x_end = min(out_w, x + interior_F.shape[1])
                            if y1c > y0c and x_end > x:
                                F_assembled[y0c:y1c, x: x_end] = interior_F[y0a:y1a, : x_end - x]
                    x += interior
                    jF_path = sdir / f"join_{j}_F.png"
                    if jF_path.exists():
                        with Image.open(jF_path) as jF_im:
                            jF_arr = np.asarray(jF_im.convert("RGB"))
                        jH, jW = jF_arr.shape[:2]
                        join_y = (out_h - jH) // 2
                        y0c = max(0, join_y); y1c = min(out_h, join_y + jH)
                        y0a = y0c - join_y;   y1a = y0a + (y1c - y0c)
                        x_end = min(out_w, x + jW)
                        if y1c > y0c and x_end > x:
                            F_assembled[y0c:y1c, x: x_end] = jF_arr[y0a:y1a, : x_end - x]
                        x += jW
                    else:
                        print(f"[regen-alpha] WARNING: join_{j}_F.png missing")
                        jFC_path = sdir / f"join_{j}_full_canvas.png"
                        if jFC_path.exists():
                            with Image.open(jFC_path) as jFC_im:
                                jFC_arr = np.asarray(jFC_im.convert("RGB"))
                            jH, jW = jFC_arr.shape[:2]
                            join_y = (out_h - jH) // 2
                            y0c = max(0, join_y); y1c = min(out_h, join_y + jH)
                            y0a = y0c - join_y;   y1a = y0a + (y1c - y0c)
                            x_end = min(out_w, x + jW)
                            if y1c > y0c and x_end > x:
                                F_assembled[y0c:y1c, x: x_end] = jFC_arr[y0a:y1a, : x_end - x]
                            x += jW
                Image.fromarray(F_assembled).save(sdir / "assembled_F.png")
                print(f"[regen-alpha] assembled_F in {round(time.time()-tF,2)}s")
            except Exception as e:
                traceback.print_exc()
                print(f"[regen-alpha] assembled_F failed: {e}")
                F_assembled = None

            # Stage C: RGBA
            if make_rgba:
                t1 = time.time()
                rgb_path = sdir / "assembled_final.png"
                if rgb_path.exists():
                    rgb = Image.open(rgb_path).convert("RGB")
                    if material_alpha_canvas.size != rgb.size:
                        ac = Image.new("L", rgb.size, 0)
                        ac.paste(material_alpha_canvas, (0, 0))
                        alpha_for_merge = ac
                    else:
                        alpha_for_merge = material_alpha_canvas
                    rgb = _desaturate_background_spill_rgb(
                        rgb,
                        alpha_for_merge,
                        background_linear=B_red_lin,
                    )
                    rgba = Image.merge(
                        "RGBA",
                        (rgb.split()[0], rgb.split()[1], rgb.split()[2], alpha_for_merge),
                    )
                    rgba.save(sdir / "assembled_rgba.png", "PNG")
                    assembled_rgba_url = f"/api/multifragment/file/{sid}/assembled_rgba.png"
                    print(f"[regen-alpha] RGBA composite (source RGB + fringe spill cleanup + material alpha) in {round(time.time()-t1,2)}s")
                elif F_assembled is not None:
                    F_pil = Image.fromarray(F_assembled, mode="RGB")
                    if material_alpha_canvas.size != F_pil.size:
                        ac = Image.new("L", F_pil.size, 0)
                        ac.paste(material_alpha_canvas, (0, 0))
                        alpha_for_merge = ac
                    else:
                        alpha_for_merge = material_alpha_canvas
                    F_pil = _desaturate_background_spill_rgb(
                        F_pil,
                        alpha_for_merge,
                        background_linear=B_red_lin,
                    )
                    rgba = Image.merge(
                        "RGBA",
                        (F_pil.split()[0], F_pil.split()[1], F_pil.split()[2], alpha_for_merge),
                    )
                    rgba.save(sdir / "assembled_rgba.png", "PNG")
                    assembled_rgba_url = f"/api/multifragment/file/{sid}/assembled_rgba.png"
                    print(f"[regen-alpha] RGBA composite (fallback RGB + fringe spill cleanup + material alpha) in {round(time.time()-t1,2)}s")
        except Exception as e:
            traceback.print_exc()
            print(f"[regen-alpha] composite failed: {e}")

    # Stage D: dark-blue composite
    if make_dark_blue and assembled_alpha_url:
        try:
            t1 = time.time()
            F_path = sdir / "assembled_F.png"
            rgb_path = sdir / "assembled_final.png"
            alpha_path = sdir / "assembled_alpha.png"
            f_src_path = F_path if F_path.exists() else rgb_path
            if f_src_path.exists() and alpha_path.exists():
                f_src_pil = Image.open(rgb_path if rgb_path.exists() else f_src_path).convert("RGB")
                material_alpha_path = sdir / "assembled_material_alpha.png"
                a_pil = Image.open(material_alpha_path if material_alpha_path.exists() else alpha_path).convert("L")
                if a_pil.size != f_src_pil.size:
                    a_tmp = Image.new("L", f_src_pil.size, 0)
                    a_tmp.paste(a_pil, (0, 0))
                    a_pil = a_tmp
                F_for_comp = np.asarray(f_src_pil).astype(np.float32)
                a = np.asarray(a_pil).astype(np.float32) / 255.0
                if a.shape != F_for_comp.shape[:2]:
                    a_pil = Image.fromarray((a * 255).astype(np.uint8))
                    a = np.asarray(a_pil.resize((F_for_comp.shape[1], F_for_comp.shape[0]), Image.NEAREST)).astype(np.float32) / 255.0
                bg = np.array([10.0, 40.0, 130.0], dtype=np.float32)
                a3 = a[..., None]
                comp = F_for_comp * a3 + bg * (1.0 - a3)
                comp_u8 = np.clip(comp, 0, 255).astype(np.uint8)
                Image.fromarray(comp_u8, mode="RGB").save(sdir / "assembled_dark_blue.png", "PNG")
                assembled_dark_blue_url = f"/api/multifragment/file/{sid}/assembled_dark_blue.png"
                print(f"[regen-alpha] dark-blue composite in {round(time.time()-t1,2)}s")
        except Exception as e:
            traceback.print_exc()
            print(f"[regen-alpha] dark-blue composite failed: {e}")

    export_urls = {}
    try:
        built = _build_export_set(
            sdir,
            strip_w,
            background_linear=B_red_lin,
            make_rgba=make_rgba,
        )
        for kind, fname in built.items():
            export_urls[kind] = f"/api/multifragment/file/{sid}/{fname}"
    except Exception as e:
        print(f"[regen-alpha] export-set build failed (non-fatal): {e}")

    return {
        "boxes": boxes,
        "assembled_alpha_url": assembled_alpha_url,
        "assembled_rgba_url": assembled_rgba_url,
        "assembled_dark_blue_url": assembled_dark_blue_url,
        "export_urls": export_urls,
        "w": out_w, "h": out_h,
    }


# --- Export ---------------------------------------------------------------

@router.post("/api/multithread/export")
async def multithread_export(payload: dict = Body(default_factory=dict)) -> dict:
    """Build no-wraparound export images + metadata.json."""
    sid = payload.get("multifragment_session_id") or payload.get("session_id")
    mt_sid = payload.get("multithread_session_id")
    fragments = payload.get("fragments") or []
    strip_w = int(payload.get("strip_width", 512))
    join_usage = payload.get("join_usage") or []
    metadata_only = bool(payload.get("metadata_only", False))
    if not sid or not _SAFE_SESSION_RE.match(sid):
        raise HTTPException(status_code=400, detail="Missing/invalid multifragment_session_id")
    sdir = (MULTIFRAG_DEBUG_DIR / sid).resolve()
    try:
        sdir.relative_to(MULTIFRAG_DEBUG_DIR.resolve())
    except ValueError:
        raise HTTPException(status_code=404, detail="Session not found")
    if not sdir.is_dir():
        raise HTTPException(status_code=404, detail="Session not found")
    if not fragments:
        raise HTTPException(status_code=400, detail="fragments[] required")

    try:
        N = len(fragments)
        if not mt_sid or not _SAFE_SESSION_RE.match(mt_sid):
            raise HTTPException(status_code=400, detail="multithread_session_id required for export")
        mt_dir = MULTITHREAD_OUTPUT_DIR / mt_sid
        if not mt_dir.is_dir():
            raise HTTPException(status_code=404, detail=f"multithread session not found: {mt_sid}")

        summary = None
        sp = mt_dir / "summary.json"
        if sp.exists():
            with open(sp) as f:
                summary = json.load(f)

        export_urls: dict[str, str] = {}
        if not metadata_only:
            built = _build_export_set(
                sdir,
                strip_w,
                background_linear=_summary_background_linear(summary),
                make_rgba=bool(payload.get("make_rgba", True)),
            )
            for kind, fname in built.items():
                export_urls[kind] = f"/api/multifragment/file/{sid}/{fname}"

        # Width measurement now comes from the post-inpaint detector running on
        # the assembled alpha (export_assembled_alpha.png). The pre-inpaint
        # per-thread c_band averages are no longer used. See docs/WebUIbands/.
        export_alpha_path = sdir / "export_assembled_alpha.png"
        if not export_alpha_path.exists():
            raise HTTPException(
                status_code=409,
                detail=(
                    "export_assembled_alpha.png missing — run Regenerate Alpha "
                    "before Export so band detection can run on the final image."
                ),
            )
        export_alpha_arr = np.asarray(Image.open(export_alpha_path).convert("L"))
        export_bands = _band_detect.detect_bands(export_alpha_arr)
        export_core = export_bands["bands_px"]["core"]
        unified_top = int(export_core[0])
        unified_bot = int(export_core[1])
        unified_width_px = unified_bot - unified_top + 1

        dpi = (summary or {}).get("dpi", 1600.0)
        export_w = export_h = None
        ergb = sdir / "export_assembled_final.png"
        if ergb.exists():
            with Image.open(ergb) as eim:
                export_w, export_h = eim.size
        else:
            asm = sdir / "assembled_final.png"
            if asm.exists():
                with Image.open(asm) as aim:
                    export_w, export_h = aim.size

        joins_meta = []
        for i in range(N):
            usage = join_usage[i] if i < len(join_usage) else "inpaint"
            joins_meta.append({
                "join_index": i,
                "from_thread_index": i,
                "to_thread_index": (i + 1) % N,
                "mode": "stitched" if usage == "skip" else "inpainted",
                "is_wraparound_excluded_from_export": (i == N - 1),
            })

        def _mm(px):
            if px is None: return None
            return round(px / dpi * 25.4, 4)

        meta = {
            "multithread_session_id": mt_sid,
            "multifragment_session_id": sid,
            "dpi": dpi,
            "n_threads": N,
            "export_size_px": {"width": export_w, "height": export_h},
            "width": {
                "px": unified_width_px,
                "mm": _mm(unified_width_px),
                "top_y_in_export": unified_top,
                "bottom_y_in_export": unified_bot,
                "description": "Top-to-bottom of the unified solid thread band, in the EXPORT image's coordinates.",
            },
            "length": {
                "px": export_w,
                "mm": _mm(export_w),
                "description": "Left-to-right of the export image (no wraparound).",
            },
            "joins": joins_meta,
            "threads_solid_band": [
                {
                    "thread_index": t.get("index"),
                    "c_band": t.get("c_band"),
                    "d_band": t.get("d_band"),
                } for t in (summary or {}).get("threads", [])
            ],
        }
        with open(sdir / "export_metadata.json", "w") as f:
            json.dump(meta, f, indent=2)
        export_urls["metadata"] = f"/api/multifragment/file/{sid}/export_metadata.json"

        return {"ok": True, "export_urls": export_urls, "metadata": meta}
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Export failed: {e}")


# --- Save to library ------------------------------------------------------

@router.post("/api/multithread/save-to-library")
async def multithread_save_to_library(payload: dict = Body(default_factory=dict)) -> dict:
    """Persist a finished multifragment session into the on-disk yarn library.

    Wraps `app.yarnseamless.yarn_library.save_to_library`. The new
    `metadata.blender` block (texture_world_width_m + V-band scalars) is
    produced by that function — see docs/putting-it-together/data_contract.md.
    """
    sid = payload.get("multifragment_session_id") or payload.get("session_id")
    mt_sid = payload.get("multithread_session_id")
    label = payload.get("label")
    library_root_override = payload.get("library_root")

    if not sid or not _SAFE_SESSION_RE.match(sid):
        raise HTTPException(status_code=400, detail="Missing/invalid multifragment_session_id")

    mf_dir = (MULTIFRAG_DEBUG_DIR / sid).resolve()
    try:
        mf_dir.relative_to(MULTIFRAG_DEBUG_DIR.resolve())
    except ValueError:
        raise HTTPException(status_code=404, detail="multifragment session not found")
    if not mf_dir.is_dir():
        raise HTTPException(status_code=404, detail="multifragment session not found")

    mt_dir: Path | None = None
    if mt_sid:
        if not _SAFE_SESSION_RE.match(mt_sid):
            raise HTTPException(status_code=400, detail="Invalid multithread_session_id")
        candidate = (MULTITHREAD_OUTPUT_DIR / mt_sid).resolve()
        try:
            candidate.relative_to(MULTITHREAD_OUTPUT_DIR.resolve())
        except ValueError:
            candidate = None
        if candidate and candidate.is_dir():
            mt_dir = candidate

    try:
        # CRITICAL: pass YARN_LIBRARY_ROOT explicitly. The yarn_library module
        # in this package has its own `default_library_root()` that computes
        # `<repo>/yarn_library` via `Path(__file__).parent.parent` — but in
        # the ported copy that resolves to `backend/app/yarn_library/`,
        # NOT the shared `yarnseamless UI/yarn_library/`. Passing the right
        # path here overrides that broken default. Bug found 2026-05-13 after
        # 4 successful saves went to the wrong folder.
        library_root = (Path(library_root_override).resolve()
                        if library_root_override else YARN_LIBRARY_ROOT)
        entry = _yarn_library.save_to_library(
            mf_dir,
            mt_dir,
            library_root=library_root,
            label=label,
        )
        return {"ok": True, **entry}
    except FileNotFoundError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"save-to-library failed: {e}")
