# Presets

The user should mostly **not** dial raw numbers. There are two independent
preset layers:

1. **Render-quality presets** — how fast/clean the Cycles frame is.
2. **Weave-control presets** — named bundles of the exposed weave-control values.

They are orthogonal: a user can render a "Loose Drape" control preset at "draft"
quality while exploring, then bump to "crisp" for a final look before leaving
Live Preview for the full render.

## Render-quality presets

The three tiers from [render_profile.md](render_profile.md#quality-tiers-preset-selectable),
surfaced as a selector in the live panel. Stored as a declarative table so
tuning is a data edit, not a code change:

```ts
// frontend/src/domain/livePreview.ts (proposed)
export const LIVE_QUALITY_TIERS = [
  { key: 'draft',    label: 'Draft',    res: 960,  note: 'Fast structural check' },
  { key: 'balanced', label: 'Balanced', res: 1280, note: 'Default' },
  { key: 'crisp',    label: 'Crisp',    res: 1600, note: 'Closest to the full render' },
] as const;
```

The numeric render settings behind each tier (samples, adaptive threshold,
denoiser, time limit, JPEG quality) live on the **backend** so the
authoritative profile is server-side and overridable by env
(`WEAVE_LIVE_PREVIEW_*`). The frontend only sends the tier `key`.

Default tier: `balanced` (`WEAVE_LIVE_PREVIEW_DEFAULT_TIER`). The machine is
fast, so defaulting above "draft" is intentional.

## Weave-control presets

Named bundles of the five exposed controls
([RenderPanel.tsx:20](../../frontend/src/components/RenderPanel.tsx#L20)):
Weave Zoom (thread count), Spacing, Pattern Noise X, Pattern Noise Y, Texture U
Scatter, Arc 1 V Padding.

Clicking a preset stages all of its values and fires **one** frame — the user
never touches a number unless they want to.

```ts
// frontend/src/domain/livePreview.ts (proposed)
export interface WeaveControlPreset {
  key: string;
  label: string;
  note?: string;
  settings: Partial<DraftRenderSettings>;   // same keys the full render accepts
}

export const WEAVE_CONTROL_PRESETS: WeaveControlPreset[] = [
  {
    key: 'tight-plain',
    label: 'Tight Plain',
    note: 'Dense, crisp weave',
    settings: { spacing: 0.02, patternNoiseX: 0, patternNoiseY: 0, uvRandomU: 0, arc1VPadding: 0.02 },
  },
  {
    key: 'loose-drape',
    label: 'Loose Drape',
    note: 'Open, relaxed spacing',
    settings: { spacing: 0.06, patternNoiseX: 0.2, patternNoiseY: 0.2, uvRandomU: 4, arc1VPadding: 0.04 },
  },
  {
    key: 'hand-woven',
    label: 'Hand-woven',
    note: 'Irregular, organic',
    settings: { spacing: 0.045, patternNoiseX: 0.4, patternNoiseY: 0.4, uvRandomU: 8, arc1VPadding: 0.05 },
  },
];
```

Notes:

- Values above are **placeholders** for shape; the real defaults must be dialed
  on the actual `.blend` and the winners recorded in
  [phase_log.md](phase_log.md). The exposed-control ranges/steps are defined in
  [RenderPanel.tsx](../../frontend/src/components/RenderPanel.tsx#L20).
- `settings` uses the same keys as `DraftRenderSettings`, so a preset is just a
  pre-filled `settings` object on the frame request
  ([data_contract.md](data_contract.md#post-apiblenderlive-previewsessionsessionidframe--tweak)).
  The backend already maps these to sockets in
  [blender_sync.py](../../backend/app/blender_sync.py#L150) (`map_unit_setting`,
  etc.) — presets need **no** new backend mapping.
- A preset can omit keys; omitted keys keep their current staged value. This
  lets a preset be "just spacing + padding" without forcing the noise fields.
- Presets are not live-preview-only — the same table can back quick-start
  buttons in the normal render panel later. Keep it in `domain/`, not inside the
  live component.

## How a preset click flows

```
click "Loose Drape"
  → stage settings into the control inputs (so the user can then fine-tune)
  → POST /live-preview/session/{id}/frame { controlPreset: 'loose-drape', seq, tier }
  → one Cycles frame returns → <img> swaps
```

Either the frontend expands the preset into `settings` before sending, or it
sends `controlPreset` and the backend expands it from a mirrored table. Prefer
**frontend expansion** (single source of preset truth in `domain/`, backend
stays a thin applier); send `controlPreset` only as a label for telemetry.

## Acceptance

- Selecting a quality tier changes only speed/clarity, never camera, materials,
  or color.
- Selecting a control preset stages all its values into the visible inputs and
  renders exactly one frame.
- Presets are defined in one declarative table; adding a preset is a one-object
  edit with no backend change.
