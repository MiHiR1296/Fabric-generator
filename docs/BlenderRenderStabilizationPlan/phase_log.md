# Phase Log

This file is append-only. Each phase should say what changed, why, how it was
verified, and what was intentionally not done.

## Phase 0 - Live Blender Truth Capture

Date: 2026-06-05

### Motivation

The HTML guide and older docs identified the right problem areas but disagreed
with current code and the live `.blend`. The user clarified that live Blender
is the only source of truth.

### Symptom

Historical docs claimed alpha remap existed in generated materials, while live
Blender and `backend/app/render_jobs.py` showed direct alpha.

### Diagnosis

MCP readback confirmed:

```text
ParametricWeave > Weave > Parametric Weave knotty
Texture Scale U = 1.0
Sub Texture Scale V = 1.0
Arc 2 deterministic same-strand U active
nearest-surface Arc 2 U node muted
FabricStudioAlphaRemap absent
PBR nodes present
Texture World Width BU absent
Profile V Steps absent
```

### Fix

Created this documentation folder and made [current_state.md](current_state.md)
the current stabilization source of truth.

### Verification

`blender_status` succeeded on `127.0.0.1:9876`, and focused MCP readback
returned the socket/material state above.

### What Was Not Done

No `.blend` mutation was made in Phase 0.

### Lesson

Do not rely on historical phase logs for active graph details when Blender is
open and reachable. Read the live session first.

## Phase 1 - Generated Alpha Remap

Date: 2026-06-05

### Motivation

Low-alpha yarn haze was reaching Principled alpha directly and could flatten
fiber/twist contrast.

### Symptom

Live active material:

```text
FabricStudioAlphaNode.Alpha -> Principled BSDF.Alpha
```

### Diagnosis

`ensure_texture_preview_material(...)` linked `alpha_output` straight to
`shader.inputs['Alpha']`. The unit tests explicitly asserted that
`FabricStudioAlphaRemap` was absent, proving the docs and implementation had
drifted.

### Fix

Added generated material helper `link_alpha_to_shader(...)` in
`backend/app/render_jobs.py` with defaults:

```text
WEAVE_ALPHA_REMAP_ENABLED = true
WEAVE_ALPHA_REMAP_LOW = 0.10
WEAVE_ALPHA_REMAP_HIGH = 0.78
WEAVE_ALPHA_CURVE_GAMMA = 1.0
```

Default path now generates `FabricStudioAlphaRemap`; `FabricStudioAlphaCurve`
is generated only when gamma differs from `1.0`.

### Verification

Unit coverage in `backend/tests/test_render_jobs.py` checks default constants,
scalar Map Range mode, and env override generation.

The saved project payload `runtime/projects/578a28cba9aa.json` was pushed to
live Blender through the same generated setup path used by
`/api/blender/push-project-bandmeta`, with `render_still=False`.

Live readback after refresh:

```text
FabricStudioAlphaRemap present = true
FabricStudioAlphaCurve present = false
FabricStudioAlphaNode.Alpha -> FabricStudioAlphaRemap.Value
FabricStudioAlphaRemap.Result -> Principled BSDF.Alpha
FabricStudioAlphaRemap.data_type = FLOAT
From Min = 0.10000000149011612
From Max = 0.7799999713897705
To Min = 0.0
To Max = 1.0
```

### What Was Not Done

No still render was fired. The setup script intentionally used
`render_still=False`.

### Lesson

Material cleanup belongs in the generated setup script, not as a one-off live
node edit, so headless and live preview paths cannot drift.

## Phase 2 - Metadata-Only Root U Pin

Date: 2026-06-05

### Motivation

Metadata-only pushes should clean up dangerous root texture state just like
full project setup does.

### Symptom

Earlier diagnostics showed `/api/blender/push-bandmeta` could leave root
`Texture Scale U` at a stale manual value.

### Diagnosis

`backend/app/blender_live.py` pinned the V footgun sockets but did not pin
root `Texture Scale U`.

### Fix

Added:

```python
("Texture Scale U", 1.0)
```

to `PINNED_FOOTGUN_SOCKETS`.

### Verification

Unit coverage in `backend/tests/test_blender_live.py` checks the pin is
present.

### What Was Not Done

No `.blend` socket or node graph change was made.

### Lesson

Metadata-only sync is still a Blender state mutation. It must pin the same
safe global texture defaults that artists expect from full setup.

## Phase 3 - Arc 2 V Sampling Diagnostic

Date: 2026-06-05

### Motivation

The user asked whether there was a U-scale mismatch and what was happening to
the fibers on Arc 2. Live U readback was clean, so the next suspect was Arc 2
V sampling against the source alpha/fiber rows.

### Symptom

Arc 2 looked visually vulnerable to haze even after U was corrected. The live
graph was sampling a wider final V range than the metadata Arc 2 silhouette.

### Diagnosis

Created:

```text
runtime/arc2_v_sampling_diagnostics/20260605_122921/blender_v_sampling.json
runtime/arc2_v_sampling_diagnostics/20260605_122921/alpha_v_sampling_report.json
runtime/arc2_v_sampling_diagnostics/20260605_122921/alpha_v_sampling_profile.png
runtime/arc2_v_sampling_diagnostics/20260605_122921/sub_texture_scale_v_ab.json
```

Live evaluated mesh:

```text
Arc 1 final V span = 0.46316969..0.53847778  span 0.07530808
Arc 2 final V span = 0.40280062..0.60049427  span 0.19769365

Arc 2 top halo    = 0.40280062..0.43574959
Arc 2 core overlap = 0.44233936..0.56095552
Arc 2 bottom halo = 0.56754529..0.60049427
```

Against the source alpha profile for `greyrescan02`:

```text
Arc 2 evaluated samples put about 45.2% of vertex weight outside the metadata
Arc 2 silhouette band.

Top/bottom evaluated halo rows have very low mean alpha:
  top mean alpha    = 0.0531
  bottom mean alpha = 0.0458

Arc 2 core overlap carries stronger alpha:
  weighted p90 alpha = 0.7011
```

The forced live A/B showed the final sub-strand V scale is the main widening
stage:

```text
Current Sub Texture Scale V = 1.0
  Arc 2 final V = 0.40280062..0.60049427  span 0.19769365

Temporary Sub Texture Scale V = 0.0
  Arc 2 final V = 0.45140031..0.55024713  span 0.09884682

Restored Sub Texture Scale V = 1.0
```

### Fix

No production graph fix was applied. The live socket was restored to
`Sub Texture Scale V = 1.0` after the A/B.

### Verification

MCP readback confirmed the restored value and the alpha/material setup remained
active. The diagnostic image was visually inspected.

### What Was Not Done

Did not save a `.blend` change and did not ship `Sub Texture Scale V = 0.0`.
That path is useful evidence but has prior visual rejection history. The next
safe implementation should be an explicit Arc 2 V sampling mode or socket, not
an invisible change to the approved baseline.

### Lesson

When comparing metadata V bands to evaluated `uv_scaled.y`, account for the
final texture V scale stage. The Arc 2 overreach is not U drift; it is final V
scaling plus the free-flow halo model sampling rows with very low mean alpha.

## Phase 4 - Rejected Arc 2 Metadata Endpoint-Fit A/B

Date: 2026-06-05

### Motivation

The user asked how to fix the live mismatch:

```text
Current Arc 2 final V = 0.40280062..0.60049427
Metadata Arc 2 silhouette = 0.44645798..0.55518943
```

### Symptom

The live graph used two widening mechanisms together:

```text
Arc 2 pre-final free-flow V = 0.45140031..0.55024713
effective_v_scale = Texture Scale V + is_sub * Sub Texture Scale V
Texture Scale V = 1.0
Sub Texture Scale V = 1.0
Arc 2 effective scale = 2.0
```

That doubled Arc 2 around `0.5`, producing the measured final range
`0.40280062..0.60049427`.

### Diagnosis

Setting `Sub Texture Scale V = 0.0` was only a diagnostic narrowing. It would
land Arc 2 at `0.45140031..0.55024713`, which is close but still not the
metadata silhouette. It also revives a socket state with prior visual rejection
history.

To hit the metadata exactly while keeping `Sub Texture Scale V = 1.0`, the
graph needed both:

```text
1. Arc 2 outer endpoints from Material N Arc 2 V Min/Max.
2. Absolute sub-scale semantics instead of additive sub-scale semantics.
```

### Attempted Fix

Added `_pw_enforce_arc2_v_sampling_contract(...)` to
`backend/app/blender_live.py`. The helper runs inside Blender from the shared
metadata apply script used by both live MCP pushes and headless render setup.

It rewires:

```text
PW Band - Arc2 Top.To Min <- PW Select Active Material - Arc 2 V Min
PW Band - Arc2 Bot.To Max <- PW Select Active Material - Arc 2 V Max
```

It also creates/reuses:

```text
PW V Scale - Sub Minus Root = Sub Texture Scale V - Texture Scale V
```

and changes the final scale node to:

```text
effective = Texture Scale V + is_sub * (Sub Texture Scale V - Texture Scale V)
```

The pinned sockets remain:

```text
Texture Scale V = 1.0
Sub Texture Scale V = 1.0
Texture Offset V = 0.0
Sub Texture Offset V = 0.0
```

### Numeric Verification

Unit coverage in `backend/tests/test_blender_live.py` checks that the generated
Blender apply body contains the Arc 2 V contract.

The live Blender session accepted the generated apply path:

```text
arc2_v_contract = metadata_endpoint_fit_absolute_sub_scale
changed_links = 6
```

MCP readback confirmed the active links:

```text
PW Band - Arc2 Top.To Min <- PW Select Active Material - Arc 2 V Min
PW Band - Arc2 Bot.To Max <- PW Select Active Material - Arc 2 V Max
Math.015 input 0 <- Named Attribute.002.Attribute
Math.015 input 1 <- PW V Scale - Sub Minus Root.Value
Math.015 input 2 <- PW Input - Texture UV Output.Texture Scale V
```

Live evaluated mesh `uv_scaled.y` after the patch:

```text
Arc 1 = 0.4631696939468384..0.5384777784347534
Arc 2 = 0.44645798206329346..0.5551894307136536
```

Arc 2 now matches the Material 1 Arc 2 metadata silhouette exactly.

### Visual Review Result

Rejected. The user reported that this messed up the Arc 2 look and feel and
pressed Cmd+Z in Blender.

### Rollback

Removed `_pw_enforce_arc2_v_sampling_contract(...)` from
`backend/app/blender_live.py` and removed the unit test that expected that
contract. Future metadata pushes no longer reapply the rejected graph change.

Live Blender readback after Cmd+Z:

```text
PW Band - Arc2 Top.To Min <- PW HaloFlow - Top Outer Free V
PW Band - Arc2 Bot.To Max <- PW HaloFlow - Bot Outer Free V
Math.015 input 1 <- PW Input - Texture UV Output.Sub Texture Scale V
Math.015 input 2 <- PW Input - Texture UV Output.Texture Scale V
Math.015 label = Scale V + Sub*is_sub
PW V Scale - Sub Minus Root exists = false
```

Live evaluated mesh `uv_scaled.y` after rollback:

```text
Arc 1 = 0.4631696939468384..0.5384777784347534
Arc 2 = 0.40280061960220337..0.6004942655563354
```

### What Was Not Done

No `.blend` save was performed. The open Blender scene is dirty because the
live node graph was patched for verification and then undone.

No beauty crop was accepted from the endpoint-fit path. It is numerically
correct but visually rejected.

### Lesson

Do not treat exact metadata range matching as sufficient for Arc 2. The
free-flow halo path is part of the intended visual character. Future fixes
should preserve that look and target low-alpha haze/material cleanup with
crop renders, not collapse Arc 2 to the measured silhouette by graph rewiring.

## Phase 5 - Direct RGBA Alpha And Arc 1 Padding Update

### Trigger

The user manually adjusted the live Blender material and reported that the best
current readback uses the diffuse texture's embedded alpha channel directly,
without the generated alpha texture and without the Map Range boost. The same
inspection set `Arc 1 V Padding` to `0.02`.

### Live Readback

```text
Arc 1 V Padding = 0.019999999552965164
Active material alpha link:
  FabricStudioDiffuseNode.Alpha -> Principled BSDF.Alpha
FabricStudioAlphaRemap:
  stale/orphan only, not linked to shader alpha
```

### Code Update

Generated RGBA preview materials now use one RGBA image node:

```text
FabricStudioDiffuseNode.Color -> Principled BSDF.Base Color
FabricStudioDiffuseNode.Alpha -> Principled BSDF.Alpha
```

Split diffuse/alpha assets still keep `FabricStudioAlphaNode` as their fallback
path. `WEAVE_ALPHA_REMAP_ENABLED=1` remains available for explicit A/B testing.

`Arc 1 V Padding` now defaults to `0.02` in backend and frontend render settings.

### Verification

```text
python3 -m py_compile backend/app/render_jobs.py backend/app/blender_sync.py
python3 -m unittest backend.tests.test_render_jobs backend.tests.test_blender_sync

31 tests passed.
```

### Lesson

When the source asset is RGBA, the Blender material contract should preserve the
single-source image relationship: color and alpha come from the same sampled
texture unless a specific opt-in diagnostic says otherwise.
