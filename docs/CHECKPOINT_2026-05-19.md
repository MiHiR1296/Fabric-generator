# Checkpoint - 2026-05-19 Visual Baseline

This checkpoint captures the current application state after manual visual approval of the direct web-to-Blender material test. The setup is considered a good baseline for the next round of work.

## Status

- Visual result: approved in the current test session.
- Canonical Blender file: `Codex_ParametricWeave.blend`.
- Rollback snapshot before the Scale U denominator experiment: `Codex_ParametricWeave.pre-scale-u-denominator-test-20260519_004510.blend`.
- Rollback snapshot before the Spacing default change: `Codex_ParametricWeave.pre-spacing-default-20260519_030050.blend`.
- Backend live mode was restarted after the driver/socket changes and responded healthy on `http://127.0.0.1:8000`.

## Frozen Blender Defaults

Object: `bpy.data.objects["ParametricWeave"]`
Modifier: `modifiers["Weave"]`

| Socket identifier | UI name | Checkpoint value |
|---|---|---:|
| `Socket_6` | Spacing | `0.026` |
| `Socket_44` | Texture Offset V | `0` |
| `Socket_87` | Sub Texture Scale V | `1` |
| `Socket_88` | Sub Texture Offset V | `0` |
| `Socket_97` | Texture Scale U (root test knob) | `1` |
| `Socket_244` | Arc 1 V Padding | `0.008` |

`Texture Scale U` stays neutral. It is only a temporary visual test knob; per-material U correction belongs on `Material N Texture Scale U`.

## Active U-Scale Contract

The backend now treats the old `0.6` denominator as geometry provenance, not the active auto-scale denominator.

```text
ARC1_V_AROUND_SPAN = 0.6
AUTO_TEXTURE_SCALE_U_DENOMINATOR = 1.0

arc1_v_min_padded        = max(core_v_min - Arc 1 V Padding, fiber_bot_v_min)
arc1_v_max_padded        = min(core_v_max + Arc 1 V Padding, fiber_top_v_max)
visible_v_span           = arc1_v_max_padded - arc1_v_min_padded
Material N Texture Scale U = visible_v_span / AUTO_TEXTURE_SCALE_U_DENOMINATOR
```

The `0.6` value still explains the Arc 1 / Arc 2 radius-owned core split (`0.015 / 0.025`). It should not be used as the automatic `Material N Texture Scale U` denominator for this checkpoint.

## Pinned Footgun Values

These are asserted defensively by the backend and should match the saved `.blend` baseline for scan-driven yarns:

| Socket | Value |
|---|---:|
| Sub Strand Enable | `True` |
| Texture Scale V | `1` |
| Texture Offset V | `0` |
| Texture Side Flatten | `0` |
| Sub Texture Scale V | `1` |
| Sub Texture Offset V | `0` |

The previous non-zero `Texture Offset V = 0.031914920` was part of a checker/material phase-alignment experiment. The approved checkpoint returns Offset V to neutral `0`.

## Code Defaults

- `backend/app/blender_sync.py`: `DEFAULT_ARC1_V_PADDING = 0.008`; setup forces Texture Offset V `0`, Sub Texture Scale V `1`, and Sub Texture Offset V `0`.
- `backend/app/blender_sync.py`: `DEFAULT_SPACING = 0.026`; Web UI spacing `0` maps to physical Blender `Spacing = 0.026`.
- `backend/app/blender_live.py`: `PINNED_FOOTGUN_SOCKETS` matches the pinned values above; `AUTO_TEXTURE_SCALE_U_DENOMINATOR = 1.0`.
- `frontend/src/domain/draft.ts`: `DEFAULT_ARC1_V_PADDING = 0.008`.

## Verification

- Blender socket readback confirmed the frozen defaults above.
- Backend unit suite passed: `python3 -m unittest discover backend/tests` (`40` tests).
- Frontend unit suite passed after the UI default update: `npm run test:unit`.

## Revert Point

To compare against the pre-test state, restore the snapshot:

```text
Codex_ParametricWeave.pre-scale-u-denominator-test-20260519_004510.blend
```

Then reset the backend denominator to the previous visible-span formula only for comparison:

```text
Material N Texture Scale U = visible_v_span / 0.6
```
