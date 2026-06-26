# Risks & Open Questions

What could bite us, and what still needs a decision or a measurement before or
during implementation. Each item names how we will resolve it.

## R1 — Main-thread serialization

`execute_code` runs on Blender's main thread, and a Cycles render blocks it for
the whole render. So **no two MCP commands can overlap**: a live frame, a full
render, and a draft sync all contend for the same thread.

Mitigation: a per-session render lock (frontend single-flight on top). The full
render and live preview must also not run at once — entering Live Preview should
disable the full-render button, and vice versa (mirror the existing
`renderActive` gating in
[RenderPanel.tsx](../../frontend/src/components/RenderPanel.tsx#L137)).

Open: confirm the BlenderMCP addon executes `execute_code` synchronously on the
main thread (a timer/modal handler) vs. a worker. Verify by timing overlapping
calls during Phase 1. If it queues internally, our lock is still correct, just
redundant.

## R2 — Socket timeout vs. render time

The default socket timeout is 30 s
([blender_sync.py:28](../../backend/app/blender_sync.py#L28)). A cold first
frame (kernel compile) can exceed that.

Mitigation: `BLENDER_LIVE_PREVIEW_TIMEOUT_SECONDS` (default 120) for the live
path; the warm-up frame absorbs the cold compile during session enter. The
per-tier `time_limit` bounds warm frames well under the socket timeout.

Open: measure the real cold-frame time on the target machine and set the default
timeout with margin.

## R3 — Large base64 over the socket

A high-res frame is a multi-MB base64 body in the JSON response.
`send_blender_command` reads until the buffer parses as JSON
([blender_sync.py:41](../../backend/app/blender_sync.py#L41)), which works but
holds the whole body in memory and retries `json.loads` on every chunk
(O(n²)-ish on a big body).

Mitigation: JPEG keeps frames small (< 1 MB target). If profiling shows the
incremental `json.loads` is costly, switch the live path to a length-prefixed
read or a sentinel-terminated frame rather than parse-on-every-chunk. Local-only
concern today; revisit if it shows up.

Open: is parse-on-every-chunk measurably slow at our frame sizes? Measure in
Phase 1; only optimize if it bites.

## R4 — Persistent data staleness

`use_persistent_data = True` caches the depsgraph/BVH. The assumption is that
Blender re-evaluates changed datablocks so a tweaked frame is never stale.

Risk: a geometry-topology change (Weave Zoom) or a material swap renders against
a stale cache.

Mitigation: trust Blender's dependency invalidation by default; **verify** with
a known A/B (change Weave Zoom, confirm the frame reflects new thread count;
swap a yarn, confirm new material). If any case is stale, force a one-frame
persistent-data flush for geometry-dirty controls (the
[dirty matrix](render_profile.md#persistent-data--the-geometry-vs-shading-dirty-matrix)
already classifies them).

Open: does any exposed control produce a stale frame under persistent data?
Resolve by test in Phase 1/2.

## R5 — GPU device not actually engaged

If the Cycles device isn't set to GPU (or falls back to CPU because no device is
enabled in preferences on the render host), frames are far slower than the tiers
assume.

Mitigation: the live profile sets `compute_device_type` + enables devices +
`scene.cycles.device = 'GPU'`, and the frame payload reports `device`. The
diagnostics endpoint (Phase 6) surfaces a CPU fallback.

Open: which device type per host (`METAL` on the current Mac; `OPTIX`/`CUDA`/
`HIP` on a future remote GPU box) — make it env-driven
(`WEAVE_LIVE_PREVIEW_DENOISER` and a device-type override).

## R6 — Color / framing mismatch between preview and full render

If the live path and full render diverge on camera, world, exposure, or view
transform, the preview lies and the feature loses trust.

Mitigation: factor a shared `_pw_configure_render_scene(...)` used by both; only
the speed profile and film transparency differ
([render_profile.md](render_profile.md#parity-with-the-full-render)). Add a
visual A/B to the verification step.

Open: is the full render's camera setup easily extractable into a shared helper
without disturbing the headless path? Confirm when refactoring in Phase 1.

## R7 — Remote security (the serious one)

Port 9876 is arbitrary remote code execution in Blender. Exposing it to reach a
remote render host turns a preview into an incident.

Mitigation: D7 — private network only (tunnel/VPN), never a public bind; hard
gate in Phase 5 with a deployment checklist.

Open: which private-channel mechanism for the production remote host (managed
tunnel vs. VPN)? Decide before the first remote deploy.

## R8 — Session leakage

A browser that navigates away without calling `DELETE` leaves
`use_persistent_data` on and a cache dir behind.

Mitigation: TTL-reap idle sessions (restore profile, clear cache) like a render
job sweep; restore persistent-data state on reap, not just on explicit exit.

Open: session idle TTL value — start at a few minutes, tune.

## R9 — Concurrency across users

Multiple users (or tabs) hitting one Blender session would interleave renders
and clobber each other's scene state (one `.blend`, one camera, one set of
sockets).

Mitigation: today there is **one** Blender session, so live preview is
effectively single-user. The render lock prevents corruption but not logical
interleaving (user B's settings render into user A's frame).

Open: is concurrent live preview a requirement? If yes, it needs per-user
Blender instances (a render-host pool) — a larger architecture decision, out of
scope for v1. Document the single-session limitation in the UI for now.
