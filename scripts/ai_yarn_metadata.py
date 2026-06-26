#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.ai_yarn_metadata import (  # noqa: E402
    refresh_all_existing_ai_yarns,
    refresh_existing_ai_yarn_metadata,
    save_ai_yarn_to_library,
)
from app.runtime_paths import YARN_LIBRARY_ROOT  # noqa: E402
from app.yarn_assets import import_yarn_from_library, sync_imported_yarn_band_meta  # noqa: E402


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"}


def _image_paths_from_source(source: Path) -> list[Path]:
    if source.is_file() and source.suffix.lower() in IMAGE_SUFFIXES:
        return [source]
    if source.is_dir():
        return [
            path
            for path in sorted(source.iterdir())
            if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
        ]
    return []


def _matching_measurements(image_path: Path) -> Path | None:
    same_stem = image_path.with_suffix(".json")
    if same_stem.exists():
        return same_stem
    measurements = image_path.parent / "measurements.json"
    if measurements.exists():
        return measurements
    return None


def _command_import(args: argparse.Namespace) -> dict:
    sources = [Path(value).expanduser().resolve() for value in args.sources]
    image_paths: list[Path] = []
    for source in sources:
        image_paths.extend(_image_paths_from_source(source))
    if not image_paths:
        raise SystemExit("No image files found.")

    results = []
    for index, image_path in enumerate(image_paths, start=1):
        label = args.label or image_path.stem
        if len(image_paths) > 1 and args.label:
            label = f"{args.label} {index:02d}"
        saved = save_ai_yarn_to_library(
            image_path,
            measurements_path=_matching_measurements(image_path),
            label=label,
            library_root=YARN_LIBRARY_ROOT,
            sync_runtime=False,
            external_corrected_dir=image_path.parent / "corrected_metadata",
        )
        asset = import_yarn_from_library(saved["id"]) if args.import_runtime else None
        metadata = saved.get("metadata") or {}
        blender = metadata.get("blender") or {}
        results.append({
            "id": saved.get("id"),
            "label": saved.get("label"),
            "source": str(image_path),
            "metadataPath": saved.get("metadataPath"),
            "externalCorrectedMetadataPath": saved.get("externalCorrectedMetadataPath"),
            "runtimeAssetId": asset.get("id") if asset else None,
            "bands_px": metadata.get("bands_px"),
            "textureScaleU": blender.get("texture_scale_u"),
            "textureScaleUStrategy": blender.get("texture_scale_u_strategy"),
        })
    return {"ok": True, "count": len(results), "results": results}


def _command_refresh(args: argparse.Namespace) -> dict:
    if args.yarn_ids:
        raw_results = [
            refresh_existing_ai_yarn_metadata(
                yarn_id,
                library_root=YARN_LIBRARY_ROOT,
                sync_runtime=False,
            )
            for yarn_id in args.yarn_ids
        ]
    else:
        payload = refresh_all_existing_ai_yarns(
            library_root=YARN_LIBRARY_ROOT,
            sync_runtime=False,
        )
        raw_results = list(payload.get("results") or [])

    results = []
    for result in raw_results:
        metadata = result.get("metadata") or {}
        runtime_ids = (
            sync_imported_yarn_band_meta(result.get("id"), metadata)
            if args.sync_runtime
            else []
        )
        results.append({
            "id": result.get("id"),
            "label": result.get("label"),
            "metadataPath": result.get("metadataPath"),
            "externalCorrectedMetadataPath": result.get("externalCorrectedMetadataPath"),
            "updatedRuntimeAssetIds": runtime_ids,
            "previousTextureScaleU": result.get("previousTextureScaleU"),
            "textureScaleU": result.get("textureScaleU"),
            "textureScaleUStrategy": result.get("textureScaleUStrategy"),
        })
    return {"ok": True, "count": len(results), "results": results}


def main() -> None:
    parser = argparse.ArgumentParser(description="AI yarn metadata importer/refresher.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    import_parser = subparsers.add_parser("import", help="Import AI image files/folders into yarn_library.")
    import_parser.add_argument("sources", nargs="+", help="Image file(s) or folder(s).")
    import_parser.add_argument("--label", help="Label or label prefix.")
    import_parser.add_argument("--import-runtime", action="store_true", help="Also import each new library yarn as a runtime asset.")
    import_parser.set_defaults(func=_command_import)

    refresh_parser = subparsers.add_parser("refresh-u-scale", help="Refresh existing AI yarn metadata U scale.")
    refresh_parser.add_argument("yarn_ids", nargs="*", help="Specific library yarn IDs. Omit to refresh all AI yarns.")
    refresh_parser.add_argument("--no-sync-runtime", dest="sync_runtime", action="store_false", help="Do not update existing runtime asset bandMeta.")
    refresh_parser.set_defaults(sync_runtime=True, func=_command_refresh)

    args = parser.parse_args()
    result = args.func(args)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
