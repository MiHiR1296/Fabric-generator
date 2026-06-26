from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image
from scipy import ndimage


Image.MAX_IMAGE_PIXELS = None

GENERATOR_VERSION = "yarn_pbr_v1.3"
GENERATOR_MAJOR = 1
MANIFEST_RELATIVE_PATH = "pbr/manifest.json"
NORMAL_HEIGHT_FILENAME = "normal_height.png"
ROUGHNESS_SPECULAR_FILENAME = "roughness_specular.png"
PREVIEW_FILENAME = "preview.png"


DEFAULT_OPTIONS: dict[str, Any] = {
    "alpha_support_threshold": 5,
    "normal": {
        "space": "OBJECT",
        "strength": 1.6,
        "blur_sigma": 0.8,
        "method": "sobel",
    },
    "height": {
        "high_pass_sigma": 8.0,
        "gamma": 1.0,
    },
    "roughness": {
        "low": 0.55,
        "high": 0.85,
    },
    "specular_ior_level": {
        "low": 0.05,
        "high": 0.30,
    },
}

DEFAULT_CONSUMER_DEFAULTS: dict[str, float] = {
    "normal_strength": 0.1,
    "bump_strength": 1.0,
    "bump_distance_bu": 0.0008,
}


@dataclass
class PbrPreflightError(ValueError):
    asset_id: str
    asset_label: str
    missing_maps: list[str]
    stale_reason: str

    @property
    def remediation(self) -> str:
        return f"POST /api/yarn-assets/{self.asset_id}/regenerate-pbr"

    def __str__(self) -> str:
        return f"PBR maps are not ready for {self.asset_label or self.asset_id}: {self.stale_reason}"

    def to_response(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "asset_label": self.asset_label,
            "missing_maps": self.missing_maps,
            "stale_reason": self.stale_reason,
            "remediation": self.remediation,
        }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _file_mtime_iso(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _merge_options(options: dict[str, Any] | None) -> dict[str, Any]:
    merged = json.loads(json.dumps(DEFAULT_OPTIONS))
    for key, value in (options or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key].update(value)
        else:
            merged[key] = value
    return merged


def _luminance(rgb: np.ndarray) -> np.ndarray:
    return (
        (0.2126 * rgb[..., 0])
        + (0.7152 * rgb[..., 1])
        + (0.0722 * rgb[..., 2])
    ).astype(np.float32)


def vertical_edge_extend_luma(luma: np.ndarray, support: np.ndarray) -> np.ndarray:
    """Fill transparent rows with the nearest supported row in each column.

    This prevents Sobel from reading the alpha matte as a fake height edge.
    Yarn strips are horizontal bands, so vertical edge extension is the cheap
    and targeted fill for the top/bottom transparent halo.
    """
    if luma.shape != support.shape:
        raise ValueError("luma/support shape mismatch")
    filled = np.array(luma, copy=True, dtype=np.float32)
    if support.any():
        fallback = float(np.median(luma[support]))
    else:
        fallback = float(np.median(luma))
    height, width = filled.shape
    for x in range(width):
        rows = np.flatnonzero(support[:, x])
        if rows.size == 0:
            filled[:, x] = fallback
            continue
        first = int(rows[0])
        last = int(rows[-1])
        if first > 0:
            filled[:first, x] = filled[first, x]
        if last < height - 1:
            filled[last + 1:, x] = filled[last, x]
    return filled


def _normalize_u8(value: np.ndarray) -> np.ndarray:
    return np.clip(np.rint(np.clip(value, 0.0, 1.0) * 255.0), 0, 255).astype(np.uint8)


def _bake_normal_height(
    luma_filled: np.ndarray,
    support: np.ndarray,
    *,
    options: dict[str, Any],
) -> Image.Image:
    normal_options = options["normal"]
    height_options = options["height"]

    normal_source = luma_filled.astype(np.float32)
    blur_sigma = float(normal_options.get("blur_sigma", 0.0) or 0.0)
    if blur_sigma > 0:
        normal_source = ndimage.gaussian_filter(normal_source, sigma=blur_sigma, mode="nearest")

    gx = ndimage.sobel(normal_source, axis=1, mode="nearest")
    gy = ndimage.sobel(normal_source, axis=0, mode="nearest")
    strength = float(normal_options.get("strength", 1.0) or 1.0)
    nx = -gx * strength
    ny = -gy * strength
    nz = np.ones_like(nx, dtype=np.float32)
    length = np.sqrt((nx * nx) + (ny * ny) + (nz * nz))
    length = np.maximum(length, 1e-6)

    normal = np.stack((
        (nx / length) * 0.5 + 0.5,
        (ny / length) * 0.5 + 0.5,
        (nz / length) * 0.5 + 0.5,
    ), axis=-1)
    normal_u8 = _normalize_u8(normal)
    normal_u8[~support] = np.array([128, 128, 255], dtype=np.uint8)

    height = luma_filled.astype(np.float32)
    high_pass_sigma = float(height_options.get("high_pass_sigma", 0.0) or 0.0)
    if high_pass_sigma > 0:
        low = ndimage.gaussian_filter(height, sigma=high_pass_sigma, mode="nearest")
        height = height - low + 0.5
    gamma = float(height_options.get("gamma", 1.0) or 1.0)
    height = np.power(np.clip(height, 0.0, 1.0), gamma)
    height[~support] = 0.5
    height_u8 = _normalize_u8(height)

    packed = np.dstack((normal_u8, height_u8))
    return Image.fromarray(packed)


def _bake_roughness_specular(
    luma_filled: np.ndarray,
    support: np.ndarray,
    *,
    options: dict[str, Any],
) -> Image.Image:
    roughness_options = options["roughness"]
    specular_options = options["specular_ior_level"]
    rough_low = float(roughness_options.get("low", 0.55))
    rough_high = float(roughness_options.get("high", 0.85))
    spec_low = float(specular_options.get("low", 0.05))
    spec_high = float(specular_options.get("high", 0.30))

    luma = np.clip(luma_filled.astype(np.float32), 0.0, 1.0)
    roughness = rough_high - ((rough_high - rough_low) * luma)
    specular = spec_low + ((spec_high - spec_low) * luma)
    roughness[~support] = 1.0
    specular[~support] = 0.0

    zeros = np.zeros_like(roughness, dtype=np.uint8)
    alpha = np.full_like(roughness, 255, dtype=np.uint8)
    packed = np.dstack((
        _normalize_u8(roughness),
        _normalize_u8(specular),
        zeros,
        alpha,
    ))
    return Image.fromarray(packed)


def _tile_image_set(
    source_path: Path,
    output_dir: Path,
    *,
    max_dimension: int,
) -> dict[str, Any] | None:
    if max_dimension <= 0:
        return None
    with Image.open(source_path) as image:
        width, height = image.size
        if max(width, height) <= max_dimension:
            return None
        if height > max_dimension:
            raise ValueError(f"PBR map height exceeds Cycles tile cap: {source_path.name}")

        tile_count = math.ceil(width / max_dimension)
        if tile_count < 2 or tile_count > 12:
            raise ValueError(f"PBR map needs unsupported UDIM tile count {tile_count}: {source_path.name}")

        output_dir.mkdir(parents=True, exist_ok=True)
        tile_paths: list[Path] = []
        tile_widths: list[int] = []
        for index in range(tile_count):
            left = round(index * width / tile_count)
            right = round((index + 1) * width / tile_count)
            udim = 1001 + index
            tile_path = output_dir / f"{source_path.stem}_{udim}{source_path.suffix}"
            image.crop((left, 0, right, height)).save(tile_path)
            tile_paths.append(tile_path)
            tile_widths.append(right - left)

    return {
        "tile_count": tile_count,
        "tile_width_px": max(tile_widths),
        "tile_height_px": height,
        "pattern": output_dir / f"{source_path.stem}_<UDIM>{source_path.suffix}",
        "paths": tile_paths,
    }


def _relative_to(path: Path, root: Path) -> str:
    return str(path.resolve().relative_to(root.resolve()))


def _write_preview(normal_height_path: Path, roughness_specular_path: Path, preview_path: Path) -> None:
    with Image.open(normal_height_path) as normal_image, Image.open(roughness_specular_path) as rs_image:
        normal_thumb = normal_image.convert("RGB")
        rs_rgb = rs_image.convert("RGBA")
        rough, spec, _b, _a = rs_rgb.split()
        rs_preview = Image.merge("RGB", (rough, spec, rough))
        normal_thumb.thumbnail((128, 128), Image.LANCZOS)
        rs_preview.thumbnail((128, 128), Image.LANCZOS)
        canvas = Image.new("RGB", (256, 128), (24, 24, 24))
        canvas.paste(normal_thumb, (0, (128 - normal_thumb.height) // 2))
        canvas.paste(rs_preview, (128, (128 - rs_preview.height) // 2))
        canvas.save(preview_path)


def _remove_stale_base_color_outputs(output_dir: Path) -> None:
    for path in [
        output_dir / "base_color.png",
        *(output_dir / "cycles_tiled").glob("base_color_*.png"),
    ]:
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def bake_pbr_map_set(
    rgba_path: Path,
    output_dir: Path,
    *,
    options: dict[str, Any] | None = None,
    consumer_defaults: dict[str, float] | None = None,
    max_dimension: int = 16384,
) -> dict[str, Any]:
    if not rgba_path.exists():
        raise FileNotFoundError(rgba_path)

    output_dir.mkdir(parents=True, exist_ok=True)
    merged_options = _merge_options(options)
    merged_consumer_defaults = {
        **DEFAULT_CONSUMER_DEFAULTS,
        **(consumer_defaults or {}),
    }

    with Image.open(rgba_path) as image:
        rgba = image.convert("RGBA")
        source_size = list(rgba.size)
        arr = np.asarray(rgba, dtype=np.uint8)

    rgb = arr[..., :3].astype(np.float32) / 255.0
    alpha = arr[..., 3]
    support_threshold = int(merged_options.get("alpha_support_threshold", 5))
    support = alpha > support_threshold
    luma = _luminance(rgb)
    luma_filled = vertical_edge_extend_luma(luma, support)

    normal_height_path = output_dir / NORMAL_HEIGHT_FILENAME
    roughness_specular_path = output_dir / ROUGHNESS_SPECULAR_FILENAME
    preview_path = output_dir / PREVIEW_FILENAME

    _remove_stale_base_color_outputs(output_dir)
    _bake_normal_height(luma_filled, support, options=merged_options).save(normal_height_path)
    _bake_roughness_specular(luma_filled, support, options=merged_options).save(roughness_specular_path)
    _write_preview(normal_height_path, roughness_specular_path, preview_path)

    source_hash = sha256_file(rgba_path)
    pbr_root = output_dir
    source_rel = os.path.relpath(rgba_path.resolve(), pbr_root.resolve())
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "generator_version": GENERATOR_VERSION,
        "generated_at": _utc_now(),
        "source_rgba": source_rel,
        "source_size_px": source_size,
        "source_sha256": source_hash,
        "source_mtime": _file_mtime_iso(rgba_path),
        "normal_space": "OBJECT",
        "options": merged_options,
        "consumer_defaults": merged_consumer_defaults,
        "maps": {
            "normal_height": {
                "path": NORMAL_HEIGHT_FILENAME,
                "channels": {"r": "normal_x", "g": "normal_y", "b": "normal_z", "a": "height"},
                "size_px": source_size,
                "colorspace": "Non-Color",
            },
            "roughness_specular": {
                "path": ROUGHNESS_SPECULAR_FILENAME,
                "channels": {"r": "roughness", "g": "specular_ior_level", "b": "unused_zero", "a": "opaque"},
                "size_px": source_size,
                "colorspace": "Non-Color",
            },
            "anisotropy_tangent": None,
        },
        "preview": {"path": PREVIEW_FILENAME, "size_px": [256, 128]},
        "udim": {"enabled": False},
    }

    tiled_root = output_dir / "cycles_tiled"
    normal_tiles = _tile_image_set(normal_height_path, tiled_root, max_dimension=max_dimension)
    roughness_tiles = _tile_image_set(roughness_specular_path, tiled_root, max_dimension=max_dimension)
    if normal_tiles or roughness_tiles:
        if not normal_tiles or not roughness_tiles:
            raise ValueError("PBR packed maps produced inconsistent UDIM state.")
        if normal_tiles["tile_count"] != roughness_tiles["tile_count"]:
            raise ValueError("PBR packed maps produced inconsistent UDIM tile counts.")
        manifest["udim"] = {
            "enabled": True,
            "tile_count": int(normal_tiles["tile_count"]),
            "tile_width_px": int(normal_tiles["tile_width_px"]),
            "tile_height_px": int(normal_tiles["tile_height_px"]),
            "normal_height": {
                "pattern": _relative_to(normal_tiles["pattern"], pbr_root),
                "tiles": [1001 + index for index in range(int(normal_tiles["tile_count"]))],
                "paths": [_relative_to(path, pbr_root) for path in normal_tiles["paths"]],
            },
            "roughness_specular": {
                "pattern": _relative_to(roughness_tiles["pattern"], pbr_root),
                "tiles": [1001 + index for index in range(int(roughness_tiles["tile_count"]))],
                "paths": [_relative_to(path, pbr_root) for path in roughness_tiles["paths"]],
            },
        }

    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def _major_from_version(version: str) -> int | None:
    prefix = "yarn_pbr_v"
    if not isinstance(version, str) or not version.startswith(prefix):
        return None
    rest = version[len(prefix):]
    major = rest.split(".", 1)[0]
    try:
        return int(major)
    except ValueError:
        return None


def _manifest_path_from_asset(asset_dir: Path, pbr_maps: dict[str, Any] | None) -> Path:
    manifest_rel = (pbr_maps or {}).get("manifestFilename") or MANIFEST_RELATIVE_PATH
    return asset_dir / str(manifest_rel)


def validate_asset_pbr(
    *,
    asset_dir: Path,
    asset_id: str,
    asset_label: str,
    pbr_maps: dict[str, Any] | None,
    max_dimension: int = 16384,
) -> dict[str, Any]:
    missing: list[str] = []
    manifest_path = _manifest_path_from_asset(asset_dir, pbr_maps)
    if not manifest_path.exists():
        raise PbrPreflightError(asset_id, asset_label, [MANIFEST_RELATIVE_PATH], "missing_pbr_manifest")

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise PbrPreflightError(asset_id, asset_label, [MANIFEST_RELATIVE_PATH], f"invalid_pbr_manifest: {exc}") from exc

    version = manifest.get("generator_version")
    if _major_from_version(version) != GENERATOR_MAJOR:
        raise PbrPreflightError(
            asset_id,
            asset_label,
            [MANIFEST_RELATIVE_PATH],
            f"generator_major_mismatch: expected {GENERATOR_MAJOR}, got {version}",
        )

    pbr_root = manifest_path.parent
    source_rel = manifest.get("source_rgba")
    source_path = (pbr_root / str(source_rel)).resolve() if source_rel else asset_dir / "rgba.png"
    if not source_path.exists():
        raise PbrPreflightError(asset_id, asset_label, [str(source_rel or "rgba.png")], "missing_source_rgba")

    with Image.open(source_path) as source_image:
        current_size = list(source_image.size)
    if current_size != list(manifest.get("source_size_px") or []):
        raise PbrPreflightError(asset_id, asset_label, [], "source_size_mismatch")

    current_hash = sha256_file(source_path)
    if current_hash != manifest.get("source_sha256"):
        raise PbrPreflightError(asset_id, asset_label, [], "source_sha256_mismatch")

    maps = manifest.get("maps") or {}
    normal_entry = maps.get("normal_height") or {}
    roughness_entry = maps.get("roughness_specular") or {}
    if not normal_entry or not roughness_entry:
        raise PbrPreflightError(
            asset_id,
            asset_label,
            [MANIFEST_RELATIVE_PATH],
            "invalid_pbr_manifest: missing map entries",
        )
    normal_path = pbr_root / str(normal_entry.get("path") or NORMAL_HEIGHT_FILENAME)
    roughness_path = pbr_root / str(roughness_entry.get("path") or ROUGHNESS_SPECULAR_FILENAME)
    if not normal_path.exists():
        missing.append(str(normal_path.relative_to(asset_dir)))
    if not roughness_path.exists():
        missing.append(str(roughness_path.relative_to(asset_dir)))
    if missing:
        raise PbrPreflightError(asset_id, asset_label, missing, "missing_packed_pbr_maps")

    source_needs_udim = max(current_size) > max_dimension
    udim = manifest.get("udim") or {}
    udim_enabled = bool(udim.get("enabled"))
    if source_needs_udim and not udim_enabled:
        raise PbrPreflightError(asset_id, asset_label, [], "missing_pbr_udim_tiles")

    payload: dict[str, Any] = {
        "pbr_manifest_path": str(manifest_path),
        "pbr_generator_version": version,
        "pbr_source_sha256": current_hash,
        "pbr_normal_space": manifest.get("normal_space") or "OBJECT",
        "pbr_consumer_defaults": manifest.get("consumer_defaults") or DEFAULT_CONSUMER_DEFAULTS,
    }
    if udim_enabled:
        tile_count = int(udim.get("tile_count") or 0)
        normal_udim = udim.get("normal_height") or {}
        roughness_udim = udim.get("roughness_specular") or {}
        normal_paths = [pbr_root / path for path in normal_udim.get("paths") or []]
        roughness_paths = [pbr_root / path for path in roughness_udim.get("paths") or []]
        if (
            tile_count <= 1
            or len(normal_paths) != tile_count
            or len(roughness_paths) != tile_count
        ):
            raise PbrPreflightError(asset_id, asset_label, [], "invalid_pbr_udim_manifest")
        missing_tiles = [
            str(path.relative_to(asset_dir))
            for path in [*normal_paths, *roughness_paths]
            if not path.exists()
        ]
        if missing_tiles:
            raise PbrPreflightError(asset_id, asset_label, missing_tiles, "missing_pbr_udim_tiles")
        payload.update({
            "pbr_texture_mode": "pbr_udim_tiled",
            "pbr_tile_count": tile_count,
            "pbr_tile_width_px": udim.get("tile_width_px"),
            "pbr_tile_height_px": udim.get("tile_height_px"),
            "pbr_normal_height_tile_pattern": str(pbr_root / str(normal_udim.get("pattern"))),
            "pbr_roughness_specular_tile_pattern": str(pbr_root / str(roughness_udim.get("pattern"))),
            "pbr_normal_height_tile_paths": [str(path) for path in normal_paths],
            "pbr_roughness_specular_tile_paths": [str(path) for path in roughness_paths],
        })
    else:
        payload.update({
            "pbr_texture_mode": "pbr_single",
            "pbr_normal_height_path": str(normal_path),
            "pbr_roughness_specular_path": str(roughness_path),
        })
    return payload


def build_asset_pbr_summary(asset_dir: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    pbr_root = asset_dir / "pbr"
    udim = manifest.get("udim") or {}
    summary: dict[str, Any] = {
        "manifestFilename": MANIFEST_RELATIVE_PATH,
        "generatorVersion": manifest.get("generator_version"),
        "generatorMajor": _major_from_version(str(manifest.get("generator_version"))),
        "sourceSha256": manifest.get("source_sha256"),
        "sourceSizePx": manifest.get("source_size_px"),
        "normalSpace": manifest.get("normal_space") or "OBJECT",
        "normalHeightFilename": f"pbr/{NORMAL_HEIGHT_FILENAME}",
        "roughnessSpecularFilename": f"pbr/{ROUGHNESS_SPECULAR_FILENAME}",
        "previewFilename": f"pbr/{PREVIEW_FILENAME}",
        "textureMode": "pbr_udim_tiled" if udim.get("enabled") else "pbr_single",
        "validation": "complete",
    }
    if udim.get("enabled"):
        normal_udim = udim.get("normal_height") or {}
        roughness_udim = udim.get("roughness_specular") or {}
        summary.update({
            "tileCount": udim.get("tile_count"),
            "tileWidthPx": udim.get("tile_width_px"),
            "tileHeightPx": udim.get("tile_height_px"),
            "normalHeightTilePattern": f"pbr/{normal_udim.get('pattern')}",
            "normalHeightTileFilenames": [f"pbr/{path}" for path in normal_udim.get("paths") or []],
            "roughnessSpecularTilePattern": f"pbr/{roughness_udim.get('pattern')}",
            "roughnessSpecularTileFilenames": [f"pbr/{path}" for path in roughness_udim.get("paths") or []],
        })
    return summary
