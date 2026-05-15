# Fabric Generator Try-On Studio

One repo for the integrated yarn-to-fabric workflow: yarn scan processing, weave draft authoring, Blender preview rendering, and browser-side 3D try-on.

The final project handoff lives in [docs/FINAL_HANDOFF.md](docs/FINAL_HANDOFF.md). Start there when you want the full collaboration summary, feature list, process map, and open-item inventory.

External runtime assets live in Google Drive:

https://drive.google.com/drive/folders/18UPKaVFXKBNetcwFR0fXdipJ3HLsZSXU?usp=drive_link

Direct asset bundle:

https://drive.google.com/drive/folders/1z3Ucq0O4ETbsYhVzkTka9l_xxtMeQAsP

## What The App Does

The web app is a four-step studio:

1. **Yarn Library** - process yarn scans inside the app, split multi-thread scans, stitch multi-fragment yarns, inpaint joins with LaMa, save yarn dossiers, and import ready yarns into the current project.
2. **Pattern Builder** - create or import weaving drafts, edit threading/tie-up/treadling/drawdown, paint warp and weft colors, and bind draft colors to real scanned yarn assets.
3. **Render Preview** - push yarn metadata and render settings to Blender, render a scanned-yarn fabric swatch, and export canonical draft or Blender handoff JSON.
4. **Try On 3D** - tile the rendered fabric on an interactive browser-side 3D preview.

## Key Features

- FastAPI backend for draft parsing, yarn asset processing, yarn library import/delete, Blender health checks, render jobs, and live band metadata pushes.
- React + Vite + TypeScript frontend with the integrated yarnseamless editors and the draft studio.
- Shared `yarn_library/<yarn_id>/` contract for `rgba.png`, thumbnail, and `metadata.json`.
- Blender `Parametric Weave knotty` integration through either headless Blender renders or live MCP socket pushes.
- Per-yarn V-band metadata mapping into Arc 1 / Arc 2 Blender sockets.
- Cycles-safe texture handling, including downscale fallback and UDIM-style tiling for very wide yarn strips.
- Render controls for weave zoom, spacing, pattern noise, U scatter, and Arc 1 V padding.
- Unit coverage for backend render payloads, yarn assets, Blender live setup helpers, and frontend draft/project domain logic.

## Repo Layout

```text
backend/      FastAPI service, Blender render orchestration, yarn pipeline port
frontend/     React/Vite studio UI
docs/         final handoff, architecture notes, phase logs, lessons
runtime/      local generated assets, render jobs, projects, and debug output
*.blend       Blender source scenes
```

## Large Artifact Policy

Do not commit local generated data, raw scan uploads, virtual environments, or the reconstructed `big-lama.pt` file.

Git LFS is currently disabled for the GitHub repository, so this branch does not rely on LFS. The current Blender scene is about 26 MB and is committed normally. Raw model weights stay external or local.

The Drive folder should contain:

```text
FabricGenerator_ExternalAssets_2026-05-16/
  README_ASSETS.md
  CHECKSUMS.sha256
  yarn_library/
  models/
    big-lama.pt
```

The repo already ignores:

- `backend/vendor/yarn_pipeline/big-lama.pt`
- `backend/.venv/`
- `frontend/node_modules/`
- `runtime/debug/`
- generated runtime assets/jobs/projects except their `.gitkeep` placeholders
- Blender autosaves and timestamped pre-change snapshots

The LaMa model loader searches these locations in order:

1. `BIG_LAMA_MODEL_PATH` or `LAMA_MODEL`
2. `../big-lama.pt` from this repo, usually `<yarnseamless UI>/big-lama.pt`
3. `backend/vendor/yarn_pipeline/big-lama.pt`
4. `~/.cache/torch/hub/checkpoints/big-lama.pt`
5. vendored chunk reconstruction if chunk files are available

Recommended local setup for the raw model:

```bash
export BIG_LAMA_MODEL_PATH="/absolute/path/to/big-lama.pt"
```

Recommended local placement after downloading the Drive folder:

```text
yarnseamless UI/
  Fabric-generator-tryon/
  yarn_library/
  big-lama.pt
```

## Prerequisites

- Python 3.11+
- Node.js 20+
- Blender
- Git LFS only if the GitHub repository enables it later

## Quick Start

Install backend dependencies:

```bash
make backend-install
```

Install frontend dependencies:

```bash
make frontend-install
```

Run the backend:

```bash
make backend-dev
```

Run the frontend:

```bash
make frontend-dev
```

Open `http://127.0.0.1:5180`.

## Useful Environment Variables

```bash
export YARN_LIBRARY_ROOT="/absolute/path/to/yarn_library"
export BIG_LAMA_MODEL_PATH="/absolute/path/to/big-lama.pt"
export BLENDER_BINARY_PATH="/Applications/Blender.app/Contents/MacOS/Blender"
export WEAVE_BLEND_FILE="/absolute/path/to/Codex_ParametricWeave.blend"
export WEAVE_RENDER_ROOT="/absolute/path/to/runtime/render_jobs"
export BLENDER_PORT=9876
```

For development against an already open Blender scene:

```bash
make backend-dev-live
```

## Verification

Backend tests:

```bash
make backend-test
```

Frontend unit tests:

```bash
make frontend-test
```

Frontend build:

```bash
cd frontend
npm run build
```

Frontend e2e tests:

```bash
make frontend-e2e
```
