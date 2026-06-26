# Try-On 3D Render — decision log

### D1. Fabric texture source = Step-3 seamless tile (preferred), flat render (fallback)

The drape material samples a *tileable* texture across a curved surface, so the
seam-repaired tile export from Step 3 is the correct source. When no tile exists
yet we fall back to the flat render-preview image so the user still gets
something. The frontend passes the **job id**, not bytes; the backend resolves
the file. Why: keeps the wire format tiny, reuses the job's on-disk image, and
avoids re-uploading large PNGs.

### D2b. Targets toggle collections; the camera is left as authored (2026-06-15)

**Supersedes the camera-framing parts of D2/D7.** First pass isolated objects by
per-mesh show/hide and auto-framed the camera (fit to bounding sphere). User
feedback: the authored camera angle is *intentional* — the slight crop and angle
are the desired look — and the scene is organized so each object lives in its own
collection. So a target now just names the collection(s) to enable; the render
keeps the camera's collection, excludes the rest, and **never moves the camera**.
This also matches how the artist works the file (toggling collections per shot)
and removes the fragile bounding-sphere fit entirely. Objects whose collection
the artist excluded from the view layer are re-enabled for their render.

### D2. Targets are data-driven, not hardcoded UI

A catalog (code default + `Renders/tryon_targets.json` override) defines the
selectable objects. Why: `Objects.blend` is an evolving art file. An artist can
add a draped garment + camera and expose it as a target by editing JSON, with no
frontend/backend code change. The default catalog is seeded from the meshes that
exist today (cloth, cushion, full scene).

### D3. Sequential single-worker render queue

All selected targets submit at once, but a single worker thread renders them
FIFO, one Blender process at a time. Why: (a) the user explicitly asked for "one
at a time"; (b) parallel full-scene Cycles renders would thrash CPU/RAM and make
every render slower; (c) progressive display falls out naturally — each job
finishes and its card updates while the rest stay queued.

### D4. Try-On renders are always headless against Objects.blend

Even when `BLENDER_LIVE_RENDER=1`, Try-On does not use the live MCP session. Why:
the open Blender session holds `Codex_ParametricWeave.blend` (the weave
generator), not `Objects.blend`. Routing Try-On there would render the wrong
scene and disturb the user's open file. Headless also lets Try-On run while the
artist keeps working in the weave session.

### D5. Reuse the existing RenderJob registry + endpoints

Try-On jobs are ordinary `RenderJob` entries, so `GET /render-jobs/{id}` and
`/image` serve them unchanged, and the frontend reuses `fetchDraftRenderJob` +
the `BlenderRenderJob` type. Why: less surface area, consistent polling/UX, and
the job dir layout (`preview.png`, logs) already matches.

### D6. Namespace endpoints under `/api/blender/tryon`

Rather than a new `/api/tryon` root (which would need a new vite proxy entry),
Try-On endpoints live under `/api/blender`, already proxied. Why: zero proxy/
config churn.

### D7. Normal map neutralized when absent

We apply only a diffuse today. Rather than leave the previous pattern's normal
(`3x1_Normal.png`) bleeding through, the script sets the Normal Map node strength
to 0 when no normal is supplied. Why: correctness over fidelity for the MVP; a
real weave-derived normal/roughness set is a future enhancement.

### D8. Keep the old three.js step? No — replace it

The procedural torso/sofa was a placeholder. The new step is the real feature.
We remove the fake-model code path. The instant in-browser tiling is lost, but
the Blender drape is the actual deliverable the manual `TMPrenders` workflow was
producing. (If a fast in-browser preview is wanted later, it can come back as a
secondary tab.)

### D9. Commit `Renders/Objects.blend`, keep generated renders ignored

The Try-On backend defaults to `Renders/Objects.blend`; without that scene, a
fresh clone can list targets but cannot render them. The scene is small enough
for normal Git in this repository, so it is tracked beside
`Codex_ParametricWeave.blend`. Generated outputs under `Renders/` (`*.png`,
`*.exr`, `TMPrenders/`, autosaves) remain ignored because they are local render
products, not source assets.
