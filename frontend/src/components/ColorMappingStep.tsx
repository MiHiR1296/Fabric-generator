import { useMemo } from 'react';
import type { Dispatch, SetStateAction } from 'react';
import RenderPanel from './RenderPanel';
import { deriveColorBindingSlots, missingColorBindings } from '../domain/project';
import type { BlenderLivePreview, ColorBinding, DraftDocument, DraftRenderSettings, YarnAsset } from '../domain/types';

interface ColorMappingStepProps {
  draft: DraftDocument;
  yarnAssets: YarnAsset[];
  colorBindings: ColorBinding[];
  setColorBindings: Dispatch<SetStateAction<ColorBinding[]>>;
  livePreview: BlenderLivePreview | null;
  previewBusy: boolean;
  previewMessage: string;
  onUpdatePreview: (settings: Partial<DraftRenderSettings>) => void;
  onExportCanonical: () => void;
  onExportBlender: () => void;
}

export default function ColorMappingStep({
  draft,
  yarnAssets,
  colorBindings,
  setColorBindings,
  livePreview,
  previewBusy,
  previewMessage,
  onUpdatePreview,
  onExportCanonical,
  onExportBlender,
}: ColorMappingStepProps) {
  const slots = useMemo(() => deriveColorBindingSlots(draft), [draft]);
  const readyAssets = useMemo(
    () => yarnAssets.filter((asset) => asset.status === 'ready'),
    [yarnAssets],
  );
  const missingBindingsList = useMemo(
    () => missingColorBindings(slots, colorBindings),
    [slots, colorBindings],
  );

  return (
    <section className="fabric-step-panel" data-testid="color-mapping-step">
      <section className="card fabric-step-card">
        <div className="fabric-step-card__header">
          <div>
            <p className="eyebrow">Step 3</p>
            <h2>Color To Yarn Mapping</h2>
            <p className="fabric-step-card__summary">
              Each unique warp and weft color becomes a binding slot. Assign a processed yarn asset to every slot before rendering.
            </p>
          </div>
          <div className="fabric-step-card__actions">
            <div className="status-pill status-pill--source">Slots: {slots.length}</div>
            <div className="status-pill status-pill--online">Ready Yarns: {readyAssets.length}</div>
          </div>
        </div>

        {slots.length ? (
          <div className="color-binding-grid">
            {slots.map((slot) => {
              const binding = colorBindings.find(
                (entry) => entry.scope === slot.scope && entry.colorHex.toLowerCase() === slot.colorHex.toLowerCase(),
              );
              return (
                <label className="color-binding-card" key={slot.key}>
                  <span className="color-binding-card__label">
                    <span className="color-binding-card__swatch" style={{ background: slot.colorHex }} />
                    <span>{slot.label}</span>
                  </span>
                  <select
                    value={binding?.yarnAssetId || ''}
                    data-testid={`binding-select-${slot.key}`}
                    onChange={(event) => {
                      const yarnAssetId = event.target.value || null;
                      setColorBindings((current) =>
                        current.map((entry) =>
                          entry.scope === slot.scope && entry.colorHex === slot.colorHex
                            ? { ...entry, yarnAssetId }
                            : entry,
                        ),
                      );
                    }}
                  >
                    <option value="">Select processed yarn</option>
                    {readyAssets.map((asset) => (
                      <option key={asset.id} value={asset.id}>
                        {asset.label}
                      </option>
                    ))}
                  </select>
                </label>
              );
            })}
          </div>
        ) : (
          <div className="fabric-empty-state">
            <strong>No color slots yet</strong>
            <span>The pattern builder will create slots once the draft contains warp and weft color sequences.</span>
          </div>
        )}

        <p className="muted" data-testid="binding-status-message">
          {missingBindingsList.length
            ? `${missingBindingsList.length} slot${missingBindingsList.length === 1 ? '' : 's'} still need yarn assignments before previewing.`
            : 'Every visible draft color is assigned to a processed yarn asset.'}
        </p>
      </section>

      <RenderPanel
        draft={draft}
        importMessage=""
        livePreview={livePreview}
        previewBusy={previewBusy}
        onUpdatePreview={onUpdatePreview}
        onExportCanonical={onExportCanonical}
        onExportBlender={onExportBlender}
        stepLabel="Step 3"
        title="Blender Material Preview"
        summaryText="Adjust the geometry-node controls locally, then click Update Preview to refresh the live Blender camera preview."
        statusMessage={previewMessage}
        renderDisabled={!readyAssets.length || missingBindingsList.length > 0}
      />
    </section>
  );
}
