# Putting it together

The integration project. One workflow across three apps: **yarnseamless** (asset authoring) → **Fabric-generator-tryon** (studio + Blender preview) → **Try-On 3D** (browser-side fabric → garment / furniture).

This folder is the living record of how we made the three talk to each other. Read it in the order below.

---

## Why this exists

We have three good things that don't talk to each other yet:

1. **yarnseamless** — a careful image-science pipeline that turns physical yarn scans into clean RGBA + dimensions + V-band metadata. Documented to a high bar at [yarnseamless/docs/](../../../docs/).
2. **Fabric-generator-tryon** — a fresh 4-step React/TS wizard UI (Yarn Library → Pattern Builder → Render Preview → Try On 3D) shipped by a teammate. Visually right. Backend was a placeholder.
3. **Blender** — `Codex_ParametricWeave.blend` with the `Parametric Weave knotty` geometry-node graph. Persistent per-yarn material sockets. MCP socket bridge on port 9876.

We want one workflow: scan → save to library → click Import in the studio → assign yarns → Preview → Try On 3D. No tab juggling, no manual file copies, no Blender knowledge needed for designers.

This folder records every step of stitching them together. **One phase = one entry in [phase_log.md](phase_log.md)**. **One earned rule = one entry in [lessons.md](lessons.md)**. The contract that all three apps share lives in [data_contract.md](data_contract.md). For the finished executive handoff, read [../FINAL_HANDOFF.md](../FINAL_HANDOFF.md).

---

## Documentation index

Read in this order:

| # | doc | what it covers |
|---|---|---|
| 1 | [architecture.md](architecture.md) | The three processes, ports, shared `yarn_library/` folder, request flow when you import. **Read first.** |
| 2 | [data_contract.md](data_contract.md) | The `metadata.json` schema, the pre-computed `blender` block, every field → Blender socket map. **The single source of truth** — if anything else here disagrees with this, this wins. |
| 3 | [phase_log.md](phase_log.md) | What we did, when, and why. Each phase recorded as Symptom / Diagnosis / Fix / Verification. Append-only. |
| 4 | [lessons.md](lessons.md) | Rules earned the hard way. Read before making non-trivial cross-app changes. |

---

## Current status (2026-05-15)

All planned phases are shipping. See [phase_log.md](phase_log.md) for the full history.

- **Phase 1 — library wiring**: ✓ done. Studio lists and imports yarns from shared `yarn_library/`. `bandMeta.blender` populated on every imported asset.
- **Phase 2a–2f — yarnseamless processing UI inside the wizard**: ✓ done. Multi-thread split → multi-fragment stitch → save runs inside Step 1; the original yarnseamless server is no longer required at runtime.
- **Phase 3 — push `bandMeta.blender` to live Blender**: ✓ done. The MCP socket on 9876 receives bandMeta pushes; headless Blender (subprocess) handles production render jobs.
- **Phase 3a–3c — sub-fixes**: Cycles 16384 texture cap, v2 control-surface alignment (3 exposed render controls with defaults 0), producer-side `fiber_bot_v_max` bug fix, per-strand `UV Random U` scatter control. ✓ done.
- **Phase 3d — Arc 1 / Arc 2 socket rename**: ✓ done. 68 V-band sockets renamed in place; internal wiring preserved via identifier stability.
- **Phase 3e — Arc 2 internal link rewire**: ✓ done. Four Map Range link swaps inside `Parametric Weave knotty` so the halo region actually renders.
- **Phase 3f — modifier panel reorganization + dead-socket removal**: ✓ done. 5 legacy global V-band sockets removed; Materials 1-16 picks consolidated in `Material Slots` panel; V-band controls grouped in `V-Band Mapping` panel.
- **Phase 3g — pin Sub Strand Enable + `BLENDER_LIVE_RENDER` dev mode**: ✓ done. Arc 2 halo now active on the rendered yarn by default; `make backend-dev-live` routes render jobs to the open Blender session via MCP.
- **Publish prep**: ✓ done. Local debug/backups ignored, raw `big-lama.pt` can be supplied by `BIG_LAMA_MODEL_PATH` / `LAMA_MODEL`, GitHub's current LFS-disabled state is documented, and [../FINAL_HANDOFF.md](../FINAL_HANDOFF.md) summarizes the final application.

For the in-depth Blender side (node-group structure, socket-rename history, Arc 1 / Arc 2 details, live-render dev mode), see [../BlenderFixes/](../BlenderFixes/).

## What's remaining

- **Arc 2 visual mapping is in live geometry-split review**: Phase 3q now computes the split from Arc 1/Arc 2 profile radii (`0.015 / 0.025 -> 0.6`, splits `0.2 / 0.8`) and stores evaluated debug attributes. Needs viewport approval. See [../BlenderFixes/README.md](../BlenderFixes/README.md).
- **`Texture World Width BU` socket** still doesn't exist on the .blend. Producer publishes the value already; consumer uses legacy `Image Width Px ÷ Scanner Pixels Per BU` divide.
- **Live-render UI toggle** — currently a backend env var, no frontend control.
- **Internal switch-chain node names** still say "Core" / "Fiber" (interface was renamed in Phase 3d, internals weren't). Cosmetic.
- **`Set Material` (first node) is dead** — bypassed in the active geometry chain. Safe but confusing for the artist.

## Quickstart

Two terminals (or use the Makefile shortcuts).

```bash
# Terminal 1 — Fabric-generator-tryon backend (this app)
cd Fabric-generator-tryon
make backend-install        # one-time
make backend-dev            # starts FastAPI on :8000 with BLENDER_PORT=9876 pinned

# Terminal 2 — Fabric-generator-tryon frontend
cd Fabric-generator-tryon
make frontend-install       # one-time
make frontend-dev           # Vite on :5180

# Optional: run against an open Blender session instead of headless renders
make backend-dev-live       # sets BLENDER_LIVE_RENDER=1 and BLENDER_PORT=9876
```

Then open **http://localhost:5180/**. Step 1 can process yarns directly, save them into `../yarn_library/`, and auto-import them into the project.

For live Blender setup, open `Codex_ParametricWeave.blend` in Blender and start the `BlenderMCPAddon` socket on port 9876.

## Where things break — first look

| symptom | first place to look | doc |
|---|---|---|
| Step 1 library section is empty | Backend log: is `YARN_LIBRARY_ROOT` resolving correctly? `curl /api/yarn/library` directly | [architecture.md](architecture.md) → "Ports" |
| `image_size_px` doesn't match the actual `rgba.png` | The producer skipped the file open. [web/yarn_library.py:save_to_library](../../../web/yarn_library.py) | [lessons.md](lessons.md) → Rule 1 |
| Render uses wrong texture scale | `metadata.blender.image_width_px`, `scanner_pixels_per_bu`, and `Material N Texture Scale U` vs the socket values Blender received. | [data_contract.md](data_contract.md) → socket map |
| Fiber bands look misaligned (Arc 2 strands) | Someone set `Sub Texture Scale V ≠ 0` in the .blend | [lessons.md](lessons.md) → Rule 3 |
| Backend can't reach Blender | `BLENDER_PORT=9876` vs your MCP addon's listening port | [architecture.md](architecture.md) → "Ports" |
| Import works but `renderDiffuseUrl` is `cycles_safe/..._max16384.png` | Normal: the source exceeded 16384 px and got auto-downscaled for Cycles | [lessons.md](lessons.md) → Open items, `CYCLES_MAX_TEXTURE_DIM` |

## How to update these docs

Every non-trivial change ships with a doc update in the **same commit**:

- **Touched a contract field?** Update [data_contract.md](data_contract.md) (the socket map / shape / derivations) first, then change code.
- **Finished a piece of work?** Add a Phase entry to [phase_log.md](phase_log.md) using the template at the bottom of that file.
- **Got bitten by something non-obvious?** Add a rule to [lessons.md](lessons.md). Lead with **Rule**, then **Why**, then a **Concrete example** with a file path.
- **System layout changed** (new process, new port, new shared folder)? Update [architecture.md](architecture.md).

If you find yourself wanting to "leave the docs and come back to them" — don't. They drift in hours. The yarnseamless docs work because they were written the same day as the code.

---

## Stakeholders / hand-off

| role | what they do | what they should read first |
|---|---|---|
| Yarn designer | Scans yarn, saves to library, and imports the yarn into the project. | [../FINAL_HANDOFF.md](../FINAL_HANDOFF.md), then Step 1 in the app. |
| 3D / Blender artist | Owns `Codex_ParametricWeave.blend`. Adds/edits sockets, materials. | [data_contract.md](data_contract.md) → socket map, then [lessons.md](lessons.md) Rule 3. |
| Integration / backend engineer (you, probably) | Owns this folder, both backends, the wiring. | This file → architecture → phase_log → lessons → data_contract. In that order. |
| Frontend engineer (the teammate) | Owns the wizard UI shape and the Try-On 3D scene. | [architecture.md](architecture.md) → "Request flow", then the relevant component files. |
