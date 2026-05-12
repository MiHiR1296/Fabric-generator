# Live Preview Worklog

## Goal

Build a staged Blender Material Preview workflow inside the web app:

- expose the practical preview controls needed for web review while keeping warp/weft thread counts fixed to the default
- let the user change them in the web UI without immediately touching Blender
- send the batch only when the user clicks `Preview`
- refresh the web UI with a camera-framed Material Preview image from Blender

This is intentionally lighter than a continuous live render session.

## Current Implementation

### Backend

- Added `POST /api/blender/live-preview`
- Added `GET /api/blender/live-preview/{session_id}`
- Added `GET /api/blender/live-preview/{session_id}/image`
- Added managed Blender session lifecycle support:
  - `GET /api/blender/session`
  - `POST /api/blender/session/restart`
  - `POST /api/blender/session/stop`
- Added `runtime/live_preview/` storage for preview screenshots and per-session project snapshots
- Added `backend/app/live_preview.py` to:
  - validate the project draft and color bindings
  - resolve ready yarn assets
  - build material assignments from the processed diffuse/alpha outputs
  - push the update into the connected Blender session
  - render a camera-framed preview image directly from Blender's active camera
- Expanded the Blender sync payload so the backend can pass the staged preview settings into Blender:
  - spacing, mapped from UI `0..1` to Blender `0.03..0.10`
  - pattern noise X/Y, mapped from UI `0..1` to Blender `0.00..0.03`
  - warp/weft threads remain fixed to at least `180`
- Added `backend/app/blender_session.py` so Blender can be:
  - launched on demand in `managed` mode
  - reused while the user is active
  - stopped automatically after an idle timeout
  - restarted after transport-level socket failures
- Added `backend/app/blender_session_startup.py` so backend-managed Blender launches:
  - enable `BlenderMCPAddon`
  - set the configured socket port
  - start the BlenderMCP socket server automatically

### Frontend

- Step 3 now uses a lazy preview flow instead of the queued render-job flow
- The preview panel stages control edits locally
- Blender is updated only when the user clicks `Preview`
- The returned screenshot is shown directly in the Step 3 panel
- The preview panel exposes only the current practical controls: spacing and pattern noise X/Y
- New drafts default warp/weft counts to at least `180`, and imported/older drafts are normalized upward to that floor before preview without showing those count fields in the UI

### Material Handling

- For live preview and render jobs, the backend now creates clean generated yarn materials instead of copying a preset material from the Blender file
- Each generated material loads the processed diffuse texture from the uploaded yarn asset and wires it to the shader base color
- Each generated material also loads the processed alpha texture as non-color data for future use and traceability
- The render script assigns generated materials through the geometry-node material path: it fills modifier `Material N` sockets when they exist, applies warp/weft material-cycle inputs when available, and falls back to the `Weave From Draft` material-id chain only for older/non-knotty node groups
- `Codex_ParametricWeave.blend` now keeps the `Parametric Weave knotty` per-yarn material selector and UV metadata nodes permanently in the file
- The backend fills persistent sockets such as `Material N Image Width Px`, `Material N Texture Scale U`, `Material N Core V Min/Max`, and the flipped outer fiber-band sockets from each processed yarn asset
- The backend also pins the knotty V mapping controls to the scan defaults: `Texture Scale V = 1`, `Texture Offset V = 0`, `Texture Side Flatten = 0`, `Sub Texture Scale V = 0`, and `Sub Texture Offset V = 0`. The sub-texture values are additive deltas for Arc 2, so `Sub Texture Scale V = 1` incorrectly doubles the Arc 2 V scale.
- The live render no longer creates temporary `Web Material UV` or `Web Material Assign` nodes
- The generated preview materials load the alpha map into shader alpha. The geometry still defines the main yarn silhouette, while the alpha image preserves scan cutout detail where the material graph uses it.
- This avoids the failure mode where a changed yarn upload still appears to render with the Blender file's preset material

## Local Testing Workflow

1. Open `Codex_ParametricWeave.blend` in Blender.
2. Start the Blender MCP/socket bridge.
3. Run the backend from `backend/`.
4. Run the frontend from `frontend/`.
5. Upload yarn assets in Step 1 and wait until they are `ready`.
6. Build or import the draft in Step 2.
7. Assign yarns and adjust preview controls in Step 3.
8. Click `Preview`.

Expected result:

- Blender applies the draft/material changes
- Blender renders the camera directly from the managed session
- the backend writes a camera preview image
- the browser refreshes the Step 3 preview image

## Session Lifecycle

Current default backend mode is `managed`:

- first Blender-backed request can launch Blender automatically
- repeated requests reuse the warm session for faster preview updates
- if the user is idle, the backend stops Blender after `BLENDER_IDLE_TIMEOUT_SECONDS`

Fallback mode is `attach`:

- the backend expects Blender to already be running
- the backend does not launch or stop Blender

Managed mode now also supports a launch wrapper through `BLENDER_LAUNCH_PREFIX`, which is useful for terminal-only Linux hosts where Blender needs to start inside `xvfb-run`.

This split is useful because:

- `managed` is the right default for the future server deployment
- `attach` stays useful while editing the `.blend` manually during development

## Known Constraints

- The staged live preview path now supports up to 16 distinct yarn assets directly. This covers the expected 8x8 draft color-binding workflow while still leaving larger final renders to the atlas path.
- The atlas-based render path still exists for larger final renders
- This is a screenshot refresh workflow, not a continuous interactive stream
- A real Blender GUI session is still required for the Material Preview capture path
- The preview request now applies its `max_size` value to Blender render resolution. The current default is `2400`, which avoids stretching a low-resolution scene render in the browser.

## Server Rollout Direction

For the later H100 deployment, the current direction is:

- run Blender in a managed GUI-capable session on the server
- provide a virtual display instead of relying on a physical monitor
- keep the same lazy `Preview` request cycle from the web UI
- use camera-framed Material Preview images for quick feedback
- reserve heavier background renders for final confirmation output

## Setup Automation

The repo now includes:

- `scripts/setup_doctor.py`
  - inspects the host machine
  - reports missing Python, Node, Blender, and optional server helpers
  - prints the current backend and frontend dependency manifests
- `scripts/bootstrap.py`
  - creates the backend virtualenv
  - installs `backend/requirements.txt`
  - runs `npm install`
  - optionally installs the Playwright Chromium browser
  - optionally attempts a package-manager Blender install

That gives us a repeatable first-run workflow to hand to teammates before we debug Blender-specific issues.
