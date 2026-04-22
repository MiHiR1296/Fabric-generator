# Fabric Generator

One self-contained repo for the yarn-processing pipeline, the web-based weave draft builder, and the Blender preview scene.

## Included In This Repo

- `frontend/`
  - React + Vite app for:
  - `Step 1` yarn uploads and processing status
  - `Step 2` pattern building and draft import/editing
  - `Step 3` color-to-yarn mapping and Blender preview
- `backend/`
  - FastAPI service for draft parsing, yarn asset processing, atlas generation, and Blender render jobs
- `backend/vendor/yarn_pipeline/`
  - vendored yarn-processing code plus the required `big-lama` model split into repo-safe chunks
- `Weave_GUIConnection.blend`
  - Blender scene used for headless preview rendering
- `docs/application-blueprint.md`
  - product and workflow reference for the pattern builder
- `runtime/`
  - local storage root for generated yarn assets, render jobs, and saved project snapshots

## Important Note About Large Assets

This repo keeps the Blender scene directly in Git and stores the `big-lama` model as chunk files under `backend/vendor/yarn_pipeline/model_chunks/`.

The backend reconstructs `big-lama.pt` automatically on first use, so a fresh clone does not need a separate model download step.

## Prerequisites

- Python 3.11+
- Node.js 20+
- Blender
## Quick Start

1. Install backend dependencies:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Install frontend dependencies:

```bash
cd frontend
npm install
```

3. Start the backend:

```bash
cd backend
source .venv/bin/activate
python -m app.main
```

4. Start the frontend in another terminal:

```bash
cd frontend
npm run dev
```

The frontend runs on `http://127.0.0.1:5180` by default and proxies API requests to the backend on `http://127.0.0.1:8000`.

## Environment

You can override the Blender binary and blend file path with:

```bash
export BLENDER_BINARY_PATH="/Applications/Blender.app/Contents/MacOS/Blender"
export WEAVE_BLEND_FILE="/absolute/path/to/Weave_GUIConnection.blend"
export WEAVE_RENDER_ROOT="/absolute/path/to/runtime/render_jobs"
```

## Common Commands

Use the root `Makefile` for the most common tasks:

```bash
make backend-install
make backend-dev
make frontend-install
make frontend-dev
make backend-test
make frontend-test
make frontend-e2e
```

## Verification

Backend tests:

```bash
cd backend
python3 -m unittest discover tests
```

Frontend unit tests:

```bash
cd frontend
npm run test:unit
```

Frontend e2e:

```bash
cd frontend
npx playwright install chromium
npm run test:e2e
```
