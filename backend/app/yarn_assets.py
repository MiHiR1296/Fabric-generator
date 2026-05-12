from __future__ import annotations

import json
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
from .runtime_paths import YARN_ASSETS_ROOT, ensure_runtime_dirs


VENDOR_ROOT = Path(__file__).resolve().parents[1] / "vendor" / "yarn_pipeline"
if str(VENDOR_ROOT) not in sys.path:
    sys.path.insert(0, str(VENDOR_ROOT))

Image.MAX_IMAGE_PIXELS = None

from band_segmenter import process as segment_yarn_bands  # type: ignore  # noqa: E402
from yarn_pipeline import run_pipeline  # type: ignore  # noqa: E402


_LOCK = threading.Lock()
_ASSETS: dict[str, YarnAsset] = {}
MAX_CYCLES_TEXTURE_DIMENSION = 16384


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


def _relative_asset_path(asset_id: str, path: str | Path | None) -> str | None:
    if path is None:
        return None
    try:
        return str(Path(path).resolve().relative_to(_asset_dir(asset_id).resolve()))
    except ValueError:
        return str(path)


def _ensure_cycles_safe_texture(src_path: Path, output_dir: Path) -> Path:
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
    asset.normalUrl = _build_file_url(asset.id, asset.normalFilename)
    asset.roughnessUrl = _build_file_url(asset.id, asset.roughnessFilename)
    asset.overlayUrl = _build_file_url(asset.id, asset.overlayFilename)
    asset.bandMetaUrl = _build_file_url(asset.id, asset.bandMetaFilename)
    return asset


def load_yarn_assets() -> None:
    ensure_runtime_dirs()
    with _LOCK:
        if _ASSETS:
            return
        for meta_path in sorted(YARN_ASSETS_ROOT.glob("*/asset.json")):
            asset = _refresh_asset_urls(_load_asset_from_disk(meta_path))
            _ASSETS[asset.id] = asset


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


def _process_asset(asset_id: str) -> None:
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
            keep_intermediate=True,
            verbose=False,
        )
        diffuse_path = Path(result["seamless"])
        alpha_path = Path(result["alpha"])
        preprocessed_path = Path(result["preprocessed"]) if result.get("preprocessed") else None
        band_root = processed_dir / "bands"
        band_name = "analysis"
        band_meta = segment_yarn_bands(
            str(diffuse_path),
            str(alpha_path),
            str(band_root),
            name=band_name,
            verbose=False,
        )
        band_output_dir = band_root / band_name
        render_diffuse_path = _ensure_cycles_safe_texture(diffuse_path, processed_dir / "cycles_safe")
        render_alpha_path = _ensure_cycles_safe_texture(alpha_path, processed_dir / "cycles_safe")

        _update_asset(
            asset_id,
            status="ready",
            diffuseFilename=_relative_asset_path(asset_id, diffuse_path),
            alphaFilename=_relative_asset_path(asset_id, alpha_path),
            preprocessedFilename=_relative_asset_path(asset_id, preprocessed_path),
            renderDiffuseFilename=_relative_asset_path(asset_id, render_diffuse_path),
            renderAlphaFilename=_relative_asset_path(asset_id, render_alpha_path),
            normalFilename=_relative_asset_path(asset_id, band_output_dir / "normal.png"),
            roughnessFilename=_relative_asset_path(asset_id, band_output_dir / "roughness.png"),
            overlayFilename=_relative_asset_path(asset_id, band_output_dir / "overlay.png"),
            bandMetaFilename=_relative_asset_path(asset_id, band_output_dir / "meta.json"),
            preprocessMeta=result.get("preprocess_meta") or {},
            alphaMeta=result.get("alpha_meta") or {},
            bandMeta=band_meta,
            error=None,
        )
    except Exception as exc:
        _update_asset(asset_id, status="failed", error=str(exc))


def create_yarn_assets(files: list[tuple[str, bytes]]) -> list[dict]:
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
            args=(asset_id,),
            daemon=True,
            name=f"yarn-asset-{asset_id}",
        )
        thread.start()

    return [asset.to_dict() for asset in created]


def retry_yarn_asset(asset_id: str) -> dict:
    asset = get_yarn_asset(asset_id)
    if asset is None:
        raise FileNotFoundError(asset_id)
    thread = threading.Thread(
        target=_process_asset,
        args=(asset_id,),
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
