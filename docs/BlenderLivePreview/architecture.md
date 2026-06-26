# Architecture

## The three processes

```
Frontend (React/Vite)        Backend (FastAPI, app.main)        Blender (GUI app)
  RenderPanel.tsx              main.py / render_jobs.py            BlenderMCP addon
  + LivePreviewPanel           + blender_live_preview.py           TCP socket :9876
        (browser)                  (HTTP server)                  execute_code handler
```

The backend is a **client** of Blender. Everything reaches Blender through one
primitive: `send_blender_command("execute_code", {"code": <python>})` in
[blender_sync.py:32](../../backend/app/blender_sync.py#L32). The addon runs that
Python inside the live session and returns a JSON object over the socket.

Blender is launched separately as a normal GUI app with the MCP addon listening
on port 9876 (`BLENDER_PORT`). The backend connects as needed; it does not own
the Blender process.

## Current state (2026-06-12)

Frozen truth before this feature is built:

- **Full render** ([render_jobs.py](../../backend/app/render_jobs.py)) is
  `CYCLES`, `resolution = 3200`, `samples = 96`
  (`DEFAULT_PREVIEW_RENDER_RESOLUTION`, `DEFAULT_PREVIEW_RENDER_SAMPLES`,
  engine set at [render_jobs.py:1087](../../backend/app/render_jobs.py#L1087)).
  It writes a PNG to `scene.render.filepath`.
- **Two ways the render reaches Blender**, gated by `_is_live_render_mode()`
  (`BLENDER_LIVE_RENDER=1`, which `scripts/dev_services.sh` sets in dev):
  - **Headless** (default/production): spawn a `Blender -b` subprocess on a
    `.blend` copy, render to a job dir, poll the file.
  - **Live** (dev): `send_blender_command("execute_code", ...)` into the open
    session, which writes the PNG to `scene.render.filepath`.
- **Live values without a render**: `push-bandmeta` /
  `push-project-bandmeta` apply sockets to the open viewport instantly
  ([blender_live.py:354](../../backend/app/blender_live.py#L354)). No image
  comes back — you only see the change if you are looking at Blender yourself.
- **Exposed controls** ([RenderPanel.tsx:20](../../frontend/src/components/RenderPanel.tsx#L20)):
  Weave Zoom (warp/weft thread count), Spacing, Pattern Noise X, Pattern Noise
  Y, Texture U Scatter (`uvRandomU`), Arc 1 V Padding. That is the entire
  surface the live preview has to react to.

### The problem with the existing "live" path (the remote blocker)

In live-render mode the backend ships the render code, then checks
`job.render_path.exists()` **on its own filesystem** and serves that file
([render_jobs.py:1431](../../backend/app/render_jobs.py#L1431),
[:1489](../../backend/app/render_jobs.py#L1489),
[get_render_image_path:2178](../../backend/app/render_jobs.py#L2178)).

That only works because Blender wrote the PNG to a path the backend can also
read — i.e. **they share a disk.** The moment Blender moves to another machine,
`scene.render.filepath` is a path on the *render host*, and the backend's
`exists()` check fails. The output never comes home.

**Conclusion:** the live preview must not inherit this assumption. It pioneers a
transport that returns the frame *in the socket response*. (The full render can
adopt the same transport later; out of scope here.)

## Proposed transport: frame bytes ride the socket

The MCP `execute_code` response is a JSON object built from what the script
prints. So the live-preview script does, all on the Blender host:

1. Apply the changed sockets (reuse `APPLY_METADATA_PY` /
   `build_blender_sync_code`) — milliseconds.
2. Set the **live Cycles profile** (see [render_profile.md](render_profile.md)).
3. `bpy.ops.render.render(write_still=True)` to a temp path **on the render
   host** (e.g. `/tmp` there — never assumed visible to the backend).
4. Read those bytes back, **JPEG-encode** for transport, base64 them.
5. `print(json.dumps({... "image_b64": <b64>}))`.

The backend decodes the base64, writes it to its **own** local cache
(`runtime/live_preview/<sessionId>/frame.jpg`), and serves that to the browser
via a normal image URL. No shared filesystem anywhere in the path.

`send_blender_command` already accumulates socket chunks until the JSON parses
([blender_sync.py:41-53](../../backend/app/blender_sync.py#L41)), so a multi-MB
base64 body works as-is — but the 30 s default timeout must be raised for live
(`BLENDER_LIVE_PREVIEW_TIMEOUT_SECONDS`, default 120). JPEG keeps the body small
(target < 1 MB at 1280 px), which matters on a future WAN link.

## Request → render → frame sequence

```
Frontend                    Backend                         Blender (:9876)
   |                            |                                  |
   | enter live mode            |                                  |
   | POST /live-preview/session |                                  |
   | {draft, bindings, quality} |                                  |
   |--------------------------->| sync draft + push materials      |
   |                            | set live profile + persistent on |
   |                            | execute_code (warm-up render) --->| compile kernels (cold)
   |                            |                                  | cycles render
   |                            |   {seq:0, w,h, ms, jpeg_b64} <----| jpeg+b64
   |                            | cache frame.jpg, store session   |
   |  {sessionId, frameUrl,seq0}|                                  |
   |<---------------------------|                                  |
   | show <img src=frameUrl>    |                                  |
   |                            |                                  |
   | user nudges Spacing        |                                  |
   | (debounce ~300ms)          |                                  |
   | POST .../frame {settings,  |                                  |
   |        seq:1, quality}      |                                  |
   |--------------------------->| acquire render lock (serialize)  |
   |                            | execute_code (apply + render) -->| apply sockets (ms)
   |                            |                                  | cycles render (warm, fast)
   |                            |   {seq:1, w,h, ms, jpeg_b64} <----| jpeg+b64
   |                            | cache frame.jpg, release lock    |
   |  {seq:1, frameUrl, ms}     |                                  |
   |<---------------------------|                                  |
   | swap <img> (drop if stale) |                                  |
   |                            |                                  |
   | exit live mode             |                                  |
   | DELETE /live-preview/...   | restore full profile, persistent off,
   |--------------------------->| cleanup cache                    |
```

Key properties:

- **One render at a time.** `execute_code` runs on Blender's main thread, and a
  Cycles render blocks it. The backend holds a per-session render lock so frames
  never overlap each other (or a full render, or a sync). See
  [risks_and_open_questions.md](risks_and_open_questions.md#r1-main-thread-serialization).
- **Latest-wins.** The frontend debounces, keeps a single request in flight,
  and tags each with an increasing `seq`. If the user changes a value mid-render,
  it re-fires on completion with the newest settings and ignores any response
  whose `seq` is older than what is already displayed. Protocol in
  [data_contract.md](data_contract.md#sequencing--coalescing).
- **Live = full pipeline, minus speed.** Same camera, world/HDRI, materials,
  color management. The only intentional differences are the speed profile and
  film transparency (the preview shows the world background for legibility).
  See [render_profile.md](render_profile.md#parity-with-the-full-render).

## Topology: local now, remote later

### Local (today)
Backend and Blender on one machine; `BLENDER_HOST=127.0.0.1`. The base64
transport is mild overhead vs. a shared file, but we pay it anyway so there is
**one** code path and remote needs no rewrite.

### Remote (planned)
Backend (cloud/服务) ⟶ render host (a fast GPU machine running Blender).
`BLENDER_HOST` points at the render host. Frames already come back as bytes, so
nothing in the data path changes. Two things become mandatory:

- **The MCP socket is arbitrary remote code execution.** `execute_code` runs any
  Python in Blender. Port 9876 must **never** be exposed on a public interface.
  Reach it only over a private channel — SSH tunnel, WireGuard/Tailscale, or a
  loopback bind behind an authenticated relay. This is a hard gate before any
  non-localhost deploy; see
  [action_plan.md](action_plan.md#phase-5--remote-hardening-gate-before-any-remote-deploy).
- **Transfer time joins the latency budget.** On LAN it is negligible; on WAN,
  JPEG size and round-trip dominate. Quality tiers (resolution + JPEG quality)
  are the lever; the "live-ish, lag is OK" tolerance absorbs the rest.

## New code surface (Phase 1+)

- `backend/app/blender_live_preview.py` — builds the live-preview script
  (apply + live profile + render + read + jpeg + b64), sends it, decodes, owns
  the render lock and the session cache. Reuses `APPLY_METADATA_PY` and
  `build_blender_sync_code` so live and full cannot drift on how sockets/draft
  are applied.
- `main.py` routes — `POST /api/blender/live-preview/session`,
  `POST .../session/{id}/frame`, `GET .../session/{id}/frame.jpg`,
  `DELETE .../session/{id}`. See [data_contract.md](data_contract.md).
- `runtime/live_preview/<sessionId>/` — backend-local frame cache (sibling of
  `runtime/render_jobs/`).
- `frontend/src/components/LivePreviewPanel.tsx` (or a mode inside
  `RenderPanel`) — enter/exit, quality selector, control presets, debounced
  frame fetch, latest-wins `<img>` swap.

A shared scene-config helper (camera, world, color management) should be
factored out of the full-render script so both paths configure the scene
identically and only the speed profile differs.
