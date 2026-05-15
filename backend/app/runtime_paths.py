from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_ROOT = PROJECT_ROOT / "runtime"
YARN_ASSETS_ROOT = RUNTIME_ROOT / "yarn_assets"
PROJECTS_ROOT = RUNTIME_ROOT / "projects"
RENDER_JOBS_ROOT = RUNTIME_ROOT / "render_jobs"

# Default to Codex_ParametricWeave.blend (the knotty graph with persistent
# per-material sockets). Override via WEAVE_BLEND_FILE env if needed.
BLEND_FILE_PATH = Path(
    os.environ.get("WEAVE_BLEND_FILE")
    or (PROJECT_ROOT / "Codex_ParametricWeave.blend")
)


def _default_yarn_library_root() -> Path:
    """The shared yarn_library/ folder lives one level up from this repo, next
    to the yarnseamless web/ folder. Override via YARN_LIBRARY_ROOT env var."""
    env = os.environ.get("YARN_LIBRARY_ROOT")
    if env:
        return Path(env).resolve()
    return (PROJECT_ROOT.parent / "yarn_library").resolve()


YARN_LIBRARY_ROOT = _default_yarn_library_root()

# Yarnseamless debug folders (multithread split outputs, multifragment stitcher
# outputs, raw uploads). Layout matches yarnseamless's web/../debug/* exactly
# so session IDs and on-disk artifacts are interchangeable.
DEBUG_ROOT = RUNTIME_ROOT / "debug"
MULTITHREAD_OUTPUT_DIR = DEBUG_ROOT / "multithread_image"
MULTIFRAG_DEBUG_DIR = DEBUG_ROOT / "multifragment"
UPLOADS_DIR = DEBUG_ROOT / "uploads"


def ensure_runtime_dirs() -> None:
    for path in (RUNTIME_ROOT, YARN_ASSETS_ROOT, PROJECTS_ROOT, RENDER_JOBS_ROOT,
                 DEBUG_ROOT, MULTITHREAD_OUTPUT_DIR, MULTIFRAG_DEBUG_DIR, UPLOADS_DIR):
        path.mkdir(parents=True, exist_ok=True)
