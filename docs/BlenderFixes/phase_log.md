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

## Phase 5 — Per-strand U stride + uniform-aspect U scale + curve-normal symmetry

**Date**: 2026-05-16

### Motivation

User observation: rendered yarns looked persistently squished along U even after Phase 4i/4j calibration tuning. Each strand was showing ~3.4 full repeats of the 45 m yarn scan (the natural world-width sample rate), which compressed every along-strand feature (slubs, twist, colour drift) into the 2.4 BU strand length. Bumping U manually helped briefly but felt arbitrary.

The deeper problem: V is implicitly stretched ~18× when the texture's 0.033-wide core band (`core_v_max − core_v_min`) is mapped to Arc 1's `0.6` slice of `v_around`. U was being sampled at natural world width (1×), so the two axes had a built-in 18× aspect mismatch — the squish was the geometric consequence, not a calibration error.

Separately, the user noticed that `Arc 1 V Padding` only visibly expanded the halo on weft strands (top-ortho view); warp strands showed no equivalent expansion at the same setting. This was masked by the squished U because per-strand variation averaged out visually; once U stopped repeating identically per strand, the underlying asymmetry surfaced.

### Symptom

- Per-strand U showing ~3.4 repeats of the scan; texture features (twist, slub) visibly compressed along strand length.
- `Arc 1 V Padding ≥ 0.05` produced a visible darker halo only around weft strands; warp strands looked uniformly textured with no halo expansion.

### Diagnosis

**U squish.** Math chain reconstructed by reading the graph:

```
uv_scaled.x = u_along × (PW U Scale U Auto × Material N Texture Scale U) + uv_offset_u
PW U Scale U Auto = (Warp Threads × Spacing) / (Material N Image Width Px / Scanner Pixels Per BU)
                  = source_strand_length_BU / texture_world_width_BU
                  ≈ 3.355 for thread001 at 80×0.03 spacing
```

With `Material N Texture Scale U = 1.0` (the Phase 4i "neutral" default), each strand consumed 3.355 full texture spans. For uniform aspect (each texture pixel covering the same physical extent on geometry in both directions), the per-material scale must equal `1 / V_stretch_factor = (core_v_max − core_v_min) / 0.6` ≈ `0.0549` for this yarn. That gives `0.184` repeats per strand — small enough that "what comes after this strand" matters visually.

**Padding asymmetry.** Searched the graph for warp/weft splits in the V-band chain. `PW Band - Band V`, `PW Band - Arc1 Map`, the four `Arc1 V Padded` math nodes, and the entire V-side chain are shared between warp and weft. No per-axis logic. Then inspected curve construction: warp curves run along Y, weft along X, with no `Set Curve Normal` node anywhere in the graph. Blender's default minimum-twist normal calculation produces different cross-section orientations per axis — the profile arc's `v_around=0..1` ended up pointing to different absolute Z positions on warp vs weft strands, so the padded halo region landed on the camera-visible side for weft and on the hidden side for warp.

Verified by reading evaluated mesh attributes:
- Before fix: warp top-of-strand vertices had `v_around` mean ≠ weft top-of-strand mean — different cross-section orientation.
- After fix: both axes have top-of-strand `v_around` mean ≈ 0.5, range `[0.333, 0.667]` — the central third of the arc on both.

### Fix

**Snapshot the .blend twice (two destructive ops):**

```text
Codex_ParametricWeave.pre-u-stride-20260516_203924.blend
Codex_ParametricWeave.pre-curve-normal-20260516_*.blend
```

**Node-group additions (`Parametric Weave knotty`):**

- Added two interface sockets in the `Imperfections` panel:
  - `U Stride Per Warp End` (NodeSocketFloat, default `0.0`) — Socket_245
  - `U Stride Per Weft Pick` (NodeSocketFloat, default `0.0`) — Socket_246
- Inserted four new math nodes between `PW Warp/Weft Variation.UV Offset U` and the `Store Named Attribute` that writes `uv_offset_u`:
  - `PW Warp U Stride x Index` (MULTIPLY): `U Stride Per Warp End × Curve of Point.Curve Index`
  - `PW Warp UV Offset U Sum` (ADD): `PW Warp Variation.UV Offset U + PW Warp U Stride x Index.Value` → `PW Warp UV Offset U.Value`
  - `PW Weft U Stride x Index` (MULTIPLY): `U Stride Per Weft Pick × Curve of Point.001.Curve Index`
  - `PW Weft UV Offset U Sum` (ADD): `PW Weft Variation.UV Offset U + PW Weft U Stride x Index.Value` → `PW Weft UV Offset U.Value`
- Inserted `Set Curve Normal` nodes on both axis branches with `Mode = 'Z Up'`:
  - `PW Warp Set Curve Normal` between `Resample Curve` and `Store Warp U`
  - `PW Weft Set Curve Normal` between `Resample Curve.001` and `Store Weft U`
  - In Blender 4.6+ the mode lives on a `NodeSocketMenu` input — set via `node.inputs['Mode'].default_value = 'Z Up'`, not as a node property.

**Backend changes (`[blender_live.py](../../backend/app/blender_live.py)`):**

- Added `ARC1_V_AROUND_SPAN = 0.6` constant near `MAX_MATERIAL_SLOTS`. Mirrors the Phase 3q geometry-owned split (`arc1_radius / arc2_radius = 0.015 / 0.025 → 0.6`).
- `build_material_asset_entry` now auto-computes `texture_scale_u = core_v_span / ARC1_V_AROUND_SPAN` per yarn unless the producer ships an explicit non-`1.0` override. Per-yarn because `core_v_span` varies by scan.
- `_pw_apply_modifier_material_metadata` reads `Warp Threads`, `Weft Threads`, `Spacing` off the modifier together with the first material's `image_width_px / scanner_pixels_per_bu` and the same material's computed `texture_scale_u`, then pushes:
  ```python
  u_stride_warp = (weft_threads × spacing) / texture_world_width_bu × material_scale_u
  u_stride_weft = (warp_threads × spacing) / texture_world_width_bu × material_scale_u
  ```
  This is exactly the per-strand repeat count, so strand `N+1` picks up where strand `N` ended — one continuous yarn spooled across the swatch.

**Backend changes (`[blender_sync.py](../../backend/app/blender_sync.py)`):**

- Dropped the Phase 4i fit math entirely in the `Parametric Weave knotty` branch — `material_texture_scale_u = 1.0` always (the real per-yarn scale now comes from `build_material_asset_entry` and gets pushed via the per-material socket map).
- `UV Random U` default flipped from `1.0` → `0.0`. The per-strand stride provides natural variation through real spool progression; random scatter was a hack to break visible repetition and is no longer needed. Kept as escape-hatch override.

**Test update:**

- [backend/tests/test_blender_sync.py](../../backend/tests/test_blender_sync.py)
  - replaced `test_parametric_knotty_uses_fit_calibration_on_material_texture_scale_u` with `test_parametric_knotty_keeps_isotropic_texture_scale_u`. New assertions: no `target_length / source_strand_length` divide, no `float(texture_u_calibration)` multiply, `UV Random U` default is `0.0`.

### Verification

- All 32 backend tests pass.
- Live-session readback of evaluated mesh attributes (614 400 vertices):
  - `uv_offset_u` range `[0.0, 14.54]`, mean `7.27` — stride math is running and accumulates linearly across 80 strands × `0.184` = `14.72`.
  - `v_around` distributions on warp vs weft top-of-strand surfaces are now identical (mean `0.5`, range `[0.333, 0.667]`).
- Top-ortho viewport screenshot at `Arc 1 V Padding = 0.15` shows symmetric halo expansion on both warp and weft cells (previously only weft).

### What was NOT done

- Did not add a frontend control for `ARC1_V_AROUND_SPAN`. It's a constant derived from Arc 1/Arc 2 profile radii (Phase 3q geometry-owned split). If those profile radii change in the .blend, the constant in [blender_live.py](../../backend/app/blender_live.py) must move with them.
- Did not introduce per-axis V padding controls. Symmetry now comes from curve normals, not from separate padding sockets.
- Did not rename the inner `PW Warp/Weft Variation` group's `UV Random U` input — kept the existing wire path. The new stride math sits *outside* the variation group, leaving its semantics untouched.
- Did not retire `UV Random U` from the modifier interface. Still exposed as `0.0` default in case an artist wants both stride spooling AND random scatter for a specific look.

### Lesson

Promoted to [lessons.md](lessons.md) as **Rule 17 (curve normals)** and **Rule 18 (uniform-aspect U)**.

---

## Phase 6 — Texture interpolation inspection override

**Date**: 2026-05-16

### Motivation

The active material was confirmed to use full-height UDIM tiles, but the viewport still looked softer than the source strip. The remaining suspect was sampling/filtering rather than a hidden file downscale.

### Diagnosis

Live Blender readback for `FabricStudioMaterial_01_3879e44f7d1f` showed:

```text
source = TILED
tiles = [1001, 1002, 1003]
tile size = 15019 x 395
interpolation = Linear
```

So the active material was not sampling `cycles_safe/albedo_max16384.png`; it was using the full-resolution UDIM path. `Linear` still blends adjacent texels, which can read as blur during close inspection.

### Fix

- [backend/app/render_jobs.py](../../backend/app/render_jobs.py)
  - added `WEAVE_TEXTURE_INTERPOLATION`;
  - accepts `Linear`, `Closest`, `Cubic`, or `Smart`;
  - keeps `Linear` as the default normal preview mode;
  - embeds `_PW_TEXTURE_INTERPOLATION` in generated render/setup scripts and applies it to generated yarn texture nodes.
- [backend/tests/test_render_jobs.py](../../backend/tests/test_render_jobs.py)
  - verifies the default interpolation variable is emitted;
  - verifies `WEAVE_TEXTURE_INTERPOLATION=Closest` reaches the generated Blender script.
- Live diagnostic only: switched the active material's diffuse/alpha texture nodes to `Closest` so the viewport can immediately reveal whether the softness is filtering.

### Verification

```text
BLENDER_PORT=9876 readback:
active material: FabricStudioMaterial_01_3879e44f7d1f
diffuse/alpha source: TILED
diffuse/alpha filepath: runtime/yarn_assets/3879e44f7d1f/cycles_tiled/*_<UDIM>.png
diffuse/alpha interpolation after probe: Closest
```

### What was NOT done

- Did not change the normal default away from `Linear`; `Closest` is sharper but can look blocky.
- Did not remove the `cycles_safe` fallback; it is still needed for atlas/fallback paths and non-tiled assets.

---

## Phase 7 — Flip Arc 2 V Map Range direction for visual review

**Date**: 2026-05-16

### Motivation

User asked to flip the Arc 2 V mapping direction while inspecting the live viewport.

### Diagnosis

Before the flip, readback showed the Phase 3k direction:

```text
PW Band - Arc2 Top:  Fiber Top -> Arc 1 V Max
PW Band - Arc2 Core: Arc 1 V Max -> Arc 1 V Min
PW Band - Arc2 Bot:  Arc 1 V Min -> Fiber Bot
```

This is continuous, but samples the halo from outer edge toward core on the top side and core toward outer edge on the bottom side.

A plain `To Min` / `To Max` swap on all three Map Range nodes is not a valid full flip: it reverses each section locally but breaks the joins between Top/Core and Core/Bot. The correct edit has to reverse the whole stitched path:

```text
Original:  Arc 2 V Max -> Arc 1 V Max -> Arc 1 V Min -> Arc 2 V Min
Flipped:   Arc 2 V Min -> Arc 1 V Min -> Arc 1 V Max -> Arc 2 V Max
```

### Fix

Snapshots:

```text
Codex_ParametricWeave.pre-arc2-v-flip-20260516_232528.blend
Codex_ParametricWeave.pre-arc2-v-corrective-20260516_233011.blend
```

Inside `Parametric Weave knotty`, rewired the three Arc 2 destination ranges to reverse the full path while preserving split-boundary continuity:

- `PW Band - Arc2 Top`: `Arc 2 V Min -> Arc 1 V Min`
- `PW Band - Arc2 Core`: `Arc 1 V Min -> Arc 1 V Max`
- `PW Band - Arc2 Bot`: `Arc 1 V Max -> Arc 2 V Max`

Saved the live file back to [Codex_ParametricWeave.blend](../../Codex_ParametricWeave.blend).

### Verification

Live MCP readback after save:

```text
PW Band - Arc2 Top.To Min  = PW Material Fiber Bot V Max Select 16.Output
PW Band - Arc2 Top.To Max  = PW Band - Arc1 V Min Padded.Value
PW Band - Arc2 Core.To Min = PW Band - Arc1 V Min Padded.Value
PW Band - Arc2 Core.To Max = PW Band - Arc1 V Max Padded.Value
PW Band - Arc2 Bot.To Min  = PW Band - Arc1 V Max Padded.Value
PW Band - Arc2 Bot.To Max  = PW Material Fiber Top V Min Select 16.Output
```

Current Arc 2 direction is therefore:

```text
Arc2 Top:  outer bottom -> core bottom
Arc2 Core: core bottom -> core top
Arc2 Bot:  core top -> outer top
```

Numeric readback for the active yarn confirmed continuity:

```text
0.369620 -> 0.471544 -> 0.528456 -> 0.637975
```

### What was NOT done

- Did not change producer metadata or backend socket mappings.
- Did not alter Arc 1 mapping.
- Did not make this a UI toggle; it is a direct `.blend` graph edit for review.

---

## Phase 8 — Smooth live texture preview sampling

**Date**: 2026-05-16

### Motivation

User compared `rgba.png` against Blender's `Diffuse_UDIM` image editor preview and saw a chunky/pixelated look in Blender.

### Diagnosis

- The active UDIM tiles are not downscaled: `15019 + 15020 + 15019 = 45058`, matching the source width, with height `395`.
- Pixel comparison showed `albedo.png` stitched from the three UDIM tiles has max RGB diff `0`; `rgba.png` split into `albedo.png` + `alpha.png` also has max channel diff `0`.
- The open Blender material still had the temporary diagnostic sampler set to `Closest` on `FabricStudioDiffuseNode` and `FabricStudioAlphaNode`.
- `Diffuse_UDIM` is raw RGB only. It will show gray/black foreground-solve pixels that `rgba.png` hides through alpha compositing.
- The generated per-yarn material used `HASHED` / `DITHERED` alpha, which can look grainy in the viewport for soft hair alpha.

### Fix

- Reset live FabricStudio image texture nodes to `Linear` interpolation and saved [Codex_ParametricWeave.blend](../../Codex_ParametricWeave.blend).
- Switched live FabricStudio materials to `BLEND` / `BLENDED` alpha and saved the `.blend`.
- Updated [render_jobs.py](../../backend/app/render_jobs.py) so future generated per-yarn materials default to `Linear` texture interpolation plus blended alpha.
- Added env escape hatches: `WEAVE_TEXTURE_INTERPOLATION`, `WEAVE_CUTOUT_BLEND_METHOD`, and `WEAVE_SURFACE_RENDER_METHOD`.

### Verification

Live readback:

```text
FabricStudioDiffuseNode interpolation Linear
FabricStudioAlphaNode   interpolation Linear
blend_method BLEND
surface_render_method BLENDED
```

Backend tests: `python -m unittest tests.test_render_jobs`.

### What was NOT done

- Did not yet switch Blender to RGBA UDIM sampling in this phase; Phase 9 does that.

---

## Phase 9 — Prefer source RGBA UDIM tiles for Blender materials

**Date**: 2026-05-17

### Motivation

User confirmed the right target: build the tiled image from the original imported `rgba.png`, so Blender uses the same source image the Web/Preview inspection uses and does not lose detail through the separate raw-albedo inspection path.

### Diagnosis

The existing `cycles_tiled/albedo_<UDIM>.png` files were full-resolution crops, not `cycles_safe` downscales, but they were RGB-only. Opening raw albedo in Blender hides the alpha/compositing context and makes the texture look harsher/different from `rgba.png`.

### Fix

- Added RGBA UDIM tile generation in [yarn_assets.py](../../backend/app/yarn_assets.py): `ensure_cycles_tiled_rgba_texture_set`.
- Added `renderRgbaTilePattern` / `renderRgbaTileFilenames` / `renderRgbaTileUrls` fields to [models.py](../../backend/app/models.py).
- Updated [render_jobs.py](../../backend/app/render_jobs.py) so material payloads prefer `udim_rgba_tiled` when RGBA tiles exist, and the Blender material links:

```text
RGBA UDIM Color -> Principled Base Color
RGBA UDIM Alpha -> Principled Alpha
```

- Kept separate albedo/alpha UDIMs as fallback for older/manual assets.
- Generated `runtime/yarn_assets/3879e44f7d1f/cycles_tiled/rgba_1001.png` through `rgba_1003.png`, updated that asset's `asset.json`, and pointed the live Blender material at the RGBA UDIM image.

### Verification

```text
rgba_1001 + rgba_1002 + rgba_1003 width = 45058
source rgba.png width = 45058
stitched RGBA tile max channel diff = 0
```

Live Blender readback:

```text
FabricStudioDiffuseNode image ..._RGBA_UDIM
FabricStudioAlphaNode   image ..._RGBA_UDIM
Principled Alpha link   FabricStudioAlphaNode.Alpha
```

Backend tests: `python -m unittest discover -s tests` -> 37 tests OK.

---

## Phase 10 — Per-section U scale (uniform texel aspect across Arc 1 and Arc 2)

**Date**: 2026-05-17

### Motivation

User reported that Arc 2's top and bottom halo regions still look hazy / stretched / "not to scale" along the strand, and that Arc 1's edges look sloppy in the same direction. They identified per-section U scale as the right fix and explicitly rejected leaning on `Arc 1 V Padding` (which is for post-processing visual tuning, not for fixing the underlying mapping).

The geometric root cause is that the Phase 3q split partitions Arc 2's `v_around` at fixed proportions (`0.2 / 0.6 / 0.2` from `arc1_radius / arc2_radius = 0.6`), but the texture-V proportions are scan-driven and very different. For `black_white`: padded core span `0.063`, top halo span `0.099`, bot halo span `0.107`. The V slope (texture-V per `v_around`) per section:

| section | v_around width | tex-V span | V slope |
|---|---|---|---|
| Arc 2 Top  | 0.2 | 0.099 | 0.494 |
| Arc 2 Core | 0.6 | 0.063 | 0.105 |
| Arc 2 Bot  | 0.2 | 0.107 | 0.533 |
| Arc 1 main strand | 1.0 | 0.063 | 0.063 |

The U scale was calibrated for Arc 2 Core (Phase 5: `core_v_span / 0.6`), so Top/Bot halos and Arc 1 main strand all read the texture at the wrong U:V aspect — features in the halo end up stretched ~5× along strand length, and Arc 1 ends up sampled at ~1.65× more U per visible texel than core.

### Symptom

- Halo bands at the top/bottom outer rings of the sub-strand silhouette read as hazy/stretched smears; reducing root `Texture Scale U` masks the haze because U slows enough that the core fills the view.
- Arc 1 main-strand edges (where its 1.0-wide `v_around` maps to a much narrower V band than the Arc 2 Core ring does) look sloppy in the same way.

### Diagnosis

Live MCP readback of the U chain in `Parametric Weave knotty`:

```
PW U - Strand Length         = Warp Threads × Spacing
PW U - Image World Width     = Material N Image Width Px / Scanner Pixels Per BU
PW U - Scale U Auto          = Strand Length / Image World Width
PW Material Texture Scale U Final = root Texture Scale U × Material N Texture Scale U
PW U - Scale U Final         = Scale U Auto × Texture Scale U Final
Math.013                     = u_along × PW U - Scale U Final
PW UV U Add                  = Math.013 + uv_offset_u attribute
Combine XYZ.006.X            = PW UV U Add.Value
Store Named Attribute.002    = writes uv_scaled FLOAT2
```

This U chain is shared by both Arc 1 (main strand, `is_sub_strand=0`) and Arc 2 (sub-strand, `is_sub_strand=1`) faces. There is no section-aware logic — every face gets the same `Scale U Final`.

Section detection on the V side already exists:

```
v_around          → Named Attribute.001
Split Minus/Plus  → PW Band - Split Minus / Split Plus  (0.2 / 0.8 from geometry-owned ratio)
IsTop             = v_around < Split Minus
IsBot             = v_around > Split Plus
IsCore            = 1 - IsTop - IsBot
is_sub_strand     → Named Attribute.002
```

So everything needed to compute the per-section V slope and gate by main-strand-vs-sub-strand was already wired.

### Fix

Snapshot: `Codex_ParametricWeave.pre-per-section-u-scale-20260517_151547.blend`.

Added 22 nodes inside `Parametric Weave knotty` (`PW U - Sec *` prefix) and one rewire on `Combine XYZ.006.X`:

```text
Per-section V spans
  PW U - Sec Core Span       = Arc 1 V Max Padded - Arc 1 V Min Padded
  PW U - Sec Top Span        = Arc 1 V Min Padded - Arc 2 V Min
  PW U - Sec Bot Span        = Arc 2 V Max - Arc 1 V Max Padded

Per-section v_around widths
  PW U - Sec Core Width      = Split Plus - Split Minus
  PW U - Sec Bot Width       = 1 - Split Plus
  (Top width is Split Minus itself)

Safe denominators (MAXIMUM with 1e-6)
  PW U - Sec Core Width Safe, Top Width Safe, Bot Width Safe
  PW U - Sec Core Slope Safe

Per-section V slope = span / width
  PW U - Sec Core Slope, Top Slope, Bot Slope
  PW U - Sec Arc1 Slope     = Core Span × 1.0       (Arc 1 uses full v_around)

Sub-strand section selection
  PW U - Top/Core/Bot Weighted Slope = IsTop/IsCore/IsBot × respective slope
  PW U - Sub Slope Sum 1            = Top + Core
  PW U - Sub Slope Sum              = Sum 1 + Bot

Gate by is_sub_strand
  PW U - Sub Minus Arc1 Slope       = Sub Slope Sum - Arc1 Slope
  PW U - Section Slope              = MULTIPLY_ADD(is_sub_strand, Sub Minus Arc1 Slope, Arc1 Slope)

Ratio against the Arc 2 Core slope the existing U calibration targets
  PW U - Section Ratio              = Section Slope / Sec Core Slope Safe

Apply once, after the existing U + offset add
  PW U - Per Section Multiplier     = PW UV U Add.Value × PW U - Section Ratio
  Combine XYZ.006.X                 ← PW U - Per Section Multiplier (rewired)
```

Multiplying the *post-add* value scales both the `u_along × Scale_U_Final` contribution AND the `uv_offset_u` per-curve stride. This is deliberate: Phase 5's strand-to-strand spool (`U Stride × curve_index`) is calibrated against the Arc 2 Core sampling rate, so on halo sections the stride also needs to scale by the section ratio for the spool to remain continuous within each ring.

Two debug Store Named Attribute nodes (`pw_section_ratio`, `pw_section_slope`) were spliced into the geometry stream before the `uv_scaled` write so the result is verifiable from Python via the evaluated mesh.

### Verification

Live MCP readback of evaluated mesh attributes (2,560,000 points after eval) with `Sub Strand Enable = True` and the `black_white` yarn live-pushed:

```
pw_section_ratio: min=0.6000 max=5.0795 mean=1.5797
pw_section_slope: min=0.0629 max=0.5326 mean=0.1656

is_sub_strand distribution: 1,280,000 main / 1,280,000 sub
  main strand (ratio ≈ 0.6):   1,280,000 points (50.0%)
  Arc 2 Core (ratio ≈ 1.0):      768,000 points (30.0% = 50% sub × 60% core slice)
  Arc 2 Halo (ratio 4–6):        512,000 points (20.0% = 50% sub × 40% halo slices)
```

The 50/30/20 distribution matches the geometry partition (sub vs main, then core vs halo). The numeric ratios match hand calculation for the active yarn:

- Arc 2 Core slope = 0.063 / 0.6 = 0.105 → ratio = 1.000 ✓
- Arc 2 Top slope  = 0.099 / 0.2 = 0.494 → ratio = 4.70 ✓
- Arc 2 Bot slope  = 0.107 / 0.2 = 0.533 → ratio = 5.08 ✓
- Arc 1 main slope = 0.063 / 1.0 = 0.063 → ratio = 0.600 ✓

`uv_scaled.x` range expanded from a narrow band (one calibration everywhere) to `[-1.41, 78.72]`, reflecting the ~5× faster U sampling rate on halo regions where each texel covers less along-strand distance and the spool accumulates farther.

Saved live file back to [Codex_ParametricWeave.blend](../../Codex_ParametricWeave.blend); file size 27,559,392 bytes.

### What was NOT done

- Did not change `Arc 1 V Padding` — user explicitly wanted padding kept as a post-process visual control.
- Did not change `Material N Texture Scale U` calibration. The Phase 5 per-yarn `core_v_span / 0.6` math is the baseline the per-section ratio normalizes against. Artists can still tune absolute aspect via root `Texture Scale U` or the per-material socket.
- Did not introduce a frontend toggle. The fix is structural (the only "right" behavior); there is no per-render setting to expose.
- Did not retire the `PW Band - Geo Split Minus / Plus` chain. Section split still comes from geometry (Phase 3q), as intended — the per-section U scale fixes the consequence of fixed geometric splits without changing the splits themselves.
- Did not migrate `ARC1_V_AROUND_SPAN = 0.6` out of `blender_live.py`. It still represents the same Arc 2 Core fraction the per-section ratio measures live; if Arc 1/Arc 2 profile radii ever change in the .blend, both the constant in the backend and the geometric split in the graph need to move together (already noted in Phase 5).
- Did not add a `Per Section Scale Enable` toggle. If we ever want to bypass the new path for A/B comparison, reroute `Combine XYZ.006.X` back to `PW UV U Add.Value` — the old chain is still present, just unlinked from the X input.

### Side effects to be aware of

- **U Stride strand-to-strand spool is now per-section continuous**, not globally continuous. Within the Arc 2 Core ring the spool is unchanged. Within the halo rings the per-strand stride is effectively `Phase 5 stride × ratio` (~5×), so adjacent strands' halos line up cleanly. Across the **core ↔ halo seam at `v_around = Split Minus / Split Plus`**, U values are not continuous (the section ratio changes discontinuously). This is acceptable because the texture content on each side of that seam is different (core texture vs halo texture) and the discontinuity is in a region whose alpha is already low (lessons.md Rule 23).
- **`UV Random U`** variation is now multiplied by the section ratio too. In halo rings, random scatter is ~5× larger in U than in core. This is *proportional* to the section's texture-feature size, so the visual scatter density relative to texture features stays uniform across sections. If artists want axis-uniform scatter they should set `UV Random U = 0` (already the Phase 5 default).

### Lesson

Promoted to [lessons.md](lessons.md) as **Rule 27 (per-section U scale)** — when one map-range produces piecewise-different slopes, the orthogonal axis needs a piecewise scale to keep texel aspect uniform; one global scale cannot satisfy every section.

---

## Phase 10a — Fix Arc 1 baseline (Phase 10 follow-up)

**Date**: 2026-05-17

### Motivation

User reported that after Phase 10, Arc 2's Scale U "seems incorrect" while Arc 1 looks correctly loaded. The visible mismatch was between the Arc 1 main-strand cylinder (rendered at `K_u × 0.6`) and the Arc 2 Core ring (rendered at `K_u × 1.0`) — same texture content, two different K_u values.

### Symptom

- Arc 1 (smaller inner cylinder, the main-strand body) and Arc 2 Core (the central ring of the larger outer cylinder, when `Sub Strand Enable = True`) showed the same scanned core texture at different along-strand zoom levels.
- Live readback after Phase 10 confirmed `Arc 1 ratio = 0.6` against `Arc 2 Core ratio = 1.0`.

### Diagnosis

Phase 3q's geometric split is `arc1_radius / arc2_radius = 0.015 / 0.025 = 0.6`. That value was chosen precisely so that **Arc 1's full v_around span and Arc 2's central 60% v_around slice cover the same physical around-strand width**:

```text
Arc 1 around-strand width = 2π × 0.015 × 1.0 = 0.0942 BU
Arc 2 Core around-strand width = 2π × 0.025 × 0.6 = 0.0942 BU
```

Because both surfaces map the same padded-core texture-V span to that same physical width, they have **identical tex_v-per-BU-around rate** by construction. So they should share K_u — Arc 1's per-section ratio should be **1.0**, not 0.6.

Phase 10's `PW U - Sec Arc1 Slope` node computed `Sec Core Span × 1.0` (V slope per *parametric* v_around, treating Arc 1's full circumference as `v_around = 1.0`). It then divided by `Sec Core Span / 0.6` (Arc 2 Core's parametric V slope) and produced `1.0 / (1/0.6) = 0.6`. The error was treating parametric v_around as the unit of comparison; the right unit is physical around-strand BU, which already accounts for the radius difference via Phase 3q's split.

### Fix

Snapshot: `Codex_ParametricWeave.pre-arc1-ratio-fix-20260517_163716.blend`.

Two-link rewire inside `Parametric Weave knotty` — no new nodes:

```text
PW U - Section Slope.in[2] (fallback when is_sub_strand=0)
  was: PW U - Sec Arc1 Slope.Value   (= core_span × 1.0)
  now: PW U - Sec Core Slope.Value   (= core_span / 0.6 = Arc 2 Core slope)

PW U - Sub Minus Arc1 Slope.in[1] (subtractor in the gating math)
  was: PW U - Sec Arc1 Slope.Value
  now: PW U - Sec Core Slope.Value
```

`PW U - Sec Arc1 Slope` is left in place but unlinked, so a revert is a single re-link.

### Verification

Live MCP readback after temporarily enabling `Sub Strand Enable = True` for the eval pass (restored to its previous value after):

```
region         n          slope    ratio mean     range
Arc 1 main   280000      0.06308   1.0000         exact
Arc 2 Core   120000      0.06308   1.0000         exact
Arc 2 Top     80000      0.06253   0.9913         exact
Arc 2 Bot     80000      0.06737   1.0680         exact
```

Arc 1 and Arc 2 Core now share ratio `1.0` exactly — confirming the Phase 3q physical-rate equalization carries through to U sampling. The Arc 2 Top/Bot ratios are near 1.0 on this yarn because its current `Material 1 Arc 2 V Min/Max = 0.4681 / 0.5319` defines a very tight halo (top span `0.014`, bot span `0.015`) relative to a `0.038` padded core; on a wispier yarn (e.g. the earlier `black_white` push with halo spans `0.099 / 0.107`) the halo ratios climb back to ~4–5× as designed.

### What was NOT done

- Did not remove `PW U - Sec Arc1 Slope`. Keeping it in place documents the original (wrong) baseline and makes the rewire diff-readable.
- Did not change `ARC1_V_AROUND_SPAN = 0.6` in `blender_live.py`. The constant remains the producer-side mirror of Phase 3q's geometric split; the per-section logic now correctly consumes it via the existing `PW U - Sec Core Slope` denominator.
- Did not toggle `Sub Strand Enable` on persistently. The verification flip was a temporary read; the user's session value (False at the time) was restored after the readback.

### Lesson

Updated [lessons.md](lessons.md) Rule 27 with the unit gotcha: when comparing V slopes across surfaces with different cross-section radii, normalize by physical around-strand BU (not by parametric v_around), or rely on whatever construction equalizes the two — Phase 3q's `0.6` split already does this for Arc 1 vs Arc 2 Core.

---

## Phase 10b — Align Arc 2 profile vertices with section boundaries

**Date**: 2026-05-17

### Motivation

After Phase 10a, user added a UV checker test pattern and reported that on Arc 2 the texture sampling skipped letter rows (e.g. "F, [thick noisy band], H" with G missing; "A, [thick noisy band], C" with B missing). The same texture rendered correctly on Arc 1.

### Symptom

- On Arc 2 (sub-strand), the checker pattern showed letter rows in alphabetical sequence interrupted by **two visible thick blurry bands** — one between the top halo's last visible row and the core's first visible row, another between the core's last visible row and the bottom halo's first visible row.
- The two interruption bands contained a smeared mix of textures (looked like a "noisy image"), not a clean checker cell.
- Arc 1 was unaffected (uses a single Map Range, no section boundaries).

### Diagnosis

Read evaluated `uv_scaled.Y` per section and found the actual sampled tex_v ranges had **gaps** that didn't meet at section boundaries:

```
Arc 2 Top    sampled tex_v [0.4681, 0.4785]    (expected end at 0.4806 = Arc 1 V Min Padded)
Arc 2 Core   sampled tex_v [0.4890, 0.5100]    (expected start at 0.4806, end at 0.5184)
Arc 2 Bot    sampled tex_v [0.5207, 0.5319]    (expected start at 0.5184 = Arc 1 V Max Padded)
```

Two gaps of `~0.010` in tex_v never landed on a vertex.

Walked the cross-section profile and found the root cause: both `Arc` and `Arc.001` (the Curve Arc primitives that build the Arc 1 and Arc 2 profiles) had **`Resolution = 7`**, producing 7 control points at `v_around = 0, 1/6, 2/6, 3/6, 4/6, 5/6, 1` = `0, 0.1667, 0.3333, 0.5, 0.6667, 0.8333, 1.0`.

The Phase 3q geometric split places section boundaries at `v_around = 0.2` and `v_around = 0.8` (= `(1 - 0.6)/2` and `(1 + 0.6)/2`). Neither boundary coincides with a profile vertex. The mesh face spanning `v_around = 0.1667 → 0.3333` therefore had vertex 1 at tex_v `0.4785` (Arc 2 Top mapping) and vertex 2 at tex_v `0.4890` (Arc 2 Core mapping), and the rasterizer linearly interpolated tex_v across that face — meaning the V slope discontinuity that *should* happen exactly at `v_around = 0.2` was smeared across `[0.1667, 0.3333]`, mixing halo content with core content in a single quad.

That smear is the "thick noisy band" the user saw. The "missing G/B" is the same effect viewed letter-wise: any checker cell whose tex_v sits in `[0.4785, 0.4890]` got interpolated across one face instead of having its own clean band.

### Fix

Snapshot: `Codex_ParametricWeave.pre-profile-resolution-fix-20260517_172112.blend`.

Bumped both Curve Arc primitives from Resolution `7` to Resolution `11`. New v_around vertices: `0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0`. Now `0.2` and `0.8` land **exactly** on vertices 2 and 8.

```python
ng.nodes['Arc'].inputs['Resolution'].default_value      = 11   # Arc 1 profile
ng.nodes['Arc.001'].inputs['Resolution'].default_value  = 11   # Arc 2 profile
```

### Verification

Live MCP readback of evaluated mesh after the change:

```
Unique v_around values on sub-strand: 11 distinct
  [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
Boundary check: 0.2 in vertices? True
Boundary check: 0.8 in vertices? True

Post-fix tex_v at each v_around vertex:
  v_around=0.0000  tex_v=0.46809  (Top)
  v_around=0.1000  tex_v=0.47434  (Top)
  v_around=0.2000  tex_v=0.48059  (BOUNDARY top<->core)
  v_around=0.3000  tex_v=0.48690  (Core)
  v_around=0.4000  tex_v=0.49321  (Core)
  v_around=0.5000  tex_v=0.49952  (Core)
  v_around=0.6000  tex_v=0.50582  (Core)
  v_around=0.7000  tex_v=0.51213  (Core)
  v_around=0.8000  tex_v=0.51844  (BOUNDARY core<->bot)
  v_around=0.9000  tex_v=0.52518  (Bot)
  v_around=1.0000  tex_v=0.53191  (Bot)
```

tex_v at `v_around = 0.2` reads back as exactly `Arc 1 V Min Padded = 0.4806`; at `v_around = 0.8` it reads as exactly `Arc 1 V Max Padded = 0.5184`. The boundary values are now vertex values, not interpolated face values. tex_v progresses monotonically across all 11 vertices with no gaps.

Viewport screenshot post-fix confirms every checker letter row is now cleanly readable across the strand cross-section — no thick blurry bands, no smeared content between sections.

Mesh size dropped from 1.6M to 440k points on this readback, but that's because of an unrelated state change in the user's session (likely Sub Strand Width/Height edits) — the resolution change itself goes from `7 × 2` profiles = `14` vertices to `11 × 2` profiles = `22` vertices, a `1.57×` per-cross-section ratio.

### What was NOT done

- Did not change the Phase 3q geometric split itself (`arc1_radius / arc2_radius = 0.6` still produces boundaries at `0.2 / 0.8`). The fix is upstream of the V mapping; the split is unchanged.
- Did not handle arbitrary future radii. If the user changes Arc 1 or Arc 2 profile radius to a ratio whose boundary `(1 ± ratio)/2` doesn't land on a `1/10` step, the boundaries would again miss the resolution-11 vertices. A robust long-term fix would resample the profile to insert vertices *exactly* at `Split Minus` and `Split Plus`. Logged as an open item.
- Did not retire the `pw_section_ratio` / `pw_section_slope` debug attributes. They remain useful for any future per-section debugging.

### Lesson

Promoted as a sub-bullet of [lessons.md](lessons.md) Rule 27: **when a piecewise V mapping has section boundaries inside the v_around range, the profile geometry must have a vertex exactly at every boundary**, otherwise the rasterizer's linear interpolation across the spanning face smears the V discontinuity into a visible blurry band. Bump profile Resolution, or actively resample the profile curve at the boundary fractions.

---

## Phase 10c — Radius-agnostic robust Arc 2 profile (per-vertex piecewise resample)

**Date**: 2026-05-17

### Motivation

Phase 10b's fix (`Resolution = 11` on both Curve Arc primitives) works while `arc1_radius / arc2_radius = 0.6` keeps Split Minus / Plus at `0.2 / 0.8`. The moment a user changes the radii, the new boundaries (e.g. `0.14 / 0.86` for ratio `0.72`, or `0.26 / 0.74` for ratio `0.48`) drift back off the vertex grid and the smeared "thick noisy band" returns. Required a profile geometry that **always** places vertices at the live Split Minus / Plus regardless of radii.

### Symptom (regression risk, not user-visible at the time)

With Resolution = 11 fixed:
- `arc1 = 0.012, arc2 = 0.025 → split 0.26 / 0.74` → not on `1/10` grid; gap returns.
- `arc1 = 0.018, arc2 = 0.025 → split 0.14 / 0.86` → not on `1/10` grid; gap returns.

### Diagnosis

The existing Arc 2 profile was a single `GeometryNodeCurveArc` primitive with a static Resolution. `Store Named Attribute.003` writes `v_around` to that profile by reading `Spline Parameter.002.Factor` (cumulative arc length / total length). For the boundary in v_around space to coincide with a vertex, the vertex must sit at exactly `cumulative_length / total = Split Minus` along the profile arc — which the static-resolution arc cannot guarantee for arbitrary split fractions.

### Fix

Snapshot: `Codex_ParametricWeave.pre-profile-robust-fix-20260517_173118.blend`.

Replaced `Arc.001` as the Arc 2 profile source with a custom 31-point polyline built from a `GeometryNodeMeshLine` whose vertex positions are sampled along `Arc.001` at piecewise-mapped factors. Added 17 nodes prefixed `PW Profile -` and rewired `Store Named Attribute.003.Geometry`.

**Architecture**:

```text
GeometryNodeMeshLine (Count=31, Offset=(1/30, 0, 0))
    │ creates 31 points uniformly spaced along X from (0,0,0) to (1,0,0)
    ▼
Position → Separate XYZ → X  (== natural_factor in [0, 1])
    │
    ├── compute IsTop / IsCore / IsBot vs FIXED anchors 0.2 and 0.8
    │
    ├── three Map Range nodes (CLAMPED) — natural → actual factor:
    │     PW Profile - Top Map:  From [0, 0.2] → To [0, Split Minus]
    │     PW Profile - Core Map: From [0.2, 0.8] → To [Split Minus, Split Plus]
    │     PW Profile - Bot Map:  From [0.8, 1.0] → To [Split Plus, 1.0]
    │
    ├── IsTop·Top Mapped + IsCore·Core Mapped + IsBot·Bot Mapped = actual_factor
    │
    ▼
GeometryNodeSampleCurve (Mode = FACTOR) on Arc.001 → Position output
    │
    ▼
GeometryNodeSetPosition (geom = Mesh Line, position = sampled)
    │
    ▼
GeometryNodeMeshToCurve → polyline Curve
    │
    ▼
Store Named Attribute.003.Geometry  (rewired here)
```

**Why this works for any radii**:

The piecewise mapping is built around two FIXED natural anchors (`0.2` and `0.8`) that land exactly on Mesh Line vertices 6 and 24. Wherever the live `Split Minus / Plus` values sit, vertex 6 is sampled at actual factor `Split Minus` along Arc.001 and vertex 24 at `Split Plus`. Within each section the 6/18/6 vertex split linearly maps to its actual-factor range, so all segments within a section have equal length on the source arc.

The downstream chain is unchanged — `Spline Parameter.002.Factor` evaluates on the new polyline as `cumulative_length / total_length`. Because each section's segments have equal length, and the Top section's segments together have arc-length proportional to `Split Minus`, vertex 6 ends up at `Spline Parameter.Factor = Split Minus` automatically. Same for vertex 24 = `Split Plus`. So `v_around` at every vertex matches the V Map Range domain, and the boundaries land exactly on vertices for any radius ratio.

### Verification

Live MCP readback after the rewire:

```
Sub-strand unique v_around values: 31 distinct
  [0.0, 0.033, 0.067, 0.1, 0.133, 0.167, 0.2, 0.233, 0.267, 0.3, 0.333,
   0.367, 0.4, 0.433, 0.467, 0.5, 0.533, 0.567, 0.6, 0.633, 0.667, 0.7,
   0.733, 0.767, 0.8, 0.833, 0.867, 0.9, 0.933, 0.967, 1.0]

Live arc1 = 0.015, arc2 = 0.025, core_frac = 0.60:
  Split Minus 0.20000 in vertex set? True
  Split Plus  0.80000 in vertex set? True

Stress test — change arc1_radius, re-eval, re-check:
  arc1 = 0.012 (core_frac 0.48): Split 0.26 / 0.74 → both in vertex set ✓
  arc1 = 0.018 (core_frac 0.72): Split 0.14 / 0.86 → both in vertex set ✓
  arc1 = 0.013 (core_frac 0.52): Split 0.24 / 0.76 → both in vertex set ✓
```

Viewport screenshot confirms every checker letter row now reads cleanly across the strand: the previously-missing G appears between F and H, the previously-missing B appears between A and C, and there are no thick interpolation bands at the boundaries.

### What was NOT done

- Did not delete `Arc.001`. It's still in the graph as the *source curve* that the polyline samples positions from (via `Sample Curve`). Removing it would break the new chain.
- Did not change `Resolution = 11` on `Arc.001` either. With the polyline interposed, the master arc's resolution becomes a smoothness budget (Sample Curve evaluates positions along the arc, smoother source → smoother sampled positions). 11 is plenty; could even go lower. Did not bump.
- Did not apply the same treatment to `Arc` (the Arc 1 profile). Arc 1 uses a single Map Range with no section boundaries inside `v_around`, so the smear failure mode doesn't apply.
- Did not expose a Mesh Line `Count` socket on the modifier panel. `31` is hard-coded because the natural anchors `0.2 / 0.8` only land on vertices when `Count - 1` is a multiple of 5. Could parameterize via `Resolution × 5 + 1` if we want a single user-facing knob.
- Did not retire `pw_section_ratio` / `pw_section_slope` debug attributes.

### Lesson

Extended [lessons.md](lessons.md) Rule 27: a profile constructed by Mesh Line + Sample Curve at piecewise-mapped factors lets you place vertices at *any* dynamic-fraction boundary, even when the fraction comes from runtime sockets. The mapping anchors stay on a fixed parametric grid; the polyline's arc-length-derived `v_around` ends up at the dynamic boundary automatically — no per-yarn re-tuning, no resolution constraints on the source arc.

---

## Phase 10d — Arc 2 boundary inset (hide section-discontinuity behind Arc 1)

**Date**: 2026-05-17

### Motivation

Even with the Phase 10c robust profile (vertices on exact split fractions for any radii), the section-boundary V slope discontinuity still produces a *visible* texture transition right on the strand silhouette. User asked for a way to **tuck the boundary region radially inward** so the discontinuity sits inside Arc 1's silhouette and is occluded by Arc 1's main-strand surface.

### Symptom

Boundary regions on Arc 2 — where the texture content switches from halo (Top section) to padded core (Core section) — show a visible kink in the rendered checker pattern. Even when sharp, the texture transition reads as an obvious seam.

### Fix

Snapshot: `Codex_ParametricWeave.pre-boundary-inset-20260517_173931.blend`.

Two changes inside `Parametric Weave knotty`:

**A. New interface socket `Arc 2 Boundary Inset`** (Socket_247, NodeSocketFloat, default `0.0`, range `[0.0, 0.025]`), placed inside the `Surface` panel. Default `0.0` keeps Phase 10c behavior unchanged.

**B. Tent-weighted radial inset chain** on the Mesh Line profile, applied *after* the Sample Curve position. Per-vertex math:

```
nat = vertex.x   (natural factor in [0, 1])

dist_to_boundary = min(|nat − 0.2|, |nat − 0.8|)
inset_range      = 0.2                                   (hard-coded; full halo span)
weight           = max(0, 1 − dist_to_boundary / inset_range)
                   # 1 at boundary, linear taper to 0 at the halo outer edges (nat=0,1)
                   # and into the core at nat=0.4 / 0.6

inset_BU         = Arc 2 Boundary Inset (socket) × weight
scale_factor     = 1 − inset_BU / arc2_radius
final_position   = sampled_position × scale_factor       (uniform scale toward origin)
```

At inset = `0.010 BU` (= `arc2_radius − arc1_radius`), the boundary vertex (weight `1`) lands exactly on Arc 1's silhouette; the section-boundary face folds inside Arc 1 and is hidden. Smaller values give partial tuck — at `0.005` the kink is muted but the halo content remains visible.

**C. Bake natural factor as a custom attribute** before `Set Position`. Without this, the inset shifts segment lengths along the polyline, which shifts `Spline Parameter Factor` — so the `v_around` boundary value (`0.2` / `0.8`) ends up *between* vertices again, undoing Phase 10c's alignment.

Implementation:
- Inserted `PW Profile - Store Natural Factor` (`Store Named Attribute`, name=`pw_profile_natural`, FLOAT/POINT) between `Mesh Line` and `Set Position`. Records `Position.X` per vertex.
- `Store Named Attribute.003.Value` (the canonical `v_around` writer) is now driven by a new `GeometryNodeInputNamedAttribute` reading `pw_profile_natural`, replacing the previous `Math.019 ← Spline Parameter.002` chain.

Net effect: `v_around` is anchored to vertex *index*, not to vertex *arc length*. Inset can move vertices anywhere radially without disturbing the V mapping.

### Verification

Live MCP readback with `Arc 2 Boundary Inset = 0.010`:

```
v_around unique values: 31 distinct
  [0.0, 0.033, 0.067, 0.1, 0.133, 0.167, 0.200, 0.233, ..., 0.767, 0.800, 0.833, ..., 1.0]
0.2 in vertex set? True
0.8 in vertex set? True
```

`v_around` stays at clean `1/30` increments regardless of the socket value. Visual: at `0.010` the boundary regions are fully occluded by Arc 1 (only the outer halo edges and the Arc 1 core/halo surface are visible); at `0.005` G/B rows are squashed but still readable; at `0.0` Phase 10c behavior is preserved exactly.

### What was NOT done

- Did not pin `Arc 2 Boundary Inset` in `PINNED_FOOTGUN_SOCKETS` (`backend/app/blender_live.py`). It's an artistic tuning knob, not a footgun; producer should leave the user's value alone across pushes.
- Did not expose `inset_range` as a socket. Hard-coded at `0.2` (= the halo width when split = `0.6`), which gives a taper that exactly covers the halo and reaches to the outer halo edges + symmetric reach into the core. Could be parameterized later if artists want a narrower / wider falloff zone.
- Did not apply this to Arc 1 (`Arc` node / `Store Named Attribute.001`). Arc 1 has no section boundaries; nothing to tuck.
- Did not delete the old `Math.019` / `Spline Parameter.002` chain. They're now unused for `v_around` but still present in the graph — leaving them in place keeps the revert one-link away.

### Lesson

Updated [lessons.md](lessons.md) Rule 27 with the **anchor-attribute pattern**: when you want to deform a profile *after* its parametric attribute is computed, bake the parametric attribute as a custom point-domain attribute on the profile mesh *before* the position deformation, then read it back downstream. This decouples the topological-parameter meaning from the geometric layout, so radial / tangential / displacement modifications don't perturb the parameter-driven texture chain.

---

## Phase 10e — Match Section Slopes (texture-proportional split eliminates boundary band)

**Date**: 2026-05-17

### Motivation

After Phase 10c (boundary vertex alignment) and the Phase 10 per-section U multiplier, user reported a still-visible *small* band on Arc 2 near letters G and B even with the per-section multiplier bypassed. Diagnosis: the residual band is the V slope discontinuity at the section boundaries — Phase 3q's geometric split is `0.6` fixed, but the texture's top-halo / core / bot-halo proportions are scan-driven and rarely match `0.2 / 0.6 / 0.2`. For the active yarn, top halo span = 0.0125, core padded = 0.0378, bot halo = 0.0135 — slopes work out to `0.0625 / 0.063 / 0.0675`, a 7% slope step at the Bot boundary that reads as a tiny cell-aspect band right where the B row sits.

### Symptom

- Very small band visible on Arc 2 near `v_around = 0.2` (around G row) and `v_around = 0.8` (around B row), persisting after Phase 10c + per-section U multiplier disabled.
- Cells on either side of each boundary have slightly different height-to-width aspect.

### Diagnosis

V slopes per section on the current yarn:

| section | tex-V span | v_around span | slope (tex-V / v_around) |
|---|---|---|---|
| Arc 2 Top  | 0.0125 | 0.2 | **0.0625** |
| Arc 2 Core | 0.0378 | 0.6 | **0.0630** |
| Arc 2 Bot  | 0.0135 | 0.2 | **0.0675** |

The 7% slope difference between Core and Bot is the visible band at `v_around = 0.8`.

To eliminate the discontinuity, the *geometric* split has to track the *texture* proportions: each section's `v_around` width should equal its tex-V span fraction of the total. Then `tex-V / v_around` is the same everywhere by construction.

### Fix

New interface socket **`Match Section Slopes`** (Socket_248, NodeSocketBool, default `False`) inside the `Surface` panel.

When `True`, the global Split Minus / Plus values are switched from Phase 3q's geometric ratio (`arc1_radius / arc2_radius = 0.6`) to a texture-proportional split derived from Material 1's V values:

```text
M1_Arc1_V_Min_Padded = max(Material 1 Arc 1 V Min − Arc 1 V Padding, Material 1 Arc 2 V Min)
M1_Arc1_V_Max_Padded = min(Material 1 Arc 1 V Max + Arc 1 V Padding, Material 1 Arc 2 V Max)

top_v   = M1_Arc1_V_Min_Padded − Material 1 Arc 2 V Min
core_v  = M1_Arc1_V_Max_Padded − M1_Arc1_V_Min_Padded
bot_v   = Material 1 Arc 2 V Max − M1_Arc1_V_Max_Padded
total_v = top_v + core_v + bot_v

Tex Split Minus = top_v / total_v
Tex Split Plus  = (top_v + core_v) / total_v
```

A pair of `GeometryNodeSwitch` (FLOAT, gated by `Match Section Slopes`) picks between Geo Split (Phase 3q, when `False`) and Tex Split (Phase 3m–style, when `True`), feeding `PW Band - Split Minus` and `PW Band - Split Plus` — the canonical scalars consumed by the V Map Range chain, the polyline natural-anchor chain (Phase 10c), and the per-section U multiplier (Phase 10).

### Why this works without breaking Phase 10c

Phase 10c's polyline uses **fixed natural anchors** `0.2 / 0.8` for the Mesh Line vertex placement; its piecewise Map Range maps `natural ∈ [0, 0.2] → [0, Split Minus]` etc. When Split Minus changes (because of the new toggle), the polyline simply re-samples Arc.001 at the new actual factor, and per-section segment lengths stay equal within each section. The polyline's section boundary in `v_around` space lands at `natural = 0.2` (vertex 6) regardless of the live Split Minus value.

With slopes equal on both sides of the boundary, **linear interpolation across the mesh face that spans `v_around = Split Minus` produces the correct tex_v even though the face's vertices straddle the boundary**. That's what makes the slope-match approach valid without requiring per-material polyline rebuilds.

### Verification

Live MCP readback with `Match Section Slopes = True` on the active yarn:

```
region           count      slope      ratio
Arc 1 main      440000     0.06383     1.0000
Arc 2 Top       240000     0.06383     1.0000
Arc 2 Core      720000     0.06383     1.0000
Arc 2 Bot       280000     0.06383     1.0000
```

All four section slopes equal to 5 decimal places (`0.06383`). All `pw_section_ratio` values equal to `1.0000` exactly — the Phase 10 per-section U multiplier becomes a no-op (multiplies by 1.0 everywhere) since there's no slope mismatch to compensate for.

Viewport screenshot confirms: every letter row (F, G, H, A, B, …) is visible in clean alphabetical sequence across the strand cross-section. No band at the boundaries.

### What was NOT done

- Did not change the default from `False` to `True`. Phase 3q's geometric split is the legacy behavior; making the toggle opt-in avoids surprising existing setups. Recommended to turn it on for clean-render mode.
- Did not generalize beyond Material 1. The texture-proportional split uses Material 1's V values for the global splits. For multi-material renders, slopes are exactly equal for Material 1 only — other materials see a residual slope mismatch proportional to how much their V proportions diverge from Material 1's. A per-material variant would need either per-material split sockets (heavy graph rework) or per-face split routing through new switch chains.
- Did not retire the Phase 10 per-section U multiplier. When `Match Section Slopes = False` (Phase 3q split), the multiplier still compensates for slope mismatch on wide-halo yarns. When `True`, it's a no-op.
- Did not retire the Phase 10d Arc 2 Boundary Inset socket. It still works on the texture-proportional polyline; just becomes less necessary when slopes match.

### Lesson

Two paths produce equal section slopes:
1. **Match the geometric split to the texture proportions** (this phase): clean but makes the split yarn-specific.
2. **Smoothing zones at the boundary** (not implemented): keeps the geometric split rigid but blends V slope across small ranges.

Path 1 is preferable when there's a single dominant material per render (which is the common case here). Recorded in [lessons.md](lessons.md) Rule 27 — extended.

---

## Phase 10f — Cosine-weighted Top/Bot V mapping (silhouette de-stretch)

**Date**: 2026-05-17

### Motivation

After Phase 10e, user observed the silhouette edges of Arc 2 still looked stretched: in Top and Bot sections the linear-in-`v_around` mapping spreads the (thin) halo V band across `20%` of `v_around`, so when `Arc 1 V Padding ≥ 0.012` shrinks the halo `top_v_span` to ~`0.003` for the active yarn, one tex-V cell ends up stretched across most of the section's width. Arc 1 doesn't have this problem because its mapping is uniform across `v_around[0, 1]` with the full padded core span. User asked for an angle-of-curvature-aware UV mapping for Top and Bot only — Core looks correct as-is.

### Symptom

- With Edge Angle Mapping OFF (linear V in `v_around`): silhouette polygons of Arc 2 show one huge stretched cell each (visible bright pink/red bands taking up the full Top/Bot section width).
- With Match Section Slopes either state, the linear-in-`v_around` form leaves the same stretching at silhouette polygons because the V slope per polygon was symmetric in `v_around`, not in projected screen size.

### Diagnosis

On a 120° cross-section arc, polygon projected screen size when viewed from `+Z` is proportional to `sin(θ)` where `θ` is the angle of curvature on the arc (start `30°`, sweep `120°`, end `150°`). Silhouette polygons (`θ` near `30°` or `150°`) have `sin(θ) ≈ 0.5` — half the screen footprint of polygons near the top of the arc (`θ = 90°`, `sin(θ) = 1`). For uniform cell appearance in screen space, the V coordinate should advance proportionally to `sin(θ)`, which integrates to `cos(θ_start) − cos(θ)` cumulatively. The linear-in-`v_around` mapping has constant slope in `θ` and therefore allocates the same V band to every polygon regardless of how thin its screen projection is — silhouette polygons end up showing too much of the texture content, which reads as stretched.

### Fix

New interface socket **`Arc 2 Edge Angle Mapping`** (Socket_249, NodeSocketBool, default `False`) in the Surface panel. When `True`, Arc 2 Top and Bot use a cumulative-`sin` V mapping (equivalent to linear-in-`cos(θ)`) instead of linear-in-`v_around`. Core remains untouched.

Math:

```text
THETA_START = 0.5236  (= 30°, from Arc.001 Start Angle)
SWEEP        = 2.0944  (= 120°, from Arc.001 Sweep Angle)
THETA_END    = THETA_START + SWEEP   (= 150°, both silhouettes are at sin=0.5)
cos_start    = cos(THETA_START)      (= +0.866)
cos_end      = cos(THETA_END)        (= −0.866)

Top section (v_around ∈ [0, Split Minus], θ ∈ [THETA_START, THETA_START + Split Minus·SWEEP]):
  θ(v)        = THETA_START + v × (Split Minus × SWEEP / 0.2)
  norm_top(v) = (cos_start − cos(θ(v))) / (cos_start − cos(THETA_START + Split Minus × SWEEP))
  tex_v_top   = Arc 2 V Min + norm_top × (Arc 1 V Min Padded − Arc 2 V Min)

Bot section (v_around ∈ [0.8, 1], θ ∈ [THETA_START + Split Plus·SWEEP, THETA_END]):
  actual_factor(v) = Split Plus + (v − 0.8)/0.2 × (1 − Split Plus)
  θ(v)             = THETA_START + actual_factor × SWEEP
  cos_start_bot    = cos(THETA_START + Split Plus × SWEEP)
  norm_bot(v)      = (cos_start_bot − cos(θ(v))) / (cos_start_bot − cos_end)
  tex_v_bot        = Arc 1 V Max Padded + norm_bot × (Arc 2 V Max − Arc 1 V Max Padded)
```

Implementation: ~22 nodes (`PW EdgeAng - Top *` and `PW EdgeAng - Bot *`) compute these expressions; two `GeometryNodeSwitch` (FLOAT, gated by the toggle) pick between the existing linear `Map Range.Result` and the new curvature-weighted output, feeding `PW Band - Top Weighted.in[0]` and `PW Band - Bot Weighted.in[0]`. Boundary continuity is preserved: at `v_around = Split Minus`, `norm_top → 1` so `tex_v_top → Arc 1 V Min Padded`, matching the Core section's `From Min`.

### Why Core stays linear

Core polygons span the central part of the arc (around `θ = 90°`) where `sin(θ)` is near `1` — they're already nearly face-on to the camera. Linear-in-`v_around` is approximately right there, and the user reported Core looks correct. The cosine remap would barely change Core values; not worth the complexity.

### Verification

Live MCP A/B at `Match Section Slopes = False`, `Arc 2 Edge Angle Mapping = True/False`:

- **OFF**: silhouette polygons show one huge stretched cell per section (clear pink/red bands across `v_around ∈ [0, 0.2]` and `[0.8, 1]`).
- **ON**: F, G, H, A, B rows visible in clean alphabetical sequence across the strand cross-section, cells approximately square across all sections.

Hand-calc sanity at `v_around = 0.0333` with current modifier state (Arc 1 V Padding `0.012` → Top span `0.0025`, Split Minus `0.2`):

```
θ(0.0333)  = 30° + 0.0333 × (0.2 × 120° / 0.2) = 30° + 4° = 33.92°
norm_top   = (cos(30°) − cos(33.92°)) / (cos(30°) − cos(54°))
           = (0.866 − 0.829) / (0.866 − 0.588)
           = 0.037 / 0.278 = 0.133
tex_v_top  = 0.4681 + 0.133 × 0.0025 = 0.46843
```

vs evaluated mesh readback `0.46848` — match to ±0.00005. (Tiny gap is from the float-precision `0.2 × 120° / 0.2 = 120°` round-trip.)

### What was NOT done

- Did not change Core mapping. Cosine remap on Core would barely move tex_v (small angle around 90°).
- Did not handle the asymmetric case where `Match Section Slopes = True` makes Top section very thin (e.g., `Split Minus = 0.039` for current padding). In that case the cosine remap operates only on the tiny natural-factor window and has negligible effect. Recommended setting for visible Edge Angle effect: `Match Section Slopes = False` (Phase 3q geometric split, `Split Minus = 0.2`).
- Did not auto-toggle Edge Angle based on padding magnitude. Padding-dependent dispatch could be a follow-up, but the explicit toggle is clearer for now.
- Did not retire any prior phase's machinery. Phase 10/10a per-section U multiplier, Phase 10c polyline profile, Phase 10d Boundary Inset, Phase 10e Match toggle — all still present.

### Lesson

When the V mapping per polygon needs to compensate for the cylinder cross-section's apparent screen-space size, use a **cumulative-`sin(θ)` mapping** instead of linear-in-`v_around` (or equivalently, linear-in-`cos(θ)`). The cumulative integral of `sin(θ)` is `cos(θ_start) − cos(θ)`, which naturally allocates less tex_v at the silhouette (low `sin(θ)`) and more near the top of the arc (high `sin(θ)`). Apply only on sections that span significant angular range relative to the camera (Top/Bot for a 120° arc with vertical camera); skip on Core where the section is already near face-on.

Recorded in [lessons.md](lessons.md) Rule 28.

### Postscript — when Edge Angle Mapping helps and when it doesn't

Subsequent user inspection: with Edge Angle ON, the cosine remap creates a **slope discontinuity at the section boundary** between cosine-Top and linear-Core. With `Arc 1 V Padding = 0.012` (high), `top_v_span = 0.0025` (very thin); the cosine peak slope at `v_around = 0.2` is `0.0152`, vs Core's linear slope `0.0963` — a 6× mismatch right at the boundary, which reads as cells changing size discontinuously across the seam.

The root cause is the small `top_v_span` (squeezed by high padding). **Reducing `Arc 1 V Padding` to `0.002`** restored `top_v_span = 0.0125` and made all four section slopes naturally close (`0.0625 / 0.0630 / 0.0675` — within 7%). Pure linear-in-`v_around` then produces continuous cells across the cross-section without needing the cosine remap.

**Recommended baseline for clean renders**: `Arc 1 V Padding = 0.002`, `Match Section Slopes = False`, `Arc 2 Edge Angle Mapping = False`, `Arc 2 Boundary Inset = 0.0`. Linear V mapping with low padding is sufficient when the yarn's halo/core proportions are not extreme.

Edge Angle Mapping remains in the graph as an opt-in tool for cases where high padding is artistically required and the resulting silhouette stretch needs compensation — but expect the boundary-slope-discontinuity trade-off and pair it with `Match Section Slopes = True` or a different yarn V layout to mitigate.

---

## Phase 10g — Arc 2 V sampled at Arc 1's physical rate

**Date**: 2026-05-17

### Motivation

After Phase 10e (`Match Section Slopes = True`) the V slope discontinuity at section boundaries disappeared, but Arc 2's V mapping then stretched the full texture span across `~0.907` of `v_around` on the larger Arc 2 cylinder, while Arc 1 sampled the (smaller) padded core across full `v_around` on the smaller cylinder. The same texture content covering different physical around-strand widths → cells `1.52×` larger in V on Arc 2 than on Arc 1 → Arc 2 looked "squished" in U relative to Arc 1 (taller-and-thinner aspect). User wanted Arc 2 to **sample at the same physical tex_v per BU as Arc 1**, accepting that the wider Arc 2 cylinder samples past the yarn's V band where the alpha map naturally hides it.

### Symptom

- With Match Section Slopes ON and Arc 1 V Padding ≥ 0.012, evaluated mesh readback: Arc 1 V span `0.0578`, Arc 2 V span `0.0638` (Arc 2 used wider span on a 1.67× wider cylinder).
- Physical V rate Arc 1 `1.84 tex_v/BU`, Arc 2 `1.21 tex_v/BU` — 52% mismatch.
- Cells on Arc 2 appeared visibly different scale than Arc 1 (taller, narrower in U).

### Fix

New interface socket **`Arc 2 Match Arc 1 V Rate`** (Socket_250, NodeSocketBool, default `False`) in the Surface panel. When `True`, replaces the entire piecewise Arc 2 V chain output with a single linear mapping:

```text
mid         = (Arc 1 V Min Padded + Arc 1 V Max Padded) / 2
span_padded = Arc 1 V Max Padded − Arc 1 V Min Padded
ratio       = Arc 2 Radius / Arc 1 Radius           (= 5/3 with default radii)
matched     = span_padded × ratio
tex_v(v_around) = mid + (v_around − 0.5) × matched
```

Implementation: 11 new nodes (`PW MatchScale - *`) compute the matched V, and a single `GeometryNodeSwitch` (FLOAT, gated by the toggle) replaces `PW Band - Diff.in[0]` from `PW Band - Arc2 V` (piecewise sum) to the matched output. Arc 1's `PW Band - Arc1 Map` is untouched — Arc 1 still does its own thing.

The matched mapping is symmetric around the padded core midpoint: at `v_around = 0.5` (top of cylinder), both Arc 1 and Arc 2 sample exactly the core midpoint. At the silhouette extremes (`v_around = 0` and `1`), Arc 2 samples tex_v at `mid ± 0.0482` for the current yarn, which sits **outside** Arc 2 V Min/Max = `[0.4681, 0.5319]` by `~0.017` on each side. On yarn scans those V regions are background (alpha `0`) → invisible. On a UV checker test pattern they'd show extra rows.

### Verification

Live MCP readback with `Arc 2 Match Arc 1 V Rate = True`:

```
Arc 1 main (full v_around):  V[0.4706, 0.5284]  span 0.0578
Arc 2     (full v_around):   V[0.4513, 0.5477]  span 0.0964

Tex_v samples at v_around = 0 / 0.5 / 1:
  Arc 1:  0.4706  /  0.4995  /  0.5284
  Arc 2:  0.4513  /  0.4995  /  0.5477
```

Both arcs share `tex_v = 0.4995` at the midpoint, and the V rates per physical BU around are now equal:
- Arc 1: `0.0578 / (2π × 0.015 × 120/360) = 0.0578 / 0.0314 = 1.84 tex_v/BU`
- Arc 2: `0.0964 / (2π × 0.025 × 120/360) = 0.0964 / 0.0524 = 1.84 tex_v/BU` ✓

Viewport screenshot on a real yarn material confirms uniform cell scale across Arc 1 and Arc 2 surfaces, no visible "squish" on Arc 2 silhouettes.

### Composition with other toggles

- Pair with `Match Section Slopes = True` for slope-continuous V mapping that *also* matches Arc 1's cell scale.
- `Arc 2 Boundary Inset` still works (deforms the polyline, doesn't affect the V mapping value).
- `Arc 2 Edge Angle Mapping` is overridden — its switch outputs feed `PW Band - Top/Bot Weighted` which sum into `PW Band - Arc2 V`, but the Match Arc 1 V Rate switch downstream replaces that whole sum.

### What was NOT done

- Did not change Arc 1's mapping (already correct).
- Did not handle the UV-checker-test case where the V extras beyond Arc 2 V Min/Max would show extra rows. The user explicitly accepted this trade-off — production yarn scans have alpha `0` outside the silhouette V band, so the extras are hidden.
- Did not auto-pair with Match Section Slopes. Both are independent opt-in toggles — user controls each.
- Did not bake the radius ratio as a constant. The ratio is read live from `PW Band - Geo Arc1/Arc2 Radius Value` so it tracks any future radius changes.

### Recommended setup with this toggle ON

```
Arc 1 V Padding         = 0.012  (your artistic choice)
Match Section Slopes    = True   (slope continuity at section boundaries)
Arc 2 Match Arc 1 V Rate = True  (Arc 1 and Arc 2 cells visually match)
Arc 2 Edge Angle Mapping = False (unnecessary with the matched mapping)
Arc 2 Boundary Inset    = 0.0    (smooth U cross-section)
```

### Lesson

When two concentric cylinder surfaces (Arc 1 inner, Arc 2 outer) need cells to visually match, the **physical tex_v per BU around** must match — not the parametric V slope. With Match Section Slopes ON, Arc 2's parametric V slope is artificially uniform across its piecewise sections, but the wider Arc 2 cylinder means each `v_around` unit covers more BU around → less tex_v per BU around → cells larger in V than Arc 1's. The fix is to scale Arc 2's V mapping by `r_arc2/r_arc1` and center it on the padded core midpoint; Arc 2 then samples past the yarn V band at the silhouette, which the alpha map naturally hides on real yarn scans. Promoted to [lessons.md](lessons.md) Rule 29.

### Postscript — ratio reverted to 1.0 (Arc 2 samples Arc 1's V range exactly)

User clarification: matching **physical** tex_v-per-BU (the `r_arc2/r_arc1 = 1.67×` scaling) made Arc 2 cells *physically* the same size as Arc 1's, but because Arc 2's cylinder is `1.67×` wider in circumference, more cells visibly fit across Arc 2's silhouette — perceived as Arc 2 cells being "1.7× squished" compared to Arc 1.

What user actually wanted: **same cells-per-silhouette count** on both arcs. That means Arc 2 samples *exactly* Arc 1's V range — `tex_v(v_around) = mid + (v_around − 0.5) × padded_core_span`, with no radius scaling. Then Arc 2's wider cylinder shows the same V content over more physical BU, so cells are physically larger on Arc 2 (in V direction, proportional to cylinder radius) but the cell *count* across the silhouette matches Arc 1's exactly.

Implementation: changed `PW MatchScale - Matched Span` to multiply `padded_core_span × 1.0` instead of `× ratio`. The radius nodes are still wired but the multiplier is now `1.0`.

Side effect: with ratio `1.0`, Arc 2 never samples tex_v outside `[Arc 1 V Min Padded, Arc 1 V Max Padded]` — i.e., **Arc 2 never shows halo content on its surface**. Where Arc 2 covers more cross-section area than the padded core, it still samples within the core V range (tex_v clamps to the boundaries at the silhouette extremes via the linear formula). For the user's UV-checker test this gives perfectly matched Arc 1 / Arc 2 cells. For yarn scans this means the wispy halo content (originally between `Arc 2 V Min` and `Arc 1 V Min Padded`) isn't rendered on Arc 2's surface; the halo wisps only appear via Arc 1's natural texture content at its silhouette extreme.

If the user wants halo content visible on Arc 2 *and* cells matched in scale, that's a different (and inherently contradictory) request — halo content lives outside `[Arc 1 V Min Padded, Arc 1 V Max Padded]`, so Arc 2 must sample beyond that range, which means more tex_v per silhouette than Arc 1, which means cells per silhouette ≠ Arc 1.

---

## Phase 10h — Visible-span U scale and completed Arc 2 range-match

**Date**: 2026-05-17

### Motivation

User reported that Arc 1 and Arc 2 were intended to overlap exactly, but the along-thread `Scale U` still looked misaligned after the unwrapping, padding, and thickness changes compounded. The important correction was not random U scatter; it was that automatic U scale was still derived from the raw core span while the graph was displaying the padded visible span.

### Symptom

Live readback before the fix:

```text
Material 1 Texture Scale U = 0.056415
raw core span              = 0.033849
Arc 1 V Padding            = 0.012
padded visible span        = 0.057849
Arc 1 evaluated V span     = 0.057849
Arc 2 evaluated V span     = 0.096415
U Stride Per Warp/Weft     = 0.181266
```

`0.056415 = raw_core_span / 0.6`, so U was calibrated to the unpadded core. Meanwhile Arc 1 was actually sampling the padded range. Arc 2 was also still using the older radius-ratio span (`0.057849 × 1.6667 = 0.096415`), even though the Phase 10g postscript documented the intended `× 1.0` range-match.

### Diagnosis

- [backend/app/blender_live.py](../../backend/app/blender_live.py) computed automatic `texture_scale_u` in `build_material_asset_entry`, where only asset metadata is available. That means the formula could see raw `core_v_min/max`, but not the current `Arc 1 V Padding` modifier socket.
- In the live node graph, `PW MatchScale - Radius Ratio.Value` was still linked into `PW MatchScale - Matched Span.Value`, so `Arc 2 Match Arc 1 V Rate` still produced physical-rate matching rather than the documented visual range-match.

### Fix

- Backup before changes:
  - `Codex_ParametricWeave.pre-u-visible-span-fix-20260517_223710.blend`
- Live `.blend`:
  - removed the link `PW MatchScale - Radius Ratio.Value -> PW MatchScale - Matched Span.Value`;
  - set `PW MatchScale - Matched Span` input 1 default to `1.0`;
  - recalculated current material U sockets from visible span:
    - `Material 1/2 Texture Scale U = 0.096415`;
    - `U Stride Per Warp End = U Stride Per Weft Pick = 0.309788`;
  - saved `Codex_ParametricWeave.blend`.
- Backend:
  - `build_material_asset_entry` now marks automatic U scale with `texture_scale_u_is_auto`;
  - `_pw_apply_modifier_material_metadata` resolves automatic U scale from:
    ```text
    padded_min = max(core_v_min - Arc 1 V Padding, fiber_bot_v_min)
    padded_max = min(core_v_max + Arc 1 V Padding, fiber_top_v_max)
    texture_scale_u = (padded_max - padded_min) / 0.6
    ```
  - the same resolved scale is used for `U Stride Per Warp End / Weft Pick`, so stride cannot stay on the old raw-core scale.

### Verification

Live readback after the fix:

```text
PW MatchScale - Matched Span input 1 linked = False
PW MatchScale - Matched Span input 1 value  = 1.0

Material 1 Texture Scale U = 0.096415
U Stride Per Warp End      = 0.309788
U Stride Per Weft Pick     = 0.309788

Arc 1 evaluated V span     = 0.057849
Arc 2 evaluated V span     = 0.057849
Arc 1/Arc 2 evaluated U span = identical
```

Backend tests updated to assert that automatic scale is resolved in the apply script and that explicit producer overrides still bypass auto derivation.

### What was NOT done

- Did not change `UV Random U`; user confirmed it has separate mechanics/use cases.
- Did not remove the `PW MatchScale - Radius Ratio` node; it remains available as a reference/revert point, but it is no longer linked into the current range-match path.
- Did not force users into the range-match toggle. If `Arc 2 Match Arc 1 V Rate` is off, the original piecewise Arc 2 halo mapping remains available.

### Lesson

Promoted to [lessons.md](lessons.md) Rule 30: automatic U scale must follow the visible padded V span, not the raw core span.

---

## Phase 10i — post-bend U storage and stride phase

**Date**: 2026-05-17

### Motivation

After Phase 10h, Arc 1 and Arc 2 had the same visible-span U scale, but the user's red-line viewport markup still showed along-thread checker columns drifting near the Arc 1 / Arc 2 transition. The user explicitly ruled out `UV Random U` and pointed to the secondary/thread-length U mechanics.

### Diagnosis

The active curve order was:

```text
Set Curve Normal -> Store Warp/Weft U -> PW Warp/Weft Set Position -> UV Offset U
```

`Store Warp U` / `Store Weft U` consumed `Warp/Weft U Compensated`, which uses `Spline Parameter × (Spline Length / Straight Length)`. Because the store node sat before `PW Warp/Weft Set Position`, the `Spline Length` field measured the straight/pre-bend curve. The visible amplitude/over-under bend was added afterward, so the rendered curve became longer than the U coordinate it carried.

This is separate from `UV Random U`: random U adds a variation offset; it does not change where deterministic thread length is measured.

### Backup

Before the graph edit:

```text
Codex_ParametricWeave.pre-postbend-u-fix-20260517_225951.blend
```

The earlier Phase 10h backup is also still present:

```text
Codex_ParametricWeave.pre-u-visible-span-fix-20260517_223710.blend
```

### Fix

Live `.blend` node graph:

- rewired `PW Warp Set Curve Normal.Curve -> PW Warp Set Position.Geometry`;
- rewired `PW Warp Set Position.Geometry -> Store Warp U.Geometry`;
- rewired `Store Warp U.Geometry -> PW Warp UV Offset U.Geometry`;
- applied the same order to the weft branch;
- added `PW Warp U Stride Post-Bend Ratio = U Stride Per Warp End × Warp Length Ratio`;
- added `PW Weft U Stride Post-Bend Ratio = U Stride Per Weft Pick × Weft Length Ratio`;
- fed those post-bend stride outputs into `PW Warp/Weft U Stride x Index`;
- saved `Codex_ParametricWeave.blend`.

The backend still computes the stride socket as the straight-baseline repeats-per-strand. The graph now multiplies that socket by the contextual post-bend length ratio, so `u_along` and `uv_offset_u` use the same effective path length.

### Verification

Live readback after save:

```text
PW Warp Set Position.Geometry <- PW Warp Set Curve Normal.Curve
Store Warp U.Geometry         <- PW Warp Set Position.Geometry
PW Warp UV Offset U.Geometry  <- Store Warp U.Geometry

PW Weft Set Position.Geometry <- PW Weft Set Curve Normal.Curve
Store Weft U.Geometry         <- PW Weft Set Position.Geometry
PW Weft UV Offset U.Geometry  <- Store Weft U.Geometry

PW Warp U Stride x Index.Value <- PW Warp U Stride Post-Bend Ratio.Value
PW Weft U Stride x Index.Value <- PW Weft U Stride Post-Bend Ratio.Value
```

Evaluated mesh sample:

```text
u_along span, Arc 1/main = 0.0 .. 1.075270
u_along span, Arc 2/sub  = 0.0 .. 1.075270
pw_section_ratio         = 1.0 in the current Match Arc 1 V Rate state
```

The important change is that `u_along` now includes the visible bend's extra length (`~7.5%` on the current swatch) instead of stopping at the straight pre-bend `1.0`.

### What was NOT done

- Did not change `UV Random U`; the user was right that it is a separate variation mechanic.
- Did not add a new backend socket. The correction is graph-owned because the post-bend length ratio is already available contextually inside Geometry Nodes.
- Did not alter Arc 2 V matching or per-material `Texture Scale U`; Phase 10h remains the visible-span scale fix.

### Lesson

Promoted to [lessons.md](lessons.md) Rule 31: store U after the visible curve deformation, and scale stride by the same length ratio.

---

## Phase 10j — Arc 2 visual-projection U correction

**Date**: 2026-05-17

**Status**: reverted after user reported complete visual distortion.

### Motivation

User clarified that the red-line screenshot was exactly the problem to solve: Arc 1 and Arc 2 are separate screen-projected shells, and the goal is visual registration between those shells, not merely equal raw UV values.

### Diagnosis

After Phase 10i:

- `uv_scaled.y` matched between Arc 1 and Arc 2 at common `v_around` bins down to float noise;
- base U matched for corresponding samples;
- the viewport still read different because Arc 2 is physically offset from Arc 1 in radius/depth and projects to a different top-view X/Y location.

The deterministic missing term is:

```text
projected Arc 2 surface axis - centerline axis used by U
```

That term must be converted back into texture-U units and added to Arc 2 only.

### Backup

Before the graph edit:

```text
Codex_ParametricWeave.pre-arc2-projected-u-fix-20260517_233330.blend
```

### Attempted fix

Live `.blend` node graph:

- added `PW Warp Thread Kind Store` and `PW Weft Thread Kind Store`, writing `pw_thread_kind = 0/1` before the warp/weft curves join;
- added `PW Warp U Factor Store` and `PW Weft U Factor Store`, writing raw `pw_u_factor` after `PW Warp/Weft Set Position` and before compensated `u_along`;
- added the `PW VisU - *` correction chain:
  - reads `Position.X/Y`, `pw_thread_kind`, `pw_u_factor`, `Warp/Weft Straight Length`, `PW U - Scale U Final`, and `is_sub_strand`;
  - computes projected axis (`Y` for warp, `X` for weft);
  - computes centerline axis (`pw_u_factor × straight_length`);
  - converts the projected-axis delta to U;
  - gates the correction by `is_sub_strand × Arc 2 Match Arc 1 V Rate`;
  - feeds `PW U - Per Section Multiplier` from `PW VisU - Corrected U Add`;
- added debug store `pw_visual_u_correction`;
- reset the diagnostic-only `Arc 2 Boundary Inset` tweak back to `0.0`;
- saved `Codex_ParametricWeave.blend`.

### Verification

Live readback:

```text
PW U - Per Section Multiplier.Value <- PW VisU - Corrected U Add.Value
pw_u_factor                         stored on evaluated mesh
pw_thread_kind                      stored on evaluated mesh
pw_visual_u_correction              stored on evaluated mesh
Arc 2 Boundary Inset                = 0.0
```

Correction stats on the current swatch:

```text
Arc 1/main correction = 0.0
Arc 2/sub correction  ≈ -0.18 .. +0.18 U
median correction     ≈ 0.0
```

### Revert

User reported the result was completely distorted. The attempt was backed up and reverted immediately:

```text
Codex_ParametricWeave.failed-arc2-projected-u-fix-20260517_235124.blend
Codex_ParametricWeave.blend <- Codex_ParametricWeave.pre-arc2-projected-u-fix-20260517_233330.blend
```

The restored file was reloaded into the running Blender session. Live readback after restore:

```text
has PW VisU nodes                 = false
has pw_visual_u_correction store  = false
has pw_u_factor store             = false
Arc 2 Boundary Inset              = 0.0
Arc 2 Match Arc 1 V Rate          = true
```

### What was NOT done

- Did not use `UV Random U`; this remains a separate variation offset.
- Did not hide the boundary with `Arc 2 Boundary Inset`; the diagnostic inset was reset before saving.
- Did not keep the correction active after the distortion report.

### Lesson

Promoted to [lessons.md](lessons.md) Rule 32 as a cautionary lesson: for two visible offset shells, matching UV values is not visual registration, but a naive projected-axis U correction is not sufficient.

---

## Phase 10k — Same-strand Arc 2 U transfer

**Date**: 2026-05-18 local session

**Status**: active; still part of the Phase 10t saved inspection state.

### Motivation

After Phase 10j was reverted, the user confirmed the real target: Arc 1 and Arc 2 are two visible offset shells, and the checker columns need to visually register between those shells. `UV Random U` is not involved; the secondary U path was the suspect.

### Diagnosis

Screenshot-driven iteration showed:

- `runtime/self_iter_full_000.png`: the earlier U-only nearest-surface preview still distorted because it could sample the wrong neighboring strand;
- `runtime/self_iter_inset_*.png`: `Arc 2 Boundary Inset` near `0.010` starts hiding the seam but creates speckled/z-fighting artifacts and does not solve U registration;
- `runtime/self_iter_arc2_z_*.png`: moving Arc 2 in Z barely changes the top-view misregistration;
- `runtime/self_iter_core_xfer_u_range.png`: core-only ungrouped U transfer still creates bad beige striping;
- `runtime/self_iter_strand_group_xfer_full.png`: grouped same-strand transfer removes the large U strip distortion and keeps Arc 2's U phase tied to the matching Arc 1 strand.

The missing condition was strand identity. Arc 2 must borrow U from Arc 1 on the same physical warp/weft strand, not from whatever Arc 1 face is nearest in 3D.

### Backups

Created before risky graph branches and before saving the final active graph:

```text
Codex_ParametricWeave.pre-self-screenshot-iterate-20260518_000135.blend
Codex_ParametricWeave.pre-arc2-core-tuck-preview-20260518_001538.blend
Codex_ParametricWeave.pre-strand-group-u-transfer-save-20260518_005328.blend
```

### Fix

Saved `.blend` node graph:

- added `PW StrandID - Store Warp`, storing point INT attribute `pw_strand_id = Curve of Point.Curve Index` before warp curves join;
- added `PW StrandID - Weft Offset` and `PW StrandID - Store Weft`, storing `pw_strand_id = Curve Index + 10000` before weft curves join;
- added `PW StrandXferU - Strand ID`, reading `pw_strand_id`;
- added `PW StrandXferU - Sample Same-Strand Arc1 U`, sampling `PW U - Per Section Multiplier.Value` from the Arc 1/main mesh with both `Group ID` and `Sample Group ID` set to `pw_strand_id`;
- added `PW StrandXferU - Is Arc2`, reading `is_sub_strand`;
- added `PW StrandXferU - Use Same-Strand Arc1 U On Arc2`, selecting sampled Arc 1 U for Arc 2 and original U for Arc 1;
- rewired `Combine XYZ.006.X` from `PW U - Per Section Multiplier.Value` to `PW StrandXferU - Use Same-Strand Arc1 U On Arc2.Output`.

Saved modifier/socket state for this inspection pass:

```text
Arc 2 Boundary Inset       = 0.0
Match Section Slopes       = false
Arc 2 Edge Angle Mapping   = false
Arc 2 Match Arc 1 V Rate   = true
```

### Verification

Live screenshot:

```text
runtime/self_iter_strand_group_xfer_full.png
```

Evaluated mesh readback confirmed `pw_strand_id` exists and the U ranges remain sane after transfer:

```text
Arc 1 uv_scaled.x range      ≈ 0.01957 .. 27.53905
Arc 2 core uv_scaled.x range ≈ 0.01957 .. 27.53905
Arc 2 top/bot uv_scaled.x    ≈ 0.01957 .. 27.53905
strand id range              = 0 .. 10079
```

### What was NOT done

- Did not use `UV Random U`; this remains a separate variation offset.
- Did not keep `PW VisU - *`, `pw_visual_u_correction`, `pw_u_factor`, or `pw_thread_kind`.
- Did not keep the experimental core-tuck or ungrouped `PW CoreXferU - *` branches.
- Did not transfer V from Arc 1 to Arc 2; Arc 2 keeps its own around-profile V mapping.

### Lesson

Promoted to [lessons.md](lessons.md) Rule 32: for two visible offset shells, transfer U by same physical strand. Ungrouped nearest-surface transfer can be as wrong as raw screen projection because it can pick the wrong strand.

---

## Phase 10l — Projected matched-V skew for Arc 2

**Date**: 2026-05-18 local session

**Status**: superseded by Phase 10m in the saved inspection state.

### Motivation

After Phase 10k, U registration was correct, but the user marked a remaining V problem in the Arc 2 halo: F/G-like rows were taking too much vertical space at the extra halo edges and reading as repeated/stretchy instead of flowing evenly.

### Diagnosis

The existing Phase 10f `Arc 2 Edge Angle Mapping` nodes only sit in the piecewise Arc 2 Top/Bot path:

```text
PW Band - Arc2 Top/Bot -> PW EdgeAng - Switch Top/Bot -> weighted Arc2 V sum
```

The saved Phase 10k inspection state uses `Arc 2 Match Arc 1 V Rate = True`, which bypasses that path through `PW MatchScale - Switch Arc2 V`. So simply toggling `Arc 2 Edge Angle Mapping` did not move the active `uv_scaled.y`.

### Backup

Created before this V-skew branch:

```text
Codex_ParametricWeave.pre-arc2-v-skew-preview-20260518_001.blend
```

### Fix

Added `PW MatchProjV - *` nodes directly inside the matched-V branch:

```text
theta       = 15deg + v_around * 150deg
projected_v = (cos(15deg) - cos(theta)) / (cos(15deg) - cos(165deg))
tex_v_arc2  = mid + (projected_v - 0.5) * matched_span
```

Active links:

```text
PW MatchScale - Delta.Value <- PW MatchScale - Matched Span.Value
PW MatchScale - Delta.Value <- PW MatchProjV - projected minus 0.5.Value
```

Saved modifier/socket state:

```text
Arc 2 Boundary Inset       = 0.0
Match Section Slopes       = true
Arc 2 Edge Angle Mapping   = true
Arc 2 Match Arc 1 V Rate   = true
```

### Verification

Screenshots:

```text
runtime/self_iter_v_matchproj_hardwired.png      # physical 30deg..150deg preview
runtime/self_iter_v_matchease_hardwired.png      # full 0deg..180deg ease, rejected as too strong
runtime/self_iter_v_matchproj_15deg.png          # selected middle-ground preview
runtime/self_iter_v_projected_15deg_final.png    # final saved state
```

Readback for representative Arc 2 vertices after the final `15deg..165deg` remap:

```text
v_around 0.0 -> uv_scaled.y 0.47059184
v_around 0.2 -> uv_scaled.y 0.47834218   # linear was ~0.48216170
v_around 0.5 -> uv_scaled.y 0.49951643
v_around 0.8 -> uv_scaled.y 0.52069068   # linear was ~0.51687115
v_around 1.0 -> uv_scaled.y 0.52844101
```

Endpoints stay identical to the Arc 1 padded range, so the mapping stays continuous and does not wrap/repeat. The edge bands consume less V; the center consumes the released span.

### What was NOT done

- Did not change producer metadata or yarn band detection.
- Did not sample Arc 1 V with nearest surface; that would collapse/flatten the extra Arc 2 halo rather than distributing it.
- Did not keep the full `0deg..180deg` ease; it compressed the edges too aggressively in preview.

### Lesson

Promoted to [lessons.md](lessons.md) Rule 33: if matched Arc 2 V is active, skew the matched factor itself; the older Top/Bot edge-angle path is bypassed.

---

## Phase 10m — Project-from-view V and checker phase alignment

**Date**: 2026-05-18 local session

**Status**: partially superseded by Phase 10n. Arc 1's project-from-view map remains active; the matched Arc 2 branch and `0.029408127` offset are no longer the saved inspection state.

### Motivation

After the Phase 10l skew, the user clarified that the desired result was literal top/camera "Project From View" continuity across R1/R2, with the checker flowing through one A-to-F-like run rather than wrapping/repeating G/H at the halo.

### Backup

Created before this camera/projected V pass:

```text
Codex_ParametricWeave.pre-camera-projected-v-20260518_001.blend
```

### Diagnosis

Two separate issues were stacked:

```text
1. The active V shape was still local-shell logic, not top-view projection for both layers.
2. The current V band 0.47059187..0.52844101 was multiplied by the checker material's 12x V scale, so it crossed an integer repeat boundary:
   0.47059187 * 12 = 5.647
   0.52844101 * 12 = 6.341
```

That boundary crossing is why a sub-strand could look like it repeated G/H before flowing back into A.

### Fix

Saved node/socket state:

```text
PW Band - Arc1 Map.Value        <- PW MatchProjV - projected factor.Value
PW MatchScale - Delta.Value     <- PW MatchScale - v_around - 0.5.Value
PW MatchProjV sweep             = pi
PW MatchProjV theta start       = 0
PW MatchProjV denominator       = 2
Texture Offset V (Socket_44)    = 0.029408127
Arc 2 Match Arc 1 V Rate        = true
Match Section Slopes            = true
Arc 2 Boundary Inset            = 0.0
```

Backend persistence:

```text
backend/app/blender_live.py PINNED_FOOTGUN_SOCKETS now pushes Texture Offset V = 0.029408127069473267
backend/app/blender_sync.py uses the same fallback when no preserved Texture Offset V exists
```

The active math is:

```text
projected_v_arc1 = (1 - cos(pi * v_around)) / 2
projected_v_arc2 = v_around
uv_y_min_final    = 0.47059187 + 0.029408127 = 0.50000000
uv_y_max_final    = 0.52844101 + 0.029408127 = 0.55784911
```

Arc 2 stays linear because evaluating one strand from the top view showed its projected top coordinate is already linear in `v_around`; applying the same cosine there was another local remap, not true project-from-view.

### Verification

Screenshots:

```text
runtime/self_iter_v_same_strand_nearest_preview.png              # rejected: nearest V transfer flattened the halo
runtime/self_iter_v_project_from_view_r1_r2_material.png         # rejected: material/solid capture was not diagnostic
runtime/self_iter_v_project_arc1_cos_arc2_linear_viewport.png    # shape sanity check
runtime/self_iter_v_phase_aligned_plus_029408_viewport.png       # phase-alignment preview
runtime/self_iter_v_phase10m_final_projected_phase_aligned.png   # final saved state
```

Readback for representative vertices on strand `10000` after the save:

```text
Arc 1/R1 v_around 0.0 -> uv_scaled.y 0.500000, checker 12x phase 0.000
Arc 1/R1 v_around 0.5 -> uv_scaled.y 0.528925, checker 12x phase 0.347
Arc 1/R1 v_around 1.0 -> uv_scaled.y 0.557849, checker 12x phase 0.694

Arc 2/R2 v_around 0.0 -> uv_scaled.y 0.500000, checker 12x phase 0.000
Arc 2/R2 v_around 0.5 -> uv_scaled.y 0.528925, checker 12x phase 0.347
Arc 2/R2 v_around 1.0 -> uv_scaled.y 0.557849, checker 12x phase 0.694
```

The mapped checker phase now stays inside one tile instead of wrapping through the repeat boundary.

### Lesson

Promoted to [lessons.md](lessons.md) Rule 34: project-from-view V needs both the correct top-view shape per layer and a material-phase check. Phase 10n adds Rule 35 because the matched Arc 2 branch was the wrong active source when the halo texture must remain visible.

---

## Phase 10n — Full Arc 2 halo V path and phase re-pin

**Date**: 2026-05-18 local session

**Status**: active in `Codex_ParametricWeave.blend`.

### Motivation

The user rejected the Phase 10m result because Arc 2's visual area was still repeating/stretching the same Arc 1-covered core texture. The intended ownership is:

```text
Arc 1/R1 center/core        -> Arc 1 padded core texture range
Arc 2/R2 overlapping core   -> same core texture range
Arc 2/R2 extra halo/ends    -> extra yarn/thread texture outside the Arc 1 core
```

That means `Arc 2 Match Arc 1 V Rate = True` is conceptually wrong for the final look: it collapses Arc 2 onto the Arc 1 padded core range and never reaches the halo texture.

### Backups

Created before this correction path:

```text
Codex_ParametricWeave.pre-arc2-full-halo-v-20260518_032211.blend
Codex_ParametricWeave.pre-arc2-full-halo-phase-repin-20260518_001.blend
```

### Fix

Saved node/socket state:

```text
Arc 2 Match Arc 1 V Rate (Socket_250) = false
Match Section Slopes (Socket_248)     = true
Arc 2 Edge Angle Mapping (Socket_249) = true
Arc 2 Boundary Inset (Socket_247)     = 0.0
Texture Offset V (Socket_44)          = 0.031914920

PW Band - Arc1 Map.Value              <- PW MatchProjV - projected factor.Value
PW MatchScale - Switch Arc2 V.False   <- PW Band - Arc2 V.Value
Combine XYZ.006.X                     <- PW StrandXferU - Use Same-Strand Arc1 U On Arc2.Output
```

The active V math is now:

```text
projected_v_arc1 = (1 - cos(pi * v_around)) / 2
uv_scaled.y R1   = map(projected_v_arc1, 0..1 -> Arc 1 padded V) + 0.031914920

uv_scaled.y R2   = piecewise Arc 2 Top/Core/Bot V + 0.031914920
Top halo          Arc 2 V Min        -> Arc 1 V Min Padded
Core              Arc 1 V Min Padded -> Arc 1 V Max Padded
Bottom halo       Arc 1 V Max Padded -> Arc 2 V Max
```

### Phase Re-Pin

After disabling the matched branch, the old `0.029408127` phase offset was still aligned to Arc 1's core min. Arc 2's wider full-halo band then started at `0.497493`, which becomes checker phase `0.969918` at `12x` V scale and immediately wraps. The active offset is now aligned to Arc 2's full-halo min instead:

```text
Arc 2/R2 old offset result: 0.49749321 .. 0.56132299  # checker phase 0.970 -> wrap -> 0.736
Arc 2/R2 new offset result: 0.50000006 .. 0.56382984  # checker phase 0.000 -> 0.766
Arc 1/R1 new offset result: 0.50250685 .. 0.56035596  # checker phase 0.030 -> 0.724
```

Backend persistence:

```text
backend/app/blender_live.py PINNED_FOOTGUN_SOCKETS now pushes Texture Offset V = 0.03191491961479187
backend/app/blender_sync.py uses the same fallback when no preserved Texture Offset V exists
```

### Verification

Readback after save:

```text
Arc 2 Match Arc 1 V Rate = false
Arc 2/R2 v_around 0.0 -> uv_scaled.y 0.500000, checker 12x phase 0.000
Arc 2/R2 v_around 0.5 -> uv_scaled.y 0.531915, checker 12x phase 0.383
Arc 2/R2 v_around 1.0 -> uv_scaled.y 0.563830, checker 12x phase 0.766
```

Screenshots:

```text
runtime/self_iter_v_full_arc2_piecewise_preview.png
runtime/self_iter_v_full_arc2_piecewise_phase_repin.png
```

### Lesson

Promoted to [lessons.md](lessons.md) Rule 35: when Arc 2 needs halo texture, keep matched V rate off.

---

## Phase 10o — Sync Arc 2 profile boundaries to the canonical split

**Date**: 2026-05-18 local session

**Status**: active in `Codex_ParametricWeave.blend`.

### Motivation

User flagged that Arc 2's V mapping looked like it was copying/reusing the wrong section values even though Arc 2 is meant to run as three distinct Top/Core/Bot sections.

### Diagnosis

The current docs say `PW Band - Split Minus` / `PW Band - Split Plus` are the canonical split values consumed by the Arc 2 V Map Ranges, the per-section U multiplier, and the custom Arc 2 profile/polyline. Live graph readback showed a drift:

```text
PW Band - Arc2 Top/Core/Bot      <- PW Band - Split Minus/Plus
PW U - Sec * width nodes         <- PW Band - Split Minus/Plus
PW Profile - Top/Core/Bot Map    <- PW Band - Geo Split Minus/Plus  # stale
PW Debug Store Arc2 Split Min/Max <- PW Band - Geo Split Minus/Plus # stale
```

With `Match Section Slopes = True`, the V mapping used the texture-proportional split (`0.039273 / 0.945576` for the active Material 1), while the profile boundary placement/debug attrs still reported the old geometry-only split (`0.2 / 0.8`). That made the Arc 2 section boundaries disagree internally.

### Backup

Created before editing:

```text
Codex_ParametricWeave.pre-arc2-split-profile-sync-20260518_035357.blend
```

### Fix

Rewired the stale profile/debug inputs to the canonical split nodes:

```text
PW Profile - Top Map.To Max       <- PW Band - Split Minus.Value
PW Profile - Core Map.To Min      <- PW Band - Split Minus.Value
PW Profile - Core Map.To Max      <- PW Band - Split Plus.Value
PW Profile - Bot Map.To Min       <- PW Band - Split Plus.Value
PW Debug Store Arc2 Split Min     <- PW Band - Split Minus.Value
PW Debug Store Arc2 Split Max     <- PW Band - Split Plus.Value
```

The Arc 2 V destination path itself stayed unchanged:

```text
Arc2 Top:  Arc 2 V Min -> Arc 1 V Min Padded
Arc2 Core: Arc 1 V Min Padded -> Arc 1 V Max Padded
Arc2 Bot:  Arc 1 V Max Padded -> Arc 2 V Max
Arc 2 Match Arc 1 V Rate = false
```

### Verification

Live MCP readback after save:

```text
PW Profile - Top Map.To Max       <- PW Band - Split Minus
PW Profile - Core Map.To Min      <- PW Band - Split Minus
PW Profile - Core Map.To Max      <- PW Band - Split Plus
PW Profile - Bot Map.To Min       <- PW Band - Split Plus
PW Band - Arc2 Top/Core/Bot       <- the same Split Minus/Plus nodes
arc2_core_split_min               = 0.039273
arc2_core_split_max               = 0.945576
pw_section_ratio                  = 1.0
pw_section_slope                  = 0.06383
```

### Lesson

When adding a new switched canonical value, audit every consumer that used the older source node. For Arc 2 splits, the V Map Ranges, profile/polyline maps, debug stores, edge-angle math, and per-section U math must all read the same `PW Band - Split Minus/Plus` pair.

---

## Phase 10p — Store actual Arc 2 profile factor for v_around

**Date**: 2026-05-18 local session

**Status**: active in `Codex_ParametricWeave.blend`.

### Motivation

User clarified the desired Arc 2 interpretation: the Top and Bot halo textures should each flow from the core seam toward the outside edge, and the core-to-extreme polygon strip should not look stretched after Phase 10o.

### Diagnosis

Phase 10o made the Arc 2 profile maps consume the canonical `PW Band - Split Minus/Plus`, but `v_around` was still written from the fixed natural anchor attribute (`pw_profile_natural`). With `Match Section Slopes = True`, this meant:

```text
natural anchor vertex 6  = 0.2
actual source-arc factor = 0.039273
Arc 2 V split            = 0.039273
```

The physical profile boundary was in the right place, but parts of the halo strip still carried natural `v_around` values past the V split, so the UV section tests could classify the same physical halo strip as core. A direct link from `PW Profile - Actual Factor` to the final `v_around` store was tested first, but Blender field context collapsed the sub-strand `v_around` range to about `0..0.004`, so that direct link was not kept.

### Backups

Created before the two edits in this pass:

```text
Codex_ParametricWeave.pre-arc2-varound-actual-sync-20260518_124555.blend
Codex_ParametricWeave.pre-arc2-varound-actual-attribute-20260518_124738.blend
```

### Fix

Added a proper named-attribute bridge on the Arc 2 profile mesh:

```text
PW Profile - Store Natural Factor.Geometry -> PW Profile - Store Actual Factor.Geometry
PW Profile - Actual Factor.Value           -> PW Profile - Store Actual Factor.Value
PW Profile - Store Actual Factor.Geometry  -> PW Profile - Set Position.Geometry
PW Profile - Read Actual Factor.Attribute  -> Store Named Attribute.003.Value
```

New attribute:

```text
pw_profile_actual = computed actual source-arc factor
```

`pw_profile_natural` remains in the graph as the fixed anchor/debug attribute. `v_around` on Arc 2 now uses `pw_profile_actual`, so the UV section tests and physical profile boundaries share the same coordinate system.

### Verification

Live MCP evaluated-mesh readback:

```text
Store Named Attribute.003.Value <- PW Profile - Read Actual Factor.Attribute
sub-strand v_around range       = 0.0 .. 1.0
arc2_core_split_min             = 0.039273
arc2_core_split_max             = 0.945576

sub-strand samples:
natural 0.000000 -> actual/v_around 0.000000 -> uv_y 0.500000  # outer lower edge
natural 0.200000 -> actual/v_around 0.039273 -> uv_y 0.502507  # lower core seam
natural 0.800000 -> actual/v_around 0.945576 -> uv_y 0.560356  # upper core seam
natural 1.000000 -> actual/v_around 1.000000 -> uv_y 0.563830  # outer upper edge

pw_section_ratio = 1.0
pw_section_slope = 0.06383
```

This keeps the full Arc 2 halo destination path while making the actual UV section ownership match the vertices that define the profile sections.

### Lesson

When a field is computed before `Mesh to Curve` but consumed after it, store it as a named attribute before the domain/context change and read that attribute downstream. Direct field links across that boundary can evaluate in the wrong context.

---

## Phase 10q — Simple raw-core Arc 2 V mapping

**Date**: 2026-05-18 local session

**Status**: active in `Codex_ParametricWeave.blend`.

### Motivation

User clarified that Arc 2 must not look like the same Arc 1 padded core area stretched across the whole Arc 2 shell. Both Arc 2 halo strips should visibly map from the raw core seam outward to the outer silhouette rows.

### Fix

Saved the readable Arc 2 inspection state:

```text
Match Section Slopes       = false
Arc 2 Edge Angle Mapping   = false
Arc 2 Match Arc 1 V Rate   = false

PW Band - Split Minus      <- PW Band - Geo Split Minus   # 0.2
PW Band - Split Plus       <- PW Band - Geo Split Plus    # 0.8

PW Band - Arc2 Top.To Max  <- PW Material Core V Min Select 16
PW Band - Arc2 Core.To Min <- PW Material Core V Min Select 16
PW Band - Arc2 Core.To Max <- PW Material Core V Max Select 16
PW Band - Arc2 Bot.To Min  <- PW Material Core V Max Select 16
```

Arc 1 still uses `Arc 1 V Padding`; Arc 2 does not. Arc 2's stitched path is:

```text
Top:  Arc 2 V Min -> raw Arc 1 V Min
Core: raw Arc 1 V Min -> raw Arc 1 V Max
Bot:  raw Arc 1 V Max -> Arc 2 V Max
```

### Backup

```text
Codex_ParametricWeave.pre-arc2-hardwire-geo-split-20260518_133924.blend
```

### Verification

Live evaluated-mesh readback for Material 1 sub-strand:

```text
split_min = 0.2
split_max = 0.8

v_around 0.0 -> uv_y 0.500000  # Arc 2 V Min + offset
v_around 0.2 -> uv_y 0.514507  # raw Arc 1 V Min + offset
v_around 0.5 -> uv_y 0.531431  # raw core midpoint + offset
v_around 0.8 -> uv_y 0.548356  # raw Arc 1 V Max + offset
v_around 1.0 -> uv_y 0.563830  # Arc 2 V Max + offset
```

This confirms Arc 2 reaches the outer rows and is not collapsed to Arc 1's padded core range.

---

## Phase 10r - Force Arc 1 / Arc 2 equal-scale review mode

**Date**: 2026-05-18 local session

### Motivation

User clarified the active review target: Arc 1 and Arc 2 should have equal-looking texture scale and UV mapping. The previous folded Arc 2 experiment changed the V ownership direction but made Arc 2 visually zoom/stretch differently from Arc 1.

### Diagnosis

Setting the panel socket `Arc 2 Match Arc 1 V Rate = true` was not enough in the current graph. Evaluated debug taps showed `PW MatchScale - Switch Arc2 V` still outputting the false/piecewise branch even while the group input value stored as `1.0`.

The old piecewise U compensation also stayed active on Arc 2:

```text
Arc 2 section_ratio_attr = 1.285713 / 1.371430
```

That belongs to the full-halo branch, not the equal-scale review branch.

### Fix

Saved backup:

```text
Codex_ParametricWeave.pre-force-arc2-equal-scale-20260518_153704.blend
```

Live `.blend` changes:

```text
PW Band - Diff.Value <- PW MatchScale - Matched Arc2 V.Value
PW U - Per Section Multiplier.input[1] = 1.0  # unlinked from PW U - Section Ratio

Arc 2 Match Arc 1 V Rate = true
Arc 2 Edge Angle Mapping = false
Match Section Slopes = false
```

### Verification

Material 1 evaluated mesh readback:

```text
Arc 1 main uv_y_span = 0.057849
Arc 2 sub  uv_y_span = 0.057849

Arc 1 sample U span = 1.195049
Arc 2 sample U span = 1.195049

Arc 1 v_around 0.0 -> uv_y 0.502507
Arc 1 v_around 0.5 -> uv_y 0.531431
Arc 1 v_around 1.0 -> uv_y 0.560356

Arc 2 v_around 0.0 -> uv_y 0.502507
Arc 2 v_around 0.5 -> uv_y 0.531431
Arc 2 v_around 1.0 -> uv_y 0.560356
```

Backend Blender tests:

```text
python3 -m unittest backend.tests.test_blender_live backend.tests.test_blender_sync
8 tests OK
```

### What was NOT done

This is a scale-review state. It intentionally prioritizes matching Arc 1 / Arc 2 visible texture scale over showing the full extra Arc 2 halo V range.

---

## Phase 10s - Center Arc 2 core and restore top/bottom halo V

**Date**: 2026-05-18 local session

### Motivation

User clarified the desired Arc 2 mapping: R2 is wider than R1, so Arc 2 must not simply reuse the whole Arc 1 V span. The Arc 1-equivalent core belongs in the center of Arc 2, and the two extra R2 widths above and below that core should sample their own Arc 2 texture rows.

### Diagnosis

The saved Phase 10r review mode had hidden the real Arc 2 piecewise path:

```text
PW Band - Diff.Value <- PW MatchScale - Matched Arc2 V.Value
Arc 2 Match Arc 1 V Rate = true
```

That made Arc 2 and Arc 1 use the same V span, but it also meant Arc 2 could not sample separate Top/Core/Bot regions.

The latent piecewise branch had also drifted during the folded-core experiments:

```text
PW Band - IsTop threshold <- PW Band - Arc2 Fold Mid
PW Band - IsBot threshold <- PW Band - Arc2 Fold Mid
```

With both masks pivoting around the midpoint, the center core region was not represented correctly once the piecewise branch became active.

### Fix

Backup created before the edit:

```text
Codex_ParametricWeave.pre-arc2-centered-core-v-20260518_163746.blend
```

Saved changes in `Codex_ParametricWeave.blend`:

```text
PW Band - Diff.Value       <- PW MatchScale - Switch Arc2 V.Output
Arc 2 Match Arc 1 V Rate   = false
Arc 2 Edge Angle Mapping   = false
Match Section Slopes       = false

PW Band - IsTop threshold  <- PW Band - Split Minus
PW Band - IsBot threshold  <- PW Band - Split Plus

Arc2 Top:  0.0 -> Split Minus   maps Arc 2 V Min -> raw Arc 1 V Min
Arc2 Core: Split Minus -> Plus  maps raw Arc 1 V Min -> raw Arc 1 V Max
Arc2 Bot:  Split Plus -> 1.0    maps raw Arc 1 V Max -> Arc 2 V Max

PW U - Per Section Multiplier.input[1] <- PW U - Section Ratio.Value
```

This keeps the Phase 3q radius split (`r1/r2 = 0.015/0.025 = 0.6`, so `Split Minus/Plus = 0.2/0.8`) and uses texture metadata only as the V destinations for the three Arc 2 sections.

### Verification

Live evaluated readback for Material 1:

```text
split_min = 0.200000
split_max = 0.800000

Arc 1 main uv_y_span = 0.057849  # padded Arc 1 review range
Arc 2 sub  uv_y_span = 0.063830  # full Arc 2 outer range

Arc 2 v_around 0.0 -> uv_y 0.500000  # Arc 2 V Min
Arc 2 v_around 0.2 -> uv_y 0.514507  # raw Arc 1 V Min
Arc 2 v_around 0.5 -> uv_y 0.531431
Arc 2 v_around 0.8 -> uv_y 0.548356  # raw Arc 1 V Max
Arc 2 v_around 1.0 -> uv_y 0.563830  # Arc 2 V Max

Arc 2 top ratio  = 1.285713
Arc 2 core ratio = 1.000000
Arc 2 bot ratio  = 1.371430
```

Viewport screenshot:

```text
runtime/self_iter_arc2_centered_core_v_viewport.png
```

Backend Blender tests:

```text
python3 -m unittest backend.tests.test_blender_live backend.tests.test_blender_sync
8 tests OK
```

### What was NOT done

No backend socket contract changed. The internal selector node names still use the old `Core/Fiber` vocabulary even though their interface sockets are Arc 1 / Arc 2.

### Lesson

Promoted to [lessons.md](lessons.md) Rule 36: when returning from matched-review mode to piecewise Arc 2, restore both the section masks and the V destination links; otherwise the core can disappear even if the final V source is reconnected.

---

## Phase 10u — Scale U denominator test

**Date**: 2026-05-19

### Motivation

The user observed that direct web-to-Blender material pushes looked slightly squashed along U. Manually lowering root `Texture Scale U` (`ParametricWeave.modifiers["Weave"]["Socket_97"]`) to roughly `0.5..0.6` made the material look closer to the reference, but root Scale U is only a visual test knob and should return to `1.0`.

### Hypothesis

The current automatic per-material Scale U formula divides the padded visible V span by `ARC1_V_AROUND_SPAN = 0.6`:

```text
Material N Texture Scale U = padded_visible_v_span / 0.6
```

That `0.6` is the Arc 1 / Arc 2 radius-owned core fraction. It may be too aggressive for the current projected/reference-image judgement. The manual root Scale U value around `0.6` effectively cancels that denominator:

```text
(padded_visible_v_span / 0.6) * 0.6 = padded_visible_v_span
```

So this experiment keeps root Scale U at `1.0` and changes only the backend auto denominator to `1.0`:

```text
Material N Texture Scale U = padded_visible_v_span / 1.0
```

### Backup

Before code or .blend edits:

```text
Codex_ParametricWeave.pre-scale-u-denominator-test-20260519_004510.blend
```

### Fix Applied

- Add a separate backend constant for the auto U denominator so the old geometry constant (`ARC1_V_AROUND_SPAN = 0.6`) remains documented as radius/split provenance.
- Change only the automatic `texture_scale_u_is_auto` path from `/ 0.6` to `/ 1.0`.
- Keep `U Stride Per Warp End / Weft Pick` derived from the same final material scale, so spool continuity remains internally consistent.
- Reset saved root `Texture Scale U` (`Socket_97`) to `1.0` so the manual visual-compensation knob is neutral during the test.

Touched files:

```text
backend/app/blender_live.py
backend/tests/test_blender_live.py
Codex_ParametricWeave.blend
```

### Verification

Backend tests:

```text
python3 -m unittest discover backend/tests
40 tests OK
```

Blender readback:

```text
Socket_44  = 0
Socket_87  = 1
Socket_88  = 0
Socket_97  = 1
Socket_244 = 0.00800000037997961
```

Formula smoke test using a recent yarn metadata sample:

```text
AUTO_TEXTURE_SCALE_U_DENOMINATOR = 1.0
texture_scale_u_fallback = 0.03384912959381048
```

### What was NOT done

No Blender node graph topology is changed in this experiment. If the visual still looks wrong, the next suspect is not the denominator but the V-side padding/projection model itself.

---

## Phase 4 — (next) candidate follow-ups

## Phase 10t - Free-flow Arc 2 halo V from core rate

**Date**: 2026-05-18 local session

### Motivation

User clarified that the `0.0 -> Split Minus`, `Split Minus -> Split Plus`, `Split Plus -> 1.0` geometry split is correct, but the outer Arc 2 top/bottom texture should not be forced to snap to the outer texture edge. The desired behavior is for texture rows to flow outward from the core seam at a natural scale.

### Fix

Backup created before the edit:

```text
Codex_ParametricWeave.pre-arc2-free-halo-v-flow-20260518_170029.blend
```

Saved changes in `Codex_ParametricWeave.blend`:

```text
top_outer_v = raw Arc 1 V Min - core_v_slope * Split Minus
bot_outer_v = raw Arc 1 V Max + core_v_slope * (1 - Split Plus)

Arc2 Top:  top_outer_v -> raw Arc 1 V Min
Arc2 Core: raw Arc 1 V Min -> raw Arc 1 V Max
Arc2 Bot:  raw Arc 1 V Max -> bot_outer_v
```

Since all three sections now use the same V rate, `PW U - Section Ratio` evaluates to `1.0` throughout Arc 1 and Arc 2 and is linked back into `PW U - Per Section Multiplier`.

### Verification

Live evaluated readback for Material 1:

```text
split_min = 0.200000
split_max = 0.800000

Arc 1 main uv_y_span = 0.057849
Arc 2 sub  uv_y_span = 0.056415

Arc 2 v_around 0.0 -> uv_y 0.503224
Arc 2 v_around 0.2 -> uv_y 0.514507
Arc 2 v_around 0.5 -> uv_y 0.531431
Arc 2 v_around 0.8 -> uv_y 0.548356
Arc 2 v_around 1.0 -> uv_y 0.559639

Arc 1 ratio = 1.0
Arc 2 ratio = 1.0 in Top/Core/Bot
```

Viewport screenshot:

```text
runtime/self_iter_arc2_free_halo_v_flow_viewport.png
```

Backend Blender tests:

```text
python3 -m unittest backend.tests.test_blender_live backend.tests.test_blender_sync
8 tests OK
```

### Lesson

Promoted to [lessons.md](lessons.md) Rule 37: if the halo should read as free-flowing texture, extrapolate from the core seam using the core V rate instead of endpoint-fitting the halo to `Arc 2 V Min/Max`.

---

## Checkpoint 2026-05-19 - Approved visual baseline

**Date**: 2026-05-19 local session

### Motivation

The user visually approved the current direct web-to-Blender material result and asked to make it a checkpoint before moving into any new experiments.

### Frozen state

The checkpoint is recorded in [../CHECKPOINT_2026-05-19.md](../CHECKPOINT_2026-05-19.md).

```text
Spacing                 Socket_6   = 0.026
Texture Offset V        Socket_44  = 0
Sub Texture Scale V     Socket_87  = 1
Sub Texture Offset V    Socket_88  = 0
Texture Scale U         Socket_97  = 1
Arc 1 V Padding         Socket_244 = 0.008
AUTO_TEXTURE_SCALE_U_DENOMINATOR   = 1.0
```

### Verification

Blender readback confirmed the socket values above. Backend tests passed with:

```text
python3 -m unittest discover backend/tests
40 tests OK
```

Frontend unit tests passed after the UI default update:

```text
npm run test:unit
```

### Notes

`Codex_ParametricWeave.pre-scale-u-denominator-test-20260519_004510.blend` is the rollback snapshot for the Scale U denominator experiment. Any future Arc 2, padding, or U-scale work should create a new snapshot and state whether it supersedes this checkpoint.

---

## Phase 4 — (next) candidate follow-ups

- **Protect the 2026-05-19 visual checkpoint** before new Arc 2 / padding / U-scale work. Start from a new `.blend` backup and record whether the result replaces or branches from the approved baseline.
- **Decide between high-res inspection mode and alpha boost.** Phase 3r switched the current live material to full-res files for visual comparison, but the code still defaults to Cycles-safe textures.
- **Visually approve Phase 4a's UDIM material** in the live viewport, then run a crop render to confirm Cycles samples all three tiles correctly.
- **Run a V-Ray duplicate-file proof** with V-Ray GPU out-of-core textures enabled and original albedo/alpha maps.
- **Rename internal switch chain nodes** (`PW Material Core V Min Select N` → `PW Material Arc 1 V Min Select N`, etc.) for visual consistency with the renamed interface sockets. Cosmetic only — purely an artist QoL.
- **Separate warp/weft U correction** if non-square targets or asymmetric thread counts become important. Phase 5 already pushes per-axis `U Stride Per Warp End / Weft Pick`, but the per-material U *scale* is still one value across both axes — non-square swatches with mixed yarns might want axis-specific scales too.
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
