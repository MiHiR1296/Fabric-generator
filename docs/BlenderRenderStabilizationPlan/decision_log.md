# Decision Log

## Keep: Live Blender MCP As Current Truth

Decision:

Use live Blender readback on port `9876` as the source of truth for graph and
material state.

Reason:

The saved docs disagree with the live material path. The `.blend` is also
already modified relative to Git. Readback prevents us from implementing
against a ghost version of the graph.

## Keep: Arc 2 Free-Flow Halo V Setup

Decision:

Keep these values and graph semantics:

```text
Texture Scale V     = 1.0
Sub Texture Scale V = 1.0
Texture Offset V    = 0.0
Sub Texture Offset V = 0.0
Arc 2 free-flow halo path active
```

Reason:

The user visually rejected attempts to narrow Arc 2 by setting
`Sub Texture Scale V = 0.0`, changing the final combiner semantics, or
endpoint-fitting Arc 2 to the metadata silhouette. The approved Arc 2 behavior
must continue to sample halo as part of the same yarn.

## Keep: Deterministic Same-Strand Arc 2 U

Decision:

Keep Arc 2 using the deterministic same-yarn U stream through
`PW UV U Add.Value`.

Reason:

The nearest-surface U transfer caused measured endpoint shrink and tiny/zero
U steps. Independent own-U made Arc 2 look like a separate noisy texture layer.
The deterministic path preserves same-yarn continuity without the transfer
artifacts.

## Remove/Do Not Restore: Nearest-Surface Arc 2 U Transfer

Decision:

Do not reconnect `PW StrandXferU - Sample Same-Strand Arc1 U`.

Reason:

It is muted in live Blender and labeled as unused because it caused endpoint
shrink. Restoring it would reintroduce the exact bug Phase 1.6 removed.

## Reject: Arc 2 Own-U Bypass

Decision:

Do not ship Arc 2 independent U.

Reason:

The user rejected the look. Arc 2 is the halo surface of the same yarn, not a
separate yarn stream.

## Reject: `Sub Texture Scale V = 0.0`

Decision:

Do not set `Sub Texture Scale V` to zero as a production fix.

Reason:

It was only a diagnostic narrowing of Arc 2 sampling. It makes the control
semantics misleading and degrades the approved halo behavior.

## Reject: Exact Metadata Endpoint Fit For Arc 2

Decision:

Do not endpoint-fit Arc 2 final sampling to Material N Arc 2 V Min/Max as the
production behavior.

```text
PW Band - Arc2 Top.To Min <- Material N Arc 2 V Min
PW Band - Arc2 Bot.To Max <- Material N Arc 2 V Max
```

Reason:

The live A/B made the numbers match exactly, but the user rejected the visual
result because it damaged Arc 2 look and feel. Metadata Arc 2 bounds are useful
diagnostics, not the current target for final Arc 2 UV sampling.

## Reject: Absolute Sub-Scale Formula For Current Arc 2 Look

Decision:

Do not replace the V combiner with:

```text
Texture Scale V + is_sub * (Sub Texture Scale V - Texture Scale V)
```

Reason:

That path was paired with endpoint-fit sampling in the rejected numeric fix and
changed the Arc 2 character. Keep the live additive combiner until a visual
replacement is proven with crop renders, not only mesh-range readback.

## Implement: Direct RGBA Alpha, Remap Opt-In

Decision:

Use the diffuse/RGBA texture node's alpha output directly by default for RGBA
preview materials. Keep the mild alpha cleanup as an opt-in path via
`WEAVE_ALPHA_REMAP_ENABLED=1`.

Reason:

The 2026-06-05 live Blender material review looked closer to the expected yarn
when the material used the embedded alpha channel from the diffuse/RGBA scan,
without a Map Range boost or separate RGBA alpha image. The remap remains useful
for A/B diagnostics and difficult yarns, but it should not be the generated
default.

## Implement: Metadata-Only Root U Pin

Decision:

Pin root `Texture Scale U = 1.0` in `backend/app/blender_live.py`.

Reason:

Full project setup already cleans this value. Metadata-only setup should not
leave a stale manual root U value behind.

## Defer: `Profile V Steps`

Decision:

Do not add this socket in the same pass as backend material cleanup.

Reason:

It mutates the `.blend` and requires Count/Offset graph work plus visual
performance validation. It belongs in a separate Blender graph phase.

## Defer: `Texture World Width BU`

Decision:

Do not add this socket in the same pass as backend material cleanup.

Reason:

The old divide path is mathematically equivalent and still active. The direct
socket is a cleanup that needs `.blend`, backend, and contract updates together.
