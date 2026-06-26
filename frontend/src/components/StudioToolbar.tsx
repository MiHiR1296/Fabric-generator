import { useEffect, useState } from 'react';
import type {
  DraftCounts,
  DraftDocument,
  FabricStructureType,
  ParserStatus,
  PresetDefinition,
} from '../domain/types';

interface StudioToolbarProps {
  counts: DraftCounts;
  draft: DraftDocument;
  parserStatus: ParserStatus;
  presets: PresetDefinition[];
  busy: boolean;
  exploreOpen: boolean;
  onPresetChange: (presetId: string) => void;
  onToggleExplore: () => void;
  onCountsChange: (field: keyof DraftCounts, value: number) => void;
  onSavePattern?: () => void;
  onImportClick: () => void;
  onReset: () => void;
  structureType?: FabricStructureType;
  onStructureTypeChange?: (structureType: FabricStructureType) => void;
  showDraftControls?: boolean;
  stepLabel?: string;
  title?: string;
  summaryText?: string;
}

function CountField({
  label,
  value,
  min,
  max,
  testId,
  onCommit,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  testId: string;
  onCommit: (value: number) => void;
}) {
  const [draftValue, setDraftValue] = useState(String(value));

  useEffect(() => {
    setDraftValue(String(value));
  }, [value]);

  const commit = () => {
    const parsed = Number(draftValue);
    if (!Number.isFinite(parsed)) {
      setDraftValue(String(value));
      return;
    }
    const clamped = Math.min(max, Math.max(min, Math.round(parsed)));
    setDraftValue(String(clamped));
    onCommit(clamped);
  };

  return (
    <label className="field field--compact">
      <span>{label}</span>
      <input
        type="text"
        inputMode="numeric"
        value={draftValue}
        data-testid={testId}
        onChange={(event) => setDraftValue(event.target.value)}
        onBlur={commit}
        onKeyDown={(event) => {
          if (event.key === 'Enter') {
            commit();
          }
          if (event.key === 'Escape') {
            setDraftValue(String(value));
          }
        }}
      />
    </label>
  );
}

function parserLabel(status: ParserStatus) {
  if (status === 'online') {
    return 'Parser online';
  }
  if (status === 'offline') {
    return 'Parser offline';
  }
  return 'Checking parser';
}

export default function StudioToolbar({
  counts,
  draft,
  parserStatus,
  presets,
  busy,
  exploreOpen,
  onPresetChange,
  onToggleExplore,
  onCountsChange,
  onSavePattern,
  onImportClick,
  onReset,
  structureType = 'weave',
  onStructureTypeChange,
  showDraftControls = true,
  stepLabel = 'Step 1',
  title = 'Weaving Draft Studio',
  summaryText = 'Create or load the draft first. Once the structure feels right, move down to the render step.',
}: StudioToolbarProps) {
  return (
    <header className="toolbar" data-testid="studio-toolbar">
      <div className="toolbar__intro">
        <p className="eyebrow">{stepLabel}</p>
        <h1>{title}</h1>
        <p className="toolbar__summary">{summaryText}</p>
      </div>

      <div className="toolbar__controls">
        {onStructureTypeChange ? (
          <div className="toolbar__row toolbar__row--mode" role="group" aria-label="Pattern workflow">
            <button
              type="button"
              className={`button${structureType === 'weave' ? ' button--accent' : ''}`}
              aria-pressed={structureType === 'weave'}
              onClick={() => onStructureTypeChange('weave')}
              data-testid="workflow-weave-button"
            >
              Weave
            </button>
            <button
              type="button"
              className={`button${structureType === 'hook' ? ' button--accent' : ''}`}
              aria-pressed={structureType === 'hook'}
              onClick={() => onStructureTypeChange('hook')}
              data-testid="workflow-hook-button"
            >
              Knit / Hook
            </button>
          </div>
        ) : null}

        {showDraftControls ? (
        <>
          <div className="toolbar__row">
          <label className="field">
            <span>Quick Load</span>
            <select
              data-testid="preset-select"
              onChange={(event) => onPresetChange(event.target.value)}
              defaultValue=""
            >
              <option value="" disabled>
                Load preset directly
              </option>
              {presets.map((preset) => (
                <option key={preset.id} value={preset.id}>
                  {preset.label}
                </option>
              ))}
            </select>
          </label>

          <button className="button" onClick={onToggleExplore} data-testid="explore-library-button">
            {exploreOpen ? 'Hide Explore / Load' : 'Explore / Load'}
          </button>

          {onSavePattern ? (
            <button
              className="button button--accent"
              onClick={onSavePattern}
              data-testid="save-pattern-button"
            >
              Save Pattern
            </button>
          ) : null}

          <button
            className="button"
            onClick={onImportClick}
            disabled={busy}
            data-testid="import-file-button"
          >
            {busy ? 'Importing…' : 'Import File'}
          </button>
          <button className="button button--ghost" onClick={onReset} data-testid="reset-draft-button">
            Reset Draft
          </button>
          </div>

          <div className="toolbar__row toolbar__row--counts">
          <CountField
            label="Shafts"
            value={counts.shaftCount}
            min={2}
            max={32}
            testId="shaft-count-input"
            onCommit={(value) => onCountsChange('shaftCount', value)}
          />
          <CountField
            label="Treadles"
            value={counts.treadleCount}
            min={2}
            max={32}
            testId="treadle-count-input"
            onCommit={(value) => onCountsChange('treadleCount', value)}
          />
          <CountField
            label="Warp Ends"
            value={counts.warpEnds}
            min={4}
            max={256}
            testId="warp-ends-input"
            onCommit={(value) => onCountsChange('warpEnds', value)}
          />
          <CountField
            label="Picks"
            value={counts.picks}
            min={4}
            max={256}
            testId="picks-input"
            onCommit={(value) => onCountsChange('picks', value)}
          />

          <p className="toolbar__counts-hint">
            Type freely, then press Enter or click away to apply.
          </p>

          <div className={`status-pill status-pill--${parserStatus}`}>
            {parserLabel(parserStatus)}
          </div>
          <div className="status-pill status-pill--source">
            Source: {draft.sourceType.toUpperCase()}
          </div>
          </div>
        </>
        ) : (
          <div className="toolbar__row">
            <div className={`status-pill status-pill--${parserStatus}`}>
              {parserLabel(parserStatus)}
            </div>
            <div className="status-pill status-pill--source">Source: HOOK PRESET</div>
          </div>
        )}
      </div>
    </header>
  );
}
