# Pattern Builder Revamp

Scoped initiative to improve the Pattern Builder page (Step 2) of `Fabric-generator-tryon` without disturbing the parts that work today. Started 2026-05-19.

Read in this order:

| # | file | what it covers |
|---|---|---|
| 1 | [README.md](README.md) | This file. Scope, hard constraints, decisions, status. |
| 2 | [current-state.md](current-state.md) | What Pattern Builder + Explore look like today. File/line map, data shapes, where the redirect-style takeover happens. |
| 3 | [import-panel-spec.md](import-panel-spec.md) | Design spec for the new in-window pattern picker. Surface, card layout, filters, data-model additions, load/cancel behavior. |

## Goals

1. **Replace the Explore "page redirect" with an in-window panel.** Today clicking *Explore* hides the whole editor and renders `ExploreLibrary` taking over the step. We want a docked panel that opens *inside* Pattern Builder so the user can keep their draft visible and load a pattern without context-switching.

2. **Make the pattern listing actually browsable.** Show pattern name, source book name, pattern type (plain / twill / satin / compound / …), and a pattern image reference for every entry. Add filters so a user with hundreds of patterns can narrow by book, type, shafts, tags, and free-text search.

3. **Preserve the v2 Pattern Builder layout for the core editor.** The reference build at `yarnseamless UI/Fabric-generator-codex-fabric-generator-v2` has StudioToolbar at the top and a clean `DraftBoard + InspectorPanel` row. That layout is the visual target.

## Hard constraints — do not break

The following surfaces have already been tuned and tested. The revamp must not refactor them:

- **DraftBoard** — threading, tie-up, treadling, drawdown, warp color strip, weft color strip. All click/paint/focus/pin handlers stay as they are.
- **Color palette / active color** behavior in `PatternBuilderStep` (the `activeColor` state and its sync with `draft.warpColors` + `draft.weftColors`).
- **ColorBindingGrid** (the tryon-only warp/weft → yarn mapping grid below DraftBoard). It is required for the Blender bind in Step 3 and is staying. The revamp should not relocate or restyle it.
- **StudioToolbar's existing buttons and counts** (Shafts, Treadles, Warp ends, Picks, preset dropdown, Reset). Only the *Explore* button's behavior changes — it should now open the in-window panel instead of toggling a takeover view.
- **Import-file flow** (the hidden `<input type="file">` triggered by *Import*). Stays as-is.

If a change here looks tempting, write it up as a separate follow-up — not part of this revamp.

## What is in scope

- New in-window pattern picker component (working name: **`PatternPickerPanel`**) that replaces the takeover behavior of `ExploreLibrary`.
- Filter UI inside the picker (book, weave type, shafts, tags, search).
- Two new optional fields on `BookPatternEntry`: `previewImage` (URL or data URI) and `weaveType` (enum). Existing entries without these still work.
- Optional layout normalization to match v2's StudioToolbar-on-top arrangement *if and only if* it does not touch DraftBoard, ColorBindingGrid, or the palette wiring.
- Docs in this folder, kept in sync as work lands.

## What is out of scope

- Any change to DraftBoard rendering or interactions.
- Any change to ColorBindingGrid (deferred to its own initiative).
- Any change to Step 1 (Yarn Library), Step 3 (Render), or Step 4 (Try-on).
- Any change to the existing book catalog data (`exploreCatalog.ts`, `oelsnerPatterns.ts`) beyond optionally tagging entries with `weaveType` and `previewImage` where we have them. Books that don't have those fields stay loadable with a placeholder.
- Server-side pattern catalog APIs. The picker reads the same in-memory `presets` + `referenceBooks` + `localBooks` the current Explore already uses.

## Status

| Phase | Status |
|---|---|
| 0 — docs seeded (this folder) | ✓ done (2026-05-19) |
| 1 — current-state + spec finalized | ✓ done (2026-05-19) |
| 2 — `BookPatternEntry.previewImage` + `weaveType` added to types and existing presets/Oelsner entries | ✓ done (2026-05-19) |
| 3a — `PatternPickerPanel` component built, replaces the takeover behavior | ✓ done (2026-05-19) |
| 3b — filters wired (book / weave type / shafts / tags / search) | ✓ done (2026-05-19) |
| 3c — drawer scroll fix: `position: fixed` + sticky header/search + scrollable `__body` (studio shell is `overflow: hidden`, the drawer must own its own scroll) | ✓ done (2026-05-19) |
| 3d — generated pattern library: ~370 family reconstructions across 10 books (twills, herringbones, broken twills, satins, baskets, ribs, color-and-weave, huck) | ✓ done (2026-05-19) |
| 3e — `testingv1_cheques` scan reconstruction + Pattern Builder `Save Pattern` action | ✓ done (2026-05-27) |
| 4 — layout normalization to v2 toolbar-on-top (optional, last) | deferred |
| 5 — retire `ExploreLibrary.tsx` once the picker proves out | pending |
| 6 — literal page transcription / WIF ingest for any single book (out of scope for the current pass; would need OCR or an existing digitized dataset) | not started |

## Decisions log

- **2026-05-19** — New docs folder is `docs/PatternBuilderRevamp/` (matches existing convention of capitalized scope folders like `BlenderFixes/`, `WebUIChanges/`).
- **2026-05-19** — `ColorBindingGrid` stays in place; revamp does not touch it.
- **2026-05-19** — v2's `PatternBuilderStep` is the layout reference; v2's `ExploreLibrary` is byte-identical to tryon's, so v2 offers nothing new for the import panel itself — that's a greenfield design.
- **2026-05-19** — Picker is implemented as a **`position: fixed`** right-edge drawer (initially attempted `position: absolute` inside `.fabric-step-panel` but the studio shell sets `height: 100dvh; overflow: hidden` so the panel itself cannot grow; an absolute child therefore inherits a bounded but non-scrollable inner list). Fixed positioning gives the drawer its own viewport-bounded height and a sticky header + search above a scrollable `__body` that owns filters + list.
- **2026-05-19** — Drawdown thumbnails are generated client-side via canvas (`PatternPickerPanel.tsx → drawdownToDataUrl`). Memoised per pattern id in a useRef-backed cache so the canvas only runs once per entry per panel open.
- **2026-05-19** — `inferWeaveTypeFromTags` runs as a fallback for entries that don't yet have `weaveType`. Entries with neither field land in the "Untyped" weave-type bucket — keep them browseable instead of hiding them.
- **2026-05-19** — Bulk pattern data is generated programmatically rather than transcribed from book scans. The advertised draftCounts on the catalog books range from 128 (Thaller) to 7,000 (Ashenhurst), totaling ~21,000 entries across the shelf. Literal transcription requires OCR or an existing digitized dataset; neither is in scope. Instead, [generatedPatterns.ts](../../frontend/src/domain/generatedPatterns.ts) emits family-taxonomy reconstructions (twills, herringbones, broken twills, satins, baskets, ribs, color-and-weave, huck) and distributes them per book based on the book's published emphasis. Every entry is honestly tagged `'generated'` with a note that it is a structural reconstruction, not a literal page transcription.
- **2026-05-27** — `thread_epson_scans/testingv1_cheques/fabric_scan20260527_13591460.png` is represented as a plain-weave plaid preset, not as a new weave structure. The image's visual pattern is driven by warp/weft colour order: broad dark and light cheque bands plus narrow pinstripes. The preset uses the same stripe repeat on warp and weft so it appears in Quick Load and in the Pattern Library's starter book.
- **2026-05-27** — `Save Pattern` writes the current normalized draft into the localStorage-backed `Saved Pattern Drafts` book. This keeps saved patterns inside the existing Explore/Load picker instead of creating a second save surface.

## Files touched

- [frontend/src/domain/types.ts](../../frontend/src/domain/types.ts) — added `WeaveType` type alias and optional `previewImage` + `weaveType` on `PresetDefinition` and `BookPatternEntry`.
- [frontend/src/domain/presets.ts](../../frontend/src/domain/presets.ts) — backfilled `weaveType` on all five starter presets. Later added `Testing V1 Cheques`, reconstructed from the scan as a plain-weave plaid colour-order draft.
- [frontend/src/domain/bookLibrary.ts](../../frontend/src/domain/bookLibrary.ts) — localStorage helpers for imported books; now also owns `saveDraftAsLocalPattern`, the `Saved Pattern Drafts` book, and a `pattern-library-updated` event so an open picker refreshes after a save.
- [frontend/src/domain/oelsnerPatterns.ts](../../frontend/src/domain/oelsnerPatterns.ts) — backfilled `weaveType` on all seven Oelsner starter reconstructions.
- [frontend/src/domain/generatedPatterns.ts](../../frontend/src/domain/generatedPatterns.ts) — new module. Deterministic weave-family generators (`generateTwills`, `generateHerringbones`, `generateBrokenTwills`, `generateSatins`, `generateBaskets`, `generateRibs`, `generateColorAndWeave`, `generateHuck`) and a per-book recipe table. Exports `generatedBookPatterns: Map<bookId, BookPatternEntry[]>` computed once at module load.
- [frontend/src/domain/exploreCatalog.ts](../../frontend/src/domain/exploreCatalog.ts) — every book's `patterns: []` replaced with `bookPatterns(bookId, curated)`. Curated entries (currently only Oelsner) sit first, generated entries follow. Notes updated on each book to disclaim generated vs. transcribed.
- [frontend/src/components/PatternPickerPanel.tsx](../../frontend/src/components/PatternPickerPanel.tsx) — new component. Sticky header + search above scrollable `__body` (filters + cards). Filter rail: Books, Weave type, Shafts, Tags, Loadable-only toggle. Pattern cards with canvas-generated drawdown thumbnails. Import book JSON path retained. Listens for local pattern-library updates after saves.
- [frontend/src/components/PatternBuilderStep.tsx](../../frontend/src/components/PatternBuilderStep.tsx) — removed the `showExplore` takeover branch and `ExploreLibrary` import. Renamed state to `showPicker`. Mounts `PatternPickerPanel` as a sibling of `studio-editor`. Added `Save Pattern` handler. `ExploreLibrary.tsx` is left on disk for the moment — wired off, not deleted, until phase 5.
- [frontend/src/components/StudioToolbar.tsx](../../frontend/src/components/StudioToolbar.tsx) — added the Pattern Builder `Save Pattern` button.
- [frontend/src/styles/index.css](../../frontend/src/styles/index.css) — appended drawer + chip + pattern-card styles, plus `.fabric-shell` dark-theme overrides. Drawer is `position: fixed`, height `100dvh`, with `__body` as the scrollable region.

## Pattern counts per book (after phase 3d)

Generated by the deterministic recipe table at the bottom of `generatedPatterns.ts`:

| Book | Curated | Generated | Total |
|---|---:|---:|---:|
| Oelsner — A Handbook of Weaves | 7 | 54 | 61 |
| Kastanek — A Manual of Weave Construction | 0 | 38 | 38 |
| Posselt — A Dictionary of Weaves | 0 | 37 | 37 |
| Jansen — Revised Textile Design Book | 0 | 30 | 30 |
| Serrure — Atlas de 4000 Armures | 0 | 43 | 43 |
| Fressinet — Atlas D'Armures Textiles | 0 | 37 | 37 |
| Morath — German Weaver's Pattern Book | 0 | 26 | 26 |
| Thaller Manuscript Drafts | 0 | 20 | 20 |
| Watson — Textile Design and Colour | 0 | 36 | 36 |
| Ashenhurst — Album of Textile Designs | 0 | 53 | 53 |
| **Total reference shelf** | **7** | **374** | **381** |

Plus 6 starter presets in the synthetic "Prototype Starter Drafts" book ⇒ **387 patterns** the picker can show.

The advertised `draftCount` field on each book is left untouched — it still reflects the literal page count of the source book, not the current bundle. The picker's footer reads "N patterns · M books" off the actual loaded entries, so the user sees the real count.

## Verification

- `npx tsc --noEmit` introduces no new errors (pre-existing errors in DraftStudio/RenderPanel/bookLibrary/tests are unchanged).
- `npm run test:unit` — 15/15 pass after Phase 3e.
- `npm run build` — succeeds. Phase 3e build: CSS 65.76 kB, JS 846.72 kB.
- Playwright smoke (2026-05-27): load `Testing V1 Cheques` from Quick Load, click `Save Pattern`, accept the prompt, open Explore/Load, search the saved name, and confirm the saved pattern card appears.
