from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_ROOT = PROJECT_ROOT / "runtime"
YARN_ASSETS_ROOT = RUNTIME_ROOT / "yarn_assets"
PROJECTS_ROOT = RUNTIME_ROOT / "projects"
RENDER_JOBS_ROOT = RUNTIME_ROOT / "render_jobs"
LIVE_PREVIEW_ROOT = RUNTIME_ROOT / "live_preview"
BLENDER_SESSION_ROOT = RUNTIME_ROOT / "blender_session"
BLEND_FILE_PATH = PROJECT_ROOT / "Codex_ParametricWeave.blend"


def ensure_runtime_dirs() -> None:
    for path in (
        RUNTIME_ROOT,
        YARN_ASSETS_ROOT,
        PROJECTS_ROOT,
        RENDER_JOBS_ROOT,
        LIVE_PREVIEW_ROOT,
        BLENDER_SESSION_ROOT,
    ):
        path.mkdir(parents=True, exist_ok=True)
