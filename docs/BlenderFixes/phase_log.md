# Phase log — Blender-side fixes

> **Read this if** you want to know what we changed in `Parametric Weave knotty`, when, and why. Append-only. Each phase recorded as Symptom / Diagnosis / Fix / Verification.

The earlier phases (3d, 3e) are also covered in [../putting-it-together/phase_log.md](../putting-it-together/phase_log.md) — they're duplicated here because BlenderFixes is the curated record of every change that touched the .blend file. Phases 3f onward live only here.

---

## Phase 3d — rename V-band sockets to Arc 1 / Arc 2 (Core/Fiber vocabulary retired)

**Date**: 2026-05-14

### Motivation

The graph's *internal* node names already used Arc 1 / Arc 2 vocabulary (`PW Band - Arc1 Map`, `PW Band - Arc2 Top/Core/Bot`), but the *interface socket* names exposed to the modifier panel still used the older Core / Fiber vocabulary. Every time the artist opened the graph the inner names said "Arc 1 / Arc 2" while the outer sockets said "Core V Min / Fiber Top V Min" — same value, different label, immediate cognitive load. User flagged this directly.

### Diagnosis

Internal-vs-interface vocabulary drift. The semantics never actually changed (the sockets always held core inner edges + fiber inner edges); only the names were inconsistent.

### Fix

Single-file destructive op via MCP. Snapshot first as `Codex_ParametricWeave.pre-arc-rename-20260514_005120.blend` before any rename. 68 interface sockets renamed in one pass on `Parametric Weave knotty.interface.items_tree`:

- 16 × `Material N Core V Min` → `Material N Arc 1 V Min`
- 16 × `Material N Core V Max` → `Material N Arc 1 V Max`
- 16 × `Material N Fiber Top V Min` → `Material N Arc 2 V Max` *(inner upper boundary)*
- 16 × `Material N Fiber Bot V Max` → `Material N Arc 2 V Min` *(inner lower boundary)*
- 4 × global counterparts (`Image Core V Min/Max`, `Image Fiber Top V Min`, `Image Fiber Bot V Max` → `Image Arc 1/Arc 2 V Min/Max`)

**Socket identifiers preserved** by Blender's interface API. Internal connections (switch chains, Map Range wiring) all survived untouched — verified by reading back `PW Band - Arc1 Map.To Min` after the rename and confirming it still links to `PW Material Core V Min Select 16` (the same switch node downstream).

Producer code (`backend/app/blender_live.py`) `PER_MATERIAL_SOCKETS` and `GLOBAL_SOCKETS` tuples updated to the new names.

### Verification

- 68 renames, 0 failures
- Push-bandmeta against test yarn: `{applied: 6, skipped: 0, pinned: 5, globals: 6}` — every renamed socket found and written
- Old socket names no longer resolve (`Material 1 Core V Min (old)` returned `<no socket>`)
- Internal wiring intact: `PW Band - Arc1 Map.To Min ← 'PW Material Core V Min Select 16'`

### What was NOT done

- Did NOT rename `bandMeta.blender.*` keys — producer-side field names describe scan data, not Blender sockets. Decoupling layers gives flexibility for future .blend changes.
- Did NOT rename the internal switch chain nodes (`PW Material Core V Min Select N` etc.). They still say "Core". Cosmetic only — wouldn't affect anything.

### Lesson

**Interface socket renames preserve wiring as long as identifiers don't change.** `it.name = 'New Name'` is safe; deleting + re-adding is not. See [lessons.md](lessons.md) Rule 1.

---

## Phase 3e — make Arc 2 actually render the fiber halo (4-link rewire + producer remap)

**Date**: 2026-05-14

### Motivation

After Phase 3d renamed sockets, the values pushed to `Arc 2 V Min/Max` still coincided with `Arc 1 V Min/Max` by construction (both inner edges of the core). Arc 2 was supposed to span the strand silhouette but instead collapsed onto the core's V range. User asked why the fiber halo wasn't showing.

### Diagnosis

Walked the four Arc Map Range nodes inside `Parametric Weave knotty`. Pre-Phase-3e wiring vs intent:

| Map Range socket | Pre-3e source (value) | Intended source (value) |
|---|---|---|
| `PW Band - Arc2 Top.To Min` | `Fiber Top V Min Select 16` (0.5482) | `Core V Max Select 16` (0.5482) — same value, but inner-edge by deliberate choice |
| `PW Band - Arc2 Top.To Max` | `Core V Min Select 16` (0.4518) — **wrong**: should be outer top, not inner bottom | `Fiber Top V Min Select 16` (now holding fiber_top_v_max = 0.5914) |
| `PW Band - Arc2 Bot.To Min` | `Core V Max Select 16` (0.5482) — **wrong**: should be outer bottom, not inner top | `Fiber Bot V Max Select 16` (now holding fiber_bot_v_min = 0.3987) |
| `PW Band - Arc2 Bot.To Max` | `Fiber Bot V Max Select 16` (0.4518) | `Core V Min Select 16` (0.4518) — same value, deliberately |

Two visibly-wrong links collapsed Arc 2 Top's output range to `[0.5482, 0.4518]` and Arc 2 Bot's to `[0.5482, 0.4518]` — both crossing the core, neither reaching the halo outer extent (0.5914 / 0.3987). The producer was writing INNER-edge values where the artist expected OUTER-edge values.

### Fix

**Producer** ([backend/app/blender_live.py](../../backend/app/blender_live.py)):

```diff
PER_MATERIAL_SOCKETS:
-   ("Arc 2 V Min", "fiber_bot_v_max", 0.0),       # inner — coincided with Arc 1 V Min
-   ("Arc 2 V Max", "fiber_top_v_min", 1.0),       # inner — coincided with Arc 1 V Max
+   ("Arc 2 V Min", "fiber_bot_v_min", 0.0),       # outer bottom of strand silhouette
+   ("Arc 2 V Max", "fiber_top_v_max", 1.0),       # outer top of strand silhouette
```

**Blender** — 4 internal link swaps inside `Parametric Weave knotty`:

| Map Range socket | From | To |
|---|---|---|
| `PW Band - Arc2 Top.To Min` | `PW Material Fiber Top V Min Select 16` | `PW Material Core V Max Select 16` |
| `PW Band - Arc2 Top.To Max` | `PW Material Core V Min Select 16` | `PW Material Fiber Top V Min Select 16` |
| `PW Band - Arc2 Bot.To Min` | `PW Material Core V Max Select 16` | `PW Material Fiber Bot V Max Select 16` |
| `PW Band - Arc2 Bot.To Max` | `PW Material Fiber Bot V Max Select 16` | `PW Material Core V Min Select 16` |

Done via Python over the MCP socket. Pre-rewire backup at `Codex_ParametricWeave.pre-arc2-rewire-20260514_013031.blend`.

### Verification

- Read-back of Material 1 sockets after push: Arc 1 V Min/Max = (0.4518, 0.5482) = core; Arc 2 V Min/Max = (0.3987, 0.5914) = strand outer extents
- Effective Map Range output ranges:
  - Arc 2 Top: `texture-V [0.5482, 0.5914]` = upper halo
  - Arc 2 Core: `texture-V [0.4518, 0.5482]` = core
  - Arc 2 Bot: `texture-V [0.3987, 0.4518]` = lower halo
- Arc 2 now spans 0.193 V (= core thickness + two halo thicknesses), vs 0.096 pre-3e

### What was NOT done

- Did NOT change the Split Minus / Plus computation. The Arc 2 cross-section partition is still `r = Main Strand Radius / (MSR + Sub Strand Width)` — independent of the per-material band metadata. See `Known not-yet-fixed` in [README.md](README.md).
- Did NOT change the `is_sub_strand` gate on `PW Band - Band V` (came up later in Phase 3g).

### Lesson

**When a graph's interface names look right but the values look wrong, the bug can be in three places at once.** Phase 3e's underlying mistake was three layers deep: producer wrote inner-edge values, graph wired Arc 2 to wrong switch chains, naming was ambiguous. See [lessons.md](lessons.md) Rule 2.

---

## Phase 3f — modifier-panel reorg + dead-socket removal

**Date**: 2026-05-14

### Motivation

User flagged two ergonomic issues with the modifier panel:

1. Materials 1-4 NodeSocketMaterial picks lived inside a `Material Slots` panel (collapsed at the bottom), while Materials 5-16 picks were scattered between V-band sockets at root level. Asymmetric — Materials 1-4 vs 5-16 felt like different categories.
2. 96 V-band sockets (16 materials × 6 sockets each) clogged the top of the panel and made finding Pattern / Texture / Imperfections controls a scroll-fest.

Plus an audit found 5 legacy global sockets that no Group Input was consuming — dead weight.

### Diagnosis

Counted 13 distinct Group Input nodes inside the graph (one per logical section: main strand, sub strand, material slots, etc.). Collected every `output.identifier` that had at least one downstream link across all Group Input nodes — that's the set of socket identifiers the graph actually consumes. Five interface input sockets weren't in that set:

```
Image Width Px            (Socket_99)
Image Arc 1 V Min         (Socket_89)
Image Arc 1 V Max         (Socket_90)
Image Arc 2 V Max         (Socket_91)
Image Arc 2 V Min         (Socket_92)
```

All five were the post-Phase-3d-renamed global V-band sockets (formerly `Image Core V Min/Max`, etc.). They had been superseded by the per-material `Material N Arc 1/2 V Min/Max` family but were never removed from the interface. Producer ([blender_live.py](../../backend/app/blender_live.py)) was still pushing values to them via `GLOBAL_SOCKETS` — pure waste.

The `Detail` panel had 0 children — placeholder slot.

### Fix

**.blend changes** (live, via MCP):

1. Removed 5 dead globals via `interface.remove(item)`. Identifiers reclaimed.
2. Removed empty `Detail` panel.
3. Moved Materials 5-16 NodeSocketMaterial picks INTO the `Material Slots` panel — all 16 picks now contiguous.
4. Created `V-Band Mapping` panel (default-closed) and moved all 96 V-band sockets (`Material N Image Width Px / Texture Scale U / Arc 1/2 V Min/Max` for N in 1..16) into it.

**Producer code** ([blender_live.py](../../backend/app/blender_live.py)):

```diff
 GLOBAL_SOCKETS: tuple[tuple[str, str, float], ...] = (
     ("Scanner Pixels Per BU", "scanner_pixels_per_bu", 1.0),
-    ("Image Width Px", "image_width_px", 1.0),
-    ("Image Arc 1 V Min", "core_v_min", 0.0),
-    ("Image Arc 1 V Max", "core_v_max", 1.0),
-    ("Image Arc 2 V Min", "fiber_bot_v_min", 0.0),
-    ("Image Arc 2 V Max", "fiber_top_v_max", 1.0),
 )
```

Producer and consumer are now in sync — no producer pushes a value the graph wouldn't read.

### Verification

- Final top-level interface order: 7 root sockets + 11 panels (down from 12 panels including the empty one)
- `Material Slots` panel children = 16
- `V-Band Mapping` panel children = 96
- Viewport unchanged — weave still renders correctly with all artist defaults intact (Warp Threads, Spacing, Amplitude, Main Strand Radius all preserved across the cleanup)

### What was NOT done

- Did NOT rename the internal switch chain nodes (`PW Material Core V Min Select N`). They're internal-only and consistent with the old data flow; renaming risks confusing the artist who already knows the chain. Cosmetic — could do in a quiet pass later.
- Did NOT add per-Material sub-panels inside `V-Band Mapping` (`Material 1` / `Material 2` / etc.). Flat 96-row list is fine when default-closed. Could subdivide later if the artist wants.

### Lesson

**Audit consumers before removing interface sockets.** A socket without a Group Input output link is genuinely dead — Blender's interface system separates declaration (in `interface.items_tree`) from consumption (via Group Input output links). The dual lookup is the right way to find dead weight. See [lessons.md](lessons.md) Rule 3.

---

## Phase 3g — pin Sub Strand Enable + add BLENDER_LIVE_RENDER dev mode

**Date**: 2026-05-14

### Motivation

Two follow-ups from user testing of Phase 3e:

1. **The Arc 2 halo wasn't visible in rendered output even after the rewire.** Walked the V-output chain and found `PW Band - Band V` was gated by an `is_sub_strand` attribute — Arc 2's three-section mapping only fired on sub-strand geometry, never on main strands. Main-strand faces collapsed to `Arc1 Map` (core texture stretched across the entire cross-section, no halo). Phase 3e's careful rewire was correct but invisible without sub-strand geometry to exercise it.

2. **The "Render Preview" button in the web UI didn't update the open Blender session.** Headless rendering writes a preview.png from a subprocess; the user has to alt-tab between the wizard and Blender to compare. Painful for diagnostic iteration on the .blend.

### Diagnosis

For (1): `PW Band - Band V` is a `MULTIPLY_ADD` math node:

```
Band V = (is_sub_strand attribute) × (Arc2 V − Arc1 Map) + Arc1 Map
```

- `is_sub_strand = 0` (main strand) → Band V = Arc1 Map → core-only sampling
- `is_sub_strand = 1` (sub strand) → Band V = Arc2 V → halo mapping active

The `is_sub_strand` attribute is set by sub-strand geometry generation, which only happens when **Sub Strand Enable (Socket_84)** is True. Default is False — so the rendered yarn never had halo unless the artist manually toggled the modifier socket.

For (2): backend's [render_jobs.py](../../backend/app/render_jobs.py) `_create_render_job` always spawned `blender -b <blend> --python <script>` as a subprocess. The render output was correct, but it ran in a separate Blender process — the open MCP session never saw the result.

### Fix

**(1) Pin Sub Strand Enable in producer** ([blender_live.py](../../backend/app/blender_live.py)):

```diff
 PINNED_FOOTGUN_SOCKETS: tuple[tuple[str, float], ...] = (
+    ("Sub Strand Enable", 1.0),
     ("Texture Scale V", 1.0),
     ("Texture Offset V", 0.0),
     ("Texture Side Flatten", 0.0),
     ("Sub Texture Scale V", 0.0),
     ("Sub Texture Offset V", 0.0),
 )
```

Also set live in the .blend: `mod["Socket_84"] = True`, saved. So both the producer and the .blend's default state now keep the gate open.

**(2) BLENDER_LIVE_RENDER env var** ([render_jobs.py](../../backend/app/render_jobs.py)):

- New helper `_is_live_render_mode()` checks env var.
- New thread function `_run_live_render(job_id, script_text)`:
  - Sends the script body via `send_blender_command("execute_code", {"code": script_text})` to the MCP socket on `BLENDER_PORT` (default 9876).
  - Locally overrides `BLENDER_TIMEOUT_SECONDS` to `BLENDER_LIVE_TIMEOUT_SECONDS` (default 900s) for the call so a long Cycles render doesn't TCP-timeout. Original env var value restored after.
  - Captures the script's stdout into `runtime/render_jobs/<id>/stdout.log`.
  - Verifies `preview.png` exists; same status / image_url shape as the headless path.
- `_create_render_job` dispatch:
  ```python
  if _is_live_render_mode():
      thread = Thread(target=_run_live_render, args=(job.id, script_text), ...)
  else:
      thread = Thread(target=_run_headless_render, args=(job.id, command, config), ...)
  ```

**(3) Makefile target**:

```
make backend-dev-live   # → BLENDER_LIVE_RENDER=1 BLENDER_LIVE_TIMEOUT_SECONDS=900 ...
```

`make backend-dev` (no `-live`) keeps the production headless path.

### Verification

- Toggle test: `BLENDER_LIVE_RENDER=1` / `=true` / `=YES` / `=on` → live mode True. `=0` / `=false` / `=` / `=no` / unset → live mode False.
- Both `_run_headless_render` and `_run_live_render` import + are referenced from `_create_render_job` dispatch.
- Live push of corrected test yarn bandMeta with `Sub Strand Enable = True` in the pinned set: socket reads True afterwards. Viewport shows the sub-strand layer activating Arc 2.

### What was NOT done

- **Did NOT fix the Arc 2 cross-section split mismatch.** Pinning `Sub Strand Enable` makes Arc 2 *fire*, but the Split Minus / Plus partition is still driven by `r = MSR / (MSR + Sub Strand Width)` rather than the per-material band proportions from the scan. Halo regions render with the wrong width relative to the core. Producer publishes the right values (`fiber_top_v_max`, `fiber_bot_v_min`); the graph just doesn't drive `r` from per-material data yet. Logged in [README.md](README.md) Known not-yet-fixed.
- **Did NOT remove the `is_sub_strand` gate from `PW Band - Band V`.** Pinning Sub Strand Enable is sufficient and preserves the dual-rendering capability (main + sub strands stacked, in case a future revision wants different mapping per strand type).
- **Did NOT add a frontend toggle for live-render mode.** Backend-side env var is enough for dev; flipping in the UI risks production users accidentally pointing renders at a Blender they didn't realise was open.

### Lesson

**A socket gate hidden inside a MULTIPLY_ADD silently invalidates upstream fixes.** Phase 3e's Arc 2 rewire was correct in isolation, but the `is_sub_strand × (Arc2 V − Arc1 Map) + Arc1 Map` math meant main-strand geometry skipped Arc 2 entirely. The bug was visible only by tracing the full math expression past the rewired Map Ranges. See [lessons.md](lessons.md) Rule 4.

---

## Phase 3h — direct material-slot binding in Render Preview

**Date**: 2026-05-14

### Motivation

The user wanted to debug Web UI output against a live Blender session. The live/headless switch from Phase 3g made the script run in open Blender, but the visible material mapping still did not match the UI because the script was not driving the material sockets the graph actually consumes.

### Symptom

Live readback:

- `Set Material.Material` and `Set Material.001.Material` were linked from Group Input `Socket_61` (`Material 1`).
- The render script set `node.inputs["Material"].default_value`, which is ignored while the input is linked.
- Modifier `Material 1` still pointed at the previous material.
- `Sub Strand Enable` stayed false despite the producer pin.

### Diagnosis

`Parametric Weave knotty` renders by selecting a modifier `Material N` socket based on per-face `material_id`. For this graph, material setup must update:

1. Object material slots
2. Modifier `Material N` sockets
3. Per-material V-band sockets
4. Warp/Weft material cycle sockets

The tryon branch had only item 3 plus a node-default fallback. The old v2 branch had item 1-4; this phase ports that behavior into tryon.

The `Sub Strand Enable` pin failed because it was sent as `1.0` to a boolean socket. Blender kept the value false.

### Fix

Code:

- [backend/app/render_jobs.py](../../backend/app/render_jobs.py)
  - Added direct per-yarn preview materials for <=16 assets (`FabricStudioMaterial_XX_<asset>`).
  - The generated material nodes load the Cycles-safe diffuse and alpha textures and sample `uv_scaled`.
  - `submit_project_render_job(...)` now passes image paths along with each `bandMeta.blender` entry.
  - The generated script sets modifier `Material N` sockets, object material slots, V-band metadata, and material-cycle inputs.
  - Atlas material remains fallback only when direct material entries are unavailable.
  - Headless failure logs now fall back to `stdout.log` if `stderr.log` is empty.
- [backend/app/blender_live.py](../../backend/app/blender_live.py)
  - Changed pinned `Sub Strand Enable` from `1.0` to `True`.
- Tests:
  - [backend/tests/test_render_jobs.py](../../backend/tests/test_render_jobs.py) covers direct material-slot generation.
  - [backend/tests/test_yarn_assets.py](../../backend/tests/test_yarn_assets.py) fake pipeline signature updated for `orientation=`.

### Verification

Unit tests:

```
cd backend && .venv/bin/python -m unittest tests.test_render_jobs
cd backend && .venv/bin/python -m unittest discover tests
```

Live Blender setup smoke against port 9876, with the actual render call replaced by a setup-only print:

```
[phase3h] material slots pushed:
materials=2
bandMeta.applied=12
bandMeta.skipped=0
bandMeta.pinned=6
bandMeta.globals=1
```

Readback from `ParametricWeave`:

| Socket / slot | Value |
|---|---|
| Slot 0 | `FabricStudioMaterial_01_bb5464ffe724` |
| Slot 1 | `FabricStudioMaterial_02_205d8ac3196e` |
| `Material 1` | `FabricStudioMaterial_01_bb5464ffe724` |
| `Material 2` | `FabricStudioMaterial_02_205d8ac3196e` |
| `Sub Strand Enable` | `true` |
| `Material 1 Arc 1` | `0.483544..0.516456` |
| `Material 1 Arc 2` | `0.458228..0.536709` |
| `Material 2 Arc 1` | `0.451827..0.548173` |
| `Material 2 Arc 2` | `0.398671..0.591362` |

### What was NOT done

- Did NOT port v2's managed Blender session auto-launch. Current tryon still needs Blender opened manually + BlenderMCP started + `make backend-dev-live`.
- Did NOT run a full live Cycles render in this phase; verification was setup-only so we could inspect sockets immediately.
- Did NOT fix the known Arc 2 split-ratio mismatch. This phase makes the right material and V-band data land on the graph; it does not change how the graph partitions halo/core/halo width.

### Lesson

When the rendered material looks stale, inspect whether the node input is linked. If linked, the modifier interface socket is the source of truth; node `default_value` is only a fallback.

---

## Phase 3i — setup-only live push clears stale material slots

**Date**: 2026-05-14

### Motivation

User found an edge case in the live Blender session: assigning the same yarn asset to warp and weft should use one material repeatedly, but Blender could still appear to use two material slots. The user had also changed V socket values in the live modifier while diagnosing Arc2, so the session needed a metadata reset.

### Symptom

`/api/blender/push-project-bandmeta` only pushed band metadata. It did not update:

- `WebDraft_Live`
- object material slots
- modifier `Material N` sockets
- Warp/Weft material cycle sockets

So an older two-material preview could leave `Material 2` and cycle inputs populated even after the current UI bindings deduped to a single yarn asset.

### Diagnosis

Backend material ordering was already correct: `validate_project_bindings(...)` dedupes by yarn asset ID. The live push endpoint was incomplete.

For the same-yarn case, expected live state is:

```
ordered_assets    = [shared_asset]
warp_material_ids = [0, 0, ...]
weft_material_ids = [0, 0, ...]
object slots      = [Material 1 only]
Material 2..16    = None / unused
```

### Fix

[backend/app/render_jobs.py](../../backend/app/render_jobs.py):

- `build_headless_render_script(..., render_still=False)` now runs the full setup body without rendering.
- New `build_project_material_payloads(...)` shares direct material payload construction between Render Preview and live setup.
- `apply_modifier_material_slots(...)` clears stale `Material 2..16` modifier sockets when fewer direct materials are active.

[backend/app/main.py](../../backend/app/main.py):

- `/api/blender/push-project-bandmeta` now sends a full setup-only script to live Blender instead of calling the narrower bandMeta-only helper.

Tests:

- [backend/tests/test_fabric_project.py](../../backend/tests/test_fabric_project.py) covers same asset across warp/weft -> one material.
- [backend/tests/test_render_jobs.py](../../backend/tests/test_render_jobs.py) covers setup-only script generation.

### Verification

Automated:

```
cd backend && .venv/bin/python -m unittest discover tests
```

Passed: `24` tests.

Live Blender readback after setup-only push using `8e4a081d9753` for both warp and weft:

| Socket / slot | Value |
|---|---|
| object slots | `["FabricStudioMaterial_01_8e4a081d9753"]` |
| `Material 1` | `FabricStudioMaterial_01_8e4a081d9753` |
| `Material 2` | `null` |
| `Material 3` | `null` |
| `Warp Length 1 / Material 1` | `4 / 1` |
| `Weft Length 1 / Material 1` | `4 / 1` |
| `Material 1 Arc 1` | `0.483544..0.516456` |
| `Material 1 Arc 2` | `0.369620..0.637975` |
| `Material 1 Top/Bot Halo Frac` | `0.448598 / 0.420561` |

Push summary: `materials=1`, `cleared=15`, `bandMeta.applied=8`, `bandMeta.skipped=0`, `bandMeta.pinned=6`.

### What was NOT done

- Did NOT change Arc2 Map Range direction; this phase only reset values and live setup state.
- Did NOT resolve the suspected draft/material orientation issue. If a `red white white white` repeat still renders as alternating, next check is column-index reversal between the frontend drawdown view and `build_blender_sync_code(...)`.

### Lesson

Material slots, material cycles, WebDraft attributes, and band metadata are one Blender state bundle. A live endpoint that updates only one piece can leave the viewport in a believable but stale mixed state.

---

## Phase 3j — Warp material orientation + U-scale guardrail

**Date**: 2026-05-14

### Motivation

User testing found two Blender-side suspects after Phase 3i:

- A `red white white white` style repeat could land differently in Blender than it appeared in the web Pattern Builder.
- U texture scale looked too compressed/distorted for the scanned yarn.

### Symptom

The web drawdown uses reversed warp/threading columns for display, but the Blender draft mesh wrote `warp_material_id` by raw column index. The matrix could be right while the per-warp material attribute was visually shifted/reversed.

The generator also still allowed root `Texture Scale U = 8.0` for `Parametric Weave knotty`, even though per-yarn physical U width is already measured by `Material N Image Width Px / Scanner Pixels Per BU`.

### Diagnosis

Relevant frontend rule: `getThreadingIndexFromDrawdownColumn(...)` returns `threadingLength - endIndex - 1`.

Relevant backend rule before fix:

```py
flat_warp_materials = [warp_material_ids[col] for row_index in range(rows) for col in range(cols)]
```

For a UI-order test sequence `[0, 1, 1, 1]`, Blender should see `[1, 1, 1, 0]` left-to-right on the drawdown mesh faces.

U-scale math for active yarn `8e4a081d9753`:

```text
45058 px / 62992.16 px-per-BU = 0.71529575 BU per texture repeat
```

So a 1 BU strand should show about `1.40` repeats with scale 1. A stale root scale of 8 would show about `11.18` repeats.

### Fix

- [backend/app/blender_sync.py](../../backend/app/blender_sync.py)
  - `warp_material_id` now writes `warp_material_ids[cols - col - 1]`.
  - Root `Texture Scale U` is pinned to `1.0` for `Parametric Weave knotty`. Superseded by Phase 3l: root U is now fit-aware and setup-owned.
- [backend/app/blender_live.py](../../backend/app/blender_live.py)
  - Root `Texture Scale U = 1.0` is part of the pinned metadata live push. Superseded by Phase 3l: metadata-only push no longer pins root U.
- [backend/app/main.py](../../backend/app/main.py)
  - Fixed the older `/api/blender/push-bandmeta` endpoint so it does metadata-only live pushes again.
- [backend/tests/test_blender_sync.py](../../backend/tests/test_blender_sync.py)
  - Added string-generation guards for the warp reversal and root U value.

### Verification

Automated:

```bash
cd backend && .venv/bin/python -m unittest discover tests
```

Passed: `25` tests.

Live Blender MCP on port `9876`:

| Probe | Readback |
|---|---|
| UI-order warp IDs | `[0, 1, 1, 1]` |
| `warp_material_id` rows | `[1, 1, 1, 0]` repeated across rows |
| restored object slots | `["FabricStudioMaterial_01_8e4a081d9753"]` |
| root `Texture Scale U` | `1.0` *(Phase 3j snapshot; Phase 3l recalculated this to `0.55556`; Phase 3m observed that `0.1` looked better, but Phase 3n marks that as an experimental multiplier, not a unit fact)* |
| `Material 1 Image Width Px` | `45058` |
| `Material 1 Texture Scale U` | `1.0` |
| `Material 1 Arc 1` | `0.483544..0.516456` |
| `Material 1 Arc 2` | `0.369620..0.637975` |
| `Material 1 Top/Bot Halo Frac` | `0.448598 / 0.420561` |

### What was NOT done

- Did NOT alter `cell_code` orientation.
- Did NOT change Arc 2 Map Range direction.
- Did NOT add the future `Texture World Width BU` socket.

### Lesson

The draft mesh is not just a bitmap of over/under cells. It also carries sampled per-warp/per-weft metadata, and each metadata axis must obey the same orientation convention as the UI that authored it.

---

## Phase 3k — Arc 2 Map Range direction flip

**Date**: 2026-05-15

### Motivation

The user identified the remaining Arc 2 visual bug: Arc 2 had three sections, but the end-band mapping was inverted. The halo portion that should sit near the core appeared at the outside edge for both top and bottom.

### Symptom

Top and bottom halo bands were present but directionally wrong. The core band looked closer, but the three-piece map was discontinuous at the section boundaries.

### Diagnosis

Live readback before the fix:

| Node | Old range |
|---|---|
| `PW Band - Arc2 Top` | `Core V Max -> Arc 2 V Max` |
| `PW Band - Arc2 Core` | `Core V Min -> Core V Max` |
| `PW Band - Arc2 Bot` | `Arc 2 V Min -> Core V Min` |

`PW Band - IsTop` uses `v_around < Split Minus`, and `PW Band - IsBot` uses `v_around > Split Plus`. In the rendered geometry, `v_around=0` is the top outer edge and `v_around=1` is the bottom outer edge. The Map Ranges therefore needed to run:

```text
Arc2 Top:  outer top -> core top
Arc2 Core: core top -> core bottom
Arc2 Bot:  core bottom -> outer bottom
```

### Fix

Snapshot first:

`/Users/mihirbotle/Desktop/Impetus/Fabric-generator/Codex_ParametricWeave.pre-arc2-direction-20260515_002417.blend`

Inside `Parametric Weave knotty`, swapped `To Min` / `To Max` links on:

- `PW Band - Arc2 Top`
- `PW Band - Arc2 Core`
- `PW Band - Arc2 Bot`

Saved `/Users/mihirbotle/Desktop/Impetus/Fabric-generator/Codex_ParametricWeave.blend` and copied it back to the tryon repo's [Codex_ParametricWeave.blend](../../Codex_ParametricWeave.blend).

### Verification

Live MCP readback after save:

| Node | New range |
|---|---|
| `PW Band - Arc2 Top` | `Fiber Top -> Core V Max` |
| `PW Band - Arc2 Core` | `Core V Max -> Core V Min` |
| `PW Band - Arc2 Bot` | `Core V Min -> Fiber Bot` |

Modifier metadata still matched the active yarn:

- `Material 1 Arc 1 = 0.483544..0.516456`
- `Material 1 Arc 2 = 0.369620..0.637975`
- `Material 1 Top/Bot Halo Frac = 0.448598 / 0.420561`

### What was NOT done

- Did NOT change producer or backend socket mappings.
- Did NOT remove old dead `r` split nodes.
- Did NOT generate a before/after render pair.

### Lesson

Correct values can still be visually wrong if the Map Range direction is wrong. For every piecewise texture section, read the input coordinate direction and confirm adjacent sections meet at the same texture V.

---

## Phase 3l — Live preview texture sampling + fit-aware U scale

**Date**: 2026-05-15

### Motivation

After the Arc 2 direction fix, the connected Blender viewport still exposed two issues that were easier to see live than through headless renders: the yarn texture looked pixelated, and the U repeat scale did not match the visible `Fit To Space` swatch.

### Symptom

The direct yarn material in Blender sampled the Cycles-safe texture as hard blocks. The modifier also had a stale/manual root `Texture Scale U`, so the visible viewport was not using a predictable U repeat.

### Diagnosis

Live readback found both generated texture nodes set to `Closest` interpolation while loading `cycles_safe` images. The active texture was `16384 × 144`, so nearest-neighbor filtering made the preview look blocky.

For U, the graph measured source strand length as `Warp Threads * Spacing = 180 * 0.03 = 5.4 BU`. The visible target after `Fit To Space` was `3.0 BU`, while texture width was `45058 / 62992.16 = 0.71529536 BU`. Root `Texture Scale U` therefore had to be `3.0 / 5.4 = 0.55556` for the fit-only model. Phase 3m observed that `0.1` looked better; Phase 3n marks that as an experimental multiplier, not a unit fact.

### Fix

- [backend/app/render_jobs.py](../../backend/app/render_jobs.py): generated direct material texture nodes now use `Linear` interpolation.
- [backend/app/blender_sync.py](../../backend/app/blender_sync.py): root `Texture Scale U` for `Parametric Weave knotty` is computed from the `Fit To Space` target: `(max(Space X/Y) * Fill Ratio) / (Warp Threads * Spacing)`.
- [backend/app/blender_live.py](../../backend/app/blender_live.py): root `Texture Scale U` was removed from the pinned live metadata set so setup/render sync remains the single owner of that value.
- Tests updated in [backend/tests/test_blender_sync.py](../../backend/tests/test_blender_sync.py) and [backend/tests/test_render_jobs.py](../../backend/tests/test_render_jobs.py).

### Verification

- `cd backend && .venv/bin/python -m py_compile app/blender_sync.py app/blender_live.py app/render_jobs.py`
- `cd backend && .venv/bin/python -m unittest tests.test_blender_sync tests.test_render_jobs`
- `cd backend && .venv/bin/python -m unittest discover tests` → `25` tests passed.

Live setup push read back:

| Value | Readback |
|---|---:|
| root `Texture Scale U` | `0.55555558` |
| `Material 1 Image Width Px` | `45058` |
| `Scanner Pixels Per BU` | `62992.16015625` |
| effective visible repeats | `4.19407` |
| diffuse/alpha interpolation | `Linear` |

After the readback, the live Blender session still contained older unused `FabricStudioMaterial_*` data-blocks with `Closest` sampling. Those stale material nodes were also switched to `Linear` in-session (`10` texture nodes changed) so future live inspection does not show mixed sampling state.

### What was NOT done

- Did NOT change the .blend graph in this phase.
- Did NOT raise the Cycles-safe texture cap.
- Did NOT add separate warp/weft U scale sockets; the current graph still exposes one root U multiplier.

### Lesson

Texture preview quality and UV repeat math can fail independently. Check material node sampling first, then trace whether the UV coordinate is computed before or after any geometry fitting modifier.

---

## Phase 3m — Center-aligned Arc 2 mapping experiment staging

**Date**: 2026-05-15

### Motivation

The current Arc 2 V mapping still does not convincingly place the yarn halo/fiber region around the core in the live Blender preview. The user proposed an alternate mapping model: keep Arc 1 geometry stable, treat Arc 2 as the full yarn silhouette, and make the central portion of Arc 2 correspond to the same core texture region Arc 1 samples.

### Backup

Before any graph experiment, saved a live Blender copy:

```text
/Users/mihirbotle/Desktop/Impetus/Fabric-generator/Codex_ParametricWeave.pre-centered-arc2-20260515_010801.blend
```

Source file at backup time:

```text
/Users/mihirbotle/Desktop/Impetus/Fabric-generator/Codex_ParametricWeave.blend
```

### Diagnosis

Do not move or resize Arc 1 geometry. Arc 1 is the structural core the weave setup is built around; changing it risks strand overlap, path placement, and downstream fabric behavior.

The experiment only changes the V mapping used by Arc 2, so Arc 2 samples:

```text
outer bottom -> core bottom -> core top -> outer top
```

with the `core bottom -> core top` span centered inside the wider Arc 2 silhouette.

U calibration finding:

```text
fit-only root U = 3.0 / (180 * 0.03) = 0.55556
user-good live root U = 0.1
observed multiplier = 0.1 / 0.55556 = 0.18
```

Interpretation at the time: this was only an empirical ratio from one live visual check. Do not treat it as `1 BU = 0.18 m`; Phase 3n corrects the naming and makes the multiplier optional.

### Fix

Live `.blend` graph:

- Added centered Arc 2 split math nodes:
  - `PW Band - Center Core Width`
  - `PW Band - Center Arc2 Width`
  - `PW Band - Center Arc2 Width Safe`
  - `PW Band - Center Core Frac`
  - `PW Band - Center Half Core Frac`
  - `PW Band - Center Split Minus`
  - `PW Band - Center Split Plus`
- Rewired existing `PW Band - Split Minus` to read from `PW Band - Center Split Minus`.
- Rewired existing `PW Band - Split Plus` to read from `PW Band - Center Split Plus`.
- Did not move or resize Arc 1 geometry.
- Saved `/Users/mihirbotle/Desktop/Impetus/Fabric-generator/Codex_ParametricWeave.blend`.
- Copied the saved file to [Codex_ParametricWeave.blend](../../Codex_ParametricWeave.blend).

Backend:

- [backend/app/blender_sync.py](../../backend/app/blender_sync.py) now applies optional `texture_u_calibration` to root `Texture Scale U`.
- Default calibration is `1.0`.
- Override paths:
  - `renderSettings.textureUCalibration`
  - `FABRIC_TEXTURE_U_CALIBRATION`

### Verification

Live Blender readback:

| Value | Readback |
|---|---:|
| root `Texture Scale U` | `0.10000000149` |
| centered core fraction | `0.1226416184` |
| centered split minus | `0.4386791908` |
| centered split plus | `0.5613208092` |
| `uv_scaled` V min/max | `0.3696202636..0.6379746795` |

Node-link readback:

- `PW Band - Split Minus.Value <- PW Band - Center Split Minus.Value`
- `PW Band - Split Plus.Value <- PW Band - Center Split Plus.Value`

Automated:

```bash
cd backend
.venv/bin/python -m py_compile app/blender_sync.py app/blender_live.py app/render_jobs.py
.venv/bin/python -m unittest tests.test_blender_sync tests.test_render_jobs
```

Result: `11` targeted backend tests passed.

### What was NOT done

- Did not add a switch/toggle; this is a direct experiment on the live graph with the backup listed above.
- Did not rename the legacy internal switch-chain nodes (`Fiber Top V Min` still carries Arc 2 V Max, etc.).
- Did not solve separate warp/weft U scaling.

---

## Phase 3n — Correct U calibration assumption

**Date**: 2026-05-15

### Motivation

The Phase 3m note framed the observed `0.18` multiplier as if it meant `1 BU = 0.18 m`. The user correctly pushed back: warp/weft counts, spacing, fitting, generated geometry, and preprocessing metadata all participate in U scale, so that ratio cannot be treated as a Blender-unit conversion.

### Findings

- Disabling `Fit To Space` gave pre-fit dimensions `5.396 × 5.396`, matching `Warp Threads * Spacing = 180 * 0.03 = 5.4`. The geometry size estimate itself is not obviously wrong.
- The graph stores `u_along` from Blender's `Spline Parameter Factor`, i.e. a normalized path coordinate, then separately multiplies by the estimated strand length.
- The generated `rgba.png` / `albedo.png` files report `72 dpi` in file metadata, while the library metadata carries `1600 dpi` from the preprocessing/export pipeline. That does not prove `1600` is wrong, but it does mean the Blender side cannot validate physical length from the PNG file alone.
- The visually preferred `0.1` root U corresponds to an observed multiplier of `0.18`, but that multiplier may be compensating for preprocessing DPI, generated geometry, texture authoring expectations, or some combination of those.

### Fix

- Renamed the code concept from `scene_bu_to_metadata_m` to `texture_u_calibration`.
- Defaulted it back to `1.0`.
- Kept override paths for continued experiments:
  - `renderSettings.textureUCalibration`
  - `FABRIC_TEXTURE_U_CALIBRATION`
- Updated docs to stop presenting `0.18` as a unit conversion.

### What is still open

- Decide whether U should use actual generated spline length instead of `Warp Threads * Spacing`.
- Validate whether the pipeline's `1600 dpi` is user truth, default truth, or stale metadata.
- Decide whether yarn U should be physically scaled or artistically stretched per swatch.

---

## Phase 3o — U scale trace + source DPI confidence

**Date**: 2026-05-15

### Motivation

The next requested direction was actual spline-length-driven U plus validation of the physical texture scale from preprocessing/scans, with the two checks informing confidence.

### Findings

Live graph trace:

- Active `u_along` is written by `Store Warp U` / `Store Weft U`, not the older dead `Store Named Attribute` node.
- `Warp U Compensated` and `Weft U Compensated` already compute:

```text
Spline Parameter Factor * (Spline Length / Straight Length)
```

- Final U scale still multiplies by `Straight Length / texture_world_width`, so the straight length cancels:

```text
Factor * (Spline Length / Straight Length) * Straight Length
= Factor * Spline Length
```

So the active graph is already spline-length-driven for warp/weft yarns. The unresolved question is why physically scaled repeats look denser than the user expects, not whether the graph lacks spline-length compensation.

Scan/preprocessing check:

| File | Embedded DPI |
|---|---:|
| `black_white_thread_red_Cropped.png` | `1600 × 1600` |
| `vegeta20260512_12555416.png` | `1600 × 1600` |
| `horizon20260512_13115640.png` | `1600 × 1600` |
| processed `20260514_153432_862ad0/rgba.png` | no embedded DPI / read as `72` by macOS tools |

Interpretation: scanner DPI is present on source scans, but processed/exported PNGs may strip it. The metadata DPI can be scanner-backed, but the saved yarn file alone cannot prove that after export.

### Fix

- [backend/app/yarnseamless/yarn_library.py](../../backend/app/yarnseamless/yarn_library.py)
  - Added embedded-DPI inspection for the original `input.*` scan.
  - Added embedded-DPI inspection for `export_assembled_rgba.png`.
  - Added `metadata.physical_scale` with declared DPI, source-scan DPI, processed-export DPI, texture world width, notes, and confidence.
- [backend/tests/test_yarn_library.py](../../backend/tests/test_yarn_library.py)
  - Added coverage that a source scan saved at 1600 DPI produces `physical_scale.confidence = high`.

### Verification

Commands:

```bash
git diff --check
cd backend
.venv/bin/python -m py_compile app/yarnseamless/yarn_library.py app/blender_sync.py app/render_jobs.py app/blender_live.py
.venv/bin/python -m unittest tests.test_yarn_library tests.test_blender_sync tests.test_render_jobs
.venv/bin/python -m unittest discover tests
```

Result: diff check passed, compile passed, `12` targeted tests passed, full backend suite passed (`26` tests).

### What is still open

- Decide whether the current physical repeat density is desired or whether the UI should expose an artistic `textureUCalibration` control.
- Existing saved yarns do not automatically get the new `physical_scale` block unless re-saved or migrated.

---

## Phase 3p — Arc 2 band provenance + geometry-owned split diagnosis

**Date**: 2026-05-15

### Motivation

The user reported that the Arc 2 V mapping still did not look right and asked when the band values are measured: before the final/inpainted image or after it.

### Findings

Producer timing:

- `width.top_y_in_export` / `width.bottom_y_in_export` are based on per-thread `c_band` rows from the multithread process. That pass runs on each thread alpha after Method-K alpha generation, before multifragment assembly and join inpainting.
- During `/api/multithread/export`, those per-thread core rows are shifted into export coordinates and averaged. They are not re-detected from the final exported RGBA.
- `bands_px.fiber_top` / `bands_px.fiber_bot` are computed later in `save_to_library` from `export_assembled_alpha.png`, after assemble, regenerate-alpha, join alpha composition, and no-wraparound export trimming.

Live Blender trace:

- `PW Band - Split Minus` is linked from `PW Band - Center Split Minus`.
- `PW Band - Split Plus` is linked from `PW Band - Center Split Plus`.
- The centered split still uses:

```text
core_frac = (Arc 1 V Max - Arc 1 V Min) / (Arc 2 V Max - Arc 2 V Min)
Split Minus = 0.5 - core_frac / 2
Split Plus  = 0.5 + core_frac / 2
```

### Diagnosis

The current Arc 2 split asks texture metadata to answer a geometry question. Texture V bands tell Blender what image rows should be sampled once a region is chosen, but they do not prove how much of Arc 2's generated cross-section is actually occupied by the Arc 1/core overlap.

That matches the viewport symptom: V endpoints and map direction can be numerically correct while the apparent core/halo area on Arc 2 still feels wrong.

### Direction

The next Blender-side change should compute Arc 2 split boundaries from generated geometry or geometry-node attributes, then use scan metadata only as the destination texture V values:

```text
Arc 2 geometry domain -> computed core interval -> texture V destinations
```

Candidate debug attributes before committing the final graph:

- `arc2_v_around`
- `arc2_region_id`
- `arc2_core_mask`
- `arc2_core_split_min`
- `arc2_core_split_max`

### Verification

- Read the producer path in `backend/app/yarnseamless_routes.py` and `backend/app/yarnseamless/yarn_library.py`.
- Queried the live Blender node group over MCP on port 9876 and confirmed `Split Minus/Plus` are still driven by the centered V-span math.
- No `.blend` or code behavior changed in this phase; docs only.

### What was NOT done

- Did not change Arc 1 geometry.
- Did not attempt another Arc 2 split formula yet.
- Did not migrate old yarn metadata.

---

## Phase 3q — Geometry-owned Arc 2 split test

**Date**: 2026-05-15

### Motivation

The user said "start" after Phase 3p concluded the Arc 2 split should be calculated by Blender geometry, not inferred from texture V bands.

### Backup

Before editing the live `.blend`, saved the current file and copied:

```text
/Users/mihirbotle/Desktop/Impetus/Fabric-generator/Codex_ParametricWeave.pre-arc2-geometry-split-20260515_014653.blend
```

### Findings

Evaluated mesh already had useful attributes:

- `v_around`
- `is_sub_strand`
- `uv_scaled`
- `material_id`

But the old radius chain was stale for this use:

- Modifier panel showed `Main Strand Radius = 0.025` and `Sub Strand Width = 0.0`.
- The old `Math.017` chain still evaluated Arc 2 radius as `0.015` on the mesh.
- Therefore `Math.017` was bypassed for the geometry-owned split test.

### Blender Changes

Saved live source and repo copy:

- `/Users/mihirbotle/Desktop/Impetus/Fabric-generator/Codex_ParametricWeave.blend`
- `Codex_ParametricWeave.blend` in the tryon repo

Node-group changes inside `Parametric Weave knotty`:

- Added `PW Band - Geo Arc1 Radius Value = 0.015`.
  - Linked to `Arc.Radius`.
  - Linked to `PW Band - Geo Core Frac Raw`.
- Added `PW Band - Geo Arc2 Radius Value = 0.025`.
  - Linked to `Arc.001.Radius`.
  - Linked to `PW Band - Geo Arc2 Radius Safe`.
- Added geometry split math:
  - `PW Band - Geo Arc2 Radius Safe`
  - `PW Band - Geo Core Frac Raw`
  - `PW Band - Geo Core Frac Clamp Hi`
  - `PW Band - Geo Core Frac`
  - `PW Band - Geo Half Core Frac`
  - `PW Band - Geo Split Minus`
  - `PW Band - Geo Split Plus`
- Rewired:
  - `PW Band - Split Minus.Value <- PW Band - Geo Split Minus.Value`
  - `PW Band - Split Plus.Value <- PW Band - Geo Split Plus.Value`
- Reset live modifier `Sub Strand Width` from `-0.01` to `0.0`.
- Added evaluated debug stores before `uv_scaled`:
  - `arc1_radius_geometry`
  - `arc2_radius_geometry`
  - `arc2_core_frac_raw`
  - `arc2_core_frac_geometry`
  - `arc2_core_split_min`
  - `arc2_core_split_max`

### Verification

MCP readback from the evaluated mesh:

```text
arc1_radius_geometry     = 0.015
arc2_radius_geometry     = 0.025
arc2_core_frac_raw       = 0.6
arc2_core_frac_geometry  = 0.6
arc2_core_split_min      = 0.2
arc2_core_split_max      = 0.8
```

First sub-strand `uv_scaled.y` samples now use the wider geometry-owned interval:

```text
v_around 0.000 -> 0.6379747  (Arc 2 top outer)
v_around 0.333 -> 0.5091420  (inside core band)
v_around 0.667 -> 0.4908579  (inside core band)
v_around 1.000 -> 0.3696203  (Arc 2 bottom outer)
```

### What was NOT done

- Did not move or resize Arc 1 beyond linking its existing `0.015` profile radius through a shared value node.
- Did not expose the new Arc 1/Arc 2 profile radius values as modifier sockets yet.
- Did not remove the old Phase 3m centered texture-span nodes or the old `Math.017` chain.
- Did not visually approve the result; this is ready for live viewport review.

---

## Phase 3r — Live high-res texture inspection

**Date**: 2026-05-15

### Motivation

The rendered yarn looked blurry and nearly transparent on Arc 2. The user suspected texture resolution.

### Findings

The active material was not sampling the original full-resolution asset. It was sampling the Cycles-safe downscale:

```text
original albedo/alpha: 45058 x 395
render albedo/alpha:   16384 x 144
```

The strip is still wide, but its V height drops to `144px`; the dense core is only about `14px` tall in the original and about `5px` tall after downscale.

Alpha is also extremely low at the Arc 2 outer V rows:

```text
Arc 2 top outer row mean alpha: ~1.5 / 255
Arc 2 bot outer row mean alpha: ~2.1 / 255
Core rows mean alpha:           ~117-205 / 255
```

### Live Change

For inspection only, the active live material `FabricStudioMaterial_01_8e4a081d9753` now points to the original files:

```text
runtime/yarn_assets/8e4a081d9753/albedo.png
runtime/yarn_assets/8e4a081d9753/alpha.png
```

No pipeline default was changed. A future Render Preview can recreate the material from `renderDiffuseFilename` / `renderAlphaFilename` and return to the Cycles-safe downscale unless the code gets a high-res inspection mode.

### What is still open

- If full-res core looks sharper, add an explicit high-res live inspection mode.
- If Arc 2 still looks transparent at full-res, add an alpha remap/boost for preview instead of using raw scan alpha directly.

---

## Phase 3s — High-resolution render path research

**Date**: 2026-05-15

### Motivation

The original yarn scan was intended for very high-detail final renders, potentially `16K` or `32K` output on rented render hardware. The Cycles-safe downscale protects the current Blender preview from crashing, but it loses V detail on the `45058 x 395` yarn strip.

### Findings

The `16384` cap in this project is a safety net added after Blender/Cycles raised the real error:

```text
Texture exceeds maximum allowed size of 16384 x 16384 (requested: 45058 x 395)
```

Our importer exposes `CYCLES_MAX_TEXTURE_DIM`, but raising that value only raises our preflight threshold. It does not prove Blender/Cycles, the GPU backend, or the render server can upload a single bitmap whose width is greater than the device texture limit.

Blender output resolution is a separate problem from texture upload size. Huge outputs are possible in principle when there is enough RAM and render time; a `32K x 32K` frame is about `1.07B` pixels before render buffers, denoising buffers, AOVs, compositor buffers, or file encode overhead.

### Research Notes

- Blender/Cycles GPU commonly hits the exact `16384 x 16384` single-texture limit. Related source: <https://blender.stackexchange.com/questions/276897/blender-reports-error-texture-exceeds-maximum-allowed-size>
- Blender supports UDIM tile workflows, where one logical texture is split across multiple image tiles. Official manual: <https://docs.blender.org/manual/en/latest/modeling/meshes/uv/workflows/udims.html>
- V-Ray GPU has an out-of-core texture mode that offloads texture data to system RAM for high-resolution texture-heavy scenes. Chaos docs: <https://support.chaos.com/hc/en-us/articles/23900002188945-Out-of-core-textures-in-V-Ray-GPU>
- V-Ray for Blender supports Blender `5.0`, `4.5 LTS`, and `4.2 LTS`. Chaos docs: <https://support.chaos.com/hc/en-us/articles/36717100424721-Which-Blender-versions-does-V-Ray-support>
- V-Ray for Blender supports V-Ray/V-Ray GPU, Chaos Cloud, and VFB. Chaos docs: <https://support.chaos.com/hc/en-us/articles/36717373170833-What-V-Ray-features-are-available-in-V-Ray-for-Blender>
- V-Ray for Blender's free Community Edition is capped at `2560 x 2560`; trial/paid plans list unlimited max resolution and batch/headless rendering. Chaos page: <https://www.chaos.com/vray/blender/community>

### Recommended Direction

Do not make "raise `CYCLES_MAX_TEXTURE_DIM`" the production solution. Use it only for local experiments.

Primary Blender/Cycles path: split the full-resolution strip into U-tiles/UDIMs so no single image exceeds `16384` on either axis. For the active `45058 x 395` texture, that means three horizontal tiles, preserving all `395px` of V detail instead of downscaling to `144px`.

Renderer evaluation path: test V-Ray for Blender on a duplicate `.blend`, with one material using the original albedo/alpha and V-Ray GPU out-of-core textures enabled. Because this setup depends on Geometry Nodes, the test must confirm that the current weave graph renders correctly before any wider migration.

### What was NOT done

- Did not install V-Ray.
- Did not change the current render pipeline.
- Did not raise `CYCLES_MAX_TEXTURE_DIM`.
- Did not implement tiled/UDIM texture generation yet.

---

## Phase 4a — Full-resolution Cycles UDIM yarn tiles

**Date**: 2026-05-15

### Motivation

Phase 3s showed the real constraint: Cycles cannot reliably upload one `45058 x 395` image, but the downscaled `16384 x 144` fallback loses vertical yarn detail. Phase 4 starts by keeping Blender/Cycles and replacing "one giant image" with legal U tiles.

### Fix

- [backend/app/models.py](../../backend/app/models.py): added runtime `YarnAsset` fields for tiled render textures:
  - `renderTextureMode`
  - `renderDiffuseTilePattern` / `renderAlphaTilePattern`
  - `renderDiffuseTileFilenames` / `renderAlphaTileFilenames`
  - tile count and tile dimensions
- [backend/app/yarn_assets.py](../../backend/app/yarn_assets.py):
  - Added `ensure_cycles_tiled_texture_set(...)`.
  - Library import now writes `cycles_tiled/albedo_1001.png`, `albedo_1002.png`, ... and matching alpha tiles when the source exceeds the Cycles single-texture cap.
  - Existing assets can be tiled lazily when material payloads are built.
- [backend/app/render_jobs.py](../../backend/app/render_jobs.py):
  - Material payloads now prefer full-resolution UDIM tile metadata when available.
  - Generated material nodes create Blender `TILED` images with `<UDIM>` file patterns.
  - The shader maps `fract(uv_scaled.x) * tile_count` into UDIM U space, so the full yarn repeat still loops like the original one-image material.
  - The old Cycles-safe image remains as fallback for atlas paths and non-tiled assets.
- Tests:
  - [backend/tests/test_yarn_assets.py](../../backend/tests/test_yarn_assets.py) covers slicing wide strips into UDIM files.
  - [backend/tests/test_render_jobs.py](../../backend/tests/test_render_jobs.py) covers UDIM script generation and lazy tile payload creation.

### Live Session

Generated tiles for the active asset `8e4a081d9753`:

```text
cycles_tiled/albedo_1001.png
cycles_tiled/albedo_1002.png
cycles_tiled/albedo_1003.png
cycles_tiled/alpha_1001.png
cycles_tiled/alpha_1002.png
cycles_tiled/alpha_1003.png
```

The active live material `FabricStudioMaterial_01_8e4a081d9753` now uses:

```text
Diffuse pattern: .../cycles_tiled/albedo_<UDIM>.png
Alpha pattern:   .../cycles_tiled/alpha_<UDIM>.png
Tiles:           1001, 1002, 1003
Tile size:       ~15019-15020 x 395
```

This preserves the original `395px` V detail while keeping every individual image below the `16384` dimension cap.

### Verification

```text
backend/.venv/bin/python -m py_compile app/models.py app/yarn_assets.py app/render_jobs.py
backend/.venv/bin/python -m unittest tests.test_yarn_assets tests.test_render_jobs
backend/.venv/bin/python -m unittest discover -s tests
```

Results:

```text
Ran 29 tests in 0.035s
OK
```

Live Blender readback showed both generated texture nodes as `source = TILED`, `extension = CLIP`, `interpolation = Linear`, and tiles `[1001, 1002, 1003]`.

### What was NOT done

- Did not install V-Ray.
- Did not remove the Cycles-safe downscale path; it remains the fallback.
- Did not run a final high-resolution headless render on server hardware.
- Did not visually approve the UDIM material in the viewport yet.

---

## Phase 4b — Arc 1 core V padding

**Date**: 2026-05-15

### Motivation

After manual Arc 1 / Arc 2 profile-radius tuning in Blender, the user liked the geometry but wanted Arc 1 to sample the core texture a little higher in V. Example requested behavior:

```text
core 0.30..0.60 -> Arc 1 map 0.25..0.65
```

Correction during the phase: the intended change is padding/expansion, not a same-direction offset. Bottom side moves by `-0.05`; top side moves by `+0.05`.

### Fix

[backend/app/blender_live.py](../../backend/app/blender_live.py) temporarily applied `DEFAULT_ARC1_V_PADDING = 0.05` when `build_material_asset_entry(...)` projected `bandMeta.blender.core_v_min/max` into the runtime material entry. Phase 4c later removed this backend ownership.

The padding:

- expands the original Arc 1 V span,
- subtracts `0.05` from Arc 1 V Min,
- adds `0.05` to Arc 1 V Max,
- clamps the padded interval inside the Arc 2 silhouette (`fiber_bot_v_min..fiber_top_v_max`) so the Arc 2 halo sections do not invert,
- could be overridden with `FABRIC_ARC1_V_PADDING` before Phase 4c removed the backend default.

### Live Session

Applied the padding directly to the current live modifier without re-running full setup, so the user's manual profile-radius changes were left intact:

```text
Material 1 Arc 1 V Min: 0.48354429 -> 0.43354431
Material 1 Arc 1 V Max: 0.51645571 -> 0.56645572
```

### Verification

```text
backend/.venv/bin/python -m py_compile app/blender_live.py app/render_jobs.py
backend/.venv/bin/python -m unittest tests.test_blender_live tests.test_render_jobs
```

Results:

```text
Ran 11 tests
OK
```

### What was NOT done

- Did not change Arc 1 / Arc 2 geometry radii.
- Did not re-run the full live setup script.
- Superseded by Phase 4c, which moved this from a backend default/env override into the Blender modifier panel.

---

## Phase 4c — Arc 1 padding modifier socket

**Date**: 2026-05-15

### Motivation

The user wanted to tune the Arc 1 padding directly from Blender for now. Phase 4b had the right padding idea but the wrong ownership: it baked padding into the backend material-entry projection. That made iteration slower and risked double-application if the graph also exposed a control.

### Backup

Saved the current live Blender state before graph edits:

```text
/Users/mihirbotle/Desktop/Impetus/Fabric-generator/Codex_ParametricWeave.pre-arc1-padding-socket-20260515_025526.blend
```

### Fix

Inside `Parametric Weave knotty`:

- Added a new modifier input socket: `Arc 1 V Padding`
- Default value at Phase 4c time: `0.05` *(Phase 4d later changed the saved Blender/Web default to `0.1`)*
- Added four math nodes:
  - `PW Band - Arc1 V Min Pad Subtract`
  - `PW Band - Arc1 V Min Padded`
  - `PW Band - Arc1 V Max Pad Add`
  - `PW Band - Arc1 V Max Padded`
- Rewired:
  - `PW Band - Arc1 Map.To Min`
  - `PW Band - Arc2 Core.To Max`
  - `PW Band - Arc2 Bot.To Min`
  to use padded min.
- Rewired:
  - `PW Band - Arc1 Map.To Max`
  - `PW Band - Arc2 Top.To Max`
  - `PW Band - Arc2 Core.To Min`
  to use padded max.

Math:

```text
padded_min = max(active_material_arc1_v_min - Arc 1 V Padding, active_material_arc2_v_min)
padded_max = min(active_material_arc1_v_max + Arc 1 V Padding, active_material_arc2_v_max)
```

Backend change:

- [backend/app/blender_live.py](../../backend/app/blender_live.py) now pushes raw `core_v_min/max` again.
- Removed the Phase 4b `FABRIC_ARC1_V_PADDING` backend default so the modifier socket is the only padding source.
- [backend/tests/test_blender_live.py](../../backend/tests/test_blender_live.py) now asserts raw Arc 1 projection.

### Live Session

Current modifier values:

```text
Arc 1 V Padding          0.05  # Phase 4c readback; Phase 4d changes this to 0.1
Material 1 Arc 1 V Min   0.48354429  # raw metadata core min
Material 1 Arc 1 V Max   0.51645571  # raw metadata core max
Material 1 Arc 2 V Min   0.38876405
Material 1 Arc 2 V Max   0.60898876
```

Effective padded Arc 1 range is therefore:

```text
0.43354429 .. 0.56645571
```

Saved both:

```text
/Users/mihirbotle/Desktop/Impetus/Fabric-generator/Codex_ParametricWeave.blend
/Users/mihirbotle/Desktop/Impetus/3D Fabric/yarnseamless UI/Fabric-generator-tryon/Codex_ParametricWeave.blend
```

### Verification

```text
backend/.venv/bin/python -m py_compile app/blender_live.py app/render_jobs.py
backend/.venv/bin/python -m unittest tests.test_blender_live tests.test_render_jobs
```

Results:

```text
Ran 11 tests
OK
```

Live readback confirmed the six Arc1/Arc2 inner links now come from `PW Band - Arc1 V Min Padded` / `PW Band - Arc1 V Max Padded`.

### What was NOT done

- Did not add this control to the Web UI.
- Did not change Arc 1 / Arc 2 profile radii.

---

## Phase 4d — Web-exposed U calibration, Arc 1 padding, and weave zoom presets

**Date**: 2026-05-15

### Motivation

The live tests across three setup versions agreed on one practical rule: the fit-aware root U value needs the tested divide-by-10 calibration. The user also wanted the tuning values reachable from the Web UI instead of hidden in code or Blender-only panels.

### Fix

- [backend/app/blender_sync.py](../../backend/app/blender_sync.py)
  - changed `DEFAULT_TEXTURE_U_CALIBRATION` from `1.0` to `0.1`;
  - reads `renderSettings.arc1VPadding`;
  - preserves and pushes the `Arc 1 V Padding` modifier socket, defaulting to `0.1`;
  - lowers fallback `Warp Threads` / `Weft Threads` defaults from `96` to `80` for close inspection.
- [frontend/src/domain/types.ts](../../frontend/src/domain/types.ts) and [frontend/src/domain/draft.ts](../../frontend/src/domain/draft.ts)
  - added `textureUCalibration` and `arc1VPadding` to `DraftRenderSettings`;
  - default `textureUCalibration = 0.1`;
  - default `arc1VPadding = 0.1`;
  - changed render preview thread defaults to `80`;
  - normalized the Web UI zoom levels to `80`, `120`, `160`, `200`, while still flooring to the draft's actual end/pick count if needed.
- [frontend/src/components/RenderPanel.tsx](../../frontend/src/components/RenderPanel.tsx)
  - exposed `Texture U Calibration` in this pass, then Phase 4e removed it from the UI because U should simply divide the calculated value by 10;
  - exposes `Arc 1 V Padding`;
  - adds one `Weave Zoom` segmented control that writes both `warpThreads` and `weftThreads` together.
- [frontend/src/styles/index.css](../../frontend/src/styles/index.css)
  - styles the new zoom preset row.
- [backend/tests/test_blender_sync.py](../../backend/tests/test_blender_sync.py)
  - asserts the Arc 1 padding override is embedded in the generated Blender sync script.

### Blender File

Created backup:

```text
/Users/mihirbotle/Desktop/Impetus/Fabric-generator/Codex_ParametricWeave.pre-phase4d-web-controls-20260515_032532.blend
```

Then set the live and saved modifier default:

```text
Arc 1 V Padding = 0.10000000149
```

Saved both:

```text
/Users/mihirbotle/Desktop/Impetus/Fabric-generator/Codex_ParametricWeave.blend
/Users/mihirbotle/Desktop/Impetus/3D Fabric/yarnseamless UI/Fabric-generator-tryon/Codex_ParametricWeave.blend
```

### Verification

```text
frontend: npm run build
backend:  .venv/bin/python -m unittest discover -s tests
Blender readback: Arc 1 V Padding default and modifier value both 0.10000000149
```

Results:

```text
frontend build succeeded
Ran 31 tests
OK
```

### What was NOT done

- Did not change Arc 1 / Arc 2 geometry again.
- Did not make separate warp and weft count controls; by design this phase exposes one zoom selector that changes both together.

---

## Phase 4e — Hide Texture U Calibration from the Web UI

**Date**: 2026-05-15

### Motivation

User correction: `Texture U Calibration` should not be an exposed control. The rule is fixed for now: take whatever U scale the setup calculates and divide by `10`.

### Fix

- [frontend/src/components/RenderPanel.tsx](../../frontend/src/components/RenderPanel.tsx)
  - removed `Texture U Calibration` from `EXPOSED_FIELDS`;
  - left `Arc 1 V Padding` and `Weave Zoom` exposed.
- [frontend/src/domain/draft.ts](../../frontend/src/domain/draft.ts)
  - still keeps hidden `textureUCalibration = 0.1` in normalized `renderSettings`.
- [backend/app/blender_sync.py](../../backend/app/blender_sync.py)
  - still defaults `DEFAULT_TEXTURE_U_CALIBRATION = 0.1`, so the final formula remains:

```text
# Phase 4e state only. Superseded by Phase 4i.
root_texture_scale_u = calculated_fit_scale * 0.1
```

### Verification

```text
frontend: npm run build
```

Result:

```text
build succeeded
```

---

## Phase 4f — Higher-quality Web preview render

**Date**: 2026-05-15

### Motivation

The user noticed the open Blender viewport and the Web UI preview did not look identical, then asked whether the preview could render at higher resolution and for a little longer.

### Diagnosis

The active backend process on `127.0.0.1:8000` had `BLENDER_PORT=9876` but no `BLENDER_LIVE_RENDER=1`, so the Web UI preview is the headless/subprocess path. That means it renders from the saved `.blend` copy on disk, not the exact interactive viewport state. The viewport can also be Material Preview / an interactive Cycles view with different sampling and zoom, while the Web UI is a saved PNG that the browser displays inside the preview panel.

### Fix

- [backend/app/render_jobs.py](../../backend/app/render_jobs.py)
  - added `DEFAULT_PREVIEW_RENDER_RESOLUTION = 3200`;
  - added `DEFAULT_PREVIEW_RENDER_SAMPLES = 96`;
  - pins still renders to Cycles, `3200 × 3200`, 100% resolution, 96 samples, and denoising on;
  - prints a `phase4f_preview_quality` block into the render job log;
  - allows debug/server overrides with `WEAVE_PREVIEW_RENDER_RESOLUTION` and `WEAVE_PREVIEW_RENDER_SAMPLES`.
- [backend/tests/test_render_jobs.py](../../backend/tests/test_render_jobs.py)
  - asserts the generated render script contains the pinned preview resolution and sample settings.
- [docs/BlenderFixes/architecture.md](architecture.md)
  - documents the new default preview quality.

### Why viewport and Web preview can still differ

- Default backend mode is headless: saved `.blend` on disk, not the live viewport session.
- Live viewport may show unsaved modifier/radius/material tweaks that were not saved or pushed.
- Viewport display mode and sampling differ from final still rendering.
- Browser preview rotates/scales the saved PNG for draft-reading direction.

For exact open-session rendering, restart backend with `make backend-dev-live` so Render Preview executes inside the live Blender session over MCP.

### Verification

```text
backend: .venv/bin/python -m unittest discover -s tests
```

---

## Phase 4g — Sync user-saved Blender file into backend copy

**Date**: 2026-05-15

### Motivation

The user saved the live Blender file after viewport tuning and asked to update the backend Blender file so headless/Web preview renders use that same saved setup.

### Fix

Copied:

```text
/Users/mihirbotle/Desktop/Impetus/Fabric-generator/Codex_ParametricWeave.blend
```

to:

```text
/Users/mihirbotle/Desktop/Impetus/3D Fabric/yarnseamless UI/Fabric-generator-tryon/Codex_ParametricWeave.blend
```

Before overwriting the backend copy, saved backup:

```text
/Users/mihirbotle/Desktop/Impetus/3D Fabric/yarnseamless UI/Fabric-generator-tryon/Codex_ParametricWeave.pre-user-save-sync-20260515_040139.blend
```

### Verification

```text
cmp -s source.blend backend-copy.blend
```

Result:

```text
blend files match
```

---

## Phase 4h — Lower Arc 1 V Padding default to 0.012

**Date**: 2026-05-15

### Motivation

The user requested `Arc 1 V Padding` default `0.012`, reducing the previous broad core expansion while keeping the control exposed for tuning.

### Fix

- [backend/app/blender_sync.py](../../backend/app/blender_sync.py)
  - added `DEFAULT_ARC1_V_PADDING = 0.012`;
  - changed the Blender sync fallback for `Arc 1 V Padding` from `0.1` to `0.012`.
- [frontend/src/domain/draft.ts](../../frontend/src/domain/draft.ts)
  - added `DEFAULT_ARC1_V_PADDING = 0.012`;
  - changed default `draft.renderSettings.arc1VPadding` to `0.012`.
- [frontend/src/components/RenderPanel.tsx](../../frontend/src/components/RenderPanel.tsx)
  - changed the Arc 1 padding input step to `0.001`, so `0.012` can be edited cleanly.
- Saved the live Blender file and backend copy with `Arc 1 V Padding = 0.012000000104308128`.

### Blender File

Created backups:

```text
/Users/mihirbotle/Desktop/Impetus/Fabric-generator/Codex_ParametricWeave.pre-arc1-padding-default-0012-20260515_041138.blend
/Users/mihirbotle/Desktop/Impetus/3D Fabric/yarnseamless UI/Fabric-generator-tryon/Codex_ParametricWeave.pre-arc1-padding-default-0012-20260515_041138.blend
```

Saved:

```text
/Users/mihirbotle/Desktop/Impetus/Fabric-generator/Codex_ParametricWeave.blend
/Users/mihirbotle/Desktop/Impetus/3D Fabric/yarnseamless UI/Fabric-generator-tryon/Codex_ParametricWeave.blend
```

### Verification

```text
backend: .venv/bin/python -m unittest discover -s tests
frontend: npm run build
Blender readback: socket default/current modifier value = 0.012000000104308128
```

---

## Phase 4i — Move U fit correction from root scale to per-material scale

**Date**: 2026-05-15

### Motivation

The user noticed that the setup was changing root `Texture Scale U`, which is a global modifier control. The graph already exposes `Material N Texture Scale U`, so imported multi-material yarns should use that socket for the fit/divide-by-10 correction. Root `Texture Scale U` should stay `1.0` unless we intentionally add a global artistic override.

### Diagnosis

Phase 3l/4d put the fit-aware U value on root `Texture Scale U`. That made one yarn look correct, but it collapsed the distinction between the global texture scale and per-material scale. When multiple materials are imported, `Material N Texture Scale U` existed in the modifier panel but was not receiving the calculated setup multiplier.

### Fix

- [backend/app/blender_sync.py](../../backend/app/blender_sync.py)
  - keeps `root_texture_scale_u = 1.0` for `Parametric Weave knotty`;
  - computes `material_texture_scale_u = (max(Space X/Y) * Fill Ratio) / (Warp Threads * Spacing) * texture_u_calibration`;
  - still defaults `texture_u_calibration = 0.1`, preserving the user-tested divide-by-10 behavior.
- [backend/app/blender_live.py](../../backend/app/blender_live.py)
  - multiplies each pushed `Material N Texture Scale U` by `_PW_TEXTURE_SCALE_U_MULTIPLIER`;
  - leaves metadata-only live pushes neutral unless a setup/render path provides the multiplier.
- [backend/app/render_jobs.py](../../backend/app/render_jobs.py)
  - passes the generated `material_texture_scale_u` multiplier into the render script before material metadata is applied.
- [backend/tests/test_blender_sync.py](../../backend/tests/test_blender_sync.py), [backend/tests/test_blender_live.py](../../backend/tests/test_blender_live.py), and [backend/tests/test_render_jobs.py](../../backend/tests/test_render_jobs.py)
  - assert root U stays neutral and per-material U receives the multiplier.
- Updated [architecture.md](architecture.md), [README.md](README.md), [lessons.md](lessons.md), and the putting-it-together docs with the Phase 4i contract.

### Blender File

Created backups:

```text
/Users/mihirbotle/Desktop/Impetus/Fabric-generator/Codex_ParametricWeave.pre-root-u-neutral-20260515_20260515_131956.blend
/Users/mihirbotle/Desktop/Impetus/3D Fabric/yarnseamless UI/Fabric-generator-tryon/Codex_ParametricWeave.pre-root-u-neutral-20260515_20260515_131956.blend
```

Saved both live and backend copies with root `Texture Scale U` default/current value set to `1.0`.

### Verification

```text
backend: .venv/bin/python -m unittest discover -s tests
Blender readback: root Texture Scale U default/current = 1.0
Blender readback: Material 1/2 Texture Scale U defaults = 1.0
cmp -s source.blend backend-copy.blend
```

Result:

```text
Ran 32 tests
OK
blend files match
```

### What was NOT done

- Did not add a separate warp-vs-weft U multiplier; the current graph still has one setup-owned U multiplier applied per material.
- Did not overwrite the user's current per-material modifier values beyond the saved defaults. The next setup/render push writes the calculated values into the relevant material sockets.

---

## Phase 4j — Re-push calibrated per-material U when Blender controls change

**Date**: 2026-05-15

### Motivation

The user saw `Material 1/2 Texture Scale U = 0.5` in Blender, manually changed those to `0.05`, and the texture immediately looked better. That matches the divide-by-10 calibration, but the value was not naturally reaching the live modifier panel.

### Diagnosis

The backend setup/render formula already includes `texture_u_calibration = 0.1`, so a fit-only `0.5` should become `0.05` before writing `Material N Texture Scale U`. The stale value came from the frontend live-push debounce signature: it watched yarn colors and bindings, but not `draft.renderSettings`. Changing zoom/spacing/render controls could leave Blender with the previous material U values until a full render/setup path ran.

Arc 2 transparency was checked against the current Vegeta/Horizon alpha maps. Core rows average around `203–213` alpha, but Arc 2 halo rows average only `20–29`; most halo pixels are below alpha `80`. The material shader is using alpha directly, so Arc 2 looks transparent because it is sampling sparse halo data.

### Fix

- [frontend/src/App.tsx](../../frontend/src/App.tsx)
  - added `draft.renderSettings` to the live-push signature so changing Weave Zoom, Spacing, Fill Ratio, or hidden U calibration retriggers `/api/blender/push-project-bandmeta`.
- [frontend/src/utils/parserApi.ts](../../frontend/src/utils/parserApi.ts)
  - updated the endpoint comment to document that project live-push includes render-setting context, not only band metadata.
- [lessons.md](lessons.md)
  - added rules for render-settings live-push ownership and alpha-driven Arc 2 transparency.

### Verification

Alpha scan:

```text
Vegeta core mean alpha: 203-214; halo mean alpha: 21-29
Horizon core mean alpha: 210-213; halo mean alpha: 19-29
```

Build/test verification is recorded in the final response for this turn.

### What was NOT done

- Did not add an alpha-boost or hard-alpha material control yet. That is the likely next visual tuning step if we want Arc 2 to read less transparent while keeping the same V mapping.

---

## Phase 4 — (next) candidate follow-ups

- **Visually approve Phase 3q's geometry-owned Arc 2 split** in the live viewport. Current evaluated split is `0.2 / 0.8`.
- **Decide between high-res inspection mode and alpha boost.** Phase 3r switched the current live material to full-res files for visual comparison, but the code still defaults to Cycles-safe textures.
- **Visually approve Phase 4a's UDIM material** in the live viewport, then run a crop render to confirm Cycles samples all three tiles correctly.
- **Run a V-Ray duplicate-file proof** with V-Ray GPU out-of-core textures enabled and original albedo/alpha maps.
- **Rename internal switch chain nodes** (`PW Material Core V Min Select N` → `PW Material Arc 1 V Min Select N`, etc.) for visual consistency with the renamed interface sockets. Cosmetic only — purely an artist QoL.
- **Separate warp/weft U correction** if non-square targets or asymmetric thread counts become important. Phase 4i still uses one setup-owned U multiplier, applied per material.
- **Frontend live-render toggle** — a dev-only checkbox in Step 3 that flips `BLENDER_LIVE_RENDER=1` for the current backend session. Useful if multiple devs share the backend.

---

## Template for new phases

```
## Phase N — <one-line title>

**Date**: YYYY-MM-DD

### Motivation
Why we're touching the .blend or the backend's Blender driver.

### Symptom
What looked wrong in the viewport / panel / render output.

### Diagnosis
Specific findings — node names, socket identifiers, link sources, actual numeric values.

### Fix
What we changed. Every node-group operation listed; every backend file path mentioned.
Snapshot the .blend BEFORE destructive ops.

### Verification
Read-back assertions. Push test bandMeta. Compare against expected values.

### What was NOT done
Honest list of follow-ups.

### Lesson
What rule this earned. Cross-link to lessons.md if promoted.
```
