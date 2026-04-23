# Live Preview Worklog

## Goal

Build a staged Blender Material Preview workflow inside the web app:

- expose the key geometry/material controls from the Blender node setup
- let the user change them in the web UI without immediately touching Blender
- send the batch only when the user clicks `Update Preview`
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
  - render a camera-framed Material Preview image
- Expanded the Blender sync payload so the web app can drive:
  - warp/weft threads
  - spacing/amplitude/fill ratio
  - thread and ply settings
  - texture mapping controls
  - lump/fiber/detail settings
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
- Blender is updated only when the user clicks `Update Preview`
- The returned screenshot is shown directly in the Step 3 panel
- The preview panel is grouped into:
  - Draft Density
  - Thread Structure
  - Texture Mapping
  - Micro Detail

### Material Handling

- For live preview, the app uses the template material in Blender:
  - `MAterial_01`
  - fallback: `Material_01`
- The backend duplicates that material, swaps the diffuse and alpha textures, and keeps the existing mapping logic already wired into the Blender file
- This preserves the texture behavior already tuned in the material and geometry node setup

## Local Testing Workflow

1. Open `Weave_GUIConnection.blend` in Blender.
2. Start the Blender MCP/socket bridge.
3. Run the backend from `backend/`.
4. Run the frontend from `frontend/`.
5. Upload yarn assets in Step 1 and wait until they are `ready`.
6. Build or import the draft in Step 2.
7. Assign yarns and adjust controls in Step 3.
8. Click `Update Preview`.

Expected result:

- Blender applies the draft/material changes
- Blender switches a 3D view to camera view in Material Preview mode
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

- The staged live preview path currently supports up to 4 distinct yarn assets at once because it duplicates the template material for each assignment
- The atlas-based render path still exists for larger final renders
- This is a screenshot refresh workflow, not a continuous interactive stream
- A real Blender GUI session is still required for the Material Preview capture path

## Server Rollout Direction

For the later H100 deployment, the current direction is:

- run Blender in a managed GUI-capable session on the server
- provide a virtual display instead of relying on a physical monitor
- keep the same lazy `Update Preview` request cycle from the web UI
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
