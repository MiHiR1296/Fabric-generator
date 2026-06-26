# Decision Log

Choices made for the live preview, with the alternative that was rejected and
why. Append new decisions; do not rewrite old ones — supersede them.

## D1 — Live preview is the full render pipeline at a speed profile, not a second renderer

Decision: render live frames in **Cycles**, reusing the full render's camera,
world/HDRI, materials, and color management. Speed comes from a profile
(resolution, adaptive samples, denoise, GPU, persistent data, time limit).

Rejected: an EEVEE or `render.opengl()` workbench preview. It would be faster but
would **not predict the Cycles render** — colors, shadows, and fiber/halo
shading differ. The entire use case is "decide whether the full render will look
right," so a non-Cycles preview defeats the purpose.

Consequence: frames cost seconds, not milliseconds. Accepted — the use case is
"live-ish, a few tweaks," explicitly tolerant of lag.

## D2 — Frames travel as bytes, not as a shared file path

Decision: the Blender-side script renders to a temp path **on the render host**,
reads the bytes, JPEG-encodes, base64s, and returns them in the `execute_code`
response. The backend decodes to its **own** local cache and serves that.

Rejected: the existing live-render approach — Blender writes
`scene.render.filepath`, the backend reads that same path
([render_jobs.py:1431](../../backend/app/render_jobs.py#L1431)). It only works
because both share a disk. The user is going remote, so this is a dead end for
the new feature.

Consequence: one code path for local and remote; remote needs only a
`BLENDER_HOST` change. Cost: base64/transfer overhead even locally — paid
deliberately to avoid a second code path.

## D3 — JPEG transport, film transparency off

Decision: encode preview frames as **JPEG** (per-tier quality, target < 1 MB at
1280 px) and render with `film_transparent = False` so the world background
shows.

Rejected: PNG with alpha (matches the full render's tiling output). PNG is
several× larger — punishing on a WAN link — and a transparent swatch is hard to
read as a live preview. A lit background reads like a real fabric swatch.

Consequence: the preview's background differs from a transparent full render.
Documented as an intentional difference
([render_profile.md](render_profile.md#intentional-documented-differences)). If
alpha preview is ever needed, add a PNG tier rather than bending JPEG.

## D4 — A session, not one-shot renders

Decision: enter/frame/exit endpoints with a backend-held session. Enter sets
persistent data on + renders a warm-up frame; exit restores prior state.

Rejected: stateless one-shot frame calls. Without a session, every frame pays
kernel warm-up and loses persistent data — the two biggest speedups
([render_profile.md](render_profile.md#what-makes-cycles-fast-enough-for-live-ish)).

Consequence: a small amount of server state (like render jobs) and a teardown
obligation (restore `use_persistent_data`). Worth it for warm, cheap frames.

## D5 — Latest-wins single-flight, not a render queue

Decision: the frontend debounces, keeps one request in flight, tags `seq`, and
drops stale responses; the backend serializes with a per-session lock.

Rejected: queueing every control change as its own render. A flurry of nudges
would back up a queue of stale renders the user no longer cares about, each
blocking Blender's main thread.

Consequence: some intermediate states are never rendered (skipped to the
latest). Correct for "show me where I ended up," which is the live-tweak intent.

## D6 — Reuse the existing apply/sync bodies

Decision: the live-preview script composes `APPLY_METADATA_PY`
([blender_live.py](../../backend/app/blender_live.py)) and
`build_blender_sync_code` ([blender_sync.py](../../backend/app/blender_sync.py))
rather than re-implementing socket/draft application.

Rejected: a bespoke live apply path. It would drift from the full render's
socket mapping — the exact class of bug
[blender_live.py](../../backend/app/blender_live.py) was written to prevent
("the two code paths cannot drift").

Consequence: live and full apply identically; only the speed profile differs.

## D7 — The MCP socket stays private; remote access is a hard gate

Decision: port 9876 (`execute_code` = arbitrary Python in Blender) is never
exposed on a public interface. Remote reaches it only over SSH tunnel /
WireGuard / Tailscale or a loopback bind behind an authenticated relay.

Rejected: binding the MCP socket to a routable address for the remote backend to
reach directly. That is an open remote shell into the render host.

Consequence: a deployment checklist gating any non-localhost run
([action_plan.md](action_plan.md#phase-5--remote-hardening-gate-before-any-remote-deploy)).
