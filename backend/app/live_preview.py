from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .blender_sync import send_blender_command, validate_drawdown_matrix
from .fabric_project import (
    build_project_snapshot,
    normalize_color_bindings,
    save_project_snapshot,
    validate_project_bindings,
)
from .render_jobs import build_headless_render_script
from .runtime_paths import LIVE_PREVIEW_ROOT, YARN_ASSETS_ROOT, ensure_runtime_dirs
from .yarn_assets import get_ready_yarn_assets_lookup


@dataclass
class BlenderPreview:
    session_id: str
    status: str
    message: str
    target_object_name: str
    draft_object_name: str
    updated_at: str | None = None
    image_path: Path | None = None
    image_url: str | None = None
    width: int | None = None
    height: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "sessionId": self.session_id,
            "status": self.status,
            "message": self.message,
            "targetObjectName": self.target_object_name,
            "draftObjectName": self.draft_object_name,
            "updatedAt": self.updated_at,
            "imageUrl": self.image_url,
            "width": self.width,
            "height": self.height,
        }


_LOCK = threading.Lock()
_PREVIEWS: dict[str, BlenderPreview] = {}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_session_id(value: str | None) -> str:
    raw = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(value or "default")).strip("-")
    return raw or "default"


def update_project_preview(
    project_payload: dict[str, Any],
    *,
    target_object_name: str = "ParametricWeave",
    draft_object_name: str = "WebDraft_Live",
    session_id: str = "default",
    max_size: int = 1400,
) -> dict[str, Any]:
    ensure_runtime_dirs()
    draft = project_payload.get("draft")
    if not isinstance(draft, dict):
        raise ValueError("live-preview requires a draft object.")

    drawdown = validate_drawdown_matrix(draft.get("drawdown"))
    normalized_draft = {
        **draft,
        "drawdown": drawdown,
    }
    bindings = normalize_color_bindings(project_payload.get("colorBindings"))
    assets_lookup = get_ready_yarn_assets_lookup()
    bindings, warp_material_ids, weft_material_ids, ordered_assets = validate_project_bindings(
        normalized_draft,
        bindings,
        assets_lookup,
    )
    if not ordered_assets:
        raise ValueError("At least one ready yarn asset must be assigned before previewing.")
    if len(ordered_assets) > 4:
        raise ValueError(
            "Live Blender preview currently supports up to 4 assigned yarn assets. "
            "Reduce the distinct yarn assignments or use the headless render path for larger previews."
        )

    safe_session_id = _safe_session_id(session_id)
    preview_dir = LIVE_PREVIEW_ROOT / safe_session_id
    preview_dir.mkdir(parents=True, exist_ok=True)
    preview_path = preview_dir / "preview.png"

    material_assets: list[dict[str, Any]] = []
    for asset in ordered_assets:
        if not asset.diffuseFilename or not asset.alphaFilename:
            raise ValueError(f"Yarn asset {asset.label} is missing processed outputs.")
        material_assets.append(
            {
                "id": asset.id,
                "diffuse_path": YARN_ASSETS_ROOT / asset.id / asset.diffuseFilename,
                "alpha_path": YARN_ASSETS_ROOT / asset.id / asset.alphaFilename,
            }
        )

    project_snapshot = build_project_snapshot(normalized_draft, bindings, ordered_assets)
    save_project_snapshot(project_snapshot, preview_dir / "project.json")

    code = build_headless_render_script(
        normalized_draft,
        render_path=preview_path,
        target_object_name=target_object_name,
        draft_object_name=draft_object_name,
        warp_material_ids=warp_material_ids,
        weft_material_ids=weft_material_ids,
        material_assets=material_assets,
        preview_only=True,
    )
    response = send_blender_command("execute_code", {"code": code})
    if response.get("status") != "success":
        raise RuntimeError(response.get("message") or "Blender could not apply the live preview update.")

    screenshot_response = send_blender_command(
        "get_viewport_screenshot",
        {
            "filepath": str(preview_path),
            "format": "PNG",
            "max_size": int(max_size),
        },
    )
    if screenshot_response.get("status") != "success":
        raise RuntimeError(
            screenshot_response.get("message") or "Blender could not capture the camera preview image."
        )
    if not preview_path.exists():
        raise RuntimeError("Blender reported a preview update, but no camera preview image was created.")

    updated_at = _utc_now()
    screenshot_result = screenshot_response.get("result") or {}
    preview = BlenderPreview(
        session_id=safe_session_id,
        status="ready",
        message="Blender camera preview updated.",
        target_object_name=target_object_name,
        draft_object_name=draft_object_name,
        updated_at=updated_at,
        image_path=preview_path,
        image_url=f"/api/blender/live-preview/{safe_session_id}/image?v={updated_at}",
        width=int(screenshot_result.get("width")) if screenshot_result.get("width") is not None else None,
        height=int(screenshot_result.get("height")) if screenshot_result.get("height") is not None else None,
    )

    with _LOCK:
        _PREVIEWS[safe_session_id] = preview

    return preview.to_dict()


def get_preview_snapshot(session_id: str = "default") -> dict[str, Any]:
    safe_session_id = _safe_session_id(session_id)
    with _LOCK:
        preview = _PREVIEWS.get(safe_session_id)
        if preview is not None:
            return preview.to_dict()

    preview_path = LIVE_PREVIEW_ROOT / safe_session_id / "preview.png"
    if preview_path.exists():
        return BlenderPreview(
            session_id=safe_session_id,
            status="ready",
            message="Preview image available.",
            target_object_name="ParametricWeave",
            draft_object_name="WebDraft_Live",
            updated_at=datetime.fromtimestamp(preview_path.stat().st_mtime, tz=timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            image_path=preview_path,
            image_url=f"/api/blender/live-preview/{safe_session_id}/image",
        ).to_dict()

    return BlenderPreview(
        session_id=safe_session_id,
        status="idle",
        message="No Blender preview has been generated yet.",
        target_object_name="ParametricWeave",
        draft_object_name="WebDraft_Live",
    ).to_dict()


def get_preview_image_path(session_id: str = "default") -> Path | None:
    safe_session_id = _safe_session_id(session_id)
    with _LOCK:
        preview = _PREVIEWS.get(safe_session_id)
        if preview is not None and preview.image_path is not None and preview.image_path.exists():
            return preview.image_path

    preview_path = LIVE_PREVIEW_ROOT / safe_session_id / "preview.png"
    if preview_path.exists():
        return preview_path
    return None
