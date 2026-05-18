# Fabric Generator Backend

FastAPI service for the integrated yarn-to-fabric workflow.

## Responsibilities

- parse weaving draft sources into the canonical document shape
- process uploaded yarn scans and port the yarnseamless multithread/multifragment flow
- save and import yarn dossiers from the shared `yarn_library/`
- split RGBA yarn assets into Blender-ready albedo/alpha textures
- create Cycles-safe downscales and UDIM-style texture tiles
- validate color-to-yarn bindings
- build material payloads and render scripts for Blender
- run either headless Blender render jobs or live MCP setup pushes

## Important Endpoints

- `GET /api/parser/health`
- `POST /api/parser/parse-file`
- `POST /api/parser/parse-text`
- `GET /api/blender/health`
- `POST /api/blender/sync-draft`
- `POST /api/blender/render-project`
- `POST /api/blender/push-bandmeta`
- `POST /api/blender/push-project-bandmeta`
- `GET /api/blender/render-jobs/{job_id}`
- `GET /api/blender/render-jobs/{job_id}/image`
- `GET /api/yarn/library`
- `POST /api/yarn/library/{yarn_id}/import`
- `DELETE /api/yarn/library/{yarn_id}`
- `GET /api/yarn/assets`
- `POST /api/yarn/assets`
- `POST /api/yarn/assets/{asset_id}/retry`
- `DELETE /api/yarn/assets/{asset_id}`
- `GET /api/lama/health`
- `POST /api/lama/inpaint`
- `POST /api/multithread/upload`
- `POST /api/multithread/process`
- `POST /api/multithread/assemble`
- `POST /api/multithread/regenerate-alpha`
- `POST /api/multithread/export`
- `POST /api/multithread/save-to-library`

## Large Model Setup

Do not commit the reconstructed `big-lama.pt`.

The loader checks, in order:

1. `BIG_LAMA_MODEL_PATH` or `LAMA_MODEL`
2. `<yarnseamless UI>/big-lama.pt`
3. `backend/vendor/yarn_pipeline/big-lama.pt`
4. `~/.cache/torch/hub/checkpoints/big-lama.pt`
5. vendored chunk reconstruction if chunk files are available

Recommended:

```bash
export BIG_LAMA_MODEL_PATH="/absolute/path/to/big-lama.pt"
```

## Setup

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m app.main
```

The service listens on `http://127.0.0.1:8000`.

## Blender Defaults

- Blender binary: `/Applications/Blender.app/Contents/MacOS/Blender`
- Blend file: `../Codex_ParametricWeave.blend`
- Runtime root: `../runtime/render_jobs`
- Live MCP port: `9876` through the Makefile

Optional overrides:

```bash
export BLENDER_BINARY_PATH="/Applications/Blender.app/Contents/MacOS/Blender"
export WEAVE_BLEND_FILE="/absolute/path/to/Codex_ParametricWeave.blend"
export WEAVE_RENDER_ROOT="/absolute/path/to/runtime/render_jobs"
export BLENDER_PORT=9876
```

## Test Command

```bash
cd backend
python3 -m unittest discover tests
```
