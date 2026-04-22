# Weaving Draft Studio Application Blueprint

This document is the main reference for rebuilding the weaving-draft subsystem inside the full application. It describes what has been implemented in the prototype, why it exists, how the pieces connect, and what needs to stay true when the UI is expanded into the larger product.

Use this as the primary integration document. The other files in this folder remain useful for history and troubleshooting, but this is the one to follow when rebuilding the feature.

## 1. Product Goal

The subsystem solves one narrow but important workflow:

1. A user creates or loads a weaving draft in the browser.
2. The browser stores that draft in one canonical document shape.
3. The same draft can be:
   - edited visually
   - imported from structured or semi-structured sources
   - exported as JSON
   - converted to a Blender-ready matrix
   - sent to a headless Blender render pipeline
4. Blender rebuilds the woven structure from the draft and returns a preview image.

The key product decision is that the web app is the drafting tool and Blender is the render worker. We are not designing a permanent live Blender editing session for end users.

## 2. What Exists Today

Current deliverables:

- Standalone React + Vite + TypeScript prototype in `prototypes/weaving-draft-studio/`
- Python parser and Blender bridge service in `services/draft-parser/`
- Canonical draft model with `threading`, `tieUp`, `treadling`, `drawdown`, color sequences, and render settings
- Draft editor with:
  - editable threading
  - editable tie-up
  - editable treadling
  - computed drawdown
  - paintable warp and weft color strips
  - drag-to-draw editing
  - hover/pin understanding layer
- Explore / Load flow with:
  - built-in presets
  - source-book shelf
  - curated Oelsner starter patterns
  - local pattern-book JSON import
- Headless Blender preview flow:
  - draft sent to service
  - service creates render job
  - Blender runs headlessly against `Weave_GUIConnection.blend`
  - preview PNG is returned to the browser
- Test coverage for domain logic and parser / render bridge

## 3. User Flow To Preserve

The overall UI should stay in this order:

### Step 1: Create or Load Draft

The user should be able to:

- start from a preset
- browse a source book and load a pattern
- import a file
- paste text
- build manually from scratch

### Step 2: Edit The Draft

The user should be able to:

- change counts
- draw threading, tie-up, and treadling directly
- paint warp and weft colors directly
- inspect why a drawdown cell is warp-over or weft-over
- optionally use advanced text editors for direct copy/paste editing

### Step 3: Render And Export

The user should be able to:

- export canonical draft JSON
- export Blender handoff JSON
- tweak Blender render settings
- render a preview
- compare the preview against the drawdown

This order is important. The top of the UI is drafting. The lower part is rendering. Rendering should not dominate the drafting UI.

## 4. Information Architecture

The current interface is intentionally split into four product regions.

### A. Toolbar

File: `src/components/StudioToolbar.tsx`

Purpose:

- small top-level entry point for loading / importing / resizing the draft

Contains:

- quick-load preset dropdown
- `Explore / Load` button
- `Import File`
- `Reset Draft`
- count inputs for:
  - shafts
  - treadles
  - warp ends
  - picks
- parser status pill
- source type pill

Important behavior:

- the count inputs are free-typing text inputs, not aggressive steppers
- user can clear the field, type naturally, and commit on blur or Enter
- values are clamped only on commit

### B. Draft Workspace

File: `src/components/DraftBoard.tsx`

Purpose:

- this is the main weaving interface and should visually read as one connected draft box

Current layout rule:

- `Tie-Up` sits at the top-right of the draft frame
- `Threading` sits to the left of the tie-up
- `Drawdown` sits below the threading
- `Treadling` sits below the tie-up
- warp paint strip sits above threading
- weft paint strip sits to the outer right of treadling
- active paint color sits at the top-right paint corner, aligned to the intersection of the outer paint strips

Why this matters:

- it matches conventional weaving draft reading more closely
- it reduces the feeling that the UI is four unrelated editors
- it makes the drawdown feel like the center result of one unified structure

### C. Inspector

File: `src/components/InspectorPanel.tsx`

Purpose:

- secondary support layer, not the main drafting surface

Visible sections:

- understanding layer
- draft color editor

Hidden behind `Advanced Draft Tools`:

- direct text editing for warp colors and weft colors
- direct text editing for threading, tie-up, and treadling
- apply-all action
- copy drawdown
- source status and parse-confidence details
- paste intake
- JSON previews

Design rule:

- keep the main UI clean
- keep power-user tools available but collapsed

### D. Render Step

File: `src/components/RenderPanel.tsx`

Purpose:

- step-two area for rendering and exporting after drafting is done

Contains:

- `Render Preview`
- `Export Draft JSON`
- `Export Blender Map`
- Blender controls:
  - warp threads
  - weft threads
  - spacing
  - amplitude
  - texture scale V
  - fill ratio
- preview image
- render status facts
- recent Blender logs

Design rule:

- this belongs below drafting, not in the toolbar

## 5. Draft Workspace Layout Rules

When you rebuild this inside the full application, preserve these rules.

### 5.1 Layout Chrome Must Stay Outside The Pattern

Do not place large titles, subtitles, or reset buttons inside the active draft box. The current pattern area is cleaner because:

- section labels moved into a compact control rail above the draft
- explanations moved behind `?` hints
- reset buttons live in that control rail too

This keeps the pattern itself visually central.

### 5.2 Orientation Rule

The draft is oriented from the tie-up corner.

That means:

- threading starts at the visible right side near the tie-up
- the drawdown uses an explicit column-mapping function
- internal sequence order and visible draft order are not the same thing

This rule is implemented by `getThreadingIndexFromDrawdownColumn(...)` in `src/domain/draft.ts`.

This rule must not be removed casually. It exists to avoid mirrored drafts when users rebuild references from weaving sources.

### 5.3 Color Strip Placement

The paint strips are part of the draft frame:

- warp colors belong above the threading
- weft colors belong on the outer side of the treadling
- the active paint color belongs in the top-right outer paint corner

This is not decorative. It makes color editing feel like a drafting operation instead of a disconnected form control.

### 5.4 Drawdown Visual Language

The drawdown is not a flat black-and-white matrix anymore.

Implemented behavior:

- warp-over is shown as a vertical strand
- weft-over is shown as a horizontal strand
- adjacent warp floats connect vertically
- adjacent weft floats connect horizontally

This makes the pattern readable as cloth instead of just cell data.

### 5.5 Editing Behavior

Implemented behavior:

- click to set a cell
- click-drag draws a straight connected path through the grid
- threading drag paints a path across ends
- treadling drag paints a path across picks
- tie-up drag paints a line of on or off cells based on the first cell clicked
- warp color and weft color strips also support drag painting

This is handled in `DraftBoard.tsx` with a drag state and a line interpolation helper.

## 6. Canonical Draft Contract

The canonical draft object is the backbone of the whole system.

Primary type:

File: `src/domain/types.ts`

```json
{
  "version": 1,
  "sourceType": "manual|wif|json|text|image",
  "shaftCount": 8,
  "treadleCount": 8,
  "threading": [1, 2, 3, 4],
  "tieUp": [[true, false], [false, true]],
  "treadling": [1, 2, 3, 4],
  "drawdown": [[1, 0, 1, 0]],
  "warpColors": ["#ffffff"],
  "weftColors": ["#cc0000"],
  "parseConfidence": 0.92,
  "warnings": [],
  "lowConfidenceCells": [],
  "title": "Example Draft",
  "sourceLabel": "Preset: Example",
  "renderSettings": {
    "warpThreads": 96,
    "weftThreads": 96,
    "spacing": 0.03,
    "amplitude": 0.005,
    "textureScaleV": 0.5,
    "fillRatio": 1
  }
}
```

Rules:

- `drawdown` is derived from `threading + tieUp + treadling`
- `warpColors` length matches warp ends
- `weftColors` length matches picks
- render settings belong to the draft document because preview output depends on them
- imported drafts are normalized immediately

Core implementation lives in `src/domain/draft.ts`.

## 7. Domain Logic That Must Be Reused

The following logic should move into the full app with minimal behavioral change:

- draft normalization
- drawdown computation
- count updates
- color sequence normalization
- structured text parsing
- Blender handoff generation
- focus-summary generation
- render-settings normalization

Main file:

- `prototypes/weaving-draft-studio/src/domain/draft.ts`

Most important functions:

- `normalizeDraft(...)`
- `computeDrawdown(...)`
- `updateDraftCounts(...)`
- `setThreadingShaft(...)`
- `toggleTieUpCell(...)`
- `setTreadlingTreadle(...)`
- `setWarpEndColor(...)`
- `setWeftPickColor(...)`
- `applyStructuredPatternEdit(...)`
- `applyColorSequenceEdit(...)`
- `buildBlenderHandoff(...)`
- `updateRenderSettings(...)`

## 8. Explore / Load System

Files:

- `src/components/ExploreLibrary.tsx`
- `src/domain/exploreCatalog.ts`
- `src/domain/oelsnerPatterns.ts`
- `src/domain/bookLibrary.ts`

Current model:

- built-in presets load instantly
- source books are shown as internal book pages
- Oelsner has a curated starter shelf of loadable patterns
- other books are cataloged but not yet populated with pattern-by-pattern reconstructions
- local book JSON can be imported and stored in localStorage

Important product rule:

- the shelf is book-first, not link-first
- users should browse a book, then browse patterns inside the book
- if a pattern is locally available, it should have a `Load Pattern` action

This structure should survive in the full application even if the visual style changes.

## 9. Import And Parse Strategy

There are two parsing layers on purpose.

### 9.1 Service Parsing

Implemented in Python:

- WIF parsing
- image parsing
- text parsing
- canonical normalization

Files:

- `services/draft-parser/app/wif_parser.py`
- `services/draft-parser/app/image_parser.py`
- `services/draft-parser/app/text_parser.py`
- `services/draft-parser/app/service.py`

### 9.2 Frontend Fallback Parsing

Implemented in the frontend:

- JSON fallback
- loose text fallback

File:

- `src/utils/parserApi.ts`

Why both exist:

- the UI stays usable even if the parser service is offline
- rich parsing stays in the service

## 10. Service API Contract

Service entry:

- `services/draft-parser/app/main.py`

Endpoints:

- `GET /api/parser/health`
- `POST /api/parser/parse-file`
- `POST /api/parser/parse-text`
- `GET /api/blender/health`
- `POST /api/blender/sync-draft`
- `POST /api/blender/render-draft`
- `GET /api/blender/render-jobs/{job_id}`
- `GET /api/blender/render-jobs/{job_id}/image`

Frontend utility:

- `src/utils/parserApi.ts`

Product rule:

- the frontend should call stable service endpoints
- the frontend should not know Blender CLI details, temp paths, or runtime file layout

## 11. Blender Integration Architecture

This is the most important backend integration to preserve.

### 11.1 Draft-To-Blender Model

The web UI does not send arbitrary geometry instructions.

It sends the canonical draft. Blender reconstruction is derived from:

- `drawdown`
- optional title / source metadata
- warp and weft base colors
- render settings

### 11.2 Draft Object

`services/draft-parser/app/blender_sync.py` builds a hidden Blender mesh object:

- object name default: `WebDraft_Live`
- one face per drawdown cell
- custom face attribute: `cell_code`
- `0 = weft over`
- `1 = warp over`

The mesh also stores metadata such as:

- repeat counts
- draft title
- source label
- serialized color arrays

### 11.3 Geometry Node Contract

The target object is currently:

- `ParametricWeave`

The required geometry-node group is:

- `Weave From Draft`

The sync code sets these inputs:

- `Draft Object`
- `Draft Columns`
- `Draft Rows`
- `Warp Threads`
- `Weft Threads`
- `Spacing`
- `Amplitude`
- `Texture Scale V`
- many preserved thread / fiber controls

Important behavior already implemented:

- existing modifier values are preserved where possible
- only targeted settings are overridden
- default dense repeat counts are used so the swatch is not stretched to only one coarse repeat

### 11.4 Material Hook

The sync code creates and assigns:

- `WebDraftMaterial`

It also rewires `Weave From Draft` internal `Set Material` nodes so the node tree uses that material instead of old hardcoded materials.

Current limitation:

- Blender currently uses the first warp color and first weft color as base material colors
- full per-end / per-pick color sequence rendering is not finished yet

### 11.5 Headless Render Jobs

File:

- `services/draft-parser/app/render_jobs.py`

Flow:

1. frontend posts the draft to `/api/blender/render-draft`
2. service writes job files under `services/draft-parser/runtime/render-jobs/<job_id>/`
3. service writes a Blender Python script for that draft
4. Blender runs headlessly against `Weave_GUIConnection.blend`
5. service exposes job state and preview image URL
6. frontend polls until the render succeeds or fails

Important product rule:

- render work is background work
- the browser owns polling and display
- Blender ownership stays server-side

## 12. Preview Orientation Rule

The browser preview image is intentionally rotated to feel closer to the drawdown reading direction.

Why:

- physical cloth orientation and draft notation orientation are not identical
- users compare the preview against the drawdown, not against Blender world axes

This is a deliberate UX choice, not a geometry change.

## 13. Styling And Visual Rules

Main stylesheet:

- `src/styles/index.css`

Visual principles already established:

- the drafting area should feel like one loom document, not many cards
- explanations should be hidden behind `?` hints where possible
- the inspector is secondary
- render controls belong in a separate second step
- the draft frame should stay compact and legible on desktop
- mobile can stack, but desktop should preserve the draft reading order

Do not regress back to:

- long explainer paragraphs inside the draft
- render/export controls crowding the top toolbar
- visible JSON and debugging tools in the main flow
- separated cards that break the draft-box illusion

## 14. Test Coverage

Frontend:

- `npm run build`
- `npm run test:unit`

Backend:

- `python3 -m unittest discover services/draft-parser/tests`

Covered areas:

- drawdown generation
- Blender handoff generation
- structured text parsing
- color-sequence editing
- local pattern-book parsing
- Blender sync code generation
- headless render-job generation

When porting into the full application, preserve the tests for:

- draft normalization
- orientation mapping
- drawdown computation
- Blender handoff
- render settings
- parser compatibility

## 15. Known Limitations

These are real current limitations and should be documented honestly.

- full per-thread warp / weft color rendering is not yet implemented in Blender materials
- screenshot parsing is best-effort and depends on visual quality of the source draft
- most cataloged source books do not yet have bundled pattern reconstructions
- Oelsner only has a starter set of curated loadable patterns, not the full book
- render jobs currently write runtime artifacts locally and do not yet have cleanup policies
- the prototype still uses standalone structure and should be integrated into the full app deliberately, not copied blindly

## 16. Recommended Port Into The Full Application

Port in this order:

1. Move the canonical draft schema and domain logic first.
2. Recreate the drafting workspace layout and interactions second.
3. Recreate the inspector and advanced tools third.
4. Recreate the render panel fourth.
5. Reconnect parser endpoints fifth.
6. Reconnect Blender sync and headless render jobs last.

Reason:

- the drafting model must be stable before Blender integration becomes meaningful

## 17. File Map To Reuse

Frontend files with the highest reuse value:

- `prototypes/weaving-draft-studio/src/domain/types.ts`
- `prototypes/weaving-draft-studio/src/domain/draft.ts`
- `prototypes/weaving-draft-studio/src/domain/presets.ts`
- `prototypes/weaving-draft-studio/src/domain/exploreCatalog.ts`
- `prototypes/weaving-draft-studio/src/domain/oelsnerPatterns.ts`
- `prototypes/weaving-draft-studio/src/domain/bookLibrary.ts`
- `prototypes/weaving-draft-studio/src/components/DraftStudio.tsx`
- `prototypes/weaving-draft-studio/src/components/StudioToolbar.tsx`
- `prototypes/weaving-draft-studio/src/components/DraftBoard.tsx`
- `prototypes/weaving-draft-studio/src/components/InspectorPanel.tsx`
- `prototypes/weaving-draft-studio/src/components/RenderPanel.tsx`
- `prototypes/weaving-draft-studio/src/components/ExploreLibrary.tsx`
- `prototypes/weaving-draft-studio/src/utils/parserApi.ts`
- `prototypes/weaving-draft-studio/src/styles/index.css`

Backend files with the highest reuse value:

- `services/draft-parser/app/main.py`
- `services/draft-parser/app/service.py`
- `services/draft-parser/app/text_parser.py`
- `services/draft-parser/app/wif_parser.py`
- `services/draft-parser/app/image_parser.py`
- `services/draft-parser/app/blender_sync.py`
- `services/draft-parser/app/render_jobs.py`

## 18. Integration Checklist

Before calling the subsystem fully integrated into the main application, confirm:

- the canonical draft model is unchanged or deliberately versioned
- the draft workspace still reads as one connected box
- orientation still starts from the tie-up corner
- drag editing works for structure and color strips
- the inspector stays secondary
- render controls stay in step two
- parser fallback still works when the service is offline
- headless Blender render jobs still accept the same draft shape
- `Weave From Draft` still exists in the blend file and exposes the expected sockets
- preview images still visually align with the drawdown

## 19. Short Summary

The subsystem is not just a pattern editor. It is a small end-to-end product slice:

- source browsing
- manual drafting
- structural understanding
- color editing
- parser-backed intake
- Blender-ready export
- headless preview rendering

When you move this into the full application, preserve the contract and the workflow first. The visual styling can evolve, but the drafting rules, orientation rules, and Blender handoff rules should stay stable unless we intentionally version them.
