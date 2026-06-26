# Try-On 3D Render — data contract

## Scene file

`Renders/Objects.blend`, overridable via env `TRYON_BLEND_FILE`.

### Object inventory (as inspected 2026-06-15)

| object | type | material | render role |
|--------|------|----------|-------------|
| `Cloth_08` | MESH | `Material.001` | draped cloth hero |
| `Plane.002` | MESH | `Material.001` | cushion hero (parent empty `Cushion`) |
| `Plane` | MESH | `Material.001` | floor / backdrop (5×5) |
| `Icosphere` | MESH | `Material.002` | hidden physics collider — never rendered |
| `Camera` | CAMERA | — | scene camera (50mm persp) |
| `Backdrop_Cloth_08`, `Cushion` | EMPTY | — | parents/controllers |

Scene render defaults: Cycles, 128 samples, `film_transparent = True`,
1024×1024 @ 200% (≈2048²).

### Fabric material contract (`Material.001`)

The Try-On render swaps images on this material. Stable assumptions:

- Base-color image-texture node feeds `Principled BSDF > Base Color` (and Sheen
  Tint + Alpha). Default node name `Image Texture.001`. The script traces the
  Base Color link first, falling back to the name.
- Normal image-texture node feeds a `Normal Map` node feeding
  `Principled BSDF > Normal`. Default node name `Image Texture.002`.
- If the contract can't be resolved (renamed nodes, missing Principled), the
  render fails loudly with a message in the job log.

## Target catalog

Default in `backend/app/tryon_render.py`; override file
`Renders/tryon_targets.json` (override path via env `TRYON_TARGETS_FILE`).
A target object:

| field | type | meaning |
|-------|------|---------|
| `id` | string | stable id used by the API and UI |
| `label` | string | UI checkbox label |
| `description` | string | UI helper text |
| `collections` | string[] | collection(s) to enable for this render (everything else except the camera's collection is excluded) |
| `camera` | string | camera object name; `""` (default) keeps the scene's authored active camera |
| `fabricMaterial` | string | material to receive the fabric texture (default `Material.001`) |

### Collection model (2026-06-15)

`Objects.blend` is organized so each showcase object is its own collection, and
the artist's camera is set up to frame whichever one is enabled:

| collection | holds | role |
|------------|-------|------|
| `Backdrop_Cloth_08` | `Cloth_08` (+ empty) | draped cloth — on by default |
| `Cushion` | `Plane.002` (+ empty) | puffed cushion |
| `Sphere` | `Plane` backdrop + `Icosphere` collider | backdrop sweep (collider is hidden) |
| `Collection` | `Camera` | camera holder — always kept on |

A render enables the target's `collections`, keeps the camera's collection, and
excludes the rest. The **camera is never moved** — its authored position/angle
(intentionally cropped) is the desired look. To add a garment, give it its own
collection in `Objects.blend` and add a target naming that collection in
`Renders/tryon_targets.json`.

Visibility rule at render time: a mesh renders iff it is in `show ∪ keep` and not
in `hide`. Every other mesh (including the collider) is hidden.

The override JSON may be either a bare array of targets or `{ "targets": [...] }`.

## API

All under `/api/blender/tryon/*` (covered by the existing `/api/blender` proxy).

### `GET /api/blender/tryon/targets`

```json
{
  "targets": [
    { "id": "draped_cloth", "label": "Draped Cloth", "description": "..." },
    { "id": "cushion",      "label": "Cushion",      "description": "..." },
    { "id": "full_scene",   "label": "Full Scene",   "description": "..." }
  ],
  "blendFileExists": true
}
```

### `POST /api/blender/tryon/render`

Request:

```json
{
  "targetIds": ["draped_cloth", "cushion"],
  "sourceJobId": "tiles_ab12cd34ef56",
  "_comment": "each targetId maps to a collection toggled on for its render",
  "resolution": 1600,
  "samples": 96
}
```

- `targetIds` — non-empty list of catalog ids.
- `sourceJobId` — id of a succeeded Step-3 render or tile job; its image is the
  fabric diffuse. Optional only if a sourceImage already lives in the project
  (MVP requires it; 400 otherwise).
- `resolution`, `samples` — optional overrides (clamped server-side).

Response:

```json
{
  "batchId": "tryon_7f3a...",
  "jobs": [
    { "targetId": "draped_cloth", "label": "Draped Cloth", "jobId": "tryon_7f3a_0", "status": "queued" },
    { "targetId": "cushion",      "label": "Cushion",      "jobId": "tryon_7f3a_1", "status": "queued" }
  ]
}
```

### Status + preview (reused)

- `GET /api/blender/render-jobs/{jobId}` → standard `RenderJob` snapshot
  (`status`, `message`, `imageUrl`, `logTail`, ...).
- `GET /api/blender/render-jobs/{jobId}/image` → PNG once `succeeded`.

### Optional: `GET /api/blender/tryon/batches/{batchId}`

Convenience aggregate returning the snapshot of every job in the batch in one
call, so the UI can poll one endpoint instead of N.

## Job dir layout

```
runtime/render_jobs/<jobId>/
  fabric_diffuse.png      # copied from the source job
  fabric_normal.png       # optional
  render_job.py           # generated script
  preview.png             # output (served by /image)
  stdout.log, stderr.log
  tryon.json              # {targetId, target, sourceJobId, options}
```

## What is NOT in the contract

- No image bytes on submit — only `sourceJobId`. The backend owns file
  resolution.
- No per-target lighting/exposure controls (scene-owned).
- No normal/roughness generation — diffuse only; normal neutralized when absent.
