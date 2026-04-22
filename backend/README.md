# Fabric Generator Backend

FastAPI service for:

- parsing weaving draft sources into one canonical document
- processing uploaded yarn images into seamless diffuse and alpha maps
- validating color-to-yarn bindings
- building texture atlases for Blender preview renders
- launching headless Blender render jobs

The vendored `big-lama` weights are stored as chunk files in the repo and reconstructed to `backend/vendor/yarn_pipeline/big-lama.pt` automatically when the seamless yarn pipeline needs them.

## Endpoints

- `GET /api/parser/health`
- `POST /api/parser/parse-file`
- `POST /api/parser/parse-text`
- `GET /api/blender/health`
- `POST /api/blender/sync-draft`
- `POST /api/blender/render-draft`
- `POST /api/blender/render-project`
- `GET /api/blender/render-jobs/{job_id}`
- `GET /api/blender/render-jobs/{job_id}/image`
- `GET /api/yarn/assets`
- `POST /api/yarn/assets`
- `GET /api/yarn/assets/{asset_id}`
- `GET /api/yarn/assets/{asset_id}/files/{filename}`
- `POST /api/yarn/assets/{asset_id}/retry`
- `DELETE /api/yarn/assets/{asset_id}`

## Setup

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m app.main
```

The service listens on `http://127.0.0.1:8000`.

## Headless Blender Defaults

- Blender binary:
  - `/Applications/Blender.app/Contents/MacOS/Blender`
- Blend file:
  - `../Weave_GUIConnection.blend`
- Runtime root:
  - `../runtime/render_jobs`

Optional environment overrides:

```bash
export BLENDER_BINARY_PATH="/Applications/Blender.app/Contents/MacOS/Blender"
export WEAVE_BLEND_FILE="/absolute/path/to/Weave_GUIConnection.blend"
export WEAVE_RENDER_ROOT="/absolute/path/to/runtime/render_jobs"
```

## Test Command

```bash
cd backend
python3 -m unittest discover tests
```
