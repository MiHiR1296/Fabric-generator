"""
Yarn library — persistent on-disk catalog of processed yarns.

Each yarn = one folder under `<library_root>/<yarn_id>/` containing:
    rgba.png         exact stitched scan RGB + natural alpha
    input_thumb.jpg  small JPEG preview of the original scan
    metadata.json    superset of export_metadata.json + bandMeta-shaped fields

`<library_root>` defaults to `<repo>/yarn_library/`; override via env var
YARN_LIBRARY_ROOT. The index file `<library_root>/index.json` is the
append-only registry consumed by the Fabric-generator app.

This module is intentionally Flask-free so it can be unit-tested without
spinning up the server.
"""
from __future__ import annotations

import io
import json
import os
import re
import secrets
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from .band_detect import detect_bands


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def default_library_root() -> Path:
    env = os.environ.get("YARN_LIBRARY_ROOT")
    if env:
        return Path(env).resolve()
    return _repo_root() / "yarn_library"


def resolve_library_root(override: str | None) -> Path:
    root = Path(override).resolve() if override else default_library_root()
    root.mkdir(parents=True, exist_ok=True)
    return root


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_LIBRARY_ID_RE = re.compile(r"^[0-9]{8}_[0-9]{6}_[a-f0-9]{4,8}$")


def _new_yarn_id() -> str:
    ts = time.strftime("%Y%m%d_%H%M%S", time.localtime())
    return f"{ts}_{secrets.token_hex(3)}"


def is_safe_yarn_id(value: str) -> bool:
    return bool(value) and bool(_LIBRARY_ID_RE.match(value))


def _slugify_label(label: str | None, fallback: str = "yarn") -> str:
    if not label:
        return fallback
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", label).strip("-._")
    return cleaned or fallback


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _make_thumbnail(src_path: Path, dst_path: Path, *, max_edge: int = 512) -> tuple[int, int] | None:
    """Make a small JPEG thumbnail of an input scan. Returns (W, H) of source."""
    Image.MAX_IMAGE_PIXELS = None
    try:
        with Image.open(src_path) as im:
            src_size = im.size
            im = im.convert("RGB")
            im.thumbnail((max_edge, max_edge), Image.LANCZOS)
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            im.save(dst_path, "JPEG", quality=85)
        return src_size
    except Exception:
        return None


def _read_embedded_dpi(image_path: Path) -> tuple[float, float] | None:
    """Return embedded image DPI when present. Many processed PNGs lose this,
    so absence is not a failure; it just lowers physical-scale confidence."""
    Image.MAX_IMAGE_PIXELS = None
    try:
        with Image.open(image_path) as im:
            dpi = im.info.get("dpi")
            if not dpi or len(dpi) < 2:
                return None
            return (float(dpi[0]), float(dpi[1]))
    except Exception:
        return None


def _dpi_matches(declared_dpi: float, embedded_dpi: tuple[float, float] | None, *, tolerance_frac: float = 0.02) -> bool | None:
    if embedded_dpi is None or declared_dpi <= 0:
        return None
    return all(abs(axis_dpi - declared_dpi) <= declared_dpi * tolerance_frac for axis_dpi in embedded_dpi)


def _physical_scale_validation(
    *,
    declared_dpi: float,
    source_image_name: str | None,
    source_size: tuple[int, int] | None,
    source_dpi: tuple[float, float] | None,
    export_size: tuple[int, int],
    export_dpi: tuple[float, float] | None,
    texture_world_width_m: float | None,
) -> dict[str, Any]:
    source_matches = _dpi_matches(declared_dpi, source_dpi)
    export_matches = _dpi_matches(declared_dpi, export_dpi)
    notes: list[str] = []

    if source_matches is True:
        confidence = "high"
        notes.append("Original scan embedded DPI matches declared preprocessing DPI.")
    elif source_matches is False:
        confidence = "low"
        notes.append("Original scan embedded DPI does not match declared preprocessing DPI.")
    elif export_matches is True:
        confidence = "medium"
        notes.append("Processed export embedded DPI matches declared preprocessing DPI, but original scan DPI was unavailable.")
    else:
        confidence = "metadata_only"
        notes.append("No matching embedded DPI was available; physical scale comes from export metadata only.")

    if export_dpi is None:
        notes.append("Processed/exported PNG has no embedded DPI; this is common and does not invalidate the scan DPI.")
    elif export_matches is False:
        notes.append("Processed/exported PNG embedded DPI differs from declared DPI; prefer original scan DPI when available.")

    return {
        "declared_dpi": declared_dpi,
        "confidence": confidence,
        "source_scan": {
            "filename": source_image_name,
            "size_px": list(source_size) if source_size else None,
            "embedded_dpi": list(source_dpi) if source_dpi else None,
            "matches_declared_dpi": source_matches,
        },
        "processed_export": {
            "filename": "export_assembled_rgba.png",
            "size_px": list(export_size),
            "embedded_dpi": list(export_dpi) if export_dpi else None,
            "matches_declared_dpi": export_matches,
        },
        "texture_world_width_m": texture_world_width_m,
        "notes": notes,
    }


def _read_json(path: Path) -> Any:
    with open(path) as f:
        return json.load(f)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w") as f:
        json.dump(payload, f, indent=2)
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# Index registry
# ---------------------------------------------------------------------------

def _index_path(library_root: Path) -> Path:
    return library_root / "index.json"


def load_index(library_root: Path) -> dict[str, Any]:
    p = _index_path(library_root)
    if p.exists():
        try:
            data = _read_json(p)
            if isinstance(data, dict) and isinstance(data.get("yarns"), list):
                return data
        except Exception:
            pass
    return {"yarns": []}


def upsert_index_entry(library_root: Path, entry: dict[str, Any]) -> None:
    data = load_index(library_root)
    yarns = [y for y in data.get("yarns", []) if y.get("id") != entry.get("id")]
    yarns.append(entry)
    yarns.sort(key=lambda y: y.get("createdAt") or "", reverse=True)
    _write_json(_index_path(library_root), {"yarns": yarns})


def list_yarns(library_root: Path) -> list[dict[str, Any]]:
    return load_index(library_root).get("yarns", [])


def get_yarn(library_root: Path, yarn_id: str) -> dict[str, Any] | None:
    if not is_safe_yarn_id(yarn_id):
        return None
    yarn_dir = library_root / yarn_id
    meta_path = yarn_dir / "metadata.json"
    if not meta_path.exists():
        return None
    return _read_json(meta_path)


def delete_yarn(library_root: Path, yarn_id: str) -> bool:
    """Remove a yarn folder + its index.json entry. Returns True if anything was
    deleted, False if the id was unknown. Validates the id is a safe slug so we
    can never walk outside `library_root`.
    """
    if not is_safe_yarn_id(yarn_id):
        raise ValueError(f"Unsafe yarn id: {yarn_id!r}")
    yarn_dir = (library_root / yarn_id).resolve()
    # Defence-in-depth: refuse if resolution escaped the library root.
    if not str(yarn_dir).startswith(str(library_root.resolve())):
        raise ValueError(f"Refusing delete outside library root: {yarn_dir}")
    removed_folder = False
    if yarn_dir.is_dir():
        shutil.rmtree(yarn_dir)
        removed_folder = True
    data = load_index(library_root)
    before = data.get("yarns") or []
    after = [y for y in before if y.get("id") != yarn_id]
    removed_index = len(after) != len(before)
    if removed_index:
        _write_json(_index_path(library_root), {"yarns": after})
    return removed_folder or removed_index


# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------

def save_to_library(
    mf_dir: Path,
    mt_dir: Path | None,
    *,
    library_root: Path | None = None,
    label: str | None = None,
) -> dict[str, Any]:
    """Copy the export artifacts from a finished multifragment session into the
    yarn library and write metadata.json + update index.json.

    Inputs:
      mf_dir       — debug/multifragment/<mf_sid>/ (must contain export_*.png + export_metadata.json)
      mt_dir       — debug/multithread_image/<mt_sid>/ (for input thumbnail; optional)
      library_root — override library root (defaults to env or repo-root yarn_library/)
      label        — friendly label; defaults to mf_sid

    Returns the new index entry.
    """
    mf_dir = Path(mf_dir).resolve()
    if not mf_dir.is_dir():
        raise FileNotFoundError(f"multifragment session dir not found: {mf_dir}")

    rgb_src = mf_dir / "export_assembled_final.png"
    if not rgb_src.exists():
        raise FileNotFoundError("export_assembled_final.png missing — run Assemble first.")
    matte_alpha_src = mf_dir / "export_assembled_alpha.png"
    if not matte_alpha_src.exists():
        raise FileNotFoundError("export_assembled_alpha.png missing.")
    material_alpha_src = mf_dir / "export_assembled_material_alpha.png"
    alpha_src = material_alpha_src if material_alpha_src.exists() else matte_alpha_src
    rgba_src = mf_dir / "export_assembled_rgba.png"
    export_meta_src = mf_dir / "export_metadata.json"
    if not export_meta_src.exists():
        raise FileNotFoundError("export_metadata.json missing — click Export once.")

    root = resolve_library_root(str(library_root) if library_root else None)
    yarn_id = _new_yarn_id()
    yarn_dir = root / yarn_id
    yarn_dir.mkdir(parents=True, exist_ok=False)

    # 1) Copy canonical RGBA texture. The RGB channels are the exact stitched
    # scan colour and the alpha channel is the natural matte, with no core boost.
    if rgba_src.exists():
        shutil.copy2(rgba_src, yarn_dir / "rgba.png")
    else:
        with Image.open(rgb_src) as rgb_im, Image.open(alpha_src) as alpha_im:
            rgb_pil = rgb_im.convert("RGB")
            alpha_pil = alpha_im.convert("L")
            if alpha_pil.size != rgb_pil.size:
                ac = Image.new("L", rgb_pil.size, 0)
                ac.paste(alpha_pil, (0, 0))
                alpha_pil = ac
            Image.merge("RGBA", (*rgb_pil.split(), alpha_pil)).save(yarn_dir / "rgba.png")

    # 2) Thumbnail from the original scan, if we can find one
    src_size = None
    source_dpi = None
    source_image_name = None
    if mt_dir is not None:
        mt_dir = Path(mt_dir).resolve()
        if mt_dir.is_dir():
            for candidate in mt_dir.iterdir():
                if candidate.name.startswith("input.") and candidate.is_file():
                    source_image_name = candidate.name
                    source_dpi = _read_embedded_dpi(candidate)
                    src_size = _make_thumbnail(candidate, yarn_dir / "input_thumb.jpg")
                    break

    # 3) Read export_metadata for dpi/joins, then run the FWHM band detector
    #    on the post-inpaint assembled alpha. We no longer read core_top /
    #    core_bot from export_metadata — the assembled alpha is the source of
    #    truth and `detect_bands` finds the core itself. See docs/WebUIbands/.
    export_meta = _read_json(export_meta_src)
    dpi = float(export_meta.get("dpi") or 1600.0)

    with Image.open(rgb_src) as im:
        image_W, image_H = im.size
    export_dpi = _read_embedded_dpi(rgb_src)

    width_meta = dict(export_meta.get("width") or {})

    with Image.open(matte_alpha_src) as alpha_im:
        alpha_arr = np.asarray(alpha_im.convert("L"))
    bands = detect_bands(alpha_arr)

    label_clean = _slugify_label(label) if label else _slugify_label(yarn_id)
    created_at = _utc_now_iso()

    # Length = actual export image width × pixel pitch. Same units as width.
    # Source of truth = the file on disk, not whatever upstream wrote into
    # export_metadata.json's "length" field (which has drifted in the past).
    length_px = image_W
    length_mm = round(length_px / dpi * 25.4, 4)
    length_meta = {
        "px": length_px,
        "mm": length_mm,
        "description": "Left-to-right of the export image (no wraparound).",
    }

    # ---- Pre-computed Blender-ready block ----
    # The consumer (Fabric-generator backend) should push these values
    # straight to the Parametric Weave knotty modifier without any further
    # math. Source of truth lives here so Blender never has to know about DPI.
    #
    #   Texture U world length (metres, BU=1m) = image_width_px / dpi × 0.0254
    #   Equivalent to image_width_px / (dpi × 39.3701) where (dpi × 39.3701)
    #   is the .blend's "Scanner Pixels Per BU" socket (62992.1 at 1600 dpi).
    bv = bands.get("bands_v_norm") or {}
    core_v = bv.get("core") or [None, None]
    fiber_top_v = bv.get("fiber_top") or [None, None]
    fiber_bot_v = bv.get("fiber_bot") or [None, None]
    texture_world_width_m = (image_W / dpi) * 0.0254 if dpi > 0 else None
    physical_scale = _physical_scale_validation(
        declared_dpi=dpi,
        source_image_name=source_image_name,
        source_size=src_size,
        source_dpi=source_dpi,
        export_size=(image_W, image_H),
        export_dpi=export_dpi,
        texture_world_width_m=texture_world_width_m,
    )
    # Historical Arc 2 split proportions, driven by actual band heights. The
    # active cleaned Blender graph now owns its split procedurally, so these are
    # retained as metadata/debug provenance rather than pushed to modifier
    # sockets.
    th = bands.get("thickness_px") or {}
    core_h = th.get("core_height")
    top_h = th.get("fiber_top_height")
    bot_h = th.get("fiber_bot_height")
    total_h = None
    top_halo_frac = None
    bot_halo_frac = None
    if (isinstance(core_h, int) and isinstance(top_h, int) and isinstance(bot_h, int)
            and (core_h + top_h + bot_h) > 0):
        total_h = core_h + top_h + bot_h
        top_halo_frac = round(top_h / total_h, 6)
        bot_halo_frac = round(bot_h / total_h, 6)
    blender_block = {
        "_convention": (
            "Pre-computed for direct push to Parametric Weave knotty. "
            "Producer owns all unit conversion (px/dpi/mm/BU). Consumer just "
            "pushes each value to the same-named modifier socket."
        ),
        "schema_version": 1,
        # The two pieces the U mapping needs. world_width is enough on its
        # own if the .blend gets a Texture World Width BU socket; image_width
        # + scanner_pixels_per_bu reproduces the legacy two-socket setup.
        "texture_world_width_m": texture_world_width_m,
        "texture_world_width_mm": round(texture_world_width_m * 1000.0, 4) if texture_world_width_m else None,
        # Back-compat: artists/older graphs that still divide image_width / pixels_per_bu.
        "image_width_px": image_W,
        "scanner_pixels_per_bu": round(dpi * 39.3701, 4),  # 1 BU = 1 m = 39.3701 in
        # V-band positions, already normalised. Push as-is.
        "core_v_min": core_v[0],
        "core_v_max": core_v[1],
        # Inner-boundary cutoffs. "Fiber Top V Min" = lower V edge of upper halo
        # (= core_v_max). "Fiber Bot V Max" = upper V edge of lower halo
        # (= core_v_min). See data_contract.md → socket map.
        # Bug fixed 2026-05-14: fiber_bot_v_max was wrongly assigned fiber_top_v[1].
        "fiber_top_v_min": fiber_top_v[0],
        "fiber_bot_v_max": fiber_bot_v[1],
        # Outer-extent provenance — kept for a future "Strand V Min/Max" socket pair.
        "fiber_bot_v_min": fiber_bot_v[0],
        "fiber_top_v_max": fiber_top_v[1],
        # Historical per-yarn Arc 2 split fractions (sum + core_frac == 1.0).
        # `top_halo_frac` = upper-hair height / total strand height,
        # `bot_halo_frac` = lower-hair height / total strand height.
        # No active cleaned-graph push target; kept for old-file comparison.
        "top_halo_frac": top_halo_frac,
        "bot_halo_frac": bot_halo_frac,
    }

    metadata = {
        "schemaVersion": 1,
        "id": yarn_id,
        "label": label_clean,
        "createdAt": created_at,
        "source": {
            "multithread_session_id": export_meta.get("multithread_session_id"),
            "multifragment_session_id": export_meta.get("multifragment_session_id"),
            "scan_size_px": list(src_size) if src_size else None,
        },
        "image_size_px": [image_W, image_H],
        "dpi": dpi,
        "physical_scale": physical_scale,
        "width": width_meta,
        "length": length_meta,
        "bands_px": bands.get("bands_px"),
        "bands_v_norm": bands.get("bands_v_norm"),
        "thickness_px": bands.get("thickness_px"),
        "params": bands.get("params"),
        "blender": blender_block,
        "joins": export_meta.get("joins") or [],
        "threads_solid_band": export_meta.get("threads_solid_band") or [],
        "files": {
            "rgb": None,
            "alpha": None,
            "rgba": "rgba.png",
            "thumbnail": "input_thumb.jpg" if (yarn_dir / "input_thumb.jpg").exists() else None,
            "metadata": "metadata.json",
        },
    }

    _write_json(yarn_dir / "metadata.json", metadata)

    index_entry = {
        "id": yarn_id,
        "label": label_clean,
        "createdAt": created_at,
        "thumbnail": metadata["files"]["thumbnail"],
        "widthPx": (width_meta or {}).get("px"),
        "widthMm": (width_meta or {}).get("mm"),
        "lengthPx": length_px,
        "lengthMm": length_mm,
        "dpi": dpi,
    }
    upsert_index_entry(root, index_entry)

    return {**index_entry, "libraryPath": str(yarn_dir), "metadata": metadata}
