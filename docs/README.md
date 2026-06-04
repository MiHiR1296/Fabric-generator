# Fabric-generator-tryon — documentation

This is the integration project: **yarnseamless** (yarn-scan authoring, now ported into Step 1) → **Fabric-generator-tryon** (studio + Blender preview) → **Try-On 3D** (in-browser fabric/garment preview). The shared contract is `yarn_library/<yarn_id>/` on disk plus the Blender file `Codex_ParametricWeave.blend`.

Read in this order:

| # | folder/file | what it covers |
|---|---|---|
| 1 | [FINAL_HANDOFF.md](FINAL_HANDOFF.md) | The consolidated final doc: what we built, workflow, process, artifact management, features, open items. |
| 2 | [CHECKPOINT_2026-05-19.md](CHECKPOINT_2026-05-19.md) | The visually approved Blender/material baseline: exact socket values, U-scale denominator, backup file, and verification. |
| 3 | [TextureResolutionFix/](TextureResolutionFix/) | Active investigation and action plan for Blender texture-resolution mismatch: source RGBA/UDIM verification, root U-scale drift, atlas fallback risk, diagnostics, and fix phases. |
| 4 | [application-blueprint.md](application-blueprint.md) | The weaving-draft subsystem product spec — what the UI must preserve when ported into the larger app. |
| 5 | [putting-it-together/](putting-it-together/) | How the app + Blender talk to each other. Read this first for system-level picture: architecture, data contract, full phase log, lessons. |
| 6 | [BlenderFixes/](BlenderFixes/) | Everything that lives inside the .blend itself + the backend code that drives it. Zoom-in on `Parametric Weave knotty`: node-group structure, Arc 1 / Arc 2 V-band system, socket-rename history, live-render dev mode. |
| 7 | [WebUIChanges/](WebUIChanges/) | Wizard / FastAPI surface changes — the three state layers (library / runtime asset / color binding), the sync points between them, and every UI-visible behavior fix logged Symptom / Diagnosis / Fix / Verification. |
| 8 | [YarnScanProcessing/](YarnScanProcessing/) | 2026-05-29 yarn-scan processing log: robust thread detection, natural RGBA, background spill removal, sub-degree rotation, connected-core bands, tests, and QA metrics. |
| 9 | [WebUIbands/](WebUIbands/) | Yarn band detection (core + fiber halos) — historical setup, FWHM post-export detector, and later connected-core refinements. |

External runtime assets are shared here:

https://drive.google.com/drive/folders/18UPKaVFXKBNetcwFR0fXdipJ3HLsZSXU?usp=drive_link

Direct asset bundle:

https://drive.google.com/drive/folders/1z3Ucq0O4ETbsYhVzkTka9l_xxtMeQAsP

---

## Current shipping status (updated through 2026-05-29)

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
| **Phase 10u / Checkpoint 2026-05-19** — visually approved direct web-to-Blender material baseline; `Spacing = 0.026`, `Arc 1 V Padding = 0.008`, `Texture Offset V = 0`, `Sub Texture Scale V = 1`, `Sub Texture Offset V = 0`, root `Texture Scale U = 1`, and auto `Material N Texture Scale U = visible_v_span / 1.0` | ✓ done |
| **Publish prep** — final handoff doc, debug ignores, external model env-path support, LFS-disabled fallback documented | ✓ done |
| **Yarn scan processing repair** — segmentation-first thread detection, natural RGBA export, full-resolution RGBA UDIM tiles, red/background chroma removal from fringe, mandatory sub-degree thread rotation, connected-core red bands | ✓ done |

## What we set out to achieve

Three goals, ordered by priority:

1. **One workflow across three apps** — scan a yarn → save to library → import in the studio → assign yarns + draft a pattern → render preview → try on a 3D garment, with no tab juggling or manual file copies.
2. **Faithful render of the scanned yarn in Blender** — the rendered fabric's strands should look like the scanned yarn at real-world dimensions (correct world width, halo where the scan has halo, core where the scan has the dense band).
3. **Decoupled producer / consumer contract** — producer (yarnseamless) computes everything Blender needs once; consumer (the studio backend) just pushes the pre-computed values to modifier sockets. No math on the consumer side.

## What's remaining

In rough priority order — the **bigger** items first.

### Open scope

- **Protect the 2026-05-19 visual checkpoint**: the current Blender/material baseline is approved and documented in [CHECKPOINT_2026-05-19.md](CHECKPOINT_2026-05-19.md). Future Arc 2, padding, or U-scale experiments should start from a new `.blend` backup and record whether they replace or branch from this checkpoint.

- **Texture World Width BU socket** still doesn't exist on the .blend. Producer publishes `bandMeta.blender.texture_world_width_m`; consumer falls back to legacy `Material N Image Width Px` ÷ `Scanner Pixels Per BU` to derive the same value. Adding the socket would simplify the math and remove a pixel-level intermediate from the wire format. Documented in [putting-it-together/data_contract.md](putting-it-together/data_contract.md).

- **Live-render UI toggle**. Currently `BLENDER_LIVE_RENDER` is a backend env var (`make backend-dev-live`). A dev-only checkbox in Step 3 would let multiple devs share a backend without restarting.

- **Large model artifact migration**. The raw `big-lama.pt` stays out of Git and can be supplied through `BIG_LAMA_MODEL_PATH` / `LAMA_MODEL`. The existing split chunks are still part of the current repository baseline; moving them to release assets or LFS would need a separate history-cleanup decision.

### Smaller cleanups

- **Internal switch chain nodes still say "Core" / "Fiber"** (`PW Material Core V Min Select N`, etc.). Phase 3d renamed the interface sockets to Arc 1 / Arc 2 vocabulary but didn't rename the internal multiplexer nodes. Purely cosmetic — they all route correctly. Would be a quiet pass when the artist is touching the graph anyway.

- **Atlas / colour-id chain for per-cell multi-yarn rendering** is the legacy v2 approach. The current Phase 3 pipeline pushes per-yarn `bandMeta` to per-Material sockets, which is cleaner. The v2 atlas path is still in the headless render script (`ensure_atlas_preview_material`) as a fallback. Could be retired once we verify multi-yarn projects don't regress. Tracked in [BlenderFixes/lessons.md](BlenderFixes/lessons.md) Open items.

- **The `Set Material` node (the first one) is dead** — its geometry output never reaches Group Output. Only `Set Material.001` is in the active chain. Leaving the dead node in place is safe but confusing for the artist. Cleanup candidate.

- **Live-sync of full project state to Blender** is one-shot, not reactive. Web UI's Render Preview re-syncs each click; there's no "auto-sync as I edit the draft" mode. Out of scope for current phases — would need a frontend WebSocket + backend sync endpoint pair.

### Deferred (logged with rationale)

- **Atlas fallback path parity** is still lower priority, but the current direct per-yarn material now uses blended alpha for a smoother live preview. Hashed/dithered alpha can still be forced for sorting experiments with `WEAVE_CUTOUT_BLEND_METHOD=HASHED WEAVE_SURFACE_RENDER_METHOD=DITHERED`.

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
