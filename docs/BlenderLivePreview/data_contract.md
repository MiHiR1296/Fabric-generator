# Data Contract

REST endpoints, the MCP frame payload, the session model, and the
sequence/coalescing protocol. Field names are proposals; lock them when Phase 2
lands and update here.

## Session model

A **session** is the unit that makes persistent data and the warm kernel pay
off. It is created on enter, holds the render profile + the latest frame, and is
torn down on exit (restoring Blender's pre-session state).

```text
LivePreviewSession
  sessionId        str           opaque id (uuid4)
  tier             'draft'|'balanced'|'crisp'
  seq              int           last seq the backend has rendered
  lastFrame        path          runtime/live_preview/<sessionId>/frame.jpg
  lastRenderMs     int
  lock             async lock    serializes frames (main-thread bound)
  priorPersistent  bool          scene.render.use_persistent_data before the session, to restore on exit
  createdAt        iso8601
```

State lives in the backend process (like render jobs). It is **not** persisted
across backend restarts; a dropped session is just re-entered.

## Endpoints

### `POST /api/blender/live-preview/session` — enter

Sync the scene, set the live profile, render the warm-up frame.

Request:
```jsonc
{
  "draft": { /* DraftDocument, as the full render uses */ },
  "bindings": { /* optional project warp/weft material bindings, as render-project uses */ },
  "tier": "balanced"          // optional; defaults to WEAVE_LIVE_PREVIEW_DEFAULT_TIER
}
```

Response:
```jsonc
{
  "sessionId": "9f3c…",
  "seq": 0,
  "frameUrl": "/api/blender/live-preview/session/9f3c…/frame.jpg?seq=0",
  "width": 1280,
  "height": 1280,
  "renderMs": 8200,            // first frame includes cold kernel compile
  "tier": "balanced",
  "status": "ok"              // or "error" with "message"
}
```

### `POST /api/blender/live-preview/session/{sessionId}/frame` — tweak

Apply changed settings, render one frame under the lock.

Request:
```jsonc
{
  "seq": 3,                    // monotonically increasing, assigned by frontend
  "settings": {                // Partial<DraftRenderSettings> — only what changed
    "spacing": 0.04,
    "arc1VPadding": 0.03
  },
  "controlPreset": "loose-drape",  // optional; if set, expands to a settings bundle
  "tier": "balanced"          // optional; switch tiers mid-session
}
```

Response:
```jsonc
{
  "sessionId": "9f3c…",
  "seq": 3,
  "frameUrl": "/api/blender/live-preview/session/9f3c…/frame.jpg?seq=3",
  "width": 1280,
  "height": 1280,
  "renderMs": 2140,
  "tier": "balanced",
  "status": "ok"              // "ok" | "coalesced" | "error"
}
```

- `status: "coalesced"` — a newer `seq` superseded this one before it rendered;
  the response points at the newest frame, not a stale render. (Only emitted if
  the backend does server-side coalescing; with strict frontend single-flight it
  is rare.)

### `GET /api/blender/live-preview/session/{sessionId}/frame.jpg?seq=N` — fetch

Returns the cached frame bytes (`Content-Type: image/jpeg`). The `seq` query
param is for cache-busting and stale-drop on the client; the backend serves the
latest cached frame for the session. 404 if the session is unknown or no frame
yet.

### `DELETE /api/blender/live-preview/session/{sessionId}` — exit

Restores `scene.render.use_persistent_data` to `priorPersistent`, restores the
full-render profile, clears the cache dir. Idempotent.

Response: `{ "status": "closed" }`.

## MCP frame payload (Blender → backend)

What the live-preview script `print`s; the backend parses it from the
`execute_code` response. **No file path crosses the boundary** — the image rides
as base64.

```jsonc
{
  "status": "success",         // or "error" + "message"
  "seq": 3,
  "format": "jpeg",
  "width": 1280,
  "height": 1280,
  "render_ms": 2140,
  "engine": "CYCLES",
  "device": "GPU",
  "samples_used": 41,          // adaptive sampling may stop below the ceiling
  "denoised": true,
  "time_limited": false,       // true if the time_limit safety cap was hit
  "image_b64": "<base64 of the jpeg bytes>"
}
```

Transport notes:

- `send_blender_command` accumulates socket chunks until the JSON parses
  ([blender_sync.py:41](../../backend/app/blender_sync.py#L41)), so a multi-MB
  body works — but use `BLENDER_LIVE_PREVIEW_TIMEOUT_SECONDS` (default 120), not
  the 30 s default.
- Keep `image_b64` small: JPEG per-tier quality, target < 1 MB at 1280 px. This
  is what makes the future WAN link tolerable.
- `time_limited: true` is a signal to the UI ("frame capped — bump the tier or
  wait for the full render") and a tuning signal for us.

## Sequencing & coalescing

Goal: a flurry of control nudges must never queue a backlog of renders, and a
stale frame must never flash over a newer one.

**Frontend (authoritative for ordering):**

1. Debounce control edits ~300 ms after the last change.
2. Assign a monotonically increasing `seq` to each frame request.
3. **Single flight:** at most one frame request outstanding. If the user changes
   something while a request is in flight, set a `dirty` flag with the newest
   settings; on completion, if `dirty`, fire one more request with the newest
   values.
4. **Latest-wins:** ignore any response whose `seq` is older than the highest
   `seq` already displayed.

**Backend (safety):**

- A per-session **render lock** serializes `execute_code` renders so they never
  overlap (main-thread constraint — see
  [risks_and_open_questions.md](risks_and_open_questions.md#r1-main-thread-serialization)).
- Optional server-side coalescing: if a request arrives while the lock is held
  and a newer `seq` is already queued, drop the older one and return
  `status: "coalesced"` pointing at the newest frame.

The two layers compose: the frontend keeps it to one in-flight request in the
common case; the backend lock guarantees correctness even if two clients or a
stray retry race.

## Reused request shapes

The session/frame bodies intentionally mirror the existing full-render request
models in [main.py](../../backend/app/main.py) (`BlenderRenderRequest`,
`ProjectRenderRequest`) and the `DraftRenderSettings` type in
[frontend/src/domain/types.ts](../../frontend/src/domain/types.ts), so the live
path and the full render accept the same draft/bindings/settings and cannot
drift on meaning.
