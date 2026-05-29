import { useMemo } from 'react';
import type { Dispatch, SetStateAction } from 'react';
import RenderPanel from './RenderPanel';
import { deriveColorBindingSlots, missingColorBindings } from '../domain/project';
import type { BlenderRenderJob, ColorBinding, DraftDocument, TileRenderOptions, YarnAsset } from '../domain/types';

interface ColorMappingStepProps {
  draft: DraftDocument;
  yarnAssets: YarnAsset[];
  colorBindings: ColorBinding[];
  setColorBindings: Dispatch<SetStateAction<ColorBinding[]>>;
  renderJob: BlenderRenderJob | null;
  renderBusy: boolean;
  liveBlenderBusy?: boolean;
  tileJob?: BlenderRenderJob | null;
  tileBusy?: boolean;
  activePreviewMode?: 'render' | 'tile';
  renderMessage: string;
  tileMessage?: string;
  onRenderPreview: () => void;
  onSendToLiveBlender?: () => void;
  onRenderTiles?: (options: TileRenderOptions) => void;
  onExportCanonical: () => void;
  onExportBlender: () => void;
  onApplyRenderSettings: (settings: {
    warpThreads?: number;
    weftThreads?: number;
    spacing?: number;
    amplitude?: number;
    textureScaleV?: number;
    fillRatio?: number;
  }) => void;
  showRender?: boolean;
  showBindings?: boolean;
}

export default function ColorMappingStep({
  draft,
  yarnAssets,
  colorBindings,
  setColorBindings,
  renderJob,
  renderBusy,
  liveBlenderBusy,
  tileJob,
  tileBusy,
  activePreviewMode,
  renderMessage,
  tileMessage,
  onRenderPreview,
  onSendToLiveBlender,
  onRenderTiles,
  onExportCanonical,
  onExportBlender,
  onApplyRenderSettings,
  showRender = true,
  showBindings = true,
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
      {showBindings ? (
      <section className="card fabric-step-card">
        <div className="fabric-step-card__header">
          <div>
            <p className="eyebrow">Step 3</p>
            <h2>Color To Yarn Mapping</h2>
            <p className="fabric-step-card__summary">
              Assign a processed yarn to every warp and weft color slot.
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
              const selectedAsset = binding?.yarnAssetId
                ? yarnAssets.find((asset) => asset.id === binding.yarnAssetId)
                : null;
              const previewUrl = selectedAsset?.diffuseUrl || selectedAsset?.sourceUrl;
              return (
                <label className="color-binding-card" key={slot.key}>
                  <span className="color-binding-card__label">
                    <span className="color-binding-card__swatch" style={{ background: slot.colorHex }} />
                    <span>{slot.label}</span>
                  </span>
                  <div className="color-binding-card__yarn">
                    {previewUrl ? (
                      <img
                        className="color-binding-card__preview"
                        src={previewUrl}
                        alt={`${selectedAsset?.label || 'Yarn'} preview`}
                        title={selectedAsset?.label}
                      />
                    ) : (
                      <span className="color-binding-card__preview color-binding-card__preview--empty" aria-hidden="true" />
                    )}
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
                  </div>
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
            ? `${missingBindingsList.length} slot${missingBindingsList.length === 1 ? '' : 's'} still need yarn assignments before rendering.`
            : 'Every visible draft color is assigned to a processed yarn asset.'}
        </p>
      </section>
      ) : null}

      {showRender ? (
        <RenderPanel
          draft={draft}
          importMessage=""
          renderJob={renderJob}
          renderBusy={renderBusy}
          liveBlenderBusy={liveBlenderBusy}
          tileJob={tileJob}
          tileBusy={tileBusy}
          activePreviewMode={activePreviewMode}
          onRenderPreview={onRenderPreview}
          onSendToLiveBlender={onSendToLiveBlender}
          onRenderTiles={onRenderTiles}
          onExportCanonical={onExportCanonical}
          onExportBlender={onExportBlender}
          onApplyRenderSettings={onApplyRenderSettings}
          stepLabel="Step 3"
          title="Render Preview"
          summaryText="Render the woven draft in Blender and compare against the drawdown."
          statusMessage={renderMessage}
          tileStatusMessage={tileMessage}
          renderDisabled={!readyAssets.length || missingBindingsList.length > 0}
        />
      ) : null}
    </section>
  );
}
