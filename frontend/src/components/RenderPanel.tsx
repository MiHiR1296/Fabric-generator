import { useEffect, useState } from 'react';
import { WEAVE_ZOOM_THREAD_LEVELS } from '../domain/draft';
import type { BlenderRenderJob, DraftDocument, DraftRenderSettings, TileRenderOptions } from '../domain/types';

// Exposed control surface mirrors v2 (Fabric-generator-codex-fabric-generator-v2/frontend/src/components/RenderPanel.tsx).
// User-facing controls. Hidden calibration defaults live in buildDefaultRenderSettings.
interface ExposedField {
  key:
    | 'spacing'
    | 'patternNoiseX'
    | 'patternNoiseY'
    | 'uvRandomU'
    | 'arc1VPadding';
  label: string;
  step: number;
  min: number;
  max: number;
}

const EXPOSED_FIELDS: ExposedField[] = [
  { key: 'spacing', label: 'Spacing', step: 0.01, min: 0, max: 1 },
  { key: 'patternNoiseX', label: 'Pattern Noise X', step: 0.01, min: 0, max: 1 },
  { key: 'patternNoiseY', label: 'Pattern Noise Y', step: 0.01, min: 0, max: 1 },
  { key: 'uvRandomU', label: 'Texture U Scatter', step: 1, min: 0, max: 20 },
  { key: 'arc1VPadding', label: 'Arc 1 V Padding', step: 0.001, min: 0, max: 0.25 },
];

const DEFAULT_WEAVE_ZOOM_THREADS = WEAVE_ZOOM_THREAD_LEVELS[0];
const TILE_EXPORT_DEFAULTS = {
  tileCount: 4 as const,
  tileResolution: 1200,
  guardThreads: 0,
  variationStrength: 0,
};

function nearestWeaveZoomLevel(value: number) {
  return WEAVE_ZOOM_THREAD_LEVELS.find((level) => value <= level)
    ?? WEAVE_ZOOM_THREAD_LEVELS[WEAVE_ZOOM_THREAD_LEVELS.length - 1];
}

function settingToInputValue(
  settings: DraftRenderSettings | undefined,
  key: ExposedField['key'],
) {
  const value = settings?.[key];
  return value === undefined || value === null ? '' : String(value);
}

interface RenderPanelProps {
  draft: DraftDocument;
  importMessage: string;
  renderJob: BlenderRenderJob | null;
  renderBusy: boolean;
  tileJob?: BlenderRenderJob | null;
  tileBusy?: boolean;
  activePreviewMode?: 'render' | 'tile';
  onRenderPreview: () => void;
  onSendToLiveBlender?: () => void;
  onRenderTiles?: (options: TileRenderOptions) => void;
  onExportCanonical: () => void;
  onExportBlender: () => void;
  onApplyRenderSettings: (settings: Partial<DraftRenderSettings>) => void;
  stepLabel?: string;
  title?: string;
  summaryText?: string;
  statusMessage?: string;
  tileStatusMessage?: string;
  renderDisabled?: boolean;
  liveBlenderBusy?: boolean;
}

export default function RenderPanel({
  draft,
  importMessage,
  renderJob,
  renderBusy,
  tileJob = null,
  tileBusy = false,
  activePreviewMode = 'render',
  onRenderPreview,
  onRenderTiles,
  onExportCanonical,
  onExportBlender,
  onApplyRenderSettings,
  stepLabel = 'Step 2',
  title = 'Render Preview',
  summaryText,
  statusMessage,
  tileStatusMessage,
  renderDisabled = false,
  onSendToLiveBlender,
  liveBlenderBusy = false,
}: RenderPanelProps) {
  const [stagedFields, setStagedFields] = useState<Record<ExposedField['key'], string>>(() => ({
    spacing: '',
    patternNoiseX: '',
    patternNoiseY: '',
    uvRandomU: '',
    arc1VPadding: '',
  }));
  const [stagedThreadCount, setStagedThreadCount] = useState<number>(DEFAULT_WEAVE_ZOOM_THREADS);

  useEffect(() => {
    const settings = draft.renderSettings;
    const currentThreadCount = settings
      ? Math.max(settings.warpThreads, settings.weftThreads)
      : DEFAULT_WEAVE_ZOOM_THREADS;
    setStagedThreadCount(nearestWeaveZoomLevel(currentThreadCount));
    setStagedFields({
      spacing: settingToInputValue(settings, 'spacing'),
      patternNoiseX: settingToInputValue(settings, 'patternNoiseX'),
      patternNoiseY: settingToInputValue(settings, 'patternNoiseY'),
      uvRandomU: settingToInputValue(settings, 'uvRandomU'),
      arc1VPadding: settingToInputValue(settings, 'arc1VPadding'),
    });
  }, [draft]);

  function parseStagedSettings(): Partial<DraftRenderSettings> {
    const out: Partial<DraftRenderSettings> = {
      warpThreads: stagedThreadCount,
      weftThreads: stagedThreadCount,
    };
    for (const field of EXPOSED_FIELDS) {
      const raw = stagedFields[field.key].trim();
      if (raw === '') continue;
      const parsed = Number(raw);
      if (!Number.isFinite(parsed)) continue;
      out[field.key] = parsed;
    }
    return out;
  }

  const renderRunning =
    renderBusy || renderJob?.status === 'queued' || renderJob?.status === 'running';
  const tileRunning =
    tileBusy || tileJob?.status === 'queued' || tileJob?.status === 'running';
  const renderActive = renderRunning || tileRunning || renderDisabled || liveBlenderBusy;

  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    if (!renderRunning) {
      setElapsed(0);
      return undefined;
    }
    const start = renderJob?.createdAt ? new Date(renderJob.createdAt).getTime() : Date.now();
    const tick = () => setElapsed(Math.max(0, (Date.now() - start) / 1000));
    tick();
    const id = window.setInterval(tick, 250);
    return () => window.clearInterval(id);
  }, [renderRunning, renderJob?.createdAt]);

  // Blender doesn't emit a real progress %, so estimate one. The curve
  // climbs quickly at first, then asymptotes to 95% so the bar never
  // hits 100% before Blender actually finishes — at which point we
  // snap it to 100%.
  const RENDER_TIME_CONSTANT = 35;
  const completedStatus = renderJob?.status === 'completed' || Boolean(renderJob?.imageUrl);
  const failedStatus = renderJob?.status === 'failed';
  const progress = completedStatus
    ? 100
    : failedStatus
      ? 0
      : renderRunning
        ? Math.min(95, (1 - Math.exp(-elapsed / RENDER_TIME_CONSTANT)) * 95)
        : 0;

  function formatElapsed(seconds: number) {
    const total = Math.floor(seconds);
    const m = Math.floor(total / 60);
    const s = total % 60;
    return `${m}:${s.toString().padStart(2, '0')}`;
  }

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
          {onSendToLiveBlender ? (
            <button
              className="button"
              onClick={onSendToLiveBlender}
              disabled={renderActive || liveBlenderBusy}
              data-testid="send-live-blender-button"
            >
              {liveBlenderBusy ? 'Sending to Blender…' : 'Send to Live Blender'}
            </button>
          ) : null}
          {onRenderTiles ? (
            <button
              className="button"
              onClick={() =>
                onRenderTiles({
                  ...TILE_EXPORT_DEFAULTS,
                })
              }
              disabled={renderActive}
              data-testid="render-tiles-button"
            >
              {tileRunning ? 'Building Tiles…' : 'Build Tile Texture'}
            </button>
          ) : null}
          <button className="button" onClick={onExportCanonical} data-testid="export-canonical-button">
            Export Draft JSON
          </button>
          <button className="button" onClick={onExportBlender} data-testid="export-blender-button">
            Export Blender Map
          </button>
        </div>
      </div>

      <div className="render-panel__body">
        <div className="render-panel__controls">
          <div className="board-section__heading">
            <div>
              <h3>Blender Controls</h3>
              <p>Adjust the swatch density and relief before you rerender.</p>
            </div>
          </div>

          <div className="render-settings">
            <div className="render-zoom-control">
              <span>Weave Zoom</span>
              <div className="render-zoom-control__buttons" role="group" aria-label="Weave zoom">
                {WEAVE_ZOOM_THREAD_LEVELS.map((level) => (
                  <button
                    key={level}
                    type="button"
                    className={`button button--tiny render-zoom-control__button${
                      stagedThreadCount === level ? ' render-zoom-control__button--active' : ''
                    }`}
                    aria-pressed={stagedThreadCount === level}
                    title={`${level} warp/weft threads`}
                    onClick={() => setStagedThreadCount(level)}
                  >
                    {level}
                  </button>
                ))}
              </div>
            </div>
            {EXPOSED_FIELDS.map((field) => (
              <label key={field.key} className="field field--compact">
                <span>{field.label}</span>
                <input
                  type="number"
                  step={field.step}
                  min={field.min}
                  max={field.max}
                  value={stagedFields[field.key]}
                  onChange={(event) =>
                    setStagedFields((prev) => ({ ...prev, [field.key]: event.target.value }))
                  }
                />
              </label>
            ))}
          </div>

          <div className="section-editor__row">
            <button className="button" onClick={() => onApplyRenderSettings(parseStagedSettings())}>
              Apply Blender Controls
            </button>
          </div>

          <p className="muted">
            The preview is rotated to match drawdown reading direction, so it feels closer to the draft
            you just built.
          </p>

          {onRenderTiles ? (
            <div className="tile-export-settings">
              <div className="board-section__heading">
                <div>
                  <h3>Tile Texture Export</h3>
                  <p>Build the final repaired texture from the current Blender material.</p>
                </div>
              </div>

              <p className="muted">
                The backend returns the final output image and clears temporary tile files.
              </p>
            </div>
          ) : null}
        </div>

        <div className="render-panel__preview">
          {activePreviewMode === 'render' && statusMessage ? (
            <p className="muted render-panel__status" data-testid="render-status-message">
              {statusMessage}
            </p>
          ) : null}
          {activePreviewMode === 'tile' && tileStatusMessage ? (
            <p className="muted render-panel__status" data-testid="tile-render-status-message">
              {tileStatusMessage}
            </p>
          ) : null}

          {activePreviewMode === 'render' ? (
            <>
              <div className="render-preview render-preview--panel">
                {renderJob?.imageUrl ? (
                  <img
                    className="render-preview__image render-preview__image--draft-aligned"
                    src={renderJob.imageUrl}
                    alt={`Rendered preview of ${renderJob.draftTitle || 'the current draft'}`}
                  />
                ) : (
                  <div className="render-preview__placeholder">
                    <strong>{renderRunning ? 'Working…' : 'No preview yet'}</strong>
                    <span>
                      {renderRunning
                        ? 'The image will appear automatically as soon as Blender finishes.'
                        : 'The next successful headless render will appear here.'}
                    </span>
                  </div>
                )}

                {renderRunning ? (
                  <div
                    className="render-progress render-progress--overlay"
                    role="progressbar"
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-valuenow={Math.round(progress)}
                    aria-valuetext={`Rendering ${Math.round(progress)}%`}
                    data-testid="render-progress"
                  >
                    <div className="render-progress__label">
                      <span>
                        {renderJob?.status === 'queued'
                          ? 'Queued for Blender…'
                          : 'Blender is generating your preview…'}
                      </span>
                      <span className="render-progress__elapsed">
                        {Math.round(progress)}% · {formatElapsed(elapsed)}
                      </span>
                    </div>
                    <div className="render-progress__track">
                      <div
                        className="render-progress__bar"
                        style={{ width: `${progress}%` }}
                      />
                    </div>
                  </div>
                ) : null}
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
            </>
          ) : (
            <>
              <div className="render-preview render-preview--panel">
                {tileJob?.imageUrl ? (
                  <img
                    className="render-preview__image"
                    src={tileJob.imageUrl}
                    alt={`Stitched tile texture of ${tileJob.draftTitle || 'the current draft'}`}
                  />
                ) : (
                  <div className="render-preview__placeholder">
                    <strong>{tileRunning ? 'Building texture…' : 'No tile texture yet'}</strong>
                    <span>
                      {tileRunning
                        ? 'Blender is rendering the tile set; the stitched result will appear here.'
                        : 'Build a tile texture when you want a larger stitched output.'}
                    </span>
                  </div>
                )}
              </div>

              {tileJob?.tileSourceImageUrls?.length ? (
                <div className="tile-source-strip" aria-label="Blender source tile renders">
                  {tileJob.tileSourceImageUrls.map((url, index) => (
                    <figure className="tile-source-strip__item" key={url}>
                      <img src={url} alt={`Blender source render ${index + 1}`} />
                      <figcaption>{index + 1}</figcaption>
                    </figure>
                  ))}
                </div>
              ) : null}

              {tileJob ? (
                <div className="inspector__facts inspector__facts--render">
                  <div>
                    <span>Tile Status</span>
                    <strong>{tileJob.status}</strong>
                  </div>
                  <div>
                    <span>Job</span>
                    <strong>{tileJob.id}</strong>
                  </div>
                  <div>
                    <span>Output</span>
                    <strong>{tileJob.imageUrl ? 'ready' : 'pending'}</strong>
                  </div>
                </div>
              ) : null}

              {tileJob?.logTail?.length ? (
                <details className="render-preview__logs">
                  <summary>Recent Blender Log</summary>
                  <pre>{tileJob.logTail.join('\n')}</pre>
                </details>
              ) : null}
            </>
          )}
        </div>
      </div>
    </section>
  );
}
