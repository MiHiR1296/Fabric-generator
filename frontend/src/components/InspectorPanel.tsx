import { useEffect, useState } from 'react';
import {
  getDraftPalette,
  getFocusSummary,
  serializeBlenderHandoff,
  serializeColorSequenceText,
  serializeDraft,
  serializeDrawdownText,
  serializeSequenceText,
  serializeTieUpEditorText,
} from '../domain/draft';
import type { DraftDocument, FocusedDrawdownCell } from '../domain/types';

interface InspectorPanelProps {
  draft: DraftDocument;
  focus: FocusedDrawdownCell | null;
  activeColor: string;
  importMessage: string;
  pastedText: string;
  onPastedTextChange: (value: string) => void;
  onParsePastedText: () => void;
  onActiveColorChange: (value: string) => void;
  onApplyColorEdit: (edits: {
    warpColorsText?: string;
    weftColorsText?: string;
  }) => void;
  onApplyStructuredEdit: (edits: {
    threadingText?: string;
    tieUpText?: string;
    treadlingText?: string;
  }) => void;
}

export default function InspectorPanel({
  draft,
  focus,
  activeColor,
  importMessage,
  pastedText,
  onPastedTextChange,
  onParsePastedText,
  onActiveColorChange,
  onApplyColorEdit,
  onApplyStructuredEdit,
}: InspectorPanelProps) {
  const summary = getFocusSummary(draft, focus);
  const palette = [activeColor, ...getDraftPalette(draft).filter((color) => color !== activeColor)];
  const [threadingText, setThreadingText] = useState('');
  const [tieUpText, setTieUpText] = useState('');
  const [treadlingText, setTreadlingText] = useState('');
  const [warpColorsText, setWarpColorsText] = useState('');
  const [weftColorsText, setWeftColorsText] = useState('');
  const [copyState, setCopyState] = useState('');

  useEffect(() => {
    setThreadingText(serializeSequenceText(draft.threading));
    setTieUpText(serializeTieUpEditorText(draft.tieUp));
    setTreadlingText(serializeSequenceText(draft.treadling));
    setWarpColorsText(serializeColorSequenceText(draft.warpColors));
    setWeftColorsText(serializeColorSequenceText(draft.weftColors));
  }, [draft]);

  const copyText = async (label: string, value: string) => {
    try {
      await navigator.clipboard.writeText(value);
      setCopyState(`${label} copied.`);
      window.setTimeout(() => setCopyState(''), 1600);
    } catch {
      setCopyState(`Could not copy ${label.toLowerCase()} in this browser.`);
      window.setTimeout(() => setCopyState(''), 2200);
    }
  };

  return (
    <aside className="inspector" data-testid="inspector-panel">
      <section className="card inspector__card">
        <p className="eyebrow">Understanding Layer</p>
        <h2>{summary.title}</h2>
        <p>{summary.body}</p>

        {summary.shaft != null ? (
          <div className="inspector__facts">
            <div>
              <span>Shaft</span>
              <strong>{summary.shaft}</strong>
            </div>
            <div>
              <span>Treadle</span>
              <strong>{summary.treadle}</strong>
            </div>
            <div>
              <span>Result</span>
              <strong>{summary.warpOver ? 'Warp Over' : 'Weft Over'}</strong>
            </div>
          </div>
        ) : null}
      </section>

      <section className="card inspector__card">
        <p className="eyebrow">Draft Color Editor</p>
        <h2>Pick the yarn colors</h2>
        <p className="muted">Paint the warp or weft strip with the active color.</p>

        <div className="color-editor__toolbar">
          <label className="field field--compact color-editor__picker">
            <span>Active Color</span>
            <input
              className="color-editor__input"
              type="color"
              value={activeColor}
              onChange={(event) => onActiveColorChange(event.target.value)}
            />
          </label>

          <div className="color-editor__active">
            <span
              className="color-editor__active-swatch"
              style={{ backgroundColor: activeColor }}
              aria-hidden="true"
            />
            <strong>{activeColor}</strong>
          </div>
        </div>

        <div className="color-editor__swatches">
          {palette.map((color) => (
            <button
              key={color}
              className={[
                'color-editor__swatch',
                color === activeColor ? 'color-editor__swatch--active' : '',
              ].join(' ')}
              style={{ backgroundColor: color }}
              onClick={() => onActiveColorChange(color)}
              title={`Use ${color}`}
            />
          ))}
        </div>
      </section>

      <details className="card inspector__card inspector__advanced">
        <summary>Advanced Draft Tools</summary>

        <div className="section-editor">
          <div className="section-editor__header">
            <strong>Warp Colors</strong>
            <div className="section-editor__actions">
              <button className="button button--tiny" onClick={() => copyText('Warp colors', warpColorsText)}>
                Copy
              </button>
              <button
                className="button button--tiny"
                onClick={() => onApplyColorEdit({ warpColorsText })}
              >
                Apply
              </button>
            </div>
          </div>
          <textarea
            value={warpColorsText}
            onChange={(event) => setWarpColorsText(event.target.value)}
          />
        </div>

        <div className="section-editor">
          <div className="section-editor__header">
            <strong>Weft Colors</strong>
            <div className="section-editor__actions">
              <button className="button button--tiny" onClick={() => copyText('Weft colors', weftColorsText)}>
                Copy
              </button>
              <button
                className="button button--tiny"
                onClick={() => onApplyColorEdit({ weftColorsText })}
              >
                Apply
              </button>
            </div>
          </div>
          <textarea
            value={weftColorsText}
            onChange={(event) => setWeftColorsText(event.target.value)}
          />
        </div>

        <div className="section-editor">
          <div className="section-editor__header">
            <strong>Threading</strong>
            <div className="section-editor__actions">
              <button className="button button--tiny" onClick={() => copyText('Threading', threadingText)}>
                Copy
              </button>
              <button
                className="button button--tiny"
                onClick={() => onApplyStructuredEdit({ threadingText })}
              >
                Apply
              </button>
            </div>
          </div>
          <textarea
            value={threadingText}
            onChange={(event) => setThreadingText(event.target.value)}
          />
        </div>

        <div className="section-editor">
          <div className="section-editor__header">
            <strong>Tie-Up</strong>
            <div className="section-editor__actions">
              <button className="button button--tiny" onClick={() => copyText('Tie-Up', tieUpText)}>
                Copy
              </button>
              <button
                className="button button--tiny"
                onClick={() => onApplyStructuredEdit({ tieUpText })}
              >
                Apply
              </button>
            </div>
          </div>
          <textarea
            value={tieUpText}
            onChange={(event) => setTieUpText(event.target.value)}
          />
        </div>

        <div className="section-editor">
          <div className="section-editor__header">
            <strong>Treadling</strong>
            <div className="section-editor__actions">
              <button className="button button--tiny" onClick={() => copyText('Treadling', treadlingText)}>
                Copy
              </button>
              <button
                className="button button--tiny"
                onClick={() => onApplyStructuredEdit({ treadlingText })}
              >
                Apply
              </button>
            </div>
          </div>
          <textarea
            value={treadlingText}
            onChange={(event) => setTreadlingText(event.target.value)}
          />
        </div>

        <div className="section-editor__row">
          <button
            className="button button--accent"
            onClick={() => onApplyStructuredEdit({ threadingText, tieUpText, treadlingText })}
          >
            Apply All Sections
          </button>
          <button
            className="button"
            onClick={() => copyText('Drawdown', serializeDrawdownText(draft.drawdown))}
          >
            Copy Drawdown
          </button>
        </div>

        <div className="inspector__advanced-block">
          <h3>Source Status</h3>
          <p>{importMessage}</p>
          {draft.warnings.length > 0 ? (
            <ul className="warning-list">
              {draft.warnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          ) : (
            <p className="muted">No import warnings on the current draft.</p>
          )}
          <p className="muted">Parse confidence: {Math.round(draft.parseConfidence * 100)}%</p>
          <p className="muted">Review flags: {(draft.lowConfidenceCells || []).length}</p>
        </div>

        <div className="inspector__advanced-block">
          <h3>Paste Intake</h3>
          <textarea
            data-testid="paste-input"
            value={pastedText}
            onChange={(event) => onPastedTextChange(event.target.value)}
            placeholder="threading: 1 2 3 4&#10;tieup:&#10;1 0 1 0&#10;0 1 0 1&#10;treadling: 1 2 1 2"
          />
          <button
            className="button button--accent button--wide"
            data-testid="parse-pasted-button"
            onClick={onParsePastedText}
          >
            Parse Pasted Input
          </button>
        </div>

        <div className="inspector__advanced-block">
          <h3>Export Preview</h3>
          <pre>{serializeDraft(draft)}</pre>
          <pre>{serializeBlenderHandoff(draft)}</pre>
        </div>

        {copyState ? <p className="muted">{copyState}</p> : null}
      </details>
    </aside>
  );
}
