# Current State — Pattern Builder + Import Flow

Snapshot of what exists today (2026-05-19), so the spec in [import-panel-spec.md](import-panel-spec.md) and any future implementation can rest on accurate file/line references.

## Components in play

| Component | Path | Role |
|---|---|---|
| `PatternBuilderStep` | [frontend/src/components/PatternBuilderStep.tsx](../../frontend/src/components/PatternBuilderStep.tsx) | The Step 2 root. Owns draft state, focus, active color, busy/parser status, the file-input ref, and the `showExplore` toggle. |
| `StudioToolbar` | [frontend/src/components/StudioToolbar.tsx](../../frontend/src/components/StudioToolbar.tsx) | Eyebrow + title + summary, preset dropdown, count inputs (Shafts / Treadles / Warp ends / Picks), Import + Explore + Reset buttons. |
| `DraftBoard` | [frontend/src/components/DraftBoard.tsx](../../frontend/src/components/DraftBoard.tsx) | The visual draft surface. Threading / tie-up / treadling / drawdown / warp & weft color strips. **Do not touch.** |
| `InspectorPanel` | [frontend/src/components/InspectorPanel.tsx](../../frontend/src/components/InspectorPanel.tsx) | Side panel: focus details, active color picker, parser/import message surface, pasted-text editor with Apply buttons. |
| `ColorBindingGrid` | [frontend/src/components/ColorBindingGrid.tsx](../../frontend/src/components/ColorBindingGrid.tsx) | Warp/weft color → ready yarn asset binding grid. tryon-only, required for Step 3 Blender bind. **Stays.** |
| `ExploreLibrary` | [frontend/src/components/ExploreLibrary.tsx](../../frontend/src/components/ExploreLibrary.tsx) | The current takeover view used when `showExplore` is true. To be replaced by an in-window panel. |

## Current Pattern Builder layout

From [PatternBuilderStep.tsx:151-279](../../frontend/src/components/PatternBuilderStep.tsx#L151-L279):

```
<section data-testid="pattern-builder-step">
  {showExplore ? <ExploreLibrary ... /> : null}   ← full-width takeover when true
  <input type="file" ... />                       ← hidden, triggered by Import
  <div class="studio-editor">                     ← only rendered when showExplore is false
    <StudioToolbar ... />                         ← (tryon moved toolbar INTO studio-editor)
    <div class="studio-editor__center">
      <DraftBoard ... />
      <ColorBindingGrid ... compact />            ← tryon-added grid, below DraftBoard
    </div>
    <InspectorPanel ... />
  </div>
</section>
```

Compared to v2 ([Fabric-generator-codex-fabric-generator-v2/.../PatternBuilderStep.tsx:134-247](/Users/mihirbotle/Desktop/Impetus/3D Fabric/yarnseamless UI/Fabric-generator-codex-fabric-generator-v2/frontend/src/components/PatternBuilderStep.tsx)):

```
<section data-testid="pattern-builder-step">
  <StudioToolbar ... />                           ← toolbar at the top, full width
  {showExplore ? <div class="studio-explore"><ExploreLibrary ... /></div> : null}
  <input type="file" ... />
  <div class="studio-editor">
    <DraftBoard ... />
    <InspectorPanel ... />
  </div>
</section>
```

The v2 layout is the reference for the toolbar position. The `studio-editor__center` + `ColorBindingGrid` block from tryon stays as-is.

## How the redirect-style takeover works today

[PatternBuilderStep.tsx:57](../../frontend/src/components/PatternBuilderStep.tsx#L57): `const [showExplore, setShowExplore] = useState(false);`

[PatternBuilderStep.tsx:153-174](../../frontend/src/components/PatternBuilderStep.tsx#L153-L174): when `showExplore` is true, the JSX renders `ExploreLibrary` and skips the `studio-editor` block. Closing the panel goes through `onClose={() => setShowExplore(false)}` or any of the load callbacks (which also set it false).

[StudioToolbar.tsx](../../frontend/src/components/StudioToolbar.tsx) raises `onToggleExplore` from its Explore button; PatternBuilderStep handles it at [PatternBuilderStep.tsx:194](../../frontend/src/components/PatternBuilderStep.tsx#L194) as `() => setShowExplore((current) => !current)`.

That's the redirect we're removing.

## ExploreLibrary itself

[ExploreLibrary.tsx:127-333](../../frontend/src/components/ExploreLibrary.tsx#L127-L333). What it already does well:

- Pulls a unified `books` list from three sources: the `presets` array, locally imported books (`loadLocalPatternBooks`), and curated `referenceBooks` from `exploreCatalog.ts`.
- Free-text search across book title / author / year / tags + each pattern's reference code / page / title / summary / tags ([lines 74-97](../../frontend/src/components/ExploreLibrary.tsx#L74-L97)).
- Book-shelf left rail with selection state, plus an "Import Local Book JSON" path.
- Pattern cards on the right with `Load Pattern` button when `pattern.status === 'loadable'`.

What it lacks for the new panel:

- No pattern thumbnail / image reference.
- No "pattern type" / weave-type filter (twill, plain, satin, compound, etc.).
- No filter for shaft count, even though most users browse by shafts.
- The whole component is a full-page card (`card explore-library`) sized to take over the step, not a docked panel inside the editor.

## Data shapes

From [frontend/src/domain/types.ts:92-125](../../frontend/src/domain/types.ts#L92-L125):

```ts
interface PresetDefinition {
  id: string;
  label: string;
  summary: string;
  document: DraftDocument;
}

interface BookPatternEntry {
  id: string;
  title: string;
  summary: string;
  referenceCode?: string;
  referencePage?: string;
  tags: string[];
  presetId?: string;
  draft?: DraftDocument;
  status: 'loadable' | 'pending';
  note?: string;
  // missing for the new panel:
  // previewImage?: string;
  // weaveType?: WeaveType;
}

interface PatternBook {
  id: string;
  title: string;
  summary: string;
  author?: string;
  year?: string;
  draftCount?: number;
  sourceLabel: string;
  referenceUrl?: string;
  access: 'builtin' | 'catalog' | 'public-domain' | 'local';
  tags: string[];
  note?: string;
  patterns: BookPatternEntry[];
}
```

Catalog data lives in:

- [frontend/src/domain/presets.ts](../../frontend/src/domain/presets.ts) — built-in starter drafts (currently 131 lines).
- [frontend/src/domain/exploreCatalog.ts](../../frontend/src/domain/exploreCatalog.ts) — five reference books: Oelsner, Kastanek, Posselt, Jansen, plus the wrapper around starter presets. Only Oelsner has populated `patterns`.
- [frontend/src/domain/oelsnerPatterns.ts](../../frontend/src/domain/oelsnerPatterns.ts) — curated Oelsner starter reconstructions with full `draft` payloads.
- [frontend/src/domain/bookLibrary.ts](../../frontend/src/domain/bookLibrary.ts) — `loadLocalPatternBooks`, `parsePatternBookJson`, `upsertLocalPatternBook` (localStorage-backed user imports).

## Load paths from a pattern entry to the draft state

[PatternBuilderStep.tsx:155-173](../../frontend/src/components/PatternBuilderStep.tsx#L155-L173):

- `onLoadPreset(presetId)` → looks up the preset and calls `setDraft({ ...preset.document, warnings: [], parseConfidence: 1, sourceLabel: 'Preset: ...' })`.
- `onLoadDraft(draft, label)` → `setDraft({ ...normalizeDraft(draft), title, sourceLabel: label })`.

Both paths also `setFocus(null)` and write a status string into `importMessage` for the Inspector to display. Both then call `setShowExplore(false)` to close the takeover. The new panel must preserve these two load entry points exactly.
