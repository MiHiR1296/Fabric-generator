import { useEffect, useState } from 'react';
import type { BlenderRenderJob, DraftDocument } from '../domain/types';

interface RenderPanelProps {
  draft: DraftDocument;
  importMessage: string;
  renderJob: BlenderRenderJob | null;
  renderBusy: boolean;
  onRenderPreview: () => void;
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
  stepLabel?: string;
  title?: string;
  summaryText?: string;
  statusMessage?: string;
  renderDisabled?: boolean;
}

export default function RenderPanel({
  draft,
  importMessage,
  renderJob,
  renderBusy,
  onRenderPreview,
  onExportCanonical,
  onExportBlender,
  onApplyRenderSettings,
  stepLabel = 'Step 2',
  title = 'Render Preview',
  summaryText,
  statusMessage,
  renderDisabled = false,
}: RenderPanelProps) {
  const [renderWarpThreads, setRenderWarpThreads] = useState('');
  const [renderWeftThreads, setRenderWeftThreads] = useState('');
  const [renderSpacing, setRenderSpacing] = useState('');
  const [renderAmplitude, setRenderAmplitude] = useState('');
  const [renderTextureScaleV, setRenderTextureScaleV] = useState('');
  const [renderFillRatio, setRenderFillRatio] = useState('');

  useEffect(() => {
    setRenderWarpThreads(String(draft.renderSettings?.warpThreads || ''));
    setRenderWeftThreads(String(draft.renderSettings?.weftThreads || ''));
    setRenderSpacing(String(draft.renderSettings?.spacing || ''));
    setRenderAmplitude(String(draft.renderSettings?.amplitude || ''));
    setRenderTextureScaleV(String(draft.renderSettings?.textureScaleV || ''));
    setRenderFillRatio(String(draft.renderSettings?.fillRatio || ''));
  }, [draft]);

  const renderRunning =
    renderBusy || renderJob?.status === 'queued' || renderJob?.status === 'running';
  const renderActive = renderRunning || renderDisabled;

  return (
    <section className="card render-panel" data-testid="render-panel">
      <div className="render-panel__header">
        <div>
          <p className="eyebrow">{stepLabel}</p>
          <h2>{title}</h2>
          <p className="render-panel__summary">
            {summaryText || importMessage || 'When the draft is ready, render it through Blender and review the swatch here.'}
          </p>
        </div>

        <div className="render-panel__actions">
          <button
            className="button button--accent"
            onClick={onRenderPreview}
            disabled={renderActive}
            data-testid="render-preview-button"
          >
            {renderRunning ? 'Rendering Preview…' : 'Render Preview'}
          </button>
          <button className="button" onClick={onExportCanonical} data-testid="export-canonical-button">
            Export Draft JSON
          </button>
          <button className="button" onClick={onExportBlender} data-testid="export-blender-button">
            Export Blender Map
          </button>
        </div>
      </div>

      {statusMessage ? (
        <p className="muted" data-testid="render-status-message">
          {statusMessage}
        </p>
      ) : null}

      <div className="render-panel__body">
        <div className="render-panel__controls">
          <div className="board-section__heading">
            <div>
              <h3>Blender Controls</h3>
              <p>Adjust the swatch density and relief before you rerender.</p>
            </div>
          </div>

          <div className="render-settings">
            <label className="field field--compact">
              <span>Warp Threads</span>
              <input value={renderWarpThreads} onChange={(event) => setRenderWarpThreads(event.target.value)} />
            </label>
            <label className="field field--compact">
              <span>Weft Threads</span>
              <input value={renderWeftThreads} onChange={(event) => setRenderWeftThreads(event.target.value)} />
            </label>
            <label className="field field--compact">
              <span>Spacing</span>
              <input value={renderSpacing} onChange={(event) => setRenderSpacing(event.target.value)} />
            </label>
            <label className="field field--compact">
              <span>Amplitude</span>
              <input value={renderAmplitude} onChange={(event) => setRenderAmplitude(event.target.value)} />
            </label>
            <label className="field field--compact">
              <span>Texture Scale V</span>
              <input value={renderTextureScaleV} onChange={(event) => setRenderTextureScaleV(event.target.value)} />
            </label>
            <label className="field field--compact">
              <span>Fill Ratio</span>
              <input value={renderFillRatio} onChange={(event) => setRenderFillRatio(event.target.value)} />
            </label>
          </div>

          <div className="section-editor__row">
            <button
              className="button"
              onClick={() =>
                onApplyRenderSettings({
                  warpThreads: Number(renderWarpThreads),
                  weftThreads: Number(renderWeftThreads),
                  spacing: Number(renderSpacing),
                  amplitude: Number(renderAmplitude),
                  textureScaleV: Number(renderTextureScaleV),
                  fillRatio: Number(renderFillRatio),
                })
              }
            >
              Apply Blender Controls
            </button>
          </div>

          <p className="muted">
            The preview is rotated to match drawdown reading direction, so it feels closer to the draft
            you just built.
          </p>
        </div>

        <div className="render-panel__preview">
          <div className="render-preview render-preview--panel">
            {renderJob?.imageUrl ? (
              <img
                className="render-preview__image render-preview__image--draft-aligned"
                src={renderJob.imageUrl}
                alt={`Rendered preview of ${renderJob.draftTitle || 'the current draft'}`}
              />
            ) : (
              <div className="render-preview__placeholder">
                <strong>No preview yet</strong>
                <span>The next successful headless render will appear here.</span>
              </div>
            )}
          </div>

          {renderJob ? (
            <div className="inspector__facts inspector__facts--render">
              <div>
                <span>Status</span>
                <strong>{renderJob.status}</strong>
              </div>
              <div>
                <span>Target</span>
                <strong>{renderJob.targetObjectName}</strong>
              </div>
              <div>
                <span>Draft</span>
                <strong>{renderJob.draftTitle}</strong>
              </div>
            </div>
          ) : null}

          {renderJob?.logTail?.length ? (
            <details className="render-preview__logs">
              <summary>Recent Blender Log</summary>
              <pre>{renderJob.logTail.join('\n')}</pre>
            </details>
          ) : null}
        </div>
      </div>
    </section>
  );
}
