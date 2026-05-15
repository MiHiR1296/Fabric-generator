# Final Handoff - Fabric Generator Try-On Studio

This is the consolidated handoff for the integrated Fabric Generator work: what we built, how the pieces talk to each other, how we managed model/filesystem state, and what the application can do now.

## Executive Summary

We turned the Fabric Generator prototype into a four-step production-shaped studio:

1. Process yarn scans directly inside the app.
2. Save and import yarn dossiers through a shared `yarn_library/` contract.
3. Build or import weaving drafts and bind draft colors to real scanned yarns.
4. Render through Blender and preview the fabric on a browser-side 3D try-on surface.

The big product change is that users no longer need to juggle separate yarnseamless, draft-builder, and Blender workflows. The app owns the workflow; Blender is treated as the render/setup engine behind the scenes.

## What We Integrated

| Layer | Result |
|---|---|
| Yarn processing | Ported the yarnseamless yarn workflow into the FastAPI backend and React Step 1 UI. |
| Library contract | Standardized `yarn_library/<yarn_id>/` as the handoff folder for `rgba.png`, thumbnail, and `metadata.json`. |
| Draft studio | Preserved the weaving draft editor, import/export paths, color painting, and canonical draft model. |
| Color binding | Added project-level warp/weft color-to-yarn assignments so draft colors become material slots. |
| Blender setup | Added live and headless paths that push per-yarn band metadata into `Parametric Weave knotty`. |
| Rendering | Added material payload generation, direct per-yarn materials, Cycles-safe texture handling, render jobs, and preview polling. |
| Try-on | Kept the rendered fabric available for the Step 4 three.js preview. |
| Documentation | Added architecture, data contract, phase logs, lessons, and this final handoff. |

## Application Workflow

### Step 1 - Yarn Library

- Upload one scan containing multiple yarn threads.
- Split and level the threads.
- Review detection overlays and band alignment.
- Move into the multifragment stitcher.
- Inpaint joins with LaMa.
- Regenerate alpha and export the assembled RGBA yarn.
- Save the yarn to the shared library.
- Auto-import new library yarns into the current Fabric Generator project.

### Step 2 - Pattern Builder

- Load presets, WIF/JSON/text/image-derived drafts, or edit manually.
- Edit threading, tie-up, treadling, drawdown, warp colors, and weft colors.
- Bind each warp/weft color slot to a ready yarn asset.
- Live-push complete band metadata to Blender after bindings and render settings stabilize.

### Step 3 - Render Preview

- Render the current project through Blender.
- Use the same slot ordering for render jobs and live setup pushes.
- Control weave zoom, spacing, pattern noise X/Y, U scatter, and Arc 1 V padding.
- Export canonical draft JSON and Blender handoff JSON.
- Poll render jobs and show the finished preview image in the UI.

### Step 4 - Try On 3D

- Use the rendered swatch as a tiled texture in the browser.
- Preview the fabric in an interactive three.js try-on scene.

## State And Data Management

### Shared Library

`yarn_library/` is the cross-app contract. A saved yarn folder contains:

```text
yarn_library/<yarn_id>/
  rgba.png
  input_thumb.jpg
  metadata.json
```

`metadata.json` carries source provenance, physical scale, band measurements, and a `blender` block with pre-computed values for the Blender modifier. The consumer should push those values; it should not redo the measurement math.

### Runtime Assets

The app imports library yarns into:

```text
runtime/yarn_assets/<asset_id>/
```

Each runtime asset stores the project-local asset JSON plus Blender-ready texture files. Very wide yarn strips get Cycles-safe downscales and UDIM-style tile sets so Blender can render without exceeding the 16384 px single-texture cap.

### Render Jobs

Render jobs live under:

```text
runtime/render_jobs/<job_id>/
```

Each job has the project payload, generated Blender Python script, logs, and output preview image.

### Debug Artifacts

The yarnseamless processing port writes large intermediate files under:

```text
runtime/debug/
```

This folder is intentionally ignored by Git. It can contain raw uploads, detection overlays, join canvases, inpaint inputs, masks, assembled images, and temporary metadata.

## Large File Strategy

The raw `big-lama.pt` model should not be committed.

The loader checks:

1. `BIG_LAMA_MODEL_PATH`
2. `LAMA_MODEL`
3. `<yarnseamless UI>/big-lama.pt`
4. `backend/vendor/yarn_pipeline/big-lama.pt`
5. `~/.cache/torch/hub/checkpoints/big-lama.pt`
6. vendored chunk reconstruction when chunk files are present

Git LFS is currently disabled for the GitHub repository, so this branch does not depend on LFS. The current Blender scene is small enough for normal Git. Future heavyweight `.blend` or model artifacts should move to Git LFS only after the repository enables it, or to release/external storage.

Recommended local model setup:

```bash
export BIG_LAMA_MODEL_PATH="/absolute/path/to/big-lama.pt"
```

## Blender Integration

The current Blender target is `Codex_ParametricWeave.blend`, object `ParametricWeave`, modifier `Weave`, node group `Parametric Weave knotty`.

There are two execution modes:

| Mode | Command | Behavior |
|---|---|---|
| Headless | `make backend-dev` | render jobs spawn Blender as a subprocess and write preview images. |
| Live MCP | `make backend-dev-live` | render/setup scripts are sent to an open Blender session over the MCP socket, default port `9876`. |

Important socket concepts:

- Arc 1 sockets receive the dense yarn core V band.
- Arc 2 sockets receive the outer silhouette / halo V band.
- `Scanner Pixels Per BU` is the remaining global scale socket.
- `Sub Strand Enable` is pinned on so Arc 2 halo mapping actually renders.
- V-axis footgun sockets are pinned to neutral values to keep scan-driven yarns aligned.
- `Material N Texture Scale U` receives the fit-aware U correction so the visible repeat matches the render context.

## Feature Inventory

- Yarn library list, import, delete, and auto-import.
- Multi-thread upload/process flow.
- Multi-fragment stitch, join inpaint, alpha regeneration, export, save-to-library.
- Post-inpaint band detection for Blender metadata.
- Draft presets, imports, editor, color painting, and export.
- Color-to-yarn binding grid.
- Live band metadata push to Blender.
- Headless Blender render jobs.
- Direct per-yarn material assignment in Blender.
- UDIM-style texture tiling for wide yarn strips.
- Render progress estimate and log/status surface.
- Render control surface for artist-tuned preview iteration.
- Browser-side Try On 3D preview.
- Backend and frontend tests for the main data contracts.

## Operating The App

Install once:

```bash
make backend-install
make frontend-install
```

Run normal development:

```bash
make backend-dev
make frontend-dev
```

Run against an open Blender session:

```bash
make backend-dev-live
```

Open:

```text
http://127.0.0.1:5180
```

## Verification Checklist

Before publishing a change:

- `make backend-test`
- `make frontend-test`
- `cd frontend && npm run build`
- optional: `make frontend-e2e`
- optional Blender check: open `Codex_ParametricWeave.blend`, run `make backend-dev-live`, bind ready yarns, and confirm the modifier receives Material socket values.

## Open Items

- Move any remaining large binary workflow to Git LFS, release assets, or external storage before adding new model weights.
- Decide whether the already-split model chunks should remain in the repo long-term or move to release assets/LFS during a history-cleaning pass.
- Add a frontend toggle for live Blender render mode; today it is an environment variable.
- Add a `Texture World Width BU` socket to the `.blend` if we want to remove the legacy image-width/divisor path.
- Rename remaining internal Blender nodes that still say Core/Fiber even though the interface now says Arc 1/Arc 2.
- Retire legacy atlas fallback after multi-yarn direct material rendering is accepted across enough projects.
- Add a runtime cleanup policy for old debug sessions and render jobs.

## Documentation Map

- [README.md](../README.md) - root setup and repo-level overview.
- [docs/README.md](README.md) - documentation index.
- [putting-it-together/data_contract.md](putting-it-together/data_contract.md) - authoritative metadata and socket contract.
- [putting-it-together/architecture.md](putting-it-together/architecture.md) - process and request-flow diagrams.
- [BlenderFixes/](BlenderFixes/) - Blender graph and socket history.
- [WebUIChanges/](WebUIChanges/) - wizard UI and FastAPI integration notes.
- [WebUIbands/](WebUIbands/) - yarn band detection history and target pipeline.
