from __future__ import annotations

import json
import os
import re
import shutil
import sys
import threading
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

from .models import YarnAsset
from .runtime_paths import YARN_ASSETS_ROOT, YARN_LIBRARY_ROOT, ensure_runtime_dirs


VENDOR_ROOT = Path(__file__).resolve().parents[1] / "vendor" / "yarn_pipeline"
if str(VENDOR_ROOT) not in sys.path:
    sys.path.insert(0, str(VENDOR_ROOT))

from yarn_pipeline import run_pipeline  # type: ignore  # noqa: E402


Image.MAX_IMAGE_PIXELS = None

_LOCK = threading.Lock()
_ASSETS: dict[str, YarnAsset] = {}

# Cycles single-texture-dimension cap. Override via CYCLES_MAX_TEXTURE_DIM env.
# 16384 is the safe ceiling for NVIDIA CUDA/OptiX, Apple Metal, AMD ROCm.
# CPU rendering has no such limit but keeping 16384 saves VRAM regardless.
MAX_CYCLES_TEXTURE_DIMENSION = int(os.environ.get("CYCLES_MAX_TEXTURE_DIM", "16384"))

# Library yarn id format from yarnseamless's yarn_library.py (YYYYMMDD_HHMMSS_hex).
_LIBRARY_ID_RE = re.compile(r"^[0-9]{8}_[0-9]{6}_[a-f0-9]{4,8}$")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _slugify(filename: str) -> str:
    stem = Path(filename).stem or "yarn"
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", stem).strip("-") or "yarn"


def _asset_dir(asset_id: str) -> Path:
    return YARN_ASSETS_ROOT / asset_id


def _meta_path(asset_id: str) -> Path:
    return _asset_dir(asset_id) / "asset.json"


def _build_file_url(asset_id: str, filename: str | None) -> str | None:
    if not filename:
        return None
    return f"/api/yarn/assets/{asset_id}/files/{filename}"


def _build_file_urls(asset_id: str, filenames: list[str] | None) -> list[str]:
    return [
        url
        for filename in filenames or []
        if (url := _build_file_url(asset_id, filename)) is not None
    ]


def _persist_asset(asset: YarnAsset) -> None:
    destination = _meta_path(asset.id)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(asdict(asset), indent=2), encoding="utf-8")


def _load_asset_from_disk(meta_path: Path) -> YarnAsset:
    payload = json.loads(meta_path.read_text(encoding="utf-8"))
    return YarnAsset(**payload)


def _refresh_asset_urls(asset: YarnAsset) -> YarnAsset:
    asset.sourceUrl = _build_file_url(asset.id, asset.sourceFilename) or ""
    asset.diffuseUrl = _build_file_url(asset.id, asset.diffuseFilename)
    asset.alphaUrl = _build_file_url(asset.id, asset.alphaFilename)
    asset.preprocessedUrl = _build_file_url(asset.id, asset.preprocessedFilename)
    asset.renderDiffuseUrl = _build_file_url(asset.id, asset.renderDiffuseFilename)
    asset.renderAlphaUrl = _build_file_url(asset.id, asset.renderAlphaFilename)
    asset.renderDiffuseTileUrls = _build_file_urls(asset.id, asset.renderDiffuseTileFilenames)
    asset.renderAlphaTileUrls = _build_file_urls(asset.id, asset.renderAlphaTileFilenames)
    return asset


def _relative_asset_path(asset_id: str, path: str | Path | None) -> str | None:
    if path is None:
        return None
    try:
        return str(Path(path).resolve().relative_to(_asset_dir(asset_id).resolve()))
    except ValueError:
        return str(path)


def load_yarn_assets() -> None:
    ensure_runtime_dirs()
    with _LOCK:
        if _ASSETS:
            return
        for meta_path in sorted(YARN_ASSETS_ROOT.glob("*/asset.json")):
            asset = _refresh_asset_urls(_load_asset_from_disk(meta_path))
            _ASSETS[asset.id] = asset
    reconcile_orphan_imports()


def reconcile_orphan_imports() -> list[str]:
    """Delete imported runtime YarnAssets whose source library yarn no longer
    exists. Catches deletes that happened outside the API (Finder, manual rm,
    or a pre-Phase-W1 cascade gap). Manually-uploaded assets (no
    `bandMeta.library_yarn_id`) are never touched. Returns the list of removed
    asset ids."""
    library_root = YARN_LIBRARY_ROOT
    live_library_ids: set[str] = set()
    if library_root.exists():
        for child in library_root.iterdir():
            if child.is_dir() and _LIBRARY_ID_RE.match(child.name):
                live_library_ids.add(child.name)

    with _LOCK:
        orphan_ids = [
            asset.id
            for asset in _ASSETS.values()
            if (lib_id := (asset.bandMeta or {}).get("library_yarn_id"))
            and lib_id not in live_library_ids
        ]
    for asset_id in orphan_ids:
        try:
            delete_yarn_asset(asset_id)
        except FileNotFoundError:
            pass
    return orphan_ids


def list_yarn_assets() -> list[dict]:
    load_yarn_assets()
    with _LOCK:
        assets = sorted(_ASSETS.values(), key=lambda asset: asset.createdAt or "", reverse=True)
        return [asset.to_dict() for asset in assets]


def get_yarn_asset(asset_id: str) -> YarnAsset | None:
    load_yarn_assets()
    with _LOCK:
        asset = _ASSETS.get(asset_id)
        if asset is None:
            return None
        return YarnAsset(**asset.to_dict())


def get_ready_yarn_assets_lookup() -> dict[str, YarnAsset]:
    load_yarn_assets()
    with _LOCK:
        return {asset_id: YarnAsset(**asset.to_dict()) for asset_id, asset in _ASSETS.items()}


def get_yarn_asset_file_path(asset_id: str, filename: str) -> Path | None:
    candidate = (_asset_dir(asset_id) / filename).resolve()
    root = _asset_dir(asset_id).resolve()
    if root not in candidate.parents and candidate != root:
        return None
    if not candidate.exists() or not candidate.is_file():
        return None
    return candidate


def _update_asset(asset_id: str, **changes: object) -> None:
    with _LOCK:
        asset = _ASSETS[asset_id]
        for key, value in changes.items():
            setattr(asset, key, value)
        asset.updatedAt = _utc_now()
        _refresh_asset_urls(asset)
        _persist_asset(asset)


def _process_asset(asset_id: str, orientation: str = "auto") -> None:
    asset = get_yarn_asset(asset_id)
    if asset is None:
        return
    source_path = _asset_dir(asset_id) / asset.sourceFilename
    processed_dir = _asset_dir(asset_id) / "processed"
    processed_dir.mkdir(parents=True, exist_ok=True)
    _update_asset(asset_id, status="processing", error=None)

    try:
        result = run_pipeline(
            input_path=str(source_path),
            output_dir=str(processed_dir),
            orientation=orientation,
            keep_intermediate=True,
            verbose=False,
        )
        _update_asset(
            asset_id,
            status="ready",
            diffuseFilename=str(Path(result["seamless"]).relative_to(_asset_dir(asset_id))),
            alphaFilename=str(Path(result["alpha"]).relative_to(_asset_dir(asset_id))),
            preprocessedFilename=(
                str(Path(result["preprocessed"]).relative_to(_asset_dir(asset_id)))
                if result.get("preprocessed")
                else None
            ),
            preprocessMeta=result.get("preprocess_meta") or {},
            alphaMeta=result.get("alpha_meta") or {},
            error=None,
        )
    except Exception as exc:
        _update_asset(asset_id, status="failed", error=str(exc))


def create_yarn_assets(
    files: list[tuple[str, bytes]],
    orientation: str = "auto",
) -> list[dict]:
    ensure_runtime_dirs()
    load_yarn_assets()
    created: list[YarnAsset] = []

    for filename, payload in files:
        asset_id = uuid.uuid4().hex[:12]
        source_name = f"{_slugify(filename)}{Path(filename).suffix or '.png'}"
        destination_dir = _asset_dir(asset_id)
        destination_dir.mkdir(parents=True, exist_ok=True)
        source_path = destination_dir / source_name
        source_path.write_bytes(payload)

        asset = YarnAsset(
            id=asset_id,
            label=_slugify(filename).replace("-", " ").strip().title() or "Yarn Asset",
            status="queued",
            sourceFilename=source_name,
            sourceUrl="",
            createdAt=_utc_now(),
            updatedAt=_utc_now(),
        )
        _refresh_asset_urls(asset)
        _persist_asset(asset)
        with _LOCK:
            _ASSETS[asset_id] = asset
        created.append(YarnAsset(**asset.to_dict()))

        thread = threading.Thread(
            target=_process_asset,
            args=(asset_id, orientation),
            daemon=True,
            name=f"yarn-asset-{asset_id}",
        )
        thread.start()

    return [asset.to_dict() for asset in created]


def retry_yarn_asset(asset_id: str, orientation: str = "auto") -> dict:
    asset = get_yarn_asset(asset_id)
    if asset is None:
        raise FileNotFoundError(asset_id)
    thread = threading.Thread(
        target=_process_asset,
        args=(asset_id, orientation),
        daemon=True,
        name=f"yarn-asset-retry-{asset_id}",
    )
    thread.start()
    return get_yarn_asset(asset_id).to_dict()  # type: ignore[union-attr]


def delete_yarn_asset(asset_id: str) -> None:
    load_yarn_assets()
    with _LOCK:
        asset = _ASSETS.pop(asset_id, None)
    if asset is None:
        raise FileNotFoundError(asset_id)
    shutil.rmtree(_asset_dir(asset_id), ignore_errors=True)


# ---------------------------------------------------------------------------
# Library import — read from shared yarn_library/ (yarnseamless's output)
# ---------------------------------------------------------------------------
# The yarnseamless app writes processed yarns to <repo_parent>/yarn_library/.
# We list those entries, and on Import copy the canonical RGBA into the
# runtime asset folder, split it into albedo + alpha, produce Cycles-safe
# downscales (≤16384 px on the long edge), and shape a bandMeta dict that
# the render pipeline pushes straight to Blender (no further math).
#
# The producer (yarnseamless/web/yarn_library.py) pre-computes a `blender`
# block inside metadata.json with values ready for direct socket push:
#   texture_world_width_m / image_width_px / scanner_pixels_per_bu /
#   core_v_min / core_v_max / fiber_top_v_min/max / fiber_bot_v_min/max
# Consumer (render_jobs.py, added in Phase 2) reads bandMeta.blender.*
# and pushes each value to its matching Parametric Weave knotty socket.


def _library_dir(yarn_id: str) -> Path | None:
    if not yarn_id or not _LIBRARY_ID_RE.match(yarn_id):
        return None
    candidate = (YARN_LIBRARY_ROOT / yarn_id).resolve()
    try:
        candidate.relative_to(YARN_LIBRARY_ROOT.resolve())
    except ValueError:
        return None
    if not candidate.is_dir():
        return None
    return candidate


def list_library_yarns() -> list[dict]:
    """List yarns saved by yarnseamless. Prefers `<library>/index.json` for
    speed; falls back to scanning `<library>/*/metadata.json` if the index is
    missing or malformed. Enriches each entry with a public thumbnail URL the
    frontend can render."""
    library_root = YARN_LIBRARY_ROOT
    if not library_root.exists():
        return []
    index_path = library_root / "index.json"
    yarns: list[dict] = []
    if index_path.exists():
        try:
            data = json.loads(index_path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("yarns"), list):
                yarns = list(data["yarns"])
        except Exception:
            yarns = []
    if not yarns:
        for meta in sorted(library_root.glob("*/metadata.json")):
            try:
                payload = json.loads(meta.read_text(encoding="utf-8"))
            except Exception:
                continue
            files = payload.get("files") or {}
            yarns.append({
                "id": payload.get("id") or meta.parent.name,
                "label": payload.get("label"),
                "createdAt": payload.get("createdAt"),
                "thumbnail": files.get("thumbnail"),
                "widthPx": (payload.get("width") or {}).get("px"),
                "widthMm": (payload.get("width") or {}).get("mm"),
                "lengthPx": (payload.get("length") or {}).get("px"),
                "lengthMm": (payload.get("length") or {}).get("mm"),
                "dpi": payload.get("dpi"),
            })
        yarns.sort(key=lambda y: y.get("createdAt") or "", reverse=True)

    enriched = []
    for entry in yarns:
        yarn_id = entry.get("id")
        if not yarn_id or not _LIBRARY_ID_RE.match(str(yarn_id)):
            continue
        thumb = entry.get("thumbnail")
        enriched.append({
            **entry,
            "thumbnailUrl": f"/api/yarn/library/{yarn_id}/files/{thumb}" if thumb else None,
        })
    return enriched


def get_library_yarn_file_path(yarn_id: str, filename: str) -> Path | None:
    yarn_dir = _library_dir(yarn_id)
    if yarn_dir is None:
        return None
    candidate = (yarn_dir / filename).resolve()
    try:
        candidate.relative_to(yarn_dir)
    except ValueError:
        return None
    if not candidate.exists() or not candidate.is_file():
        return None
    return candidate


def _split_rgba(rgba_path: Path, albedo_path: Path, alpha_path: Path) -> None:
    """Write the RGB channels of `rgba_path` to `albedo_path` (sRGB) and the
    alpha channel to `alpha_path` (single-channel L, will be loaded as
    Non-Color in Blender)."""
    with Image.open(rgba_path) as im:
        rgba = im.convert("RGBA")
        rgb = rgba.convert("RGB")
        alpha = rgba.split()[-1]
    rgb.save(albedo_path)
    alpha.save(alpha_path)


def _ensure_cycles_safe_texture(src_path: Path, output_dir: Path) -> Path:
    """If src is already ≤ MAX_CYCLES_TEXTURE_DIMENSION on every axis return it
    unchanged. Otherwise produce `<output_dir>/<stem>_max<N><suffix>` and
    return that path. The downscale preserves aspect ratio."""
    with Image.open(src_path) as image:
        width, height = image.size
        if max(width, height) <= MAX_CYCLES_TEXTURE_DIMENSION:
            return src_path

        output_dir.mkdir(parents=True, exist_ok=True)
        scale = MAX_CYCLES_TEXTURE_DIMENSION / max(width, height)
        resized_size = (
            max(1, int(round(width * scale))),
            max(1, int(round(height * scale))),
        )
        output_path = output_dir / f"{src_path.stem}_max{MAX_CYCLES_TEXTURE_DIMENSION}{src_path.suffix}"
        if not output_path.exists():
            image.resize(resized_size, Image.LANCZOS).save(output_path)
        return output_path


def _tile_bounds(width: int, tile_count: int) -> list[tuple[int, int]]:
    return [
        (round(index * width / tile_count), round((index + 1) * width / tile_count))
        for index in range(tile_count)
    ]


def ensure_cycles_tiled_texture_set(
    diffuse_path: Path,
    alpha_path: Path,
    output_dir: Path,
    *,
    max_dimension: int = MAX_CYCLES_TEXTURE_DIMENSION,
) -> dict | None:
    """Split over-wide yarn strips into full-resolution UDIM U tiles.

    Cycles cannot upload one image wider than the device cap, but it can sample
    multiple legal UDIM tiles as one logical texture. The current yarn scans are
    long horizontal strips, so this first pass slices only along U.
    """
    if max_dimension <= 0:
        return None

    with Image.open(diffuse_path) as diffuse_image, Image.open(alpha_path) as alpha_image:
        if diffuse_image.size != alpha_image.size:
            return None

        width, height = diffuse_image.size
        if max(width, height) <= max_dimension:
            return None
        if height > max_dimension:
            return None

        tile_count = (width + max_dimension - 1) // max_dimension
        # UDIMs run 1001..1010 across U before advancing to the next V row. Keep
        # this yarn-strip path horizontal so the shader can stay simple.
        if tile_count < 2 or tile_count > 10:
            return None

        output_dir.mkdir(parents=True, exist_ok=True)
        diffuse_tiles: list[Path] = []
        alpha_tiles: list[Path] = []
        tile_widths: list[int] = []

        for index, (left, right) in enumerate(_tile_bounds(width, tile_count)):
            udim = 1001 + index
            diffuse_tile = output_dir / f"{diffuse_path.stem}_{udim}{diffuse_path.suffix}"
            alpha_tile = output_dir / f"{alpha_path.stem}_{udim}{alpha_path.suffix}"
            tile_widths.append(right - left)
            if not diffuse_tile.exists():
                diffuse_image.crop((left, 0, right, height)).save(diffuse_tile)
            if not alpha_tile.exists():
                alpha_image.crop((left, 0, right, height)).save(alpha_tile)
            diffuse_tiles.append(diffuse_tile)
            alpha_tiles.append(alpha_tile)

    return {
        "tile_count": tile_count,
        "tile_width_px": max(tile_widths),
        "tile_height_px": height,
        "diffuse_pattern": output_dir / f"{diffuse_path.stem}_<UDIM>{diffuse_path.suffix}",
        "diffuse_paths": diffuse_tiles,
        "alpha_pattern": output_dir / f"{alpha_path.stem}_<UDIM>{alpha_path.suffix}",
        "alpha_paths": alpha_tiles,
    }


def _build_band_meta_from_library(metadata: dict) -> dict:
    """Shape the library metadata.json into the bandMeta dict the render
    pipeline reads. The pre-computed `blender` block (added by yarnseamless's
    yarn_library.py) is the source of truth — everything else here is for
    UI/debug only."""
    image_size = metadata.get("image_size_px") or []
    return {
        "name": metadata.get("label") or metadata.get("id"),
        "library_yarn_id": metadata.get("id"),
        "schemaVersion": metadata.get("schemaVersion", 1),
        "image_size_px": image_size,
        "dpi": metadata.get("dpi"),
        "width": metadata.get("width") or {},
        "length": metadata.get("length") or {},
        "bands_px": metadata.get("bands_px") or {},
        "bands_v_norm": metadata.get("bands_v_norm") or {},
        "thickness_px": metadata.get("thickness_px") or {},
        "params": metadata.get("params") or {},
        # The Blender-ready, pre-computed values. Phase 2's render_jobs.py
        # pushes these directly to Parametric Weave knotty sockets.
        "blender": metadata.get("blender") or {},
    }


def delete_library_yarn(yarn_id: str) -> dict:
    """Remove `<library>/<yarn_id>/` and its index.json entry, AND cascade-delete
    every imported runtime YarnAsset that came from this library id (matched by
    `bandMeta.library_yarn_id`). Pattern Builder reads runtime assets, so without
    the cascade the deleted yarn would still appear in Step 2 dropdowns.
    Idempotent — returns `removed=False` and `removedAssetIds=[]` for unknown
    ids rather than raising."""
    from .yarnseamless import yarn_library as _yl

    library_root = YARN_LIBRARY_ROOT
    library_removed = False
    if library_root.exists():
        try:
            library_removed = _yl.delete_yarn(library_root, yarn_id)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc

    load_yarn_assets()
    with _LOCK:
        cascade_ids = [
            asset.id
            for asset in _ASSETS.values()
            if (asset.bandMeta or {}).get("library_yarn_id") == yarn_id
        ]
    for asset_id in cascade_ids:
        try:
            delete_yarn_asset(asset_id)
        except FileNotFoundError:
            pass

    return {
        "id": yarn_id,
        "removed": bool(library_removed) or bool(cascade_ids),
        "removedAssetIds": cascade_ids,
    }


def import_yarn_from_library(yarn_id: str) -> dict:
    """Copy `<library>/<yarn_id>/rgba.png` into this project's runtime, split
    into albedo+alpha, produce Cycles-safe downscales, and persist a runtime
    YarnAsset with bandMeta wired up. Returns the asset's dict."""
    ensure_runtime_dirs()
    load_yarn_assets()
    yarn_dir = _library_dir(yarn_id)
    if yarn_dir is None:
        raise FileNotFoundError(f"library yarn not found: {yarn_id}")

    meta_path = yarn_dir / "metadata.json"
    if not meta_path.exists():
        raise FileNotFoundError(f"metadata.json missing for {yarn_id}")
    metadata = json.loads(meta_path.read_text(encoding="utf-8"))
    rgba_src = yarn_dir / (metadata.get("files", {}).get("rgba") or "rgba.png")
    if not rgba_src.exists():
        raise FileNotFoundError(f"rgba.png missing for {yarn_id}")

    asset_id = uuid.uuid4().hex[:12]
    destination_dir = _asset_dir(asset_id)
    destination_dir.mkdir(parents=True, exist_ok=True)

    # Provenance copy — keep the library RGBA in the runtime asset folder.
    source_name = "rgba.png"
    shutil.copy2(rgba_src, destination_dir / source_name)

    albedo_path = destination_dir / "albedo.png"
    alpha_path = destination_dir / "alpha.png"
    _split_rgba(destination_dir / source_name, albedo_path, alpha_path)

    cycles_dir = destination_dir / "cycles_safe"
    render_diffuse_path = _ensure_cycles_safe_texture(albedo_path, cycles_dir)
    render_alpha_path = _ensure_cycles_safe_texture(alpha_path, cycles_dir)
    tiled = ensure_cycles_tiled_texture_set(
        albedo_path,
        alpha_path,
        destination_dir / "cycles_tiled",
    )

    band_meta = _build_band_meta_from_library(metadata)
    label = metadata.get("label") or yarn_id

    asset = YarnAsset(
        id=asset_id,
        label=label,
        status="ready",
        sourceFilename=source_name,
        sourceUrl="",
        diffuseFilename=_relative_asset_path(asset_id, albedo_path),
        alphaFilename=_relative_asset_path(asset_id, alpha_path),
        renderDiffuseFilename=_relative_asset_path(asset_id, render_diffuse_path),
        renderAlphaFilename=_relative_asset_path(asset_id, render_alpha_path),
        renderTextureMode="tiled" if tiled else "single",
        renderDiffuseTilePattern=_relative_asset_path(asset_id, tiled.get("diffuse_pattern")) if tiled else None,
        renderDiffuseTileFilenames=[
            _relative_asset_path(asset_id, path) or ""
            for path in (tiled.get("diffuse_paths") if tiled else [])
        ],
        renderAlphaTilePattern=_relative_asset_path(asset_id, tiled.get("alpha_pattern")) if tiled else None,
        renderAlphaTileFilenames=[
            _relative_asset_path(asset_id, path) or ""
            for path in (tiled.get("alpha_paths") if tiled else [])
        ],
        renderTileCount=int(tiled.get("tile_count")) if tiled else None,
        renderTileWidthPx=int(tiled.get("tile_width_px")) if tiled else None,
        renderTileHeightPx=int(tiled.get("tile_height_px")) if tiled else None,
        bandMeta=band_meta,
        createdAt=_utc_now(),
        updatedAt=_utc_now(),
    )
    _refresh_asset_urls(asset)
    _persist_asset(asset)
    with _LOCK:
        _ASSETS[asset_id] = asset

    return asset.to_dict()
