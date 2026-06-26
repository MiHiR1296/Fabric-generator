from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import uuid

try:
    from fastapi import FastAPI, File, Form, HTTPException, UploadFile
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import FileResponse, JSONResponse
    from pydantic import BaseModel
except ImportError as exc:  # pragma: no cover - exercised through setup docs instead.
    FastAPI = None
    UploadFile = None
    File = None
    Form = None
    HTTPException = RuntimeError
    JSONResponse = None
    BaseModel = object
    IMPORT_ERROR = exc
else:
    IMPORT_ERROR = None

from .service import parse_file_bytes
from .text_parser import parse_text_payload
from .blender_live import build_material_asset_entry, push_bandmeta_to_live_blender
from .blender_sync import load_blender_socket_config, send_blender_command, sync_draft_to_blender
from .fabric_project import normalize_color_bindings, validate_project_bindings
from .hook_sync import sync_hook_to_blender
from .ai_yarn_metadata import (
    refresh_all_existing_ai_yarns,
    refresh_existing_ai_yarn_metadata,
    save_ai_yarn_to_library,
)
from .render_jobs import (
    build_headless_render_script,
    build_project_material_payloads,
    get_render_image_path,
    get_render_job,
    get_tile_source_image_path,
    load_headless_blender_config,
    submit_project_render_job,
    submit_project_tile_render_job,
    submit_hook_project_render_job,
    submit_render_job,
    sync_hook_project_to_live_blender,
)
from .yarn_assets import (
    create_yarn_assets,
    delete_library_yarn,
    delete_yarn_asset,
    get_pbr_migration_job,
    get_library_yarn_file_path,
    get_ready_yarn_assets_lookup,
    get_yarn_asset,
    get_yarn_asset_file_path,
    import_yarn_from_library,
    list_library_yarns,
    list_yarn_assets,
    migrate_pbr_assets,
    regenerate_asset_pbr,
    retry_yarn_asset,
    sync_imported_yarn_band_meta,
)
from .runtime_paths import RUNTIME_ROOT, YARN_LIBRARY_ROOT
from .tryon_render import (
    get_tryon_batch,
    public_targets as list_tryon_targets,
    resolve_source_image,
    submit_tryon_render_batch,
    tryon_blend_file,
)
from .yarn_pbr import PbrPreflightError


if FastAPI is not None:
    from . import yarnseamless_routes  # yarn processing FastAPI router (Phase 2b)

    app = FastAPI(title="One-Point Fabric Studio Backend", version="0.2.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(yarnseamless_routes.router)

    class TextParseRequest(BaseModel):
        text: str


    class BlenderSyncRequest(BaseModel):
        draft: dict
        target_object_name: str = "ParametricWeave"
        draft_object_name: str = "WebDraft_Live"


    class HookSyncRequest(BaseModel):
        pattern: dict
        target_object_name: str = "ProceduralHook"
        draft_object_name: str = "HookDraft_Live"


    class BlenderRenderRequest(BaseModel):
        draft: dict
        target_object_name: str = "ParametricWeave"
        draft_object_name: str = "WebDraft_Live"


    class ProjectRenderRequest(BaseModel):
        draft: dict
        yarnAssets: list[dict] = []
        colorBindings: list[dict] = []
        target_object_name: str = "ParametricWeave"
        draft_object_name: str = "WebDraft_Live"


    class HookProjectRenderRequest(BaseModel):
        pattern: dict
        yarnAssets: list[dict] = []
        materialBindings: list[dict] = []
        target_object_name: str = "ProceduralHook"
        draft_object_name: str = "HookDraft_Live"


    class ProjectTileRenderRequest(ProjectRenderRequest):
        tileCount: int = 4
        tileResolution: int = 1200
        guardThreads: int = 0
        variationStrength: float = 0.0


    class PushBandMetaRequest(BaseModel):
        yarnAssetIds: list[str] = []
        target_object_name: str = "ParametricWeave"
        modifier_name: str = "Weave"


    class PushProjectBandMetaRequest(BaseModel):
        draft: dict
        colorBindings: list[dict] = []
        target_object_name: str = "ParametricWeave"
        modifier_name: str = "Weave"


    class TryonRenderRequest(BaseModel):
        targetIds: list[str] = []
        sourceJobId: str
        resolution: Optional[int] = None
        samples: Optional[int] = None


    class PbrMigrationRequest(BaseModel):
        assetIds: Optional[list[str]] = None


    class AiYarnRefreshRequest(BaseModel):
        yarnIds: list[str] = []


    def _pbr_preflight_response(exc: PbrPreflightError):
        return JSONResponse(status_code=409, content=exc.to_response())


    def _is_image_upload(filename: str) -> bool:
        return Path(filename).suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"}


    def _is_json_upload(filename: str) -> bool:
        return Path(filename).suffix.lower() == ".json"


    def _minimal_ai_measurements(image_path: Path, dpi: float) -> dict:
        from PIL import Image

        with Image.open(image_path) as image:
            width, height = image.size
        return {
            "dpi": dpi,
            "image_size_px": [width, height],
            "orientation": "horizontal",
            "length": {
                "px": width,
                "mm": round(width / dpi * 25.4, 4) if dpi > 0 else None,
                "description": "Left-to-right of the AI source image.",
            },
        }


    @app.get("/api/parser/health")
    async def health():
        return {"status": "ok"}


    @app.get("/api/blender/health")
    async def blender_health():
        headless = load_headless_blender_config()
        config = load_blender_socket_config()
        response = send_blender_command("get_scene_info")
        return {
            "status": "ok",
            "headless": {
                "blender_binary": str(headless.blender_binary),
                "blend_file": str(headless.blend_file),
                "runtime_root": str(headless.runtime_root),
                "blender_binary_exists": headless.blender_binary.exists(),
                "blend_file_exists": headless.blend_file.exists(),
            },
            "bridge": {
                "host": config.host,
                "port": config.port,
                "timeout_seconds": config.timeout_seconds,
                "available": response.get("status") == "success",
            },
            "scene": response.get("result", {}) if response.get("status") == "success" else None,
            "bridge_error": None if response.get("status") == "success" else response.get("message"),
        }


    @app.post("/api/parser/parse-file")
    async def parse_file(file: UploadFile = File(...)):
        try:
            payload = await file.read()
            document = parse_file_bytes(payload, file.filename or "upload")
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return document.to_dict()


    @app.post("/api/blender/sync-draft")
    async def sync_draft(request: BlenderSyncRequest):
        try:
            response = sync_draft_to_blender(
                request.draft,
                target_object_name=request.target_object_name,
                draft_object_name=request.draft_object_name,
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return response


    @app.post("/api/blender/sync-hook")
    async def sync_hook(request: HookSyncRequest):
        try:
            response = sync_hook_to_blender(
                request.pattern,
                target_object_name=request.target_object_name,
                draft_object_name=request.draft_object_name,
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return response


    @app.post("/api/blender/render-draft")
    async def render_draft(request: BlenderRenderRequest):
        try:
            return submit_render_job(
                request.draft,
                target_object_name=request.target_object_name,
                draft_object_name=request.draft_object_name,
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


    @app.post("/api/blender/render-project")
    async def render_project(request: ProjectRenderRequest):
        try:
            return submit_project_render_job(
                {
                    "draft": request.draft,
                    "yarnAssets": request.yarnAssets,
                    "colorBindings": request.colorBindings,
                },
                target_object_name=request.target_object_name,
                draft_object_name=request.draft_object_name,
            )
        except PbrPreflightError as exc:
            return _pbr_preflight_response(exc)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


    @app.post("/api/blender/render-hook-project")
    async def render_hook_project(request: HookProjectRenderRequest):
        try:
            return submit_hook_project_render_job(
                {
                    "pattern": request.pattern,
                    "yarnAssets": request.yarnAssets,
                    "materialBindings": request.materialBindings,
                },
                target_object_name=request.target_object_name,
                draft_object_name=request.draft_object_name,
            )
        except PbrPreflightError as exc:
            return _pbr_preflight_response(exc)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


    @app.post("/api/blender/sync-hook-project")
    async def sync_hook_project(request: HookProjectRenderRequest):
        try:
            return sync_hook_project_to_live_blender(
                {
                    "pattern": request.pattern,
                    "yarnAssets": request.yarnAssets,
                    "materialBindings": request.materialBindings,
                },
                target_object_name=request.target_object_name,
                draft_object_name=request.draft_object_name,
            )
        except PbrPreflightError as exc:
            return _pbr_preflight_response(exc)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


    @app.post("/api/blender/render-project-tiles")
    async def render_project_tiles(request: ProjectTileRenderRequest):
        try:
            return submit_project_tile_render_job(
                {
                    "draft": request.draft,
                    "yarnAssets": request.yarnAssets,
                    "colorBindings": request.colorBindings,
                },
                tile_options={
                    "tileCount": request.tileCount,
                    "tileResolution": request.tileResolution,
                    "guardThreads": request.guardThreads,
                    "variationStrength": request.variationStrength,
                },
                target_object_name=request.target_object_name,
                draft_object_name=request.draft_object_name,
            )
        except PbrPreflightError as exc:
            return _pbr_preflight_response(exc)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


    @app.post("/api/blender/push-bandmeta")
    async def push_bandmeta(request: PushBandMetaRequest):
        lookup = get_ready_yarn_assets_lookup()
        if request.yarnAssetIds:
            ordered_assets = []
            for asset_id in request.yarnAssetIds:
                asset = lookup.get(asset_id)
                if asset is None:
                    raise HTTPException(status_code=404, detail=f"Yarn asset not ready: {asset_id}")
                ordered_assets.append(asset)
        else:
            ordered_assets = list(lookup.values())
        if not ordered_assets:
            raise HTTPException(status_code=400, detail="No ready yarn assets to push.")
        try:
            _atlas_entries, material_assets = build_project_material_payloads(ordered_assets)
        except PbrPreflightError as exc:
            return _pbr_preflight_response(exc)
        response = push_bandmeta_to_live_blender(
            material_assets,
            target_object_name=request.target_object_name,
            modifier_name=request.modifier_name,
        )
        if response.get("status") != "success":
            raise HTTPException(status_code=502, detail=response)
        return {
            "status": "ok",
            "pushed": len(material_assets),
            "target": request.target_object_name,
            "modifier": request.modifier_name,
            "assets": [{"id": entry["id"], "label": entry["label"]} for entry in material_assets],
            "blender": response.get("result"),
        }


    @app.post("/api/blender/push-project-bandmeta")
    async def push_project_bandmeta(request: PushProjectBandMetaRequest):
        # Phase 3f: live push from Pattern Builder. Uses the SAME slot ordering
        # rule as render-project (validate_project_bindings → ordered_assets)
        # so Material N here lines up with Material N at render time. Empty or
        # partial bindings return 400 — the frontend gates on
        # `allBindingsAssigned` already, so this is a safety net for stale UIs.
        bindings = normalize_color_bindings(request.colorBindings)
        lookup = get_ready_yarn_assets_lookup()
        try:
            _bindings, _warp_ids, _weft_ids, ordered_assets = validate_project_bindings(
                request.draft, bindings, lookup,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not ordered_assets:
            raise HTTPException(status_code=400, detail="No ready yarn assets to push.")
        try:
            _atlas_entries, material_assets = build_project_material_payloads(ordered_assets)
        except PbrPreflightError as exc:
            return _pbr_preflight_response(exc)
        script = build_headless_render_script(
            request.draft,
            render_path="/tmp/fabric-studio-live-setup.png",
            target_object_name=request.target_object_name,
            warp_material_ids=_warp_ids,
            weft_material_ids=_weft_ids,
            material_assets=material_assets,
            weave_modifier_name=request.modifier_name,
            render_still=False,
        )
        response = send_blender_command("execute_code", {"code": script})
        if response.get("status") != "success":
            raise HTTPException(status_code=502, detail=response)
        return {
            "status": "ok",
            "pushed": len(material_assets),
            "target": request.target_object_name,
            "modifier": request.modifier_name,
            "warpMaterialIds": _warp_ids,
            "weftMaterialIds": _weft_ids,
            "assets": [{"id": entry["id"], "label": entry["label"]} for entry in material_assets],
            "blender": response.get("result"),
        }


    @app.get("/api/blender/render-jobs/{job_id}")
    async def render_job_status(job_id: str):
        snapshot = get_render_job(job_id)
        if snapshot is None:
            raise HTTPException(status_code=404, detail="Render job not found.")
        return snapshot


    @app.get("/api/blender/render-jobs/{job_id}/image")
    async def render_job_image(job_id: str):
        image_path = get_render_image_path(job_id)
        if image_path is None:
            raise HTTPException(status_code=404, detail="Render image not found.")
        return FileResponse(image_path, media_type="image/png", filename=f"{job_id}.png")


    @app.get("/api/blender/tryon/targets")
    async def tryon_targets():
        return {
            "targets": list_tryon_targets(),
            "blendFileExists": tryon_blend_file().exists(),
        }


    @app.post("/api/blender/tryon/render")
    async def tryon_render(request: TryonRenderRequest):
        if not request.targetIds:
            raise HTTPException(status_code=400, detail="Select at least one object to render.")
        try:
            source_image = resolve_source_image(request.sourceJobId)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        try:
            return submit_tryon_render_batch(
                request.targetIds,
                source_image_path=source_image,
                resolution=request.resolution,
                samples=request.samples,
            )
        except FileNotFoundError as exc:
            # Blender binary or Objects.blend missing.
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


    @app.get("/api/blender/tryon/batches/{batch_id}")
    async def tryon_batch(batch_id: str):
        snapshot = get_tryon_batch(batch_id)
        if snapshot is None:
            raise HTTPException(status_code=404, detail="Try-On batch not found.")
        return snapshot


    @app.get("/api/blender/render-jobs/{job_id}/tile-sources/{source_index}")
    async def render_job_tile_source(job_id: str, source_index: int):
        image_path = get_tile_source_image_path(job_id, source_index)
        if image_path is None:
            raise HTTPException(status_code=404, detail="Tile source image not found.")
        return FileResponse(image_path, media_type="image/png", filename=f"{job_id}_source_{source_index}.png")


    @app.post("/api/parser/parse-text")
    async def parse_text(request: TextParseRequest):
        try:
            document = parse_text_payload(request.text)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return document.to_dict()


    @app.get("/api/yarn/assets")
    async def yarn_assets():
        return list_yarn_assets()


    @app.get("/api/yarn/library")
    async def yarn_library_list():
        return {"yarns": list_library_yarns()}


    @app.post("/api/yarn/ai/import")
    async def yarn_ai_import(
        files: list[UploadFile] = File(...),
        dpi: float = Form(1600.0),
        labelPrefix: str = Form("AI Yarn"),
        importRuntime: bool = Form(True),
    ):
        if not files:
            raise HTTPException(status_code=400, detail="Upload at least one AI yarn image.")
        session_dir = RUNTIME_ROOT / "ai_yarn_uploads" / uuid.uuid4().hex[:12]
        session_dir.mkdir(parents=True, exist_ok=True)

        saved_paths: list[Path] = []
        for index, upload in enumerate(files):
            source_name = Path(upload.filename or f"upload-{index}").name
            if not source_name:
                source_name = f"upload-{index}"
            destination = session_dir / f"{index:02d}_{source_name}"
            payload = await upload.read()
            destination.write_bytes(payload)
            saved_paths.append(destination)

        image_paths = [path for path in saved_paths if _is_image_upload(path.name)]
        json_paths = [path for path in saved_paths if _is_json_upload(path.name)]
        if not image_paths:
            raise HTTPException(status_code=400, detail="Upload at least one image file.")

        json_by_stem = {path.stem: path for path in json_paths}
        single_json = json_paths[0] if len(json_paths) == 1 else None
        imported_assets = []
        entries = []

        for index, image_path in enumerate(image_paths, start=1):
            measurement_path = json_by_stem.get(image_path.stem)
            if measurement_path is None and single_json is not None and len(image_paths) == 1:
                measurement_path = single_json
            measurements = None
            if measurement_path is None:
                measurements = _minimal_ai_measurements(image_path, dpi)

            label = labelPrefix.strip() or "AI Yarn"
            if len(image_paths) > 1:
                label = f"{label} {index:02d}"

            try:
                saved = save_ai_yarn_to_library(
                    image_path,
                    measurements_path=measurement_path,
                    measurements=measurements,
                    label=label,
                    library_root=YARN_LIBRARY_ROOT,
                    sync_runtime=False,
                    external_corrected_dir=session_dir / "corrected_metadata",
                )
                asset = import_yarn_from_library(saved["id"]) if importRuntime else None
            except Exception as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

            metadata = saved.get("metadata") or {}
            blender = metadata.get("blender") or {}
            entry = {
                "id": saved.get("id"),
                "label": saved.get("label"),
                "libraryPath": saved.get("libraryPath"),
                "metadataPath": saved.get("metadataPath"),
                "externalCorrectedMetadataPath": saved.get("externalCorrectedMetadataPath"),
                "runtimeAssetId": asset.get("id") if asset else None,
                "width": metadata.get("width"),
                "bands_px": metadata.get("bands_px"),
                "textureScaleU": blender.get("texture_scale_u"),
                "textureScaleUStrategy": blender.get("texture_scale_u_strategy"),
            }
            entries.append(entry)
            if asset:
                imported_assets.append(asset)

        return {
            "ok": True,
            "sessionDir": str(session_dir),
            "entries": entries,
            "assets": imported_assets,
        }


    @app.post("/api/yarn/ai/refresh-u-scale")
    async def yarn_ai_refresh_u_scale(request: AiYarnRefreshRequest):
        try:
            if request.yarnIds:
                results = [
                    refresh_existing_ai_yarn_metadata(
                        yarn_id,
                        library_root=YARN_LIBRARY_ROOT,
                        sync_runtime=False,
                    )
                    for yarn_id in request.yarnIds
                ]
            else:
                payload = refresh_all_existing_ai_yarns(
                    library_root=YARN_LIBRARY_ROOT,
                    sync_runtime=False,
                )
                results = list(payload.get("results") or [])
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

        summaries = []
        for result in results:
            metadata = result.get("metadata") or {}
            updated_runtime_ids = sync_imported_yarn_band_meta(result.get("id"), metadata)
            summaries.append({
                "id": result.get("id"),
                "label": result.get("label"),
                "metadataPath": result.get("metadataPath"),
                "externalCorrectedMetadataPath": result.get("externalCorrectedMetadataPath"),
                "updatedRuntimeAssetIds": updated_runtime_ids,
                "previousTextureScaleU": result.get("previousTextureScaleU"),
                "textureScaleU": result.get("textureScaleU"),
                "textureScaleUStrategy": result.get("textureScaleUStrategy"),
                "width": metadata.get("width"),
                "bands_px": metadata.get("bands_px"),
            })
        return {
            "ok": True,
            "count": len(summaries),
            "results": summaries,
        }


    @app.get("/api/yarn/library/{yarn_id}/files/{filename:path}")
    async def yarn_library_file(yarn_id: str, filename: str):
        file_path = get_library_yarn_file_path(yarn_id, filename)
        if file_path is None:
            raise HTTPException(status_code=404, detail="Library file not found.")
        suffix = file_path.suffix.lower()
        media_type = "image/png"
        if suffix in {".jpg", ".jpeg"}:
            media_type = "image/jpeg"
        elif suffix == ".webp":
            media_type = "image/webp"
        elif suffix == ".json":
            media_type = "application/json"
        return FileResponse(file_path, media_type=media_type, filename=file_path.name)


    @app.post("/api/yarn/library/{yarn_id}/import")
    async def yarn_library_import(yarn_id: str):
        try:
            return import_yarn_from_library(yarn_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


    @app.delete("/api/yarn/library/{yarn_id}")
    async def yarn_library_delete(yarn_id: str):
        try:
            return delete_library_yarn(yarn_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc


    @app.post("/api/yarn/assets")
    async def upload_yarn_assets(
        files: list[UploadFile] = File(...),
        orientation: str = Form("auto"),
    ):
        if not files:
            raise HTTPException(status_code=400, detail="Upload at least one yarn image.")
        if orientation not in ("auto", "horizontal", "vertical"):
            raise HTTPException(status_code=400, detail="Invalid orientation.")
        try:
            payload = []
            for file in files:
                payload.append((file.filename or "upload.png", await file.read()))
            return create_yarn_assets(payload, orientation=orientation)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


    @app.get("/api/yarn/assets/{asset_id}")
    async def yarn_asset_detail(asset_id: str):
        asset = get_yarn_asset(asset_id)
        if asset is None:
            raise HTTPException(status_code=404, detail="Yarn asset not found.")
        return asset.to_dict()


    @app.get("/api/yarn/assets/{asset_id}/files/{filename:path}")
    async def yarn_asset_file(asset_id: str, filename: str):
        file_path = get_yarn_asset_file_path(asset_id, filename)
        if file_path is None:
            raise HTTPException(status_code=404, detail="Yarn asset file not found.")
        suffix = file_path.suffix.lower()
        media_type = "image/png"
        if suffix in {".jpg", ".jpeg"}:
            media_type = "image/jpeg"
        elif suffix == ".webp":
            media_type = "image/webp"
        elif suffix == ".tif" or suffix == ".tiff":
            media_type = "image/tiff"
        return FileResponse(file_path, media_type=media_type, filename=file_path.name)


    @app.post("/api/yarn/assets/{asset_id}/retry")
    async def retry_asset(asset_id: str, orientation: str = Form("auto")):
        if orientation not in ("auto", "horizontal", "vertical"):
            raise HTTPException(status_code=400, detail="Invalid orientation.")
        try:
            return retry_yarn_asset(asset_id, orientation=orientation)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Yarn asset not found.") from exc
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


    @app.post("/api/yarn-assets/{asset_id}/regenerate-pbr")
    async def regenerate_asset_pbr_endpoint(asset_id: str):
        try:
            return regenerate_asset_pbr(asset_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


    @app.post("/api/yarn-assets/migrate-pbr")
    async def migrate_asset_pbr_endpoint(request: PbrMigrationRequest):
        return migrate_pbr_assets(request.assetIds)


    @app.get("/api/yarn-assets/migrate-pbr/{job_id}")
    async def pbr_migration_status(job_id: str):
        job = get_pbr_migration_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="PBR migration job not found.")
        return job


    @app.delete("/api/yarn/assets/{asset_id}")
    async def remove_asset(asset_id: str):
        try:
            delete_yarn_asset(asset_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Yarn asset not found.") from exc
        return {"status": "deleted", "id": asset_id}


def ensure_runtime_requirements():
    if IMPORT_ERROR is not None:
        raise RuntimeError(
            "FastAPI runtime dependencies are not installed. "
            "Install apps/fabric-studio/backend/requirements.txt before starting the backend service."
        ) from IMPORT_ERROR


if __name__ == "__main__":  # pragma: no cover
    ensure_runtime_requirements()
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
