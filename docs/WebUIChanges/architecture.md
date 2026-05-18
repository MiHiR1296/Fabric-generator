# Web UI architecture — three state layers, three sync points

> **Read this if**: you are about to change anything that touches the wizard's state — adding/removing items in any of the four steps, surfacing a dropdown that lists library or asset data, or wiring a new endpoint that mutates the runtime store. Knowing the three-layer model up front saves you from the "why is the deleted yarn still in the dropdown?" class of bug.

---

## The three layers

The wizard has four steps (Yarn Library → Pattern Builder → Render Preview → Try On 3D), but only **three layers of state** drive what the user sees. Each layer lives in a different place; each is the source of truth for a different question.

| layer | lives in | source of truth for | written by | read by |
|---|---|---|---|---|
| **L1 — Library** | `yarn_library/<id>/` on disk + `yarn_library/index.json` | "What yarns has anyone ever scanned and saved?" | yarnseamless's Save-to-Library button (now hosted inside Step 1's MultiFragmentEditor) | Step 1's library strip (`/api/yarn/library`) |
| **L2 — Runtime asset** | `runtime/yarn_assets/<asset_id>/asset.json` + supporting files; in-process cache `_ASSETS` in [backend/app/yarn_assets.py](../../backend/app/yarn_assets.py) | "What yarns has THIS project imported and processed?" | `import_yarn_from_library` (POST `/api/yarn/library/{id}/import`) and `create_yarn_assets` (POST `/api/yarn/assets`) | Step 2 ColorBindingGrid dropdowns; Step 3 render-project; live bandMeta push |
| **L3 — Color binding** | `colorBindings` React state in [App.tsx](../../frontend/src/App.tsx); not persisted on the backend | "Which yarn (by L2 asset id) is assigned to which warp/weft palette color?" | ColorBindingGrid `<select>` onChange; auto-import flow on `handleImportFromLibrary` | Pattern Builder preview; render-project; push-project-bandmeta |

**Critical invariant**: a `colorBinding.yarnAssetId` (L3) is a foreign key into L2. An L2 asset's `bandMeta.library_yarn_id` is a back-reference to L1. There are no constraints enforced — every cross-layer mutation is a place a bug can live.

---

## The three sync points

Every cross-layer mutation needs to keep the downstream layer consistent. There are exactly three of these in the current wizard.

### Sync point 1 — Library import (L1 → L2 → L3)

**Trigger**: user clicks "Import" on a library card, or the auto-import effect fires when a new library entry appears (Step 1 polls every 3 s).

**What happens**:
1. Backend copies `yarn_library/<id>/rgba.png` into a fresh `runtime/yarn_assets/<asset_id>/`, splits into albedo + alpha, builds Cycles-safe downscales, and persists a new `YarnAsset` with `bandMeta.library_yarn_id = <id>`. (See `import_yarn_from_library` in [backend/app/yarn_assets.py](../../backend/app/yarn_assets.py).)
2. Frontend [App.tsx](../../frontend/src/App.tsx) `handleImportFromLibrary` receives the new asset, calls `setColorBindings` to point every existing warp+weft binding at the new asset id, and advances the wizard to Step 2.

**Why the binding rewrite**: the user's intent on import is "use this yarn for everything until I change it". Without rewriting bindings, they'd land in Step 2 with the new asset listed but no slots assigned to it.

### Sync point 2 — Asset delete (L2 → L3, optional)

**Trigger**: user clicks the trash icon on a Step 1 asset card (legacy upload flow; not currently rendered in the wizard but the endpoint is live).

**What happens**:
1. Backend `delete_yarn_asset` pops the `YarnAsset` from `_ASSETS` and `rmtree`s its runtime folder.
2. Frontend `onDelete` calls `refreshAssets` only — bindings that referenced the asset become orphans and silently fall back to "Select processed yarn" in the dropdown (the `<select value=oldId>` matches no `<option>`).

**Known gap**: bindings are not actively cleared. Functionally harmless (the dropdown shows empty) but a future cleanup target.

### Sync point 3 — Library delete (L1 → L2 → L3) — **Phase W1**

**Trigger**: user clicks the 🗑 button on a library card in Step 1.

**What happens** (after Phase W1):
1. Backend `delete_library_yarn` removes `yarn_library/<id>/` + the index entry, **then** scans `_ASSETS` for any whose `bandMeta.library_yarn_id == <id>` and cascade-deletes them via `delete_yarn_asset`. Returns `{id, removed, removedAssetIds: [...]}`.
2. Frontend `onDeleteFromLibrary` reads `removedAssetIds`, clears any `colorBindings` whose `yarnAssetId` is in that set (sets to `null`), and calls both `refreshLibrary()` and `refreshAssets()` so the Step 1 strip and any future Step 2 view reflect the deletion immediately.

**Why both layers cascade**: Pattern Builder reads L2, not L1. Without the L2 cascade, deleting from the Step 1 library strip would leave the imported asset alive in the runtime, and it would still appear in Step 2's "Select processed yarn" dropdown — which is exactly the bug Phase W1 fixed.

---

## Where the layers are consumed in the UI

| Step | Reads | Writes | Notes |
|---|---|---|---|
| **Step 1 — Yarn Library** | L1 (strip), L2 (dedupe "imported ✓" badge) | L1 (Save-to-Library inside MFE), L2 (import endpoint), L1+L2+L3 (delete cascade) | Polls every 3 s while active. |
| **Step 2 — Pattern Builder** | L2 (dropdown options, filtered to `status==='ready'`), L3 (selected value per slot) | L3 (`<select>` onChange) | No L1/L2 mutation from this step. |
| **Step 3 — Render Preview** | L2 (asset URLs), L3 (slot → asset map for material binding) | none directly; submits a render job that snapshots L2+L3 | `requestProjectRender` includes the snapshot in the request body. |
| **Step 4 — Try On 3D** | render job output only | none | Pure consumer. |

The 3-second poll on Step 1 (`refreshLibrary` + `refreshAssets`) is the only time L1/L2 changes are pulled without an explicit user action. Step 2 onward trusts the in-memory snapshot until the user navigates back to Step 1.

---

## Quick map for new bugs

When the UI shows the wrong thing, find which layer is lying:

| symptom | first layer to check |
|---|---|
| A yarn shown in Step 1 strip but missing from Step 2 dropdown | L2 — was it actually imported? `curl /api/yarn/assets` |
| A yarn in Step 2 dropdown but not in Step 1 strip | L1 — was it deleted from the library? `curl /api/yarn/library` |
| A binding row says "Select processed yarn" even though the user assigned one | L3 — orphan binding pointing at a now-deleted L2 id |
| Render uses the wrong yarn for a color | L3 — check the binding for that color slot, then L2 for the asset's bandMeta |
| Step 1 strip is stale after Save-to-Library | L1 — check the 3 s poll, or hit `/api/yarn/library` directly |
