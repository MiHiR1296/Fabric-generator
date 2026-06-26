# Blender Live Preview (Cycles)

This folder is the design + working plan for an **interactive Cycles preview
session**: a "live-ish" mode where the user nudges the few exposed weave
controls and gets a high-quality Cycles frame back in a few seconds, rendered
from the **same scene camera** the full render uses — with none of Blender's
viewport chrome (gizmos, overlays, N-panel, outliner) leaking through.

It is **not** a video stream of the Blender viewport, and it is **not** an
EEVEE/workbench approximation. It is the *real* render pipeline run at a faster
speed profile, so what the user sees in the preview is a faithful, lower-cost
prediction of what the full render will produce.

## The use case (why this exists)

The full render is heavy (Cycles, 3200 px, 96 samples — see
[render_jobs.py](../../backend/app/render_jobs.py)). The normal flow is: the
user just hits **Render Preview** and waits.

Live Preview is the **detour** for when the full render comes back wrong:

> The user renders → it isn't what they expected → they enter Live Preview,
> tweak one or two exposed controls (or click a preset) → watch the camera
> frame update → once it looks right, they leave Live Preview and fire the full
> render again.

So the design optimizes for:

- **A handful of control changes per session**, not continuous interaction.
- **Lag is acceptable.** "Live-ish," not 60 fps. A frame every few seconds is
  the target, not a smooth video.
- **Fidelity over framerate.** Cycles, high resolution, same camera, same
  lighting, same materials, same color management as the full render.
- **A fast local machine today, a remote render host tomorrow** (see below).

## Two hard requirements that shape everything

1. **Cycles, high resolution.** No EEVEE substitute. The preview must look like
   the render. Speed comes from a *profile* (resolution, adaptive samples,
   denoise, GPU, persistent data, a time cap), never from a different renderer.
   See [render_profile.md](render_profile.md).

2. **Remote-ready transport.** The render host (Blender) may later live on a
   different machine than the backend. Frames must therefore travel **inside the
   MCP socket response as encoded image bytes** — never via a shared file path.
   The existing live-render path violates this (it reads Blender's output file
   off the backend's own disk); the new path must not. See
   [architecture.md](architecture.md) and
   [decision_log.md](decision_log.md#d2-frames-travel-as-bytes-not-as-a-shared-file-path).

## Read order

1. [architecture.md](architecture.md) — current pipeline, the shared-filesystem
   problem, the proposed transport, the request→render→frame sequence, and the
   local-vs-remote topology.
2. [render_profile.md](render_profile.md) — the exact Cycles live profile,
   quality tiers, persistent-data rules, the geometry-vs-shading dirty matrix,
   kernel warm-up, and color/camera parity with the full render.
3. [presets.md](presets.md) — the two preset layers (render-quality presets and
   weave-control presets) and how each maps to sockets / render settings.
4. [data_contract.md](data_contract.md) — REST endpoints, the MCP frame
   payload, the session model, and the sequence/coalescing protocol.
5. [action_plan.md](action_plan.md) — phase-by-phase implementation plan.
6. [decision_log.md](decision_log.md) — choices made, alternatives rejected.
7. [risks_and_open_questions.md](risks_and_open_questions.md) — what could bite
   us and what still needs a decision or a measurement.
8. [phase_log.md](phase_log.md) — append-only implementation history.

## Source-of-truth rule

This feature does not (yet) mutate `Codex_ParametricWeave.blend`. It only adds a
new render *profile* and a new transport around the existing graph. When docs,
code, and Blender disagree, trust this order:

1. Live Blender MCP readback from `127.0.0.1:9876`.
2. Current generated Python in [render_jobs.py](../../backend/app/render_jobs.py)
   and the new `blender_live_preview.py` (Phase 1).
3. Live/sync code in [blender_live.py](../../backend/app/blender_live.py) and
   [blender_sync.py](../../backend/app/blender_sync.py).
4. These docs and the phase log.

If a phase ever does touch the `.blend`, capture an MCP readback before and
after and append it to [phase_log.md](phase_log.md).

## Status

Design only. No code written yet. Phase 0 (freeze current truth) is captured in
[architecture.md](architecture.md#current-state-2026-06-12); implementation
begins at Phase 1 in [action_plan.md](action_plan.md).
