# Phase log — Web UI

> **Read this if**: you want to understand what we changed in the wizard / FastAPI surface, in what order, and why each change happened. Every non-trivial UI-visible behavior change goes here as **Symptom / Diagnosis / Fix / Verification**. Follow the same template when adding a new phase.

> Each phase is a contiguous unit of work. Numbered W1, W2, … to keep them distinct from the integration `Phase N` and Blender `Phase 3*` numbering. Append, do not edit history.

---

## Phase W1 — Library delete now cascades to runtime assets and color bindings

**Date**: 2026-05-15

### Motivation

User report: in the Pattern Builder (Step 2), the warp/weft → yarn dropdowns still listed yarns that had been deleted from the Yarn Library (Step 1). Expected behavior: deleting a yarn from the library should remove it from every place it appears in the wizard.

### Symptom

1. Open Step 1, save a yarn to library via the MultiFragmentEditor "+ Save to Library" flow (or rely on the auto-import to bring an existing library yarn into the project).
2. Click the 🗑 button on the library card to delete it.
3. Library strip updates correctly — the card disappears.
4. Navigate to Step 2 (Pattern Builder). Open any color → yarn `<select>`. **The deleted yarn is still listed as an option.**
5. If the user had already assigned the deleted yarn to any palette color, the binding row still claims that yarn is selected and the Render Preview will (try to) use it.

### Diagnosis

The wizard has three state layers (see [architecture.md](architecture.md)):

- **L1 — Library**: `yarn_library/<id>/` on disk, listed by `/api/yarn/library`.
- **L2 — Runtime asset**: `runtime/yarn_assets/<asset_id>/`, listed by `/api/yarn/assets`. Each imported asset carries `bandMeta.library_yarn_id` back-referencing its L1 source.
- **L3 — Color binding**: in-memory React state in [App.tsx](../../frontend/src/App.tsx); `yarnAssetId` is a foreign key into L2.

`delete_library_yarn` in [backend/app/yarn_assets.py](../../backend/app/yarn_assets.py) only removed L1 (the library folder + `index.json` entry). The matching L2 asset, copied during the original import, was untouched. The frontend `onDeleteFromLibrary` handler in [App.tsx](../../frontend/src/App.tsx) called `refreshLibrary` only — never `refreshAssets`, never cleared L3 bindings.

Pattern Builder reads L2 (filtered to `status === 'ready'`) for its dropdown options. Library deletion didn't touch L2, so the dropdown still saw the imported copy. The user's mental model — "the library is the source of truth, delete from there and everything follows" — didn't match the implementation, where L1, L2, L3 were independent stores.

### Fix

Cascade the delete across all three layers. The library id is the join key (L2 → L1 via `bandMeta.library_yarn_id`; L3 → L2 via `yarnAssetId`).

**Backend** ([backend/app/yarn_assets.py](../../backend/app/yarn_assets.py) `delete_library_yarn`):
```python
load_yarn_assets()
with _LOCK:
    cascade_ids = [
        asset.id
        for asset in _ASSETS.values()
        if (asset.bandMeta or {}).get("library_yarn_id") == yarn_id
    ]
for asset_id in cascade_ids:
    try:
        delete_yarn_asset(asset_id)
    except FileNotFoundError:
        pass
return {"id": yarn_id, "removed": ..., "removedAssetIds": cascade_ids}
```

The cascade is collected before iterating `delete_yarn_asset` because that helper takes the lock itself. We tolerate `FileNotFoundError` mid-cascade (race window if two delete calls overlap) — idempotent end-state is what matters.

**Frontend API** ([frontend/src/utils/parserApi.ts](../../frontend/src/utils/parserApi.ts) `deleteLibraryYarn`):
- Return type now includes `removedAssetIds: string[]` so the UI knows which L3 bindings to clear.

**Frontend handler** ([frontend/src/App.tsx](../../frontend/src/App.tsx) `onDeleteFromLibrary`):
- Read `result.removedAssetIds`, build a `Set`, map over `colorBindings` and null out any `yarnAssetId` in the set.
- Update the toast message to mention the cascade count when non-zero.
- Call `refreshLibrary()` AND `refreshAssets()` in parallel so both the strip and the in-memory L2 snapshot reflect the deletion immediately (no waiting for the 3-second Step-1 poll).

### Verification

1. Save a yarn to library via MFE (auto-import advances the wizard to Step 2 with that yarn pre-bound to every palette color).
2. Navigate back to Step 1, click 🗑 on the library card, confirm.
3. Toast reads "Removed \"<id>\" from the yarn library and 1 imported project asset." (cascade count > 0 path).
4. Navigate to Step 2: deleted yarn no longer appears in any color → yarn `<select>` ✓. Previously-bound slots show "Select processed yarn" ✓.
5. `curl /api/yarn/library` no longer lists the id ✓. `curl /api/yarn/assets` no longer lists any asset whose `bandMeta.library_yarn_id` matched ✓.
6. Repeat the delete (idempotent path) — backend returns `{removed: false, removedAssetIds: []}`, no error ✓.

### Lesson

Promoted to [lessons.md](lessons.md) as **Rule W1** — every cross-layer mutation needs to cascade to every downstream layer, and the API response must surface enough info for the UI to clean its in-memory state without a second round trip.

### What was NOT done in this phase

- **Asset-only delete** (legacy upload flow) still leaves orphan bindings — same class of bug, smaller blast radius (the dropdown shows empty, no stale data is rendered). Tracked in [architecture.md](architecture.md) Sync point 2 as a known gap.
- **Cross-tab sync**: a second browser tab on the same backend won't see the cascade until its next 3 s Step-1 poll or a manual page refresh. WebSocket push deferred — no user has hit this yet.

---

## Phase W2 — Sweep pre-existing L2 orphans on backend boot

**Date**: 2026-05-15

### Motivation

Right after shipping Phase W1, user reported "the library is still showing deleted stuff" — the cascade clearly was not the whole story.

### Symptom

Live disk inventory:
- L1 library: 2 entries (`20260515_125650_6b7cd4` Horizon, `20260515_130552_97b696` Vegeta) in `index.json`, two matching folders.
- L2 runtime: **12** asset folders in `runtime/yarn_assets/`, **9 of which** carried `bandMeta.library_yarn_id` values that no longer existed in L1.

Pattern Builder dropdown still listed 12 yarns; user expected 2 (or 3 — Horizon was imported twice).

### Diagnosis

Phase W1's cascade only fires when the user clicks 🗑 on a Step 1 library card AFTER the fix shipped. It did nothing about:

1. Deletes that happened before Phase W1 (the 9 orphans).
2. Future deletes that bypass the API — e.g., the user removes a folder from `yarn_library/` via Finder, or wipes the library directly outside the backend.

In both cases, L2 keeps assets that point at L1 ids that don't exist anymore. Pattern Builder reads L2 directly, so it shows the ghosts.

### Fix

Add a reconcile pass in [backend/app/yarn_assets.py](../../backend/app/yarn_assets.py) `reconcile_orphan_imports()`:

```python
def reconcile_orphan_imports() -> list[str]:
    library_root = YARN_LIBRARY_ROOT
    live_library_ids: set[str] = set()
    if library_root.exists():
        for child in library_root.iterdir():
            if child.is_dir() and _LIBRARY_ID_RE.match(child.name):
                live_library_ids.add(child.name)

    with _LOCK:
        orphan_ids = [
            asset.id
            for asset in _ASSETS.values()
            if (lib_id := (asset.bandMeta or {}).get("library_yarn_id"))
            and lib_id not in live_library_ids
        ]
    for asset_id in orphan_ids:
        try:
            delete_yarn_asset(asset_id)
        except FileNotFoundError:
            pass
    return orphan_ids
```

Called from `load_yarn_assets()` immediately after the cache is populated, so every backend boot reconciles before any endpoint serves traffic. Manually-uploaded assets (no `bandMeta.library_yarn_id`) are explicitly skipped.

The walrus + `is_safe_yarn_id`-equivalent regex check keeps any malformed folder name (`.DS_Store`, half-written tmp dirs) from polluting `live_library_ids`.

### Verification

1. One-shot run on the dev workstation removed the 9 pre-existing orphans:
   ```
   Removed 9 orphan asset(s)
   Runtime now has 3 asset(s)
   ```
   Three remaining assets all match live library ids (Vegeta, Horizon, Horizon — the duplicate is from a re-import, not an orphan) ✓.
2. `ls runtime/yarn_assets/` shows the trimmed set ✓.
3. Future-proof: deleting a folder under `yarn_library/<id>/` outside the API and restarting the backend automatically removes the matching L2 entries ✓.

### Lesson

Promoted to [lessons.md](lessons.md) as **Rule W4** — every cache that mirrors disk needs a boot-time reconcile if the disk can change behind its back.

### Operational note for the running backend

The reconcile runs inside `load_yarn_assets()`, which early-returns when `_ASSETS` is already populated. **A backend that started before this fix landed will keep serving stale `_ASSETS` entries until restarted.** Either restart `make backend-dev` (or `make backend-dev-live`) once after pulling, or hit the backend with a one-shot `python3 -c "from app.yarn_assets import reconcile_orphan_imports, load_yarn_assets; load_yarn_assets(); print(reconcile_orphan_imports())"` from a fresh interpreter.

### What was NOT done in this phase

- **Manual reconcile endpoint** (e.g., `POST /api/yarn/library/reconcile`) — not added; the boot-time pass is enough for the only realistic recovery path. Add later if anyone needs it without a restart.
- **Detecting drift between asset.json on disk and the in-memory cache** — orthogonal problem; today nothing else mutates `runtime/yarn_assets/` outside this module.

---

## Phase template (copy when starting a new phase)

```
## Phase Wn — <one-line title>

**Date**: YYYY-MM-DD

### Motivation
<why this work was triggered — user report, regression, follow-up to Phase X>

### Symptom
<observable user-visible behavior; reproduction steps; what the user expected>

### Diagnosis
<which layer(s) were lying; which file/function was the immediate cause; the
mental-model gap that produced the bug>

### Fix
<code change summary, with file:line references; rationale for the chosen
shape over alternatives>

### Verification
<numbered list — manual + curl + (if applicable) automated tests>

### Lesson
<promote to lessons.md if generalisable; reference the rule number here>

### What was NOT done in this phase
<known related gaps deferred to later, with a one-line why>
```
