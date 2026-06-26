# Phase Log

Append-only. Newest entries at the bottom. Record what changed, what was
measured, and any MCP readback if a phase ever touches the `.blend`.

---

## 2026-06-12 — Doc set created (design only, no code)

Captured Phase 0 (current truth) and the full design for the Cycles live
preview. No backend/frontend code or `.blend` changes yet.

Findings that shaped the design:

- Full render is `CYCLES` / 3200 px / 96 samples
  ([render_jobs.py](../../backend/app/render_jobs.py), engine at
  [:1087](../../backend/app/render_jobs.py#L1087)).
- The existing live-render path reads Blender's output **off the backend's own
  disk** (`job.render_path.exists()`,
  [render_jobs.py:1431](../../backend/app/render_jobs.py#L1431) /
  [:1489](../../backend/app/render_jobs.py#L1489)) — a shared-filesystem
  assumption that breaks when Blender goes remote. The live preview deliberately
  avoids it (D2): frames return as base64 in the MCP response.
- Exposed controls: Weave Zoom, Spacing, Pattern Noise X/Y, Texture U Scatter,
  Arc 1 V Padding ([RenderPanel.tsx:20](../../frontend/src/components/RenderPanel.tsx#L20)).
- MCP transport already accumulates socket chunks until JSON parses
  ([blender_sync.py:41](../../backend/app/blender_sync.py#L41)); only the 30 s
  timeout needs raising for live.

Key decisions: see [decision_log.md](decision_log.md) (D1–D7). Next step is
Phase 1 in [action_plan.md](action_plan.md) — the `blender_live_preview.py`
transport module.

Numbers still to measure on the target machine (fill in as phases land):

- Cold first-frame time (kernel compile).
- Warm `balanced` frame time (render + transfer), and the same for `draft` /
  `crisp`.
- Geometry-dirty (Weave Zoom) vs. shading-dirty (Arc 1 V Padding) frame cost.
- Typical JPEG frame size per tier.
