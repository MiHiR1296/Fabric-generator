# Try-On 3D Render — plan

## Goal

On Step 4, the user:

1. Sees a list of selectable 3D objects (checkboxes).
2. Selects one or more.
3. Presses **Render**.
4. Backend renders each selected object **one at a time** in Blender, draping
   the user's generated fabric onto it.
5. The UI shows each finished render as soon as it is ready (a gallery that
   fills in progressively), with per-object status (queued → rendering → done /
   failed).

## What we already have (reused, not rebuilt)

- **Render-job registry** in `backend/app/render_jobs.py`: `RenderJob` dataclass,
  `_JOBS` dict, `_job_snapshot`, `get_render_job`, `get_render_image_path`,
  `_run_headless_render`, `load_headless_blender_config`,
  `build_headless_render_command`. We reuse the job model + headless runner so
  the existing status/preview endpoints work unchanged for Try-On jobs.
- **Status/preview endpoints:** `GET /api/blender/render-jobs/{id}` and
  `GET /api/blender/render-jobs/{id}/image`. Try-On jobs are normal `RenderJob`
  entries, so these serve them with no new code.
- **Frontend job polling:** `fetchDraftRenderJob(jobId)` +
  the `BlenderRenderJob` type + the poll-on-status pattern in `App.tsx`.
- **The scene art:** `Renders/Objects.blend` and its `Material.001`, already set
  up exactly like the manual `TMPrenders/` workflow.

## The Blender scene (`Renders/Objects.blend`)

Discovered by inspection (see data_contract.md for the full dump):

- `Cloth_08` — draped cloth (≈3.14 × 1.52 × 1.94), SOLIDIFY+SUBSURF, parent
  `Backdrop_Cloth_08`. Material `Material.001`.
- `Plane.002` — small cushion (≈0.30 × 0.31 × 0.18), parent `Cushion`.
  Material `Material.001`.
- `Plane` — 5×5 floor/backdrop. Material `Material.001`.
- `Icosphere` — hidden physics collider (Material.002). Not rendered.
- `Camera` — single perspective camera at (1.385, 2.756, 2.927), 50mm.
- Render: Cycles, 128 samples, film transparent, 1024² × 200% (≈2048²).

`Material.001` node graph (the swap target):

```
Texture Coordinate.UV → Mapping → Image Texture.001 (3x1.png)  [diffuse]
Image Texture.001.Color → Principled BSDF.Base Color
Image Texture.001.Color → Principled BSDF.Sheen Tint
Image Texture.001.Alpha → Principled BSDF.Alpha
Mapping → Image Texture.002 (3x1_Normal.png) [normal]
Image Texture.002.Color → Normal Map.Color → Principled BSDF.Normal
```

So: replace `Image Texture.001`'s image with the user's fabric tile. If we have a
matching normal map, replace `Image Texture.002`; otherwise neutralize the
Normal Map node (strength 0) so the stale pattern's normal doesn't bleed through.

> Note: `Fabric 60` material references external BlenderKit textures via broken
> relative paths, but **no rendered object uses it** (only the hidden Icosphere
> uses Material.002), so missing externals do not affect Try-On renders.

## Target catalog (data-driven, collection-based)

A target is a named, selectable render. Default catalog lives in
`backend/app/tryon_render.py`; an optional `Renders/tryon_targets.json`
overrides it without code changes. Shape (see data_contract.md):

```json
{
  "id": "draped_cloth",
  "label": "Draped Cloth",
  "description": "Your fabric draped over a hanging cloth form.",
  "collections": ["Backdrop_Cloth_08"],
  "camera": "",
  "fabricMaterial": "Material.001"
}
```

The scene is organized into one collection per showcase object. A render enables
the target's `collections`, keeps the camera's own collection, and excludes the
rest. The **camera is used exactly as authored** — its angle and crop are the
intended look, so we never move or auto-fit it (`camera: ""` keeps the scene's
active camera; set a name to switch cameras).

Default targets:

| id | label | collection |
|----|-------|-----------|
| `draped_cloth` | Draped Cloth | `Backdrop_Cloth_08` |
| `cushion` | Cushion | `Cushion` |

## Request flow

```
Frontend (Step 4)
  GET  /api/blender/tryon/targets                  → [{id,label,description}, ...]
  POST /api/blender/tryon/render                    → {batchId, jobs:[{targetId,label,jobId,status}]}
        body: {targetIds:[...], sourceJobId, resolution?, samples?}
  (poll) GET /api/blender/render-jobs/{jobId}        → status + imageUrl
  (show) GET /api/blender/render-jobs/{jobId}/image  → PNG
```

`sourceJobId` is a previously-succeeded render or tile job from Step 3. The
backend resolves its on-disk image (`get_render_image_path`) and copies it into
each Try-On job dir as the fabric diffuse. No image bytes cross the wire on
submit — only the job id.

### Sequencing ("one at a time")

`submit_tryon_render_batch` creates one `RenderJob` per selected target (status
`queued`) and enqueues them on a module-level `queue.Queue` drained by a single
persistent worker thread. The worker renders jobs FIFO, headless, one process at
a time. The frontend polls every job id; cards advance queued → running →
succeeded/failed independently, so results appear progressively while later ones
are still queued.

This is deliberately a separate single-worker queue from the existing weave
render jobs (which start a thread immediately). Try-On renders are heavier (full
Cycles scene) and the user explicitly wants them serialized.

## Render script (`build_tryon_render_script`)

Runs inside headless Blender opened on `Objects.blend`:

1. Resolve `fabricMaterial` (default `Material.001`).
2. Find the base-color image-texture node (trace Principled BSDF `Base Color`
   back to a `TEX_IMAGE`; fall back to node name `Image Texture.001`). Load the
   fabric diffuse via `bpy.data.images.load(..., check_existing=False)` and
   assign.
3. Normal: if a normal path is provided, trace `Normal` → Normal Map → its Color
   input `TEX_IMAGE` and assign; else set the Normal Map node `Strength` to 0.
4. Camera: pick the target camera (or keep the scene's active camera) and set
   `scene.camera` — but do **not** move it. The authored framing is intentional.
5. Collections: walk the view-layer collection tree; set `exclude = False` for
   the target's `collections` and the camera's own collection, `True` for the
   rest. (Re-enables collections the artist excluded from the view layer.) Then
   `view_layer.update()`.
6. Render settings: resolution (default ≈1600), samples (default 96),
   `film_transparent` on, output `render_path`, `bpy.ops.render.render(write_still=True)`.
7. Print a small JSON status to stdout for the job log.

The script is generated in Python (string templating, same approach as
`build_headless_render_script`) and written to the job dir, then executed by the
existing headless command builder pointed at `Objects.blend`.

## Build phases

1. **Docs** (this folder). ✓
2. **Render script + headless verification** — generate the script, run it by
   hand against `Objects.blend` with a `TMPrenders` texture, confirm a PNG drops
   for each default target.
3. **Backend module** `tryon_render.py` — catalog load, script builder, batch
   submit + single-worker queue, source-image resolution.
4. **Endpoints** in `main.py` under `/api/blender/tryon/*` (reuses the
   `/api/blender` vite proxy — no proxy change needed).
5. **Frontend API + types** — `listTryonTargets`, `requestTryonRender`,
   `TryonTarget`, batch response type.
6. **Step 4 rewrite** — checkbox picker + Render button + progressive gallery,
   sourcing the fabric from the Step-3 tile (preferred) or render job.
7. **Wire `App.tsx`** (pass tile + render jobs to Step 4) and verify
   `npm run build` + `make backend-test`.

## Out of scope (future)

- Per-object dedicated art cameras / lighting setups (we use the one scene
  camera + optional auto-frame).
- Using a true PBR set (normal/roughness) generated from the weave — we apply
  diffuse now and neutralize the normal when none is supplied.
- Cloth re-simulation per garment (the draped meshes are already static).
- Thumbnails for the target picker (labels + descriptions only for MVP).
- Batch-level cancel / re-render-one controls.
