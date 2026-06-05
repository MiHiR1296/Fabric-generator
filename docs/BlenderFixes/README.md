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
| 2 | [geometry_nodes_guide.md](geometry_nodes_guide.md) | Cleaned graph guide: frame map, active data flow, removed sockets, and future subgroup candidates. |
| 3 | [phase_log.md](phase_log.md) | Every Blender-side fix in chronological order — Symptom / Diagnosis / Fix / Verification. Append-only. |
| 4 | [lessons.md](lessons.md) | Rules earned the hard way about touching geometry-node interfaces from Python over MCP. |
| 5 | [SeamlessTileMode/](SeamlessTileMode/) | Dedicated planning and future implementation log for optional tileable fabric exports: boundary contracts, guard bands, periodic UV/random state, and tile-set generation. |
| 6 | [TileInpaintRepair/](TileInpaintRepair/) | Dedicated planning and test log for post-render two-pass LaMa seam repair: center-cross inpaint, offset corners-to-center, wraparound inpaint, and tileable output checks. |

---

## Current state (2026-05-27 cleaned graph; 2026-05-19 visual baseline)

- **Node group**: `Parametric Weave knotty` (16 Material slots, Arc 1 / Arc 2 V mapping). The older `Weave From Draft` is still in the file but no longer the modifier's target.
- **Modifier**: `Weave` on `ParametricWeave` object, followed by `Fit To Space`.
- **Interface socket vocabulary**: Arc 1 V Min/Max (= core), Arc 2 V Min/Max (= strand silhouette outer extents). Old `Core V Min/Max` / `Fiber Top V Min` / `Fiber Bot V Max` names retired in Phase 3d.
- **Current Arc 2 free-flow halo state (Phase 10t + cleanup)**: the saved `.blend` uses the real Arc 2 Top/Core/Bot path, with `Arc 2 Match Arc 1 V Rate = false`. The old `Match Section Slopes` and `Arc 2 Edge Angle Mapping` branches were unreachable after Phase 10t and were removed in the 2026-05-27 cleanup. Arc 2's center interval is still the R1-equivalent core (`Split Minus/Plus = 0.2/0.8` from `r1/r2 = 0.015/0.025 = 0.6`), and the two outer R2 intervals extrapolate from the raw core seam at the core V rate instead of snapping to `Arc 2 V Min/Max`.
- **Arc 2 profile is a custom polyline (Phase 10c -> 10p)**: a 31-vertex polyline built via `MeshLine → piecewise Map Range → Sample Curve(Arc.001) → SetPosition → MeshToCurve`. Vertex 6 and vertex 24 always land at exactly `Split Minus / Split Plus` on the source arc, regardless of `arc1/arc2` radius ratio. Phase 10p stores the computed actual profile factor as `pw_profile_actual` and writes `v_around` from that attribute, not from `Spline Parameter Factor`, so the physical profile boundary and Arc 2 UV section tests use the same split values. `pw_profile_natural` remains as the fixed anchor/debug attribute for the polyline/inset logic.
- **Per-section U scale (Phase 10 → 10a)**: `PW U - Per Section Multiplier` between `PW UV U Add` and `Combine XYZ.006.X` keeps texel aspect equal across Arc 1 main / Arc 2 Top / Core / Bot when section slopes differ. Arc 1 main and Arc 2 Core share ratio = 1.0 by Phase 3q construction (same physical V rate).
- **Post-bend U storage (Phase 10i)**: `Store Warp U` / `Store Weft U` now sit after `PW Warp/Weft Set Position`, so `u_along` measures the visible bent curve rather than the straight pre-bend curve. `PW Warp/Weft U Stride Post-Bend Ratio` multiplies the backend's straight-baseline stride by the same live length ratio before applying `curve_index`, keeping adjacent-strand spool phase aligned with the new post-bend U length.
- **Arc 2 deterministic same-strand U (Phase 10k, revised 2026-06-04)**: active. Phase 10j's `PW VisU - *` projected-axis correction and the nearest-surface transfer both distorted because they sampled the wrong visual model / introduced small endpoint shrink. The saved graph still switches on `is_sub_strand`, but Arc 2 now uses the deterministic same-strand base U from `PW UV U Add` instead of `Sample Nearest Surface`. This keeps Arc 2 in the same yarn U stream as Arc 1 while avoiding the measured zero/reversed/short U steps. Arc 2 keeps its own V mapping. Current active graph has no `PW VisU` nodes and no `pw_visual_u_correction`, `pw_u_factor`, or `pw_thread_kind` attributes.
- **Project-from-view V + free Arc 2 halo flow (Phase 10m -> 10t)**: active for the saved inspection state. The remaining repeat was not `UV Random U`; it was two stacked V issues. Phase 10m fixed Arc 1's top-view shape, but keeping `Arc 2 Match Arc 1 V Rate = True` made Arc 2 resample only Arc 1's padded core range. Phase 10s restored the full Top/Core/Bot path, and Phase 10t changed the top/bottom endpoints to flow outward from the raw core at the core V rate. The 2026-05-19 checkpoint keeps that graph shape but returns `Texture Offset V` to neutral `0`.
- **Arc 2 Boundary Inset (Phase 10d)**: Surface-panel socket, default `0.0`. Tent-weighted radial pull of profile vertices near `v_around = 0.2` and `0.8`. At inset = `arc2_radius - arc1_radius = 0.010` the section discontinuity hides exactly behind Arc 1.
- **Removed historical Arc 2 branches (2026-05-27 cleanup)**: `Match Section Slopes` and `Arc 2 Edge Angle Mapping` were removed from the interface and graph because their downstream switch branches were unreachable from output. Their historical design remains in [phase_log.md](phase_log.md) and [lessons.md](lessons.md).
- **Arc 2 Match Arc 1 V Rate (Phase 10g, postscript-adjusted)**: Surface-panel boolean toggle, default `False`. When on, replaces Arc 2's entire piecewise V chain with a single linear mapping that samples **exactly Arc 1's padded core V range**, centered on the padded core midpoint. Arc 1 and Arc 2 then show the *same cells per cross-section* — the user sees identical cell counts on both arcs. Side effect: Arc 2 doesn't sample halo content on its surface (texture outside `[Arc 1 V Min Padded, Arc 1 V Max Padded]` is never reached). The original Phase 10g multiplied by `r2/r1` to match physical cell size, but that made Arc 2 cells appear denser due to the wider cylinder; the postscript adjustment uses `× 1.0` instead to match visual cell count.
- **Recommended baseline for clean renders**:
  - Low-padding mode: `Arc 1 V Padding = 0.002`, all four Phase 10e/f/g toggles OFF. Pure linear V with naturally-aligned slopes (Top/Core/Bot ≈ 0.063 / 0.063 / 0.067). Simplest, no machinery active.
  - Current approved free-flow halo mode: `Spacing = 0.026`, `Arc 1 V Padding = 0.02`, `Arc 2 Match Arc 1 V Rate = false`, `Arc 2 Boundary Inset = 0.0`, `Texture Offset V = 0`, with deterministic same-strand Arc 2 U, Phase 10t free halo V, and core-band auto U active. This keeps the central R1-equivalent core interval at the same scale model as Arc 1 and lets the two outer Arc 2 strips continue that V rate outward.
- **Pinned / neutral**: `Sub Strand Enable = True` (Socket_84) so Arc 2 halo always renders; the V footgun sockets are pinned at the approved checkpoint defaults (`Texture Scale V = 1`, `Texture Offset V = 0`, `Sub Texture Scale V = 1`, `Sub Texture Offset V = 0`). Root `Texture Scale U` is neutral (`1.0`); use it only as a temporary visual test knob. Per-yarn U scale comes from `Material N Texture Scale U`; when the producer leaves `texture_scale_u` unset/`1.0`, the apply step derives it from the detected core V band times `AUTO_TEXTURE_SCALE_U_CORE_FRACTION = 0.6`. Explicit non-`1.0` producer overrides are still respected.
- **Cross-axis symmetry**: Phase 5 inserted `PW Warp Set Curve Normal` and `PW Weft Set Curve Normal` (`Mode = 'Z Up'`) on the two strand branches so Arc 1 V Padding and Arc 2 halo behave identically on warp vs weft (previously asymmetric — only weft showed the halo expansion).
- **Render Preview material binding**: direct per-yarn materials for <=16 assets. Over-wide scans now prefer full-resolution RGBA UDIM tiles (`cycles_tiled/rgba_<UDIM>.png`) cut from the imported `rgba.png`, so Blender samples the same image for color and alpha. On the RGBA path, `FabricStudioDiffuseNode.Alpha` links directly to `Principled BSDF.Alpha` by default; alpha remap is opt-in with `WEAVE_ALPHA_REMAP_ENABLED=1`. Separate albedo/alpha UDIMs and `cycles_safe` downscales remain fallbacks. The script sets object material slots + modifier `Material N` sockets + V-band metadata + material cycles together. Atlas material is fallback only. Generated yarn texture nodes use `Linear` interpolation and blended alpha by default; set `WEAVE_TEXTURE_INTERPOLATION=Closest|Cubic|Smart` for controlled sharpness/debug comparisons, or `WEAVE_CUTOUT_BLEND_METHOD=HASHED WEAVE_SURFACE_RENDER_METHOD=DITHERED` to restore the old hashed viewport alpha.
- **Arc 1 core V padding**: Phase 4c exposes `Arc 1 V Padding` directly on the `Weave` modifier. The node graph expands Arc 1 V Min/Max by that amount and clamps inside Arc 2's silhouette. The 2026-06-05 Blender/Web/backend default is `0.02`; backend still pushes raw metadata core values.
- **Pattern Builder live push**: setup-only live push now runs the same setup body without rendering. Same-yarn warp/weft bindings collapse to one active material, stale `Material 2..16` sockets are cleared, and warp material IDs follow the web drawdown's reversed-column convention.
- **Arc 2 geometry/canonical split readback**: Phase 3q replaces the Phase 3m texture-span proxy with geometry-owned radius math. Arc 1 profile radius is `0.015`, Arc 2 profile radius is `0.025`, and the graph stores debug attributes on the evaluated mesh. `arc2_core_frac_geometry` stays the geometry ratio; `arc2_core_split_min/max` report the canonical split consumed by Arc 2 V/profile maps, so they read `0.2/0.8`.
- **Removed**: 5 dead global V-band sockets (`Image Width Px`, `Image Arc 1/2 V Min/Max`) that no Group Input was consuming; empty `Detail` panel; the 2026-05-27 cleanup also removed 60 legacy/dead interface items and 140 unreachable functional nodes. See [geometry_nodes_guide.md](geometry_nodes_guide.md).
- **Backups on disk**: Phase 10k/10l/10m/10n/10u created timestamped `.blend` rollback points before risky graph/backend branches, including `Codex_ParametricWeave.pre-strand-group-u-transfer-save-20260518_005328.blend`, `Codex_ParametricWeave.pre-arc2-v-skew-preview-20260518_001.blend`, `Codex_ParametricWeave.pre-camera-projected-v-20260518_001.blend`, `Codex_ParametricWeave.pre-arc2-full-halo-v-20260518_032211.blend`, `Codex_ParametricWeave.pre-arc2-full-halo-phase-repin-20260518_001.blend`, and `Codex_ParametricWeave.pre-scale-u-denominator-test-20260519_004510.blend`.

## Known not-yet-fixed

- ~~**Drawdown row sampling uses MODULO — simple twills bend wrong.**~~ **FIXED in Phase 10w (2026-05-27).** The bend now uses `row = floor(Index_in_Curve × Draft_Rows / Warp_Threads)` (symmetric formula for the weft branch). The crescent / moon-shaped inverse-geometry overlap is gone. New visual question: each drawdown cell now renders as 4×4 strands at wizard defaults (`Warp/Weft Threads = 80`, `Draft Rows/Cols = 20`), which means 2/2 twill floats span 8 strand widths and are visibly "windowed". Discuss with artist whether to lower Warp/Weft Threads to match Draft Rows/Cols, or to push higher-resolution drawdowns. Pre-fix snapshot: `Codex_ParametricWeave.pre-phase10w-rowmod-fix-20260527_163701.blend`. See [phase_log.md Phase 10w](phase_log.md#phase-10w--apply-floor-divide-fix-to-drawdown-rowcol-mapping) and [lessons.md](lessons.md) Rule 38.

- **Frontend ships `uvRandomU: 1` even though the backend default is `0`.** Backend comment in [blender_sync.py](../../backend/app/blender_sync.py) calls per-strand random U "a hack ... no longer needed" because Phase 5's cross-strand spool already provides natural variation, and defaults the producer override to `0.0`. But [frontend/src/domain/draft.ts](../../frontend/src/domain/draft.ts#L155) sets `uvRandomU: 1`, so the wizard always pushes `1.0` and the override beats the backend default. This is **cosmetic only** — it makes the Rule 38 moon-overlap geometry bug *look louder* by giving each sub-bump its own texture phase, but it does not cause the geometry artifact. Worth fixing in a cleanup pass after Rule 38 is resolved (flip the frontend default to `0`, optionally pin to `0` in `PINNED_FOOTGUN_SOCKETS`). An earlier draft of Rule 38 incorrectly blamed UV Random U as the root cause — see retraction note in Phase 10v.

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
