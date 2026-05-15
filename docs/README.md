# Fabric-generator-tryon — documentation

This is the integration project: **yarnseamless** (yarn-scan authoring, now ported into Step 1) → **Fabric-generator-tryon** (studio + Blender preview) → **Try-On 3D** (in-browser fabric/garment preview). The shared contract is `yarn_library/<yarn_id>/` on disk plus the Blender file `Codex_ParametricWeave.blend`.

Read in this order:

| # | folder/file | what it covers |
|---|---|---|
| 1 | [FINAL_HANDOFF.md](FINAL_HANDOFF.md) | The consolidated final doc: what we built, workflow, process, artifact management, features, open items. |
| 2 | [application-blueprint.md](application-blueprint.md) | The weaving-draft subsystem product spec — what the UI must preserve when ported into the larger app. |
| 3 | [putting-it-together/](putting-it-together/) | How the app + Blender talk to each other. Read this first for system-level picture: architecture, data contract, full phase log, lessons. |
| 4 | [BlenderFixes/](BlenderFixes/) | Everything that lives inside the .blend itself + the backend code that drives it. Zoom-in on `Parametric Weave knotty`: node-group structure, Arc 1 / Arc 2 V-band system, socket-rename history, live-render dev mode. |
| 5 | [WebUIChanges/](WebUIChanges/) | Wizard / FastAPI surface changes — the three state layers (library / runtime asset / color binding), the sync points between them, and every UI-visible behavior fix logged Symptom / Diagnosis / Fix / Verification. |
| 6 | [WebUIbands/](WebUIbands/) | Yarn band detection (core + fiber halos) — current two-pass setup, the YarnSeamless FWHM port target, and the cut-over plan to run band detection on the assembled alpha post-inpaint. |

External runtime assets are shared here:

https://drive.google.com/drive/folders/18UPKaVFXKBNetcwFR0fXdipJ3HLsZSXU?usp=drive_link

---

## Current shipping status (2026-05-15)

| Area | Status |
|---|---|
| **Phase 1** — library wiring (yarn_library shared folder, FastAPI library endpoints, frontend Step 1 import) | ✓ done |
| **Phase 2a–2f** — yarnseamless processing UI ported into wizard Step 1 (multi-thread split + multi-fragment stitch, FastAPI route port, frontend component port, save-to-library auto-import) | ✓ done |
| **Phase 3** — push `bandMeta.blender` to live Blender (MCP socket on 9876 + headless Blender for production) | ✓ done |
| **Phase 3a** — fix Cycles 16384 px texture cap (atlas builder uses cycles_safe downscales) | ✓ done |
| **Phase 3b** — align Render Preview controls with Fabric-generator v2 (3 exposed controls: Spacing, Pattern Noise X/Y; defaults 0) | ✓ done |
| **Phase 3c** — fix V-band producer bug (`fiber_bot_v_max` was wrongly set to `fiber_top_v[1]`); add per-strand U scatter control | ✓ done |
| **Phase 3d** — rename V-band sockets from Core/Fiber to Arc 1 / Arc 2 (68 sockets renamed in place; internal wiring preserved) | ✓ done |
| **Phase 3e** — Arc 2 internal link rewire so the halo region actually renders (4 link swaps inside `Parametric Weave knotty`) | ✓ done |
| **Phase 3f** — modifier panel reorganization + dead socket removal (5 legacy globals removed; Material Slots + V-Band Mapping panels consolidated) | ✓ done |
| **Phase 3g** — pin Sub Strand Enable + add `BLENDER_LIVE_RENDER` dev-mode env var (render jobs route to the open Blender session over MCP) | ✓ done |
| **Publish prep** — final handoff doc, debug ignores, external model env-path support, LFS-disabled fallback documented | ✓ done |

## What we set out to achieve

Three goals, ordered by priority:

1. **One workflow across three apps** — scan a yarn → save to library → import in the studio → assign yarns + draft a pattern → render preview → try on a 3D garment, with no tab juggling or manual file copies.
2. **Faithful render of the scanned yarn in Blender** — the rendered fabric's strands should look like the scanned yarn at real-world dimensions (correct world width, halo where the scan has halo, core where the scan has the dense band).
3. **Decoupled producer / consumer contract** — producer (yarnseamless) computes everything Blender needs once; consumer (the studio backend) just pushes the pre-computed values to modifier sockets. No math on the consumer side.

## What's remaining

In rough priority order — the **bigger** items first.

### Open scope

- **Arc 2 visual mapping is in live geometry-split review**: Phase 3q now computes the split from Arc 1/Arc 2 profile radii (`0.015 / 0.025 -> 0.6`, splits `0.2 / 0.8`) and stores evaluated debug attributes. Needs viewport approval. Details in [BlenderFixes/README.md](BlenderFixes/README.md).

- **Texture World Width BU socket** still doesn't exist on the .blend. Producer publishes `bandMeta.blender.texture_world_width_m`; consumer falls back to legacy `Material N Image Width Px` ÷ `Scanner Pixels Per BU` to derive the same value. Adding the socket would simplify the math and remove a pixel-level intermediate from the wire format. Documented in [putting-it-together/data_contract.md](putting-it-together/data_contract.md).

- **Live-render UI toggle**. Currently `BLENDER_LIVE_RENDER` is a backend env var (`make backend-dev-live`). A dev-only checkbox in Step 3 would let multiple devs share a backend without restarting.

- **Large model artifact migration**. The raw `big-lama.pt` stays out of Git and can be supplied through `BIG_LAMA_MODEL_PATH` / `LAMA_MODEL`. The existing split chunks are still part of the current repository baseline; moving them to release assets or LFS would need a separate history-cleanup decision.

### Smaller cleanups

- **Internal switch chain nodes still say "Core" / "Fiber"** (`PW Material Core V Min Select N`, etc.). Phase 3d renamed the interface sockets to Arc 1 / Arc 2 vocabulary but didn't rename the internal multiplexer nodes. Purely cosmetic — they all route correctly. Would be a quiet pass when the artist is touching the graph anyway.

- **Atlas / colour-id chain for per-cell multi-yarn rendering** is the legacy v2 approach. The current Phase 3 pipeline pushes per-yarn `bandMeta` to per-Material sockets, which is cleaner. The v2 atlas path is still in the headless render script (`ensure_atlas_preview_material`) as a fallback. Could be retired once we verify multi-yarn projects don't regress. Tracked in [BlenderFixes/lessons.md](BlenderFixes/lessons.md) Open items.

- **The `Set Material` node (the first one) is dead** — its geometry output never reaches Group Output. Only `Set Material.001` is in the active chain. Leaving the dead node in place is safe but confusing for the artist. Cleanup candidate.

- **Live-sync of full project state to Blender** is one-shot, not reactive. Web UI's Render Preview re-syncs each click; there's no "auto-sync as I edit the draft" mode. Out of scope for current phases — would need a frontend WebSocket + backend sync endpoint pair.

### Deferred (logged with rationale)

- **Atlas-based MixShader material** (the headless render's `FabricStudioAtlasMaterial`) renders alpha as smooth transparency; the live-bound per-yarn material uses HASHED alpha cutout. Subtle look difference but both are valid; not pursuing parity. See [putting-it-together/phase_log.md](putting-it-together/phase_log.md) Phase 3g.

- **SAM2 / ViTMatte single-image flow** from yarnseamless was deliberately not ported (Phase 2b). The yarn workflow doesn't use it. Cost to revisit: small.

- **Per-thread color variance** in `bandMeta.threads_solid_band` is diagnostic only. Not pushed to Blender. Documented in [putting-it-together/data_contract.md](putting-it-together/data_contract.md) → "What is NOT in the contract".

---

## How to update these docs

The same rules apply across both subfolders:

- Touched a contract field? Update [putting-it-together/data_contract.md](putting-it-together/data_contract.md) (the socket map / shape / derivations) first, then change code.
- Finished a piece of work? Add a Phase entry to [putting-it-together/phase_log.md](putting-it-together/phase_log.md) and, if it touched the .blend, mirror to [BlenderFixes/phase_log.md](BlenderFixes/phase_log.md).
- Got bitten by something non-obvious? Add a rule to [putting-it-together/lessons.md](putting-it-together/lessons.md) or [BlenderFixes/lessons.md](BlenderFixes/lessons.md) depending on layer.
- System layout changed (new process, new port, new shared folder)? Update [putting-it-together/architecture.md](putting-it-together/architecture.md).
- Touched the .blend (nodes, sockets, panels, internal links)? Update [BlenderFixes/architecture.md](BlenderFixes/architecture.md).

Write the doc entry **the same hour** you make the change. Drift happens fast.
