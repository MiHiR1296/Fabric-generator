import { useMemo } from 'react';
import type { Dispatch, SetStateAction } from 'react';
import { deriveColorBindingSlots, missingColorBindings } from '../domain/project';
import type { ColorBinding, DraftDocument, YarnAsset } from '../domain/types';

interface ColorBindingGridProps {
  draft: DraftDocument;
  yarnAssets: YarnAsset[];
  colorBindings: ColorBinding[];
  setColorBindings: Dispatch<SetStateAction<ColorBinding[]>>;
  eyebrow?: string;
  title?: string;
  summary?: string;
  compact?: boolean;
}

export default function ColorBindingGrid({
  draft,
  yarnAssets,
  colorBindings,
  setColorBindings,
  eyebrow = 'Color → Yarn Mapping',
  title = 'Assign yarns to draft colors',
  summary = 'Pick a processed yarn for every warp and weft color slot in the draft.',
  compact = false,
}: ColorBindingGridProps) {
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
    <section
      className={`card fabric-step-card${compact ? ' fabric-step-card--compact' : ''}`}
      data-testid="color-binding-grid"
    >
      <div className="fabric-step-card__header">
        <div>
          <p className="eyebrow">{eyebrow}</p>
          <h2>{title}</h2>
          {!compact ? <p className="fabric-step-card__summary">{summary}</p> : null}
        </div>
        <div className="fabric-step-card__actions">
          <div className="status-pill status-pill--source">Slots: {slots.length}</div>
          <div className="status-pill status-pill--online">Ready Yarns: {readyAssets.length}</div>
        </div>
      </div>

      {slots.length ? (
        <div className={`color-binding-grid${compact ? ' color-binding-grid--compact' : ''}`}>
          {slots.map((slot) => {
            const binding = colorBindings.find(
              (entry) =>
                entry.scope === slot.scope &&
                entry.colorHex.toLowerCase() === slot.colorHex.toLowerCase(),
            );
            const selectedAsset = binding?.yarnAssetId
              ? yarnAssets.find((asset) => asset.id === binding.yarnAssetId)
              : null;
            const previewUrl = selectedAsset?.diffuseUrl || selectedAsset?.sourceUrl;
            return (
              <label className="color-binding-card" key={slot.key}>
                <span className="color-binding-card__label">
                  <span
                    className="color-binding-card__swatch"
                    style={{ background: slot.colorHex }}
                  />
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
                    <span
                      className="color-binding-card__preview color-binding-card__preview--empty"
                      aria-hidden="true"
                    />
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
          <span>
            The pattern builder will create slots once the draft contains warp and weft color
            sequences.
          </span>
        </div>
      )}

      <p className="muted" data-testid="binding-status-message">
        {missingBindingsList.length
          ? `${missingBindingsList.length} slot${missingBindingsList.length === 1 ? '' : 's'} still need yarn assignments before rendering.`
          : 'Every visible draft color is assigned to a processed yarn asset.'}
      </p>
    </section>
  );
}
