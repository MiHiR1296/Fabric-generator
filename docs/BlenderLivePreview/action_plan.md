# Action Plan

## Goal

Add an interactive **Cycles** live-preview session so a user can tweak the few
exposed weave controls (or pick a preset) and see a high-quality, camera-framed
frame return in a few seconds — built so it works unchanged when Blender later
moves to a remote render host.

The plan separates the **transport** (return frames as bytes; remote-safe) from
the **render profile** (Cycles speed tiers) from the **UX** (session + presets),
so each can land and be verified independently. No phase mutates
`Codex_ParametricWeave.blend`.

## Phase 0 — Freeze current truth

Status: done (captured in [architecture.md](architecture.md#current-state-2026-06-12)).

Actions:

- Record that the full render is `CYCLES` / 3200 / 96 and writes to
  `scene.render.filepath`.
- Record that the existing live-render path reads Blender's output **off the
  backend's own disk** (`job.render_path.exists()`), i.e. assumes a shared
  filesystem — the remote blocker this feature must avoid.
- Record the exposed control surface from
  [RenderPanel.tsx](../../frontend/src/components/RenderPanel.tsx).

Acceptance: current_state captured; the shared-FS assumption is named before we
build around it.

## Phase 1 — Backend: remote-safe frame transport

Status: planned (first to build).

Actions:

- New module `backend/app/blender_live_preview.py`:
  - `build_live_preview_script(draft, bindings, profile, seq)` → Python body
    that, on the Blender host: applies sockets (reuse `APPLY_METADATA_PY` from
    [blender_live.py](../../backend/app/blender_live.py) and
    `build_blender_sync_code` from
    [blender_sync.py](../../backend/app/blender_sync.py)), sets the live Cycles
    profile ([render_profile.md](render_profile.md)), renders to a temp path
    **on that host**, reads the bytes, JPEG-encodes, base64s, and prints the
    frame payload JSON.
  - `render_live_frame(...)` → `send_blender_command("execute_code", ...)` with
    the raised timeout, parse the payload, return `{bytes, width, height,
    render_ms, seq}`.
  - A per-session render lock; latest-wins coalescing helper.
- Raise the socket timeout for live via `BLENDER_LIVE_PREVIEW_TIMEOUT_SECONDS`
  (default 120) — independent of the 30 s default in
  [blender_sync.py:28](../../backend/app/blender_sync.py#L28).
- Backend-local frame cache under `runtime/live_preview/<sessionId>/`.

Reasoning: the frame must come home **in the socket response**, decoded and
cached on the backend, so nothing depends on a shared disk. Reusing the existing
apply/sync bodies guarantees live and full never drift on how the scene is set
up.

Acceptance:

- A unit/integration call renders a frame against a local Blender and returns
  decoded JPEG bytes with `width`/`height`/`render_ms`, **without** the backend
  reading any path Blender wrote.
- With Blender pointed at a non-shared path for its temp output, the backend
  still returns the frame (proves no shared-FS dependency).

## Phase 2 — Backend: session + frame REST endpoints

Status: planned.

Actions: implement the routes in [data_contract.md](data_contract.md):

- `POST /api/blender/live-preview/session` — sync draft + push materials, set
  live profile + persistent data on, render warm-up frame, return `sessionId` +
  first `frameUrl`.
- `POST /api/blender/live-preview/session/{id}/frame` — apply changed settings,
  render one frame under the lock, cache, return `{seq, frameUrl, renderMs}`.
- `GET /api/blender/live-preview/session/{id}/frame.jpg?seq=N` — serve cached
  bytes.
- `DELETE /api/blender/live-preview/session/{id}` — restore prior profile /
  persistent-data setting, clear cache.

Reasoning: a session lets persistent data and the warm kernel pay off across
frames, and gives a clean place to restore Blender's state on exit.

Acceptance: enter → frame×N → exit works end-to-end against local Blender;
`scene.render.use_persistent_data` is restored to its pre-session value on
`DELETE`; no orphaned cache dirs.

## Phase 3 — Frontend: live preview mode

Status: planned.

Actions:

- `LivePreviewPanel.tsx` (or a mode toggle inside
  [RenderPanel.tsx](../../frontend/src/components/RenderPanel.tsx)): **Enter
  Live Preview** / **Exit**, a render-quality selector (draft/balanced/crisp),
  the existing control inputs, and a frame `<img>` with a subtle "rendering…"
  indicator + last `renderMs`.
- Debounce control changes (~300 ms after the last edit), single request in
  flight, increasing `seq`, latest-wins frame swap (drop stale `seq`). Protocol:
  [data_contract.md](data_contract.md#sequencing--coalescing).
- "Exit → Render Preview" hands back to the existing full-render button so the
  detour returns cleanly to the main flow.

Reasoning: the UX must encode "a few tweaks, then leave" — debounce + latest-wins
keeps a flurry of nudges from queuing a backlog of renders.

Acceptance: nudging a control updates the frame within the tier budget; rapid
changes never queue more than one in-flight render; stale frames never flash;
exiting restores the normal render panel.

## Phase 4 — Presets

Status: planned (can land alongside Phase 3).

Actions: implement both preset layers from [presets.md](presets.md):

- **Render-quality presets** (draft/balanced/crisp) — already a tier selector.
- **Weave-control presets** — named bundles of the exposed control values
  (e.g. "Tight Plain", "Loose Drape") as a frontend domain table; clicking one
  stages all its values and fires a single frame.

Reasoning: the user explicitly wants to avoid dialing raw numbers; a preset is
one click → one frame.

Acceptance: selecting a control preset applies all its values and renders one
frame; presets live in a single declarative table that is easy to extend.

## Phase 5 — Remote hardening (gate before any remote deploy)

Status: planned; **hard gate** — must pass before Blender runs off-box.

Actions:

- Confirm the data path needs **no change** for remote (frames already come back
  as bytes); only `BLENDER_HOST` moves.
- Document and enforce that port 9876 (`execute_code` = arbitrary RCE) is
  **never** on a public interface: reach the render host only via SSH
  tunnel / WireGuard / Tailscale, or loopback-bind behind an authenticated
  relay.
- Add a transfer-size budget check and per-tier JPEG quality so WAN frames stay
  small (target < 1 MB at 1280 px).
- Measure real end-to-end latency (render + transfer) on the remote link and
  record it.

Reasoning: the socket is a remote shell into Blender. Exposing it is the one
mistake that turns a preview feature into an incident.

Acceptance: a documented private-network requirement with a deployment checklist;
measured remote latency per tier in [phase_log.md](phase_log.md); no public bind
of 9876.

## Phase 6 — Diagnostics (optional, follow-on)

Status: planned, low priority.

Actions: extend or add a diagnostics endpoint reporting MCP reachability, active
Cycles device, persistent-data state, current tier, last `renderMs`, and last
frame bytes — so a slow/odd preview is debuggable without ad-hoc MCP scripts.

Acceptance: one API call explains why a frame was slow (cold kernel? CPU
fallback? geometry-dirty tweak? big transfer?).
