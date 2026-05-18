# Import Panel Spec — `PatternPickerPanel`

Design spec for the in-window pattern picker that replaces the current `ExploreLibrary` takeover. Reading this assumes [current-state.md](current-state.md) is fresh.

## Goals

- Open *inside* Pattern Builder instead of replacing the whole step.
- Let users browse hundreds of patterns at a glance with name, book, type, and image.
- Let users narrow the list by book, weave type, shaft count, tag, and free-text search.
- Keep both existing load paths intact (`onLoadPreset(presetId)` and `onLoadDraft(draft, label)`).

## Surface — docked drawer on the right

Three options were considered:

| Option | Why not | |
|---|---|---|
| Full overlay modal | Same context-switch problem as today; just smaller. | ✗ |
| Bottom sheet drawer | Crowds the warp/weft strips; conflicts with InspectorPanel. | ✗ |
| **Right-side docked drawer** | Slides in over `InspectorPanel`, leaves DraftBoard + ColorBindingGrid fully visible. Closeable without losing draft context. | ✓ |

**Recommendation:** docked drawer on the right edge of the `studio-editor` row. Width ~480 px on desktop; collapses to bottom drawer on narrow viewports (handled in a later phase).

Open state: `showPicker = true` ⇒ drawer slides in; `InspectorPanel` stays mounted but is visually covered by the drawer (no remount, no state loss). Close state: drawer slides out; nothing else changes.

The existing `showExplore` state in `PatternBuilderStep` is renamed to `showPicker` (or simply replaced). The `onToggleExplore` callback wired into `StudioToolbar` is repointed to toggle the drawer.

## Anatomy

```
PatternPickerPanel
├── Header
│   ├── Title: "Pattern Library"
│   ├── Result count: "247 patterns · 5 books"
│   └── Close button (×)
├── Search bar (free-text, debounced 150 ms)
├── Filter rail (collapsible row of chips/selects)
│   ├── Book           multi-select chips
│   ├── Weave type     multi-select chips
│   ├── Shafts         range / set of buttons (2, 4, 6, 8, 12, 16, 24)
│   ├── Tags           multi-select chips, scroll-overflow
│   └── Status         "Loadable only" toggle (default on)
├── Active filter pills (chip row showing applied filters with x-to-remove)
└── Pattern list (virtualized when length > 100)
    └── PatternCard × N
```

## PatternCard layout

```
┌─────────────────────────────────┐
│ ┌──────────┐                    │
│ │          │  Title             │
│ │ preview  │  Book · Ref code   │
│ │  image   │  ┌─────┬─────┐     │
│ │  64×64   │  │twill│ 4-sh│     │
│ └──────────┘  └─────┴─────┘     │
│                                 │
│  Summary (2 lines max, ellipsis)│
│                                 │
│  [Load Pattern]      [Preview]  │
└─────────────────────────────────┘
```

Fields shown:

| Slot | Source |
|---|---|
| Preview image | `pattern.previewImage` (new field; falls back to a generated drawdown thumbnail or a neutral placeholder) |
| Title | `pattern.title` |
| Book line | `book.title` + ` · ` + (`pattern.referenceCode` or `pattern.referencePage`) |
| Type chip | `pattern.weaveType` (new field; "plain", "twill", "satin", "compound", "lace", "double", etc.) |
| Shafts chip | derived from `pattern.draft?.shaftCount` or `preset.document.shaftCount` |
| Summary | `pattern.summary`, clamped |
| Load Pattern button | wired to `onLoadPreset(presetId)` or `onLoadDraft(draft, label)` exactly like today |
| Preview button | optional later phase — would show drawdown preview in a hover popover |

Cards for `status === 'pending'` are dimmed and show a "Pending" pill instead of Load.

## Filter behavior

- **Book** — multi-select; default all selected. Backed by the same merged book list `ExploreLibrary` computes today (presets + local + reference).
- **Weave type** — multi-select; default all. Populated from the set of distinct `weaveType` values present after filtering by Book. Patterns missing `weaveType` go in an "Untyped" bucket.
- **Shafts** — set of toggle buttons for common counts; "Any" by default. Derived from `pattern.draft?.shaftCount` or `presets[].document.shaftCount`.
- **Tags** — multi-select chips; the available set is the union of `pattern.tags` after the other filters are applied (so the user sees only relevant tags).
- **Status** — boolean toggle "Loadable only", default on (today's Explore Load button is also gated on this).
- **Search** — same fields as today's free-text search, plus `pattern.weaveType` and book author/year. Debounced.

Filters AND together. Empty filter set = show all.

## Data-model additions

Add to [`BookPatternEntry`](../../frontend/src/domain/types.ts#L99-L110):

```ts
export type WeaveType =
  | 'plain'
  | 'twill'
  | 'satin'
  | 'basket'
  | 'compound'
  | 'lace'
  | 'double'
  | 'huck'
  | 'other';

export interface BookPatternEntry {
  // ...existing fields
  previewImage?: string;   // URL or data URI; optional, panel falls back to placeholder
  weaveType?: WeaveType;   // optional; missing entries appear in "Untyped" bucket
}
```

Migration plan:

1. Add the two optional fields. Existing entries keep working (both are optional).
2. Backfill `weaveType` on the Oelsner starter set in [oelsnerPatterns.ts](../../frontend/src/domain/oelsnerPatterns.ts) — about 6–10 entries, mostly inferable from tags ("plain weave" → `'plain'`, "twill" → `'twill'`).
3. `previewImage` is opt-in. For patterns without one, the panel synthesizes a tiny drawdown thumbnail from `pattern.draft` (or `pattern.presetId` → preset draft) using an existing render path or a simple canvas helper. If neither exists, show a neutral placeholder tile.

## Load flow

Unchanged from today. The drawer holds its own internal state, but loading goes through the same two callbacks `PatternBuilderStep` already passes to `ExploreLibrary`:

```ts
onLoadPreset(presetId) // for built-in starter presets
onLoadDraft(draft, label) // for any `BookPatternEntry.draft`
```

After load:

1. The picker calls the appropriate callback.
2. PatternBuilderStep updates `draft`, clears `focus`, writes `importMessage`.
3. The drawer closes automatically (`setShowPicker(false)`) unless the user has Shift-clicked Load (later phase: hold Shift to keep the panel open and browse more).

## Accessibility / interaction notes

- Drawer is a `<dialog role="complementary">` so it doesn't steal focus from the editor entirely. Tab cycles inside the drawer when focused; Escape closes.
- The Explore button in StudioToolbar becomes a toggle button with `aria-expanded` reflecting the drawer state.
- Loading a pattern from the drawer must not scroll DraftBoard or reset palette state — only `draft`, `focus`, and `importMessage` change.

## Open questions

- **Preview-image source of truth.** Bundling actual scanned page crops into the repo is heavy. For the starter shelf, generated drawdown thumbnails are likely good enough. For future imported books we'd want to allow a `previewImage` URL field in the local-book JSON schema (`bookLibrary.ts`).
- **Multi-select vs single-select for Book filter.** Single-select keeps the result list shallow but breaks cross-book search ("twills across all books"). Multi-select with "Select all" / "Clear all" buttons is the better default.
- **Should the drawer be resizable?** Probably not in v1; pick a width and ship.
- **Empty state for the `'pending'` books** (Kastanek, Posselt, Jansen, Donat have empty `patterns[]`). Today they render an "No bundled pattern index yet" block. The drawer should keep that note but visually quieter — these books appear in the Book filter but contribute 0 cards until extraction work happens.

## Implementation order (when the spec is approved)

1. Add `previewImage` and `weaveType` to `BookPatternEntry`. Backfill `weaveType` on Oelsner starter entries. No UI changes yet — types + data only.
2. Build `PatternPickerPanel` as a stand-alone component reading the same merged book list `ExploreLibrary` does today. Render header, search, filter rail, and the card list. Mount it conditionally next to `InspectorPanel` in `PatternBuilderStep`.
3. Replace `showExplore` with `showPicker`. Repoint `StudioToolbar`'s Explore button to toggle the drawer. Delete the takeover branch in `PatternBuilderStep`'s render.
4. Decide whether to also restore v2's toolbar-on-top layout. Treat as a separate, optional pass — do not bundle.
5. Once the panel ships, retire `ExploreLibrary.tsx` (or keep it dormant until any external entry point is also migrated).
