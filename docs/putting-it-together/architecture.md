# Architecture — three apps, one shared folder

> **Read this if**: you want a system-level picture of how yarnseamless, Fabric-generator-tryon, and Blender talk to each other; where state lives; what runs on what port.

## The processes

```
┌────────────────────────────┐    ┌──────────────────────────────┐    ┌─────────────────────────┐
│  yarnseamless              │    │  Fabric-generator-tryon      │    │  Blender                │
│  (original reference)      │    │  (studio + yarn authoring)   │    │  (renderer)             │
│                            │    │                              │    │                         │
│  Vite     :5173            │    │  Vite      :5180             │    │  MCP socket :9876       │
│  Node API :3001            │    │  FastAPI   :8000             │    │  Codex_ParametricWeave  │
│  Flask    :3002            │    │  Step 1 ported routes        │    │  .blend                 │
└────────────┬───────────────┘    └────────────────┬─────────────┘    └────────────┬────────────┘
             │                                     │                               │
             │ writes                              │ reads / imports               │ rendered by
             ▼                                     ▼                               │
        ┌──────────────────────────────────────────────────────┐                   │
        │  yarn_library/                                       │ ◀─────────────────┘
        │  └── <yarn_id>/                                      │      Backend pushes
        │       ├── rgba.png                                   │      bandMeta.blender.*
        │       ├── input_thumb.jpg                            │      to modifier sockets
        │       └── metadata.json   (see data_contract.md)     │      to modifier sockets
        └──────────────────────────────────────────────────────┘
```

All processes can run on the same machine. Nothing requires Docker / VMs / Kubernetes — this is a localhost development tool today. The original yarnseamless app can still be used as a reference, but the product flow now runs inside Fabric-generator-tryon's Step 1.

## Why three apps and not one

| App | Responsibility | Why it stays separate |
|---|---|---|
| **yarnseamless** | Original image-science reference: scan → seamless yarn dossier. Multi-thread split, multi-fragment LaMa stitch, alpha matting, dimension extraction. | Kept as source/reference. The yarn workflow used by the product has been ported into Fabric-generator-tryon. |
| **Fabric-generator-tryon** | Yarn authoring + draft authoring + Blender orchestration + Try-On 3D. The "studio". | UX is wizard-style (4 steps) and now owns the end-to-end user flow. |
| **Blender** | Final rendering. Knotty geometry-node graph + materials. | Visible artefact + scriptable via MCP socket. Cannot live inside a web process. |

The split is also what lets us iterate independently — a bug in yarnseamless's alpha math doesn't risk breaking the studio's draft editor.

## The contract between the apps

**Not an HTTP API.** A shared on-disk folder.

```
yarnseamless UI/
├── web/                                  ← yarnseamless code
├── yarn_library/                         ← ★ THE shared contract
│   ├── index.json                        ← append-only registry
│   └── <yarn_id>/{ rgba.png, input_thumb.jpg, metadata.json }
├── Fabric-generator-tryon/               ← studio code
│   ├── backend/                          ← FastAPI on :8000
│   ├── frontend/                         ← Vite on :5180
│   ├── runtime/yarn_assets/<asset_id>/   ← per-project imports
│   ├── runtime/debug/                    ← local-only yarn processing outputs
│   └── Codex_ParametricWeave.blend       ← Blender scene
└── docs/                                 ← yarnseamless docs (unrelated)
```

- yarnseamless can still write to `yarn_library/` (via `web/yarn_library.py:save_to_library`).
- Fabric-generator-tryon's ported Step 1 can also write to `yarn_library/` (via `backend/app/yarnseamless/yarn_library.py:save_to_library`).
- Fabric-generator-tryon reads from `yarn_library/` (via `backend/app/yarn_assets.py:list_library_yarns + import_yarn_from_library`).
- The contract remains file-system based. The original yarnseamless app and the studio do not need to call each other.

**Path resolution**: Fabric-generator-tryon defaults to the sibling folder `../yarn_library/` from this repo. Override with `YARN_LIBRARY_ROOT` when the library lives somewhere else. See [data_contract.md](data_contract.md) for the file shape.

## The request flow: import a library yarn

```
User clicks "Import" in Step 1 of Fabric-generator-tryon
   │
   ▼
POST /api/yarn/library/<yarn_id>/import        (Vite → FastAPI :8000)
   │
   ▼
backend/app/yarn_assets.py:import_yarn_from_library(yarn_id)
   │
   ├──▶ read  ../yarn_library/<yarn_id>/metadata.json
   ├──▶ copy  ../yarn_library/<yarn_id>/rgba.png   →  runtime/yarn_assets/<asset_id>/rgba.png
   ├──▶ split rgba.png → albedo.png (RGB sRGB) + alpha.png (L Non-Color)
   ├──▶ if max(W,H) > CYCLES_MAX_TEXTURE_DIM (16384):
   │        write cycles_safe/{albedo,alpha}_max16384.png
   ├──▶ build bandMeta dict (mirrors metadata + carries the blender block)
   └──▶ persist YarnAsset (status="ready")
   │
   ▼
Returns YarnAsset dict; frontend re-fetches /api/yarn/assets and shows it in the imported grid.
```

Total wall time: < 2 s for a typical 42124×301 yarn.

## Blender side

```
User clicks Preview in Step 3
   │
   ▼
POST /api/blender/render-project   (FabricProject body: draft + yarnAssets + colorBindings)
   │
   ▼
backend/app/render_jobs.py:submit_project_render_job
   │
   ├──▶ For each YarnAsset → build a "material_asset" entry from asset.bandMeta.blender
   ├──▶ Build a Blender Python script (build_headless_render_script)
   ├──▶ Spawn  blender -b Codex_ParametricWeave.blend -P <script>
   │   OR
   │   Push over MCP socket to a running Blender on port 9876
   │
   ▼
Blender:
   ├──▶ Sets Parametric Weave knotty modifier sockets from material_asset entries
   │      (Scanner Pixels Per BU, Material N Arc 1/2 V Min/Max, etc.)
   ├──▶ Loads albedo.png + alpha.png into generated yarn materials (uv_scaled attribute)
   └──▶ Renders → writes PNG → backend serves it back
   │
   ▼
Frontend shows the rendered fabric in Step 3, then Step 4 (Try On 3D) tiles it as a three.js texture.
```

The push-to-Blender code now lives in `backend/app/blender_live.py` and is reused by both headless render scripts and live MCP pushes so the socket mapping cannot drift.

## Ports — full reference

| Process | Port | Purpose | Override |
|---|---|---|---|
| yarnseamless Vite | 5173 | React UI | `vite.config.js` |
| yarnseamless Node | 3001 | Multipart uploads, light proxy | hard-coded |
| yarnseamless Flask | 3002 | LaMa + alpha solver + multithread API | hard-coded |
| Fabric-generator-tryon Vite | 5180 | React UI | `vite.config.ts` |
| Fabric-generator-tryon FastAPI | 8000 | Library + draft + render endpoints | `uvicorn.run(host=, port=)` |
| Blender MCP socket | 9876 | `BlenderMCPAddon` socket server | `BLENDER_PORT` env (default 9875; Makefile pins 9876) |

If two of these collide on your machine, both backends accept the standard env-var overrides.

## Render executor — headless vs live (Phase 3g)

The backend supports two render-execution paths, selected by env var:

| `BLENDER_LIVE_RENDER` | Executor | When to use |
|---|---|---|
| unset / `0` / `false` *(default)* | **Headless** — spawns `blender -b <blend> --python <script>` as a subprocess. The .blend is reopened cleanly each render. | Production. Default behavior. |
| `1` / `true` / `yes` / `on` | **Live MCP** — sends the same Python script body to the open Blender on port 9876 via `BlenderMCPAddon.execute_code`. Renders against the user's current scene. | Dev only — when iterating on the .blend and you want renders to land in the same viewport you're editing. |

Both paths use the same script generation (`build_headless_render_script` in [render_jobs.py](../../backend/app/render_jobs.py)); only the executor differs. The live path locally overrides `BLENDER_TIMEOUT_SECONDS` → `BLENDER_LIVE_TIMEOUT_SECONDS` (default 900s) so long Cycles renders don't TCP-timeout.

One-line Makefile dispatch:

```bash
make backend-dev          # Headless executor (production-shape)
make backend-dev-live     # Live MCP executor (dev-shape; renders into open Blender)
```

See [../BlenderFixes/phase_log.md](../BlenderFixes/phase_log.md) Phase 3g for the full motivation and implementation details.

## Frontend layout — floating chrome + per-step full-page apps

> **Established 2026-05-13 (Phase 2e v4/v5)**, after we tried and failed twice to embed yarnseamless inside the wizard's viewport-locked layout. **This pattern is now the standard** for all four wizard steps.

### The pattern in one sentence

**Each wizard step is its own full-page React app. The only persistent infiknit chrome is a floating sticky header at the top (hero + stepper) and a floating sticky footer at the bottom (Back / advance hint / Next).** Everything between scrolls naturally. No height-locked viewport. No nested cards.

### Why

Each of the four steps is a fundamentally different kind of application:

| Step | What it is | What it needs |
|---|---|---|
| 1 · Yarn Library | Image-processing studio (canvas-heavy, Tailwind-styled) | Full-bleed dark surface, internal scroll for long thread strips, lots of small buttons + overlays |
| 2 · Pattern Builder | Weave-draft editor (grid-heavy, drag-paint) | A tightly-packed draft board with sidebars; viewport-locked is fine here |
| 3 · Render Preview | Color mapping + Blender preview image | Medium info density, mostly form + preview |
| 4 · Try On 3D | three.js scene (full-viewport WebGL) | Maximum viewport for the 3D canvas |

Forcing all four into the same viewport-locked layout was wrong — the yarnseamless editor in Step 1 needs scroll and width that the locked layout can't provide. Each step should opt into the layout that fits it.

### What the chrome is

Two sticky bars, ~60 px each:

```
┌────────────────────────────────────────────────────────────┐
│  Step 1 of 4 · Yarn Library         [Draft Colors: 8]      │ ← .fabric-hero
│                                     [Ready Yarns: 1]       │   compact on Step 1
│  [1·Yarn] [2·Pattern] [3·Render] [4·Try-On]                │ ← .wizard-stepper
├────────────────────────────────────────────────────────────┤
│                                                            │
│                                                            │
│     STEP CONTENT  —  natural-scroll, edge-to-edge          │
│     each step renders its own app here                     │
│                                                            │
│                                                            │
│                                                            │
├────────────────────────────────────────────────────────────┤
│  ← Back                                          Next →    │ ← .wizard-footer
└────────────────────────────────────────────────────────────┘   sticky bottom
```

The hero shrinks to ~50 px on Step 1 (no large `h1`, no summary). The wizard footer becomes `position: sticky; bottom: 0` so the advance button is always reachable even when the editor is taller than the viewport.

### How a step opts in

Two parts:

1. **App.tsx** — when the wizard step needs the full-page layout, add `step-yarnseamless` (or a step-specific class) to the shell:
   ```tsx
   const shellMode = step === 0
     ? 'studio-shell fabric-shell step-yarnseamless'
     : 'studio-shell fabric-shell';
   ```

2. **index.css** — the marker class overrides the viewport-locked rules:
   ```css
   .fabric-shell.studio-shell.step-yarnseamless {
     height: auto;
     min-height: 100vh;
     overflow: visible;
   }
   .fabric-shell.studio-shell.step-yarnseamless .wizard-page,
   .fabric-shell.studio-shell.step-yarnseamless .fabric-step-stack {
     flex: 0 0 auto;
     height: auto;
     overflow: visible;
   }
   .fabric-shell.studio-shell.step-yarnseamless .wizard-footer {
     position: sticky;
     bottom: 0;
     z-index: 30;
     background: rgba(10, 10, 20, 0.92);
     backdrop-filter: blur(8px);
   }
   ```

Steps 2-4 don't get this marker, so they keep the viewport-locked layout that suits them.

### CSS specificity rules of the road

When a step embeds a third-party UI (like the yarnseamless editors), tryon's `.fabric-shell ...` rules will fight with the third-party's class-based styling. Specificity ground rules:

- Tryon's `.fabric-shell input` rules are `(0,1,1)`.
- Third-party Tailwind utilities are `(0,1,0)`.
- Tryon wins by default — the third-party utilities are overridden.

**Fix pattern**: scope a reset using `.fabric-shell .<step-class> <element>` which is `(0,2,1)` and definitively higher than tryon's `(0,1,1)`. Reset the properties tryon sets (background, border, padding, etc.) back to neutral so the utility classes can apply. See the `.fabric-shell .ys-step input` rules at the bottom of [index.css](../../frontend/src/styles/index.css) for the working example.

### Pattern is mandatory for cross-step consistency

Any new step or any future "embed yarnseamless's X into wizard step Y" should follow this pattern:

1. Pick a step-class name (`step-yarnseamless`, `step-tryon3d`, etc.).
2. Add it conditionally on the shell in App.tsx.
3. Add the layout-override block to index.css using `.fabric-shell.studio-shell.step-X` as the prefix.
4. If embedding a third-party Tailwind UI, also scope a Tailwind preflight subset to that subtree (see [data_contract.md](data_contract.md) "Scoped preflight" if we promote that pattern).

This keeps the wizard's floating chrome consistent across all four steps while each step's content area is free to be whatever it needs.

## What is NOT in this architecture

- **No service registry, no message queue.** Adding either would be the right move only if we ever have > 5 of these processes or > 1 user.
- **No auth.** Localhost only.
- **No DB.** State is files. Restart-safe by construction.
- **No Docker.** Adds operational tax without solving any current problem.

If any of these change, write a new architecture.md.
