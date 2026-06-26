from __future__ import annotations

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

from .runtime_paths import YARN_ASSETS_ROOT, YARN_LIBRARY_ROOT
from .yarnseamless.yarn_library import upsert_index_entry


ARC1_V_AROUND_SPAN = 0.6
AI_CORE_ALPHA_THRESHOLD = 224
AI_CORE_DENSITY_FRACTION = 0.95
AI_ARC2_ALPHA_THRESHOLD = 5
AI_ARC2_ROW_DENSITY = 0.02
AI_U_ALPHA_POWER = 1.5
AI_U_MAX_BOOST = 2.0
AI_U_SCALE_STRATEGY = "ai_alpha_mass_equivalent_width_v2"
AI_BAND_STRATEGY = "ai_dense_core_plus_full_alpha_support_arc2"

_LIBRARY_ID_RE = re.compile(r"^[0-9]{8}_[0-9]{6}_[a-f0-9]{4,8}$")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _new_yarn_id() -> str:
    return f"{time.strftime('%Y%m%d_%H%M%S', time.localtime())}_{secrets.token_hex(3)}"


def _slugify_label(label: str | None, fallback: str = "AI Yarn") -> str:
    if not label:
        return fallback
    cleaned = re.sub(r"[^A-Za-z0-9._ -]+", "", label).strip()
    return cleaned or fallback


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _largest_run(mask: np.ndarray) -> tuple[int | None, int | None]:
    best_start: int | None = None
    best_end: int | None = None
    best_len = 0
    start: int | None = None
    for index, value in enumerate(mask.astype(bool).tolist()):
        if value and start is None:
            start = index
        if (not value or index == len(mask) - 1) and start is not None:
            end = index if value and index == len(mask) - 1 else index - 1
            run_len = end - start + 1
            if run_len > best_len:
                best_len = run_len
                best_start = start
                best_end = end
            start = None
    return best_start, best_end


def _contiguous_extent_around_core(mask: np.ndarray, core_top: int, core_bottom: int) -> tuple[int, int]:
    top = int(core_top)
    bottom = int(core_bottom)
    while top > 0 and bool(mask[top - 1]):
        top -= 1
    while bottom < len(mask) - 1 and bool(mask[bottom + 1]):
        bottom += 1
    return top, bottom


def _support_range(alpha_u8: np.ndarray, *, threshold: int, row_density: float) -> tuple[int | None, int | None, float]:
    density = (alpha_u8 > threshold).mean(axis=1).astype(np.float64)
    peak = float(density.max()) if density.size else 0.0
    start, end = _largest_run(density >= row_density)
    return start, end, peak


def detect_ai_yarn_bands(alpha_u8: np.ndarray, measurements: dict[str, Any] | None = None) -> dict[str, Any]:
    """Detect AI-yarn render bands from source PNG alpha.

    AI-generated metadata is treated as provenance only. Arc 1 uses a strict
    high-alpha dense run. Arc 2 uses a wider low-alpha contiguous support band
    around that core so loose generated fibers remain visible.
    """
    if alpha_u8.ndim != 2:
        raise ValueError(f"alpha_u8 must be HxW, got {alpha_u8.shape}")

    height, width = alpha_u8.shape
    fallback_thresholds = [AI_CORE_ALPHA_THRESHOLD, 192, 160, 127]
    core_top: int | None = None
    core_bottom: int | None = None
    core_threshold_used = AI_CORE_ALPHA_THRESHOLD
    core_peak_density = 0.0
    for threshold in fallback_thresholds:
        density = (alpha_u8 > threshold).mean(axis=1).astype(np.float64)
        peak = float(density.max()) if density.size else 0.0
        if peak <= 0:
            continue
        start, end = _largest_run(density >= peak * AI_CORE_DENSITY_FRACTION)
        if start is not None and end is not None:
            core_top, core_bottom = int(start), int(end)
            core_threshold_used = threshold
            core_peak_density = peak
            break

    if core_top is None or core_bottom is None:
        density = (alpha_u8 > 0).mean(axis=1).astype(np.float64)
        peak_row = int(np.argmax(density)) if density.size else height // 2
        core_top = max(0, peak_row - 1)
        core_bottom = min(height - 1, peak_row + 1)
        core_peak_density = float(density.max()) if density.size else 0.0

    arc2_density = (alpha_u8 > AI_ARC2_ALPHA_THRESHOLD).mean(axis=1).astype(np.float64)
    arc2_mask = arc2_density >= AI_ARC2_ROW_DENSITY
    if not arc2_mask[core_top:core_bottom + 1].any():
        arc2_top, arc2_bottom = core_top, core_bottom
    else:
        arc2_top, arc2_bottom = _contiguous_extent_around_core(arc2_mask, core_top, core_bottom)

    row_profile: list[dict[str, Any]] = []
    for threshold in (0, 5, 24, 64, 127, 192, 224):
        loose_start, loose_end, peak = _support_range(alpha_u8, threshold=threshold, row_density=0.002)
        support_start, support_end, _ = _support_range(alpha_u8, threshold=threshold, row_density=AI_ARC2_ROW_DENSITY)
        row_profile.append({
            "alpha_threshold": threshold,
            "support_0p2pct": [loose_start, loose_end] if loose_start is not None else None,
            "support_2pct": [support_start, support_end] if support_start is not None else None,
            "peak_density": peak,
        })

    original_core = None
    original_extent = None
    if measurements:
        c_band = measurements.get("c_band") or {}
        d_band = measurements.get("d_band") or {}
        if c_band.get("top_y") is not None and c_band.get("bottom_y") is not None:
            original_core = [int(c_band["top_y"]), int(c_band["bottom_y"])]
        if d_band.get("top_y") is not None and d_band.get("bottom_y") is not None:
            original_extent = [int(d_band["top_y"]), int(d_band["bottom_y"])]

    return {
        "image_size_px": [width, height],
        "json_image_size_px": measurements.get("image_size_px") if measurements else None,
        "size_matches": (measurements.get("image_size_px") == [width, height]) if measurements else None,
        "original_core": original_core,
        "original_extent": original_extent,
        "ai_core": [core_top, core_bottom],
        "ai_arc2_extent": [arc2_top, arc2_bottom],
        "ai_width_px": int(core_bottom - core_top + 1),
        "core_threshold_used": core_threshold_used,
        "core_peak_density": core_peak_density,
        "row_profile": row_profile,
    }


def estimate_ai_texture_scale_u(
    alpha_u8: np.ndarray,
    *,
    core_height_px: int,
    image_height_px: int,
) -> dict[str, float | str]:
    """Estimate AI U scale from visible opacity mass.

    The earlier AI pass used dense-core height only. That fixed the worst
    default-mapping stretch but underestimates yarns with transparent frays.
    This stricter pass estimates an opacity-equivalent visual width:

        sum((alpha / 255) ** 1.5) / image_width

    The exponent downweights faint single-pixel wisps while still counting
    real semi-transparent fiber mass. We clamp the boost to avoid extreme
    generated halos turning into very tight U repeats.
    """
    if image_height_px <= 0:
        raise ValueError("image_height_px must be positive")
    alpha_f = alpha_u8.astype(np.float64) / 255.0
    image_width_px = max(1, alpha_u8.shape[1])
    alpha_equivalent_width_px = float(np.power(alpha_f, AI_U_ALPHA_POWER).sum() / image_width_px)
    core_based = float(core_height_px / (image_height_px * ARC1_V_AROUND_SPAN))
    raw = float(max(core_based, alpha_equivalent_width_px / (image_height_px * ARC1_V_AROUND_SPAN)))
    clamped = float(min(raw, core_based * AI_U_MAX_BOOST))
    return {
        "texture_scale_u": clamped,
        "texture_scale_u_previous_core_only": core_based,
        "texture_scale_u_raw_alpha_mass": raw,
        "texture_scale_u_boost": clamped / core_based if core_based > 0 else 1.0,
        "alpha_equivalent_width_px": alpha_equivalent_width_px,
        "alpha_power": AI_U_ALPHA_POWER,
        "max_boost": AI_U_MAX_BOOST,
        "strategy": AI_U_SCALE_STRATEGY,
    }


def _make_ai_thumbnail(src_path: Path, dst_path: Path, *, max_edge: int = 512) -> None:
    with Image.open(src_path) as im:
        rgba = im.convert("RGBA")
        bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        bg.alpha_composite(rgba)
        thumb = bg.convert("RGB")
        thumb.thumbnail((max_edge, max_edge), Image.LANCZOS)
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        thumb.save(dst_path, "JPEG", quality=92)


def _embedded_dpi(path: Path) -> tuple[float, float] | None:
    try:
        with Image.open(path) as im:
            dpi = im.info.get("dpi")
        if not dpi or len(dpi) < 2:
            return None
        return float(dpi[0]), float(dpi[1])
    except Exception:
        return None


def _normalize_measurements(value: dict[str, Any] | None) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def build_ai_yarn_metadata(
    rgba_path: Path,
    *,
    yarn_id: str,
    label: str,
    source_dir: Path | None = None,
    measurements: dict[str, Any] | None = None,
    measurement_filename: str | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    rgba_path = Path(rgba_path).resolve()
    source_dir = Path(source_dir).resolve() if source_dir else rgba_path.parent.resolve()
    measurements = _normalize_measurements(measurements)
    with Image.open(rgba_path) as im:
        rgba = im.convert("RGBA")
        image_width, image_height = rgba.size
        alpha_u8 = np.asarray(rgba.getchannel("A"))

    detector = detect_ai_yarn_bands(alpha_u8, measurements)
    core_top, core_bottom = detector["ai_core"]
    arc2_top, arc2_bottom = detector["ai_arc2_extent"]
    core_height = int(core_bottom - core_top + 1)
    fiber_top_height = int(core_top - arc2_top)
    fiber_bot_height = int(arc2_bottom - core_bottom)
    extent_height = int(arc2_bottom - arc2_top + 1)
    if min(core_height, fiber_top_height, fiber_bot_height) < 0:
        raise ValueError("invalid detected AI bands")

    dpi = float(measurements.get("dpi") or 1600.0)
    length_px = int((measurements.get("length") or {}).get("px") or image_width)
    if length_px != image_width:
        length_px = image_width
    length_mm = round(length_px / dpi * 25.4, 4) if dpi > 0 else None
    width_mm = round(core_height / dpi * 25.4, 4) if dpi > 0 else None
    texture_world_width_m = (image_width / dpi) * 0.0254 if dpi > 0 else None

    core_v_min = 1.0 - (core_bottom / image_height)
    core_v_max = 1.0 - (core_top / image_height)
    fiber_top_v_min = core_v_max
    fiber_top_v_max = 1.0 - (arc2_top / image_height)
    fiber_bot_v_min = 1.0 - (arc2_bottom / image_height)
    fiber_bot_v_max = core_v_min
    u_scale = estimate_ai_texture_scale_u(
        alpha_u8,
        core_height_px=core_height,
        image_height_px=image_height,
    )

    embedded = _embedded_dpi(rgba_path)
    original_core = detector.get("original_core")
    original_extent = detector.get("original_extent")
    original_width = (measurements.get("width") or {}).get("px")
    delta_px = None
    if original_core and original_extent and original_width is not None:
        delta_px = {
            "core_top": core_top - int(original_core[0]),
            "core_bottom": core_bottom - int(original_core[1]),
            "core_width": core_height - int(original_width),
            "fiber_top": arc2_top - int(original_extent[0]),
            "fiber_bottom": arc2_bottom - int(original_extent[1]),
        }

    metadata = {
        "schemaVersion": 1,
        "id": yarn_id,
        "label": label,
        "createdAt": created_at or _utc_now_iso(),
        "source": {
            "kind": "ai_generated_rgba",
            "asset_dir": str(source_dir),
            "rgba_filename": rgba_path.name,
            "measurement_filename": measurement_filename,
            "scan_size_px": None,
        },
        "image_size_px": [image_width, image_height],
        "dpi": dpi,
        "physical_scale": {
            "declared_dpi": dpi,
            "confidence": "metadata_only",
            "source_scan": {
                "filename": rgba_path.name,
                "size_px": [image_width, image_height],
                "embedded_dpi": list(embedded) if embedded else None,
                "matches_declared_dpi": None,
            },
            "processed_export": {
                "filename": "rgba.png",
                "size_px": [image_width, image_height],
                "embedded_dpi": list(embedded) if embedded else None,
                "matches_declared_dpi": None,
            },
            "texture_world_width_m": texture_world_width_m,
            "notes": [
                "AI-generated source has no original scanner capture; physical scale uses declared DPI for parity with scanned yarns.",
                "Corrected band and U metadata are alpha-derived; DPI remains provenance metadata.",
            ],
        },
        "width": {
            "px": core_height,
            "mm": width_mm,
            "top_y_in_export": core_top,
            "bottom_y_in_export": core_bottom,
            "description": "Top-to-bottom of the unified solid thread band, in the EXPORT image's coordinates.",
        },
        "length": {
            "px": length_px,
            "mm": length_mm,
            "description": "Left-to-right of the export image (no wraparound).",
        },
        "bands_px": {
            "core": [core_top, core_bottom],
            "fiber_top": [arc2_top, core_top],
            "fiber_bot": [core_bottom, arc2_bottom],
        },
        "bands_v_norm": {
            "_convention": "blender (V=0 bottom, V=1 top)",
            "core": [core_v_min, core_v_max],
            "fiber_top": [fiber_top_v_min, fiber_top_v_max],
            "fiber_bot": [fiber_bot_v_min, fiber_bot_v_max],
        },
        "thickness_px": {
            "core_height": core_height,
            "fiber_top_height": fiber_top_height,
            "fiber_bot_height": fiber_bot_height,
        },
        "params": {
            "algorithm": "ai_high_alpha_core_full_support_arc2",
            "core_alpha_threshold": int(detector.get("core_threshold_used") or AI_CORE_ALPHA_THRESHOLD),
            "core_density_fraction": AI_CORE_DENSITY_FRACTION,
            "arc2_alpha_threshold": AI_ARC2_ALPHA_THRESHOLD,
            "arc2_row_density": AI_ARC2_ROW_DENSITY,
        },
        "blender": {
            "_convention": (
                "Pre-computed for direct push to Parametric Weave knotty. "
                "Producer owns all unit conversion (px/dpi/mm/BU). Consumer just "
                "pushes each value to the same-named modifier socket."
            ),
            "schema_version": 1,
            "texture_world_width_m": texture_world_width_m,
            "texture_world_width_mm": length_mm,
            "image_width_px": image_width,
            "scanner_pixels_per_bu": round(dpi * 39.3701, 2),
            "core_v_min": core_v_min,
            "core_v_max": core_v_max,
            "fiber_top_v_min": fiber_top_v_min,
            "fiber_bot_v_max": fiber_bot_v_max,
            "fiber_bot_v_min": fiber_bot_v_min,
            "fiber_top_v_max": fiber_top_v_max,
            "top_halo_frac": round(fiber_top_height / extent_height, 6) if extent_height > 0 else 0.0,
            "bot_halo_frac": round(fiber_bot_height / extent_height, 6) if extent_height > 0 else 0.0,
            "texture_scale_u": u_scale["texture_scale_u"],
            "texture_scale_u_strategy": AI_U_SCALE_STRATEGY,
            "texture_scale_u_core_v_span": core_v_max - core_v_min,
            "texture_scale_u_arc1_v_around_span": ARC1_V_AROUND_SPAN,
            "texture_scale_u_previous_auto_multiply": (core_v_max - core_v_min) * ARC1_V_AROUND_SPAN,
            "texture_scale_u_previous_core_only": u_scale["texture_scale_u_previous_core_only"],
            "texture_scale_u_raw_alpha_mass": u_scale["texture_scale_u_raw_alpha_mass"],
            "texture_scale_u_boost": u_scale["texture_scale_u_boost"],
            "texture_scale_u_alpha_equivalent_width_px": u_scale["alpha_equivalent_width_px"],
            "texture_scale_u_alpha_power": u_scale["alpha_power"],
            "texture_scale_u_max_boost": u_scale["max_boost"],
            "texture_scale_u_note": "AI U scale is derived from opacity-weighted visible yarn width, not only dense core height.",
            "v_band_strategy": AI_BAND_STRATEGY,
            "v_band_note": "AI yarns use a stricter high-alpha central core for Arc 1 and a wider low-alpha support range for Arc 2.",
        },
        "joins": [],
        "threads_solid_band": [],
        "ai_sanity_check": {
            "source_measurements_file": str(source_dir / measurement_filename) if measurement_filename else None,
            "source_rgba_file": str(rgba_path),
            "size_matches_png": detector.get("size_matches"),
            "dpi_source": "ai_measurements_declared_dpi" if measurements.get("dpi") else "default_1600",
            "embedded_png_dpi": list(embedded) if embedded else None,
            "embedded_png_dpi_matches_declared": None,
            "ai_measurements": {
                "image_size_px": measurements.get("image_size_px"),
                "dpi": measurements.get("dpi"),
                "core_band_px": original_core,
                "core_height_field": (measurements.get("c_band") or {}).get("height"),
                "core_width_px": original_width,
                "fiber_extent_px": original_extent,
                "length_px": (measurements.get("length") or {}).get("px"),
            },
            "corrected": {
                "core_band_px": [core_top, core_bottom],
                "core_width_px": core_height,
                "fiber_extent_px": [arc2_top, arc2_bottom],
                "length_px": length_px,
            },
            "delta_px": delta_px,
            "row_profile": detector.get("row_profile"),
            "u_scale_check": u_scale,
            "v_band_check": {
                "updated": {
                    "bands_px": {
                        "core": [core_top, core_bottom],
                        "fiber_top": [arc2_top, core_top],
                        "fiber_bot": [core_bottom, arc2_bottom],
                    },
                    "thickness_px": {
                        "core_height": core_height,
                        "fiber_top_height": fiber_top_height,
                        "fiber_bot_height": fiber_bot_height,
                    },
                    "blender": {
                        "core_v_min": core_v_min,
                        "core_v_max": core_v_max,
                        "fiber_bot_v_min": fiber_bot_v_min,
                        "fiber_top_v_max": fiber_top_v_max,
                        "texture_scale_u": u_scale["texture_scale_u"],
                    },
                },
                "strategy": "strict high-alpha core, wider low-alpha Arc 2 support",
            },
        },
        "files": {
            "rgb": None,
            "alpha": None,
            "rgba": "rgba.png",
            "thumbnail": "input_thumb.jpg",
            "metadata": "metadata.json",
        },
    }
    return metadata


def _index_entry_from_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": metadata.get("id"),
        "label": metadata.get("label"),
        "createdAt": metadata.get("createdAt"),
        "thumbnail": (metadata.get("files") or {}).get("thumbnail"),
        "widthPx": (metadata.get("width") or {}).get("px"),
        "widthMm": (metadata.get("width") or {}).get("mm"),
        "lengthPx": (metadata.get("length") or {}).get("px"),
        "lengthMm": (metadata.get("length") or {}).get("mm"),
        "dpi": metadata.get("dpi"),
    }


def _band_meta_from_library_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": metadata.get("label") or metadata.get("id"),
        "library_yarn_id": metadata.get("id"),
        "schemaVersion": metadata.get("schemaVersion", 1),
        "image_size_px": metadata.get("image_size_px") or [],
        "dpi": metadata.get("dpi"),
        "width": metadata.get("width") or {},
        "length": metadata.get("length") or {},
        "bands_px": metadata.get("bands_px") or {},
        "bands_v_norm": metadata.get("bands_v_norm") or {},
        "thickness_px": metadata.get("thickness_px") or {},
        "params": metadata.get("params") or {},
        "blender": metadata.get("blender") or {},
    }


def sync_runtime_bandmeta_for_library_yarn(
    library_yarn_id: str,
    metadata: dict[str, Any],
    *,
    runtime_root: Path | None = None,
) -> list[str]:
    runtime_root = runtime_root or YARN_ASSETS_ROOT
    if not runtime_root.exists():
        return []
    updated: list[str] = []
    band_meta = _band_meta_from_library_metadata(metadata)
    for asset_path in sorted(runtime_root.glob("*/asset.json")):
        try:
            asset = _read_json(asset_path)
        except Exception:
            continue
        if ((asset.get("bandMeta") or {}).get("library_yarn_id") != library_yarn_id):
            continue
        asset["bandMeta"] = band_meta
        asset["updatedAt"] = _utc_now_iso()
        _write_json(asset_path, asset)
        updated.append(asset.get("id") or asset_path.parent.name)
    return updated


def save_ai_yarn_to_library(
    rgba_path: Path,
    *,
    measurements_path: Path | None = None,
    measurements: dict[str, Any] | None = None,
    label: str | None = None,
    library_root: Path | None = None,
    yarn_id: str | None = None,
    sync_runtime: bool = True,
    external_corrected_dir: Path | None = None,
) -> dict[str, Any]:
    library_root = library_root or YARN_LIBRARY_ROOT
    rgba_path = Path(rgba_path).resolve()
    measurements_path = Path(measurements_path).resolve() if measurements_path else None
    if measurements is None and measurements_path and measurements_path.exists():
        measurements = _read_json(measurements_path)
    if yarn_id is None:
        yarn_id = _new_yarn_id()
    if not _LIBRARY_ID_RE.match(yarn_id):
        raise ValueError(f"invalid yarn id: {yarn_id}")
    label_clean = _slugify_label(label or rgba_path.stem, fallback=yarn_id)

    metadata = build_ai_yarn_metadata(
        rgba_path,
        yarn_id=yarn_id,
        label=label_clean,
        source_dir=rgba_path.parent,
        measurements=measurements,
        measurement_filename=measurements_path.name if measurements_path else None,
    )

    yarn_dir = library_root / yarn_id
    yarn_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(rgba_path, yarn_dir / "rgba.png")
    _make_ai_thumbnail(rgba_path, yarn_dir / "input_thumb.jpg")
    _write_json(yarn_dir / "metadata.json", metadata)
    upsert_index_entry(library_root, _index_entry_from_metadata(metadata))

    external_path = None
    if external_corrected_dir:
        external_corrected_dir.mkdir(parents=True, exist_ok=True)
        external_path = external_corrected_dir / f"{yarn_id}_metadata.json"
        _write_json(external_path, metadata)

    updated_runtime_asset_ids = (
        sync_runtime_bandmeta_for_library_yarn(yarn_id, metadata) if sync_runtime else []
    )
    return {
        "ok": True,
        "id": yarn_id,
        "label": label_clean,
        "libraryPath": str(yarn_dir),
        "metadataPath": str(yarn_dir / "metadata.json"),
        "externalCorrectedMetadataPath": str(external_path) if external_path else None,
        "updatedRuntimeAssetIds": updated_runtime_asset_ids,
        "entry": _index_entry_from_metadata(metadata),
        "metadata": metadata,
    }


def refresh_existing_ai_yarn_metadata(
    yarn_id: str,
    *,
    library_root: Path | None = None,
    sync_runtime: bool = True,
) -> dict[str, Any]:
    library_root = library_root or YARN_LIBRARY_ROOT
    if not _LIBRARY_ID_RE.match(yarn_id):
        raise ValueError(f"invalid yarn id: {yarn_id}")
    yarn_dir = library_root / yarn_id
    metadata_path = yarn_dir / "metadata.json"
    rgba_path = yarn_dir / "rgba.png"
    if not metadata_path.exists() or not rgba_path.exists():
        raise FileNotFoundError(f"missing library metadata or rgba for {yarn_id}")
    old = _read_json(metadata_path)
    source = old.get("source") or {}
    if source.get("kind") != "ai_generated_rgba":
        raise ValueError(f"not an AI-generated yarn: {yarn_id}")

    measurements = None
    measurement_filename = source.get("measurement_filename")
    asset_dir = source.get("asset_dir")
    measurement_path = None
    if asset_dir and measurement_filename:
        candidate = Path(asset_dir) / measurement_filename
        if candidate.exists():
            measurement_path = candidate
            measurements = _read_json(candidate)

    metadata = build_ai_yarn_metadata(
        rgba_path,
        yarn_id=yarn_id,
        label=old.get("label") or yarn_id,
        source_dir=Path(asset_dir) if asset_dir else yarn_dir,
        measurements=measurements,
        measurement_filename=measurement_filename,
        created_at=old.get("createdAt"),
    )
    _write_json(metadata_path, metadata)
    upsert_index_entry(library_root, _index_entry_from_metadata(metadata))

    external_path = None
    if asset_dir:
        corrected_dir = Path(asset_dir) / "corrected_metadata"
        corrected_dir.mkdir(parents=True, exist_ok=True)
        slug = re.sub(r"[^A-Za-z0-9._-]+", "_", old.get("label") or yarn_id).strip("_") or yarn_id
        external_path = corrected_dir / f"{slug}_metadata.json"
        _write_json(external_path, metadata)

    updated_runtime_asset_ids = (
        sync_runtime_bandmeta_for_library_yarn(yarn_id, metadata) if sync_runtime else []
    )
    return {
        "ok": True,
        "id": yarn_id,
        "label": metadata.get("label"),
        "metadataPath": str(metadata_path),
        "externalCorrectedMetadataPath": str(external_path) if external_path else None,
        "updatedRuntimeAssetIds": updated_runtime_asset_ids,
        "previousTextureScaleU": ((old.get("blender") or {}).get("texture_scale_u")),
        "textureScaleU": ((metadata.get("blender") or {}).get("texture_scale_u")),
        "textureScaleUStrategy": ((metadata.get("blender") or {}).get("texture_scale_u_strategy")),
        "metadata": metadata,
    }


def refresh_all_existing_ai_yarns(
    *,
    library_root: Path | None = None,
    sync_runtime: bool = True,
) -> dict[str, Any]:
    library_root = library_root or YARN_LIBRARY_ROOT
    results: list[dict[str, Any]] = []
    for metadata_path in sorted(library_root.glob("*/metadata.json")):
        try:
            metadata = _read_json(metadata_path)
        except Exception:
            continue
        if (metadata.get("source") or {}).get("kind") != "ai_generated_rgba":
            continue
        results.append(refresh_existing_ai_yarn_metadata(
            metadata.get("id") or metadata_path.parent.name,
            library_root=library_root,
            sync_runtime=sync_runtime,
        ))
    return {
        "ok": True,
        "count": len(results),
        "results": results,
    }
