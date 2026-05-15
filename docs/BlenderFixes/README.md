# BlenderFixes

Everything we did **inside the .blend** (`Codex_ParametricWeave.blend`, node group `Parametric Weave knotty`) and to the **backend code that drives Blender**, so the web UI's "Render Preview" produces a faithful render of the imported yarn.

Sister to [putting-it-together/](../putting-it-together/) — that folder covers the three-app integration (yarnseamless → tryon → Blender). This folder zooms in on the Blender side: node-group structure, modifier interface, the Arc 1 / Arc 2 V-band system, the headless ↔ live render switch, and every fix landed along the way.

---

## Why this exists

When the integration first wired together (Phase 1–3 in [putting-it-together/phase_log.md](../putting-it-together/phase_log.md)), the backend pushed `bandMeta.blender` values straight into modifier sockets and the geometry-node graph turned them into a rendered fabric. The pipeline ran end-to-end, but the rendered yarn didn't visually match the scanned yarn — values landed on the wrong sockets, halo regions were never sampled, and the modifier panel mixed Material 1-4 picks into one collapsible panel while Materials 5-16 sat at root level. Each fix required:

- Inspecting the node graph (interface sockets, internal nodes, link topology) over the BlenderMCPAddon socket on port 9876
- Renaming sockets / rewiring internal links / removing dead inputs
- Keeping the producer code (`backend/app/blender_live.py`) in lockstep with what the .blend actually exposes
- Documenting it before drift could set in

This folder is the record of that work.

---

## Documentation index

Read in this order:

| # | doc | what it covers |
|---|---|---|
| 1 | [architecture.md](architecture.md) | The shape of `Parametric Weave knotty`: input sockets, panels, the Arc 1 / Arc 2 system, sub-strand gating, switch chains. Read first. |
| 2 | [phase_log.md](phase_log.md) | Every Blender-side fix in chronological order — Symptom / Diagnosis / Fix / Verification. Append-only. |
| 3 | [lessons.md](lessons.md) | Rules earned the hard way about touching geometry-node interfaces from Python over MCP. |

---

## Current state (2026-05-15)

- **Node group**: `Parametric Weave knotty` (16 Material slots, Arc 1 / Arc 2 V mapping). The older `Weave From Draft` is still in the file but no longer the modifier's target.
- **Modifier**: `Weave` on `ParametricWeave` object, followed by `Fit To Space`.
- **Interface socket vocabulary**: Arc 1 V Min/Max (= core), Arc 2 V Min/Max (= strand silhouette outer extents). Old `Core V Min/Max` / `Fiber Top V Min` / `Fiber Bot V Max` names retired in Phase 3d.
- **Arc 2 direction**: fixed in Phase 3k. `v_around=0` samples the top outer silhouette and `v_around=1` samples the bottom outer silhouette; the three sections now run outer top -> core top -> core bottom -> outer bottom.
- **Pinned / neutral**: `Sub Strand Enable = True` (Socket_84) so Arc 2 halo always renders; the five V footgun sockets pinned at safe defaults (`Texture Scale V = 1`, `Texture Offset V = 0`, `Texture Side Flatten = 0`, `Sub Texture Scale V = 0`, `Sub Texture Offset V = 0`). Root `Texture Scale U` is neutral (`1.0`) after Phase 4i. The fit/divide-by-10 correction now multiplies each `Material N Texture Scale U`.
- **Render Preview material binding**: direct per-yarn materials for <=16 assets. Over-wide scans now use full-resolution Cycles UDIM tiles (`cycles_tiled/*_<UDIM>.png`) instead of only the `cycles_safe` downscale; small or fallback paths still use Cycles-safe textures. The script sets object material slots + modifier `Material N` sockets + V-band metadata + material cycles together. Atlas material is fallback only. Generated yarn texture nodes use `Linear` interpolation.
- **Arc 1 core V padding**: Phase 4c exposes `Arc 1 V Padding` directly on the `Weave` modifier. The node graph expands Arc 1 V Min/Max by that amount and clamps inside Arc 2's silhouette. Phase 4h sets the Blender/Web/backend default to `0.012`; backend still pushes raw metadata core values.
- **Pattern Builder live push**: setup-only live push now runs the same setup body without rendering. Same-yarn warp/weft bindings collapse to one active material, stale `Material 2..16` sockets are cleared, and warp material IDs follow the web drawdown's reversed-column convention.
- **Arc 2 geometry split test**: Phase 3q replaces the Phase 3m texture-span proxy with geometry-owned radius math. Arc 1 profile radius is `0.015`, Arc 2 profile radius is `0.025`, and the graph stores debug attributes (`arc2_core_frac_geometry`, `arc2_core_split_min`, `arc2_core_split_max`) on the evaluated mesh.
- **Removed**: 5 dead global V-band sockets (`Image Width Px`, `Image Arc 1/2 V Min/Max`) that no Group Input was consuming; empty `Detail` panel.
- **Backups on disk** in `/Users/mihirbotle/Desktop/Impetus/Fabric-generator/`:
  - `Codex_ParametricWeave.pre-arc-rename-20260514_005120.blend` — before the Phase 3d socket rename
  - `Codex_ParametricWeave.pre-arc2-rewire-20260514_013031.blend` — before the Phase 3e Arc 2 link rewire (this is the snapshot we restored from when the live-sync attempt broke the Weave modifier)
  - `Codex_ParametricWeave.pre-arc2-direction-20260515_002417.blend` — before the Phase 3k Arc 2 direction flip
  - `Codex_ParametricWeave.pre-arc2-geometry-split-20260515_014653.blend` — before the Phase 3q geometry-owned Arc 2 split test
  - `Codex_ParametricWeave.pre-arc1-padding-socket-20260515_025526.blend` — before Phase 4c exposed Arc 1 V Padding on the modifier
  - `Codex_ParametricWeave.pre-phase4d-web-controls-20260515_032532.blend` — before Phase 4d set Arc 1 V Padding default to 0.1 and exposed the Web UI controls
  - `Codex_ParametricWeave.pre-arc1-padding-default-0012-20260515_041138.blend` — before Phase 4h lowered Arc 1 V Padding default to 0.012

## Known not-yet-fixed

- **Managed visible-Blender auto-launch is not ported yet.** The older v2 setup could launch normal Blender on demand. This tryon branch can render into an already-open Blender via `make backend-dev-live`, but you still have to open Blender and start BlenderMCP manually. Port v2's `blender_session.py` / `blender_session_startup.py` to restore the old one-click behavior.

## Quickstart for dev work on the .blend

```bash
# 1. Open Blender, load the canonical file:
/Applications/Blender.app/Contents/MacOS/Blender \
  "/Users/mihirbotle/Desktop/Impetus/Fabric-generator/Codex_ParametricWeave.blend"

# 2. Enable BlenderMCPAddon (Preferences → Add-ons → BlenderMCP), then in
#    the 3D viewport N-panel → BlenderMCP tab → "Connect / Start MCP Server".
#    Confirm: nc -z -G 1 127.0.0.1 9876 returns connected.

# 3. Start the backend in LIVE-RENDER mode (renders into your open session
#    instead of headless Blender):
cd Fabric-generator-tryon && make backend-dev-live

# 4. Start the frontend:
make frontend-dev

# When you click "Render Preview" in the wizard, the script runs in the open
# Blender. The viewport updates with the rendered state, and you can poke at
# the node group / modifier inputs between renders.
```

## When dev is done

Switch back to headless rendering for production / cron jobs:

```bash
make backend-dev          # default — headless subprocess
```

The headless path uses `WEAVE_BLEND_FILE` (defaults to the repo copy
`Codex_ParametricWeave.blend`). Same script body, just spawned as
`blender -b <file> --python <script>` instead of pushed over MCP.

## How to update these docs

Every Blender-side change ships with a doc update in the same commit:

- **Touched a socket / panel / internal link?** Update [architecture.md](architecture.md) to describe the new shape, then add a Phase entry to [phase_log.md](phase_log.md) using the Symptom/Diagnosis/Fix/Verification template.
- **Earned a lesson?** Add it to [lessons.md](lessons.md). Lead with **Rule**, then **Why**, then **Concrete example** with a file/identifier path.
- **Snapshot the .blend before destructive ops** — `bpy.ops.wm.save_mainfile()` then `cp` to `*.pre-<change>-<timestamp>.blend` next to the canonical. Record the backup name in the phase entry.
