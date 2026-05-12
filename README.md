# Fabric Generator

One self-contained repo for the yarn-processing pipeline, the web-based weave draft builder, and the Blender preview scene.

The current product flow is:

- `Step 1` Upload yarn references and generate seamless diffuse maps, alpha mattes, band metadata, and QA maps
- `Step 2` Build or import the weave draft in the web editor
- `Step 3` Assign processed yarns to warp/weft color slots, stage preview controls, and click `Preview` to refresh a Blender Material Preview screenshot

## Included In This Repo

- `frontend/`
  - React + Vite app for:
  - `Step 1` yarn uploads and processing status
  - `Step 2` pattern building and draft import/editing
  - `Step 3` color-to-yarn mapping and lazy Blender Material Preview
- `backend/`
  - FastAPI service for draft parsing, yarn asset processing, live Blender preview sync, atlas generation, and Blender render jobs
- `backend/vendor/yarn_pipeline/`
  - vendored yarn-processing code plus band segmentation metadata generation and the required `big-lama` model split into repo-safe chunks
- `scripts/`
  - setup automation for teammate onboarding and fresh-machine checks
- `Codex_ParametricWeave.blend`
  - updated Blender scene used by default for managed live preview and final render jobs
- `Weave_GUIConnection.blend`
  - previous Blender scene kept in the repository as a reference/fallback
- `docs/application-blueprint.md`
  - product and workflow reference for the pattern builder
- `docs/system-setup.md`
  - machine setup workflow, dependency manifests, and server notes
- `runtime/`
  - local storage root for generated yarn assets, render jobs, live preview screenshots, and saved project snapshots
- `docs/live-preview-worklog.md`
  - running notes for the staged Blender preview workflow and rollout path

## Important Note About Large Assets

This repo keeps the Blender scene directly in Git and stores the `big-lama` model as chunk files under `backend/vendor/yarn_pipeline/model_chunks/`.

The backend reconstructs `big-lama.pt` automatically on first use, so a fresh clone does not need a separate model download step.

## Prerequisites

- Python 3.9+
- Node.js 20+
- Blender

## Fast Setup

The recommended way to onboard a new machine is:

```bash
python3 scripts/setup_doctor.py
python3 scripts/bootstrap.py --with-playwright
```

If Blender is missing and the machine has `brew`, `apt-get`, `dnf`, or `yum`, you can also try:

```bash
python3 scripts/bootstrap.py --install-blender
```

The doctor prints:

- which required tools are present
- which optional tools are missing
- the exact Python and npm packages this repo will install
- whether the backend virtualenv, frontend `node_modules`, and Playwright browser cache already exist

Detailed onboarding notes live in [docs/system-setup.md](docs/system-setup.md).

## Manual Quick Start

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

## Local Blender Material Preview

The web UI now uses a lazy preview workflow instead of a continuously streaming Blender session.

1. Open `Codex_ParametricWeave.blend` in Blender.
2. Start the Blender MCP / socket bridge so the backend can send update commands.
3. Start the backend and frontend from this repo.
4. In the web app:
   - upload yarn images in `Step 1`
   - build or import the draft in `Step 2`
   - assign yarns and adjust preview controls in `Step 3`
5. Click `Preview` only when you are ready to refresh the camera preview.

What happens on each update:

- the frontend sends the full project snapshot plus the staged preview settings
- the backend syncs the draft and material assignments into the running Blender session
- Blender renders the active camera directly from the managed session
- the backend writes that camera-framed render to disk and returns it to the web UI

This is intentionally not a live render loop. Controls are staged locally in the browser until the user confirms the batch of changes.

Important material note:

- the generated yarn preview materials load diffuse and alpha textures directly from the uploaded/processed asset, instead of inheriting the preset material graph from the Blender file
- the diffuse texture is wired into base color and the alpha texture is wired into shader alpha
- `Codex_ParametricWeave.blend` exposes persistent per-material sockets on `Parametric Weave knotty`, so `uv_scaled` is computed from each selected yarn asset's image-width and band metadata instead of one global modifier calibration
- web-generated warp/weft material IDs feed the knotty graph's `material_id` attribute directly, so the web assignment pattern is the source of truth

By default the backend now runs Blender in `managed` session mode:

- the first Blender-backed request can launch Blender automatically
- repeated requests reuse the warm session
- if the session stays idle for too long, the backend stops it automatically

That keeps Blender available during an active editing burst without leaving it running forever.

## Preview Controls In The Web UI

The Step 3 preview panel exposes only the practical material-preview controls while keeping the dense repeat counts fixed:

- `Spacing`, normalized from `0..1` in the UI to `0.03..0.10` in Blender
- `Pattern Noise X`, normalized from `0..1` in the UI to `0.00..0.03` in Blender
- `Pattern Noise Y`, normalized from `0..1` in the UI to `0.00..0.03` in Blender

`Warp Threads` and `Weft Threads` are intentionally not exposed in the web UI. New and imported drafts normalize both to at least `180`, and the backend applies that floor even if the Blender file still has an older lower value preserved in the modifier.

## Environment

You can override the Blender binary and blend file path with:

```bash
export BLENDER_BINARY_PATH="/Applications/Blender.app/Contents/MacOS/Blender"
export WEAVE_BLEND_FILE="/absolute/path/to/Codex_ParametricWeave.blend"
export WEAVE_RENDER_ROOT="/absolute/path/to/runtime/render_jobs"
```

For Blender bridge connectivity, you can also override:

```bash
export BLENDER_HOST="127.0.0.1"
export BLENDER_PORT="9875"
export BLENDER_TIMEOUT_SECONDS="30"
```

The new lazy preview screenshots are stored under `runtime/live_preview/`.

Managed-session controls:

```bash
export BLENDER_SESSION_MODE="managed"
export BLENDER_IDLE_TIMEOUT_SECONDS="600"
export BLENDER_STARTUP_TIMEOUT_SECONDS="120"
export BLENDER_LAUNCH_PREFIX=""
export BLENDER_LAUNCH_ARGS=""
```

Notes:

- `BLENDER_SESSION_MODE=managed` lets the backend launch and stop Blender itself
- `BLENDER_SESSION_MODE=attach` keeps the old behavior and only talks to an already-running Blender session
- `BLENDER_IDLE_TIMEOUT_SECONDS=600` means the backend stops its managed Blender session after 10 idle minutes
- `BLENDER_LAUNCH_PREFIX` lets terminal-only Linux hosts launch Blender through a wrapper such as `xvfb-run`

## Common Commands

Use the root `Makefile` for the most common tasks:

```bash
make doctor
make doctor-strict
make bootstrap
make bootstrap-playwright
make bootstrap-blender
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

## Current Direction

Local development uses a real Blender desktop session with the MCP/socket bridge attached to `Codex_ParametricWeave.blend`.

Planned server deployment is:

- GPU-backed machine such as the target H100 server
- persistent Blender GUI session with a virtual display
- the same lazy `Preview` workflow for camera-framed Material Preview images
- headless background renders kept available for higher-quality final output when needed

For terminal-only Linux environments, the managed Blender launcher can now prepend a wrapper command. Example:

```bash
export BLENDER_SESSION_MODE=managed
export BLENDER_LAUNCH_PREFIX='xvfb-run -a -s "-screen 0 1920x1080x24"'
```

The backend also exposes session lifecycle endpoints:

- `GET /api/blender/session`
- `POST /api/blender/session/restart`
- `POST /api/blender/session/stop`

Implementation notes for the current preview flow live in [docs/live-preview-worklog.md](docs/live-preview-worklog.md), and the teammate/server setup workflow lives in [docs/system-setup.md](docs/system-setup.md).
