# WebUIChanges

Everything we changed in the **web UI** (React + FastAPI surface area that backs it) that doesn't belong in [putting-it-together/](../putting-it-together/) (the three-app integration story) or [BlenderFixes/](../BlenderFixes/) (the .blend itself).

This folder is the record of UX-visible behavior fixes, sync issues between the wizard's four steps, dropdown/list staleness, and any other "the page shows the wrong thing" class of bug. Per-phase entries follow the same Symptom / Diagnosis / Fix / Verification template the sister folders use.

---

## Why this exists

The wizard has four steps that share state through three layers: the shared `yarn_library/` folder on disk (yarnseamless's output), the studio backend's runtime `YarnAsset` records (one per imported library yarn), and the frontend's `colorBindings` (one per warp/weft palette color). When any of those three layers gets out of sync with another, the UI shows stale data — a yarn appears in Step 2's dropdowns even though it was deleted in Step 1, or a binding row still points at an asset that no longer exists.

The integration docs ([putting-it-together/](../putting-it-together/)) cover the data contract between the producer and consumer. The Blender docs ([BlenderFixes/](../BlenderFixes/)) cover what `Codex_ParametricWeave.blend` exposes. **This folder is the gap between them**: the React state machine + the backend endpoints that translate user clicks into changes across all three layers.

---

## Documentation index

Read in this order:

| # | doc | what it covers |
|---|---|---|
| 1 | [architecture.md](architecture.md) | The three state layers (library / runtime assets / color bindings), where each lives, and the sync points between them. **Read first.** |
| 2 | [phase_log.md](phase_log.md) | Every web-UI fix in chronological order — Symptom / Diagnosis / Fix / Verification. Append-only. |
| 3 | [lessons.md](lessons.md) | Rules earned the hard way about cross-layer state in the wizard. |

---

## Current state (2026-05-15)

- **Phase W1 — library delete cascades to runtime assets + color bindings**: ✓ done. Deleting from the Step 1 library strip now removes the matching `YarnAsset` records (anything whose `bandMeta.library_yarn_id` matches the deleted id) and clears any `colorBindings` that pointed at them. Pattern Builder no longer shows orphaned yarns in its dropdowns.
- **Phase W2 — boot-time reconcile sweeps pre-existing L2 orphans**: ✓ done. `load_yarn_assets()` now calls `reconcile_orphan_imports()` after populating the cache, so any imported runtime asset whose source library yarn no longer exists is removed on backend boot. Catches deletes that happened before Phase W1 shipped or that bypass the API entirely (Finder delete, manual `rm`).

## What's remaining

- **Live cross-tab sync**: if two browser tabs are open on the same backend, deleting in one doesn't update the other until the next 3-second poll on Step 1 or a manual refresh elsewhere. Could be a small WebSocket push, but no user has hit it yet.
- **Undo for library delete**: today's deletion is destructive (removes files from `yarn_library/<id>/` plus the index entry). A short-lived undo would need a tombstone + restore path; out of scope for now.

## How to update these docs

Same rules as the sister folders:

- **Touched a sync point between library / runtime assets / color bindings?** Add a Phase entry to [phase_log.md](phase_log.md) using the Symptom/Diagnosis/Fix/Verification template, and update [architecture.md](architecture.md) if a new sync point was introduced.
- **Earned a lesson about web-UI state?** Add it to [lessons.md](lessons.md). Lead with **Rule**, then **Why**, then **How to apply** with file/line references.
- **Write the entry the same hour you make the change.** Drift starts the moment you don't.
