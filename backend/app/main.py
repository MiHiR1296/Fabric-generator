from __future__ import annotations

from dataclasses import dataclass

try:
    from fastapi import FastAPI, File, HTTPException, UploadFile
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import FileResponse
    from pydantic import BaseModel
except ImportError as exc:  # pragma: no cover - exercised through setup docs instead.
    FastAPI = None
    UploadFile = None
    File = None
    HTTPException = RuntimeError
    BaseModel = object
    IMPORT_ERROR = exc
else:
    IMPORT_ERROR = None

from .service import parse_file_bytes
from .text_parser import parse_text_payload
from .blender_sync import load_blender_socket_config, send_blender_command, sync_draft_to_blender
from .render_jobs import (
    get_render_image_path,
    get_render_job,
    load_headless_blender_config,
    submit_project_render_job,
    submit_render_job,
)
from .yarn_assets import (
    create_yarn_assets,
    delete_yarn_asset,
    get_yarn_asset,
    get_yarn_asset_file_path,
    list_yarn_assets,
    retry_yarn_asset,
)


if FastAPI is not None:
    app = FastAPI(title="One-Point Fabric Studio Backend", version="0.2.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    class TextParseRequest(BaseModel):
        text: str


    class BlenderSyncRequest(BaseModel):
        draft: dict
        target_object_name: str = "ParametricWeave"
        draft_object_name: str = "WebDraft_Live"


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
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


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


    @app.post("/api/yarn/assets")
    async def upload_yarn_assets(files: list[UploadFile] = File(...)):
        if not files:
            raise HTTPException(status_code=400, detail="Upload at least one yarn image.")
        try:
            payload = []
            for file in files:
                payload.append((file.filename or "upload.png", await file.read()))
            return create_yarn_assets(payload)
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
    async def retry_asset(asset_id: str):
        try:
            return retry_yarn_asset(asset_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Yarn asset not found.") from exc
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


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
