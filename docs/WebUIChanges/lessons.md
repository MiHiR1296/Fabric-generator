# Lessons — Web UI

> **Read this if**: you are about to change anything that mutates state in one of the wizard's three layers (library / runtime asset / color binding). The rules below were earned the hard way; they save you from shipping the same class of bug twice.

> Each lesson has the **Rule**, the **Why**, and **How to apply** with file paths. Add lessons the same hour you find them.

---

## On cross-layer state

### Rule W1 — Every cross-layer mutation must cascade to every downstream layer, in the same request.

The wizard has three state layers (L1 library / L2 runtime asset / L3 color binding — see [architecture.md](architecture.md)). They are joined by foreign-key-like back-references (`bandMeta.library_yarn_id`, `binding.yarnAssetId`) but no constraints. When the user mutates the upstream layer, the downstream layers don't know unless the mutation explicitly cascades. **The cascade lives in the same backend handler that does the upstream mutation, and the handler returns the cascade list so the frontend can clean its in-memory state without a second round trip.**

**Why**: Pattern Builder (Step 2) reads L2, not L1. Before Phase W1, deleting an L1 entry left the L2 copy alive — the deleted yarn kept appearing in Step 2's dropdowns. The user's mental model is "the library is the source of truth, delete from there and everything follows" — anything else is a bug, even if technically the layers are independent stores.

**How to apply**:
- Any new endpoint that deletes / renames / moves an item in L1 must also touch matching items in L2 (joined by `library_yarn_id`).
- Any endpoint that touches L2 must return the affected asset ids so the frontend can clear matching L3 bindings.
- Any frontend handler that triggers an L1 or L2 mutation must call BOTH `refreshLibrary()` and `refreshAssets()` afterwards (parallel via `Promise.all`) — never trust the 3-second Step-1 poll to catch up before the user navigates to Step 2.

**Concrete example** ([backend/app/yarn_assets.py](../../backend/app/yarn_assets.py) `delete_library_yarn`, 2026-05-15):
```python
# After removing the L1 folder, scan L2 for back-references and cascade:
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

And the matching frontend handler ([App.tsx](../../frontend/src/App.tsx) `onDeleteFromLibrary`):
```tsx
const result = await deleteLibraryYarn(yarnId);
const cascade = new Set(result.removedAssetIds);
setColorBindings((current) =>
  current.map((b) =>
    b.yarnAssetId && cascade.has(b.yarnAssetId) ? { ...b, yarnAssetId: null } : b,
  ),
);
await Promise.all([refreshLibrary(), refreshAssets()]);
```

**Generalises**: any time you have a downstream view that filters from an in-memory cache (here `_ASSETS` populated on backend boot), mutating the upstream store without invalidating the cache produces a stale view that no amount of frontend polling will fix.

---

### Rule W2 — Acquire all backend locks once, do the work outside the lock.

`_ASSETS` is guarded by a module-level `threading.Lock`. The Phase W1 cascade collects ids inside the lock, then calls `delete_yarn_asset` outside the lock — because that helper takes the lock itself, calling it while still holding the lock would deadlock.

**Why**: Python locks are not reentrant by default (they're `threading.Lock`, not `RLock`). The `with _LOCK:` block must be short and self-contained. Anything that calls back into a locked helper goes outside.

**How to apply**: when you find yourself wanting to call another module function from inside a `with _LOCK:` block, refactor: collect the work to do (ids, paths, snapshot data) inside the lock, then exit the lock and do the calls. If the cross-helper call truly needs atomicity, switch to `RLock` — but prefer the snapshot-then-act pattern.

---

## On UI feedback

### Rule W4 — Every in-memory cache that mirrors disk needs a boot-time reconcile.

Live caches that load once on startup and stay warm (`_ASSETS` in [backend/app/yarn_assets.py](../../backend/app/yarn_assets.py) is the canonical example) silently drift if anything mutates the disk behind the cache's back — whether that's a Finder delete, a half-fixed cascade, or a process from an older code revision. A boot-time reconcile is cheap insurance: walk the cache, drop entries whose backing disk state is gone, and you're back in sync without anyone having to think about it.

**Why**: Phase W2 found 9 runtime YarnAssets pointing at L1 library ids that no longer existed — leftovers from deletes that happened before Phase W1's cascade landed. The cache had no way to notice. Pattern Builder happily showed all 12 yarns in its dropdown. The user's mental model — "I deleted those, why are they back?" — is the right one; the cache was lying.

**How to apply**:
- Any cache populated from disk during a `load_*()` function should call its reconcile pass after population, in the same `load_*()`. Idempotent — only the first call after process boot does real work because `_ASSETS` is empty.
- The reconcile should join on the cross-layer back-reference (here `bandMeta.library_yarn_id` → live folders under `YARN_LIBRARY_ROOT/`) and drop entries whose join key is missing.
- Skip entries that have NO back-reference (manually-uploaded assets) — they have no upstream to be orphaned from.
- Document this clearly in the phase log: a backend that started BEFORE the reconcile fix landed will keep serving stale data until restarted. The fix has zero effect on already-running processes.

**Concrete example** ([backend/app/yarn_assets.py](../../backend/app/yarn_assets.py) `reconcile_orphan_imports`, 2026-05-15):
```python
def load_yarn_assets() -> None:
    ensure_runtime_dirs()
    with _LOCK:
        if _ASSETS:
            return
        for meta_path in sorted(YARN_ASSETS_ROOT.glob("*/asset.json")):
            ...
    reconcile_orphan_imports()  # called outside the lock; no-ops on subsequent boots
```

**Generalises**: any cache + disk pair where (a) the disk can change without going through the cache's API, or (b) a previous code revision could leave inconsistent disk state. The boot-time sweep is the cheapest safety net.

---

### Rule W3 — Toasts that report cascade counts beat toasts that don't.

When a single user action mutates more than one item, say so. "Removed \"<id>\" from the yarn library and 3 imported project assets." beats "Removed \"<id>\" from the yarn library." — the user wants to confirm the side effects matched their intent, especially when the side effect crosses screens (delete in Step 1 affecting Step 2's dropdowns).

**Why**: silent cascades are how users lose trust in the wizard. If they don't see the count, they'll either (a) not realize the cascade happened and be surprised later, or (b) navigate to Step 2 to manually verify, which defeats the point.

**How to apply**: anywhere a backend endpoint returns a list of affected ids, the frontend toast should mention the count when non-zero. Singular/plural the noun ("1 asset" / "3 assets"). Keep the zero-cascade case quiet — no need to say "and 0 other things."
