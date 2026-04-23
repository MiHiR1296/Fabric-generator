import { useEffect, useMemo, useState } from 'react';
import type {
  BlenderLivePreview,
  BlenderRenderJob,
  DraftDocument,
  DraftRenderSettings,
} from '../domain/types';

type RenderSettingsKey = keyof DraftRenderSettings;

interface BaseRenderPanelProps {
  draft: DraftDocument;
  importMessage: string;
  onExportCanonical: () => void;
  onExportBlender: () => void;
  stepLabel?: string;
  title?: string;
  summaryText?: string;
  statusMessage?: string;
  renderDisabled?: boolean;
}

interface LivePreviewRenderPanelProps extends BaseRenderPanelProps {
  livePreview: BlenderLivePreview | null;
  previewBusy: boolean;
  onUpdatePreview: (settings: Partial<DraftRenderSettings>) => void;
  renderJob?: never;
  renderBusy?: never;
  onRenderPreview?: never;
  onApplyRenderSettings?: never;
}

interface DraftRenderPanelProps extends BaseRenderPanelProps {
  renderJob: BlenderRenderJob | null;
  renderBusy: boolean;
  onRenderPreview: () => void;
  onApplyRenderSettings: (settings: Partial<DraftRenderSettings>) => void;
  livePreview?: never;
  previewBusy?: never;
  onUpdatePreview?: never;
}

type RenderPanelProps = LivePreviewRenderPanelProps | DraftRenderPanelProps;

type RenderSettingsInputState = Record<RenderSettingsKey, string>;

interface ControlGroup {
  title: string;
  description: string;
  fields: Array<{
    key: RenderSettingsKey;
    label: string;
    step?: number | 'any';
  }>;
}

const CONTROL_GROUPS: ControlGroup[] = [
  {
    title: 'Draft Density',
    description: 'Control repeat density and overall weave relief before refreshing the camera preview.',
    fields: [
      { key: 'warpThreads', label: 'Warp Threads', step: 1 },
      { key: 'weftThreads', label: 'Weft Threads', step: 1 },
      { key: 'spacing', label: 'Spacing', step: 0.001 },
      { key: 'amplitude', label: 'Amplitude', step: 0.001 },
      { key: 'fillRatio', label: 'Fill Ratio', step: 0.01 },
    ],
  },
  {
    title: 'Thread Structure',
    description: 'Shape the yarn body and plying values that feed the geometry-node strand generation.',
    fields: [
      { key: 'threadRadius', label: 'Thread Radius', step: 0.001 },
      { key: 'threadSubdivisions', label: 'Thread Subdivisions', step: 1 },
      { key: 'plyCount', label: 'Ply Count', step: 1 },
      { key: 'plyRadius', label: 'Ply Radius', step: 0.001 },
      { key: 'twistAmount', label: 'Twist Amount', step: 0.1 },
      { key: 'plyResolution', label: 'Ply Resolution', step: 1 },
      { key: 'seed', label: 'Seed', step: 1 },
    ],
  },
  {
    title: 'Texture Mapping',
    description: 'These match the material mapping controls already exposed in the Blender node setup.',
    fields: [
      { key: 'textureScaleU', label: 'Texture Scale U', step: 0.1 },
      { key: 'textureScaleV', label: 'Texture Scale V', step: 0.01 },
      { key: 'textureOffsetV', label: 'Texture Offset V', step: 0.01 },
      { key: 'textureSideFlatten', label: 'Texture Side Flatten', step: 0.01 },
    ],
  },
  {
    title: 'Micro Detail',
    description: 'Fine surface breakup and fiber controls for the camera-framed material preview.',
    fields: [
      { key: 'lumpStrength', label: 'Lump Strength', step: 0.0001 },
      { key: 'lumpScale', label: 'Lump Scale', step: 0.1 },
      { key: 'fiberDensity', label: 'Fiber Density', step: 0.01 },
      { key: 'fiberLength', label: 'Fiber Length', step: 0.001 },
      { key: 'fiberThickness', label: 'Fiber Thickness', step: 0.01 },
      { key: 'fiberFrizz', label: 'Fiber Frizz', step: 0.01 },
      { key: 'fiberSubdivs', label: 'Fiber Subdivs', step: 1 },
    ],
  },
];

function toInputState(draft: DraftDocument): RenderSettingsInputState {
  const settings = draft.renderSettings;
  return {
    warpThreads: String(settings?.warpThreads ?? ''),
    weftThreads: String(settings?.weftThreads ?? ''),
    spacing: String(settings?.spacing ?? ''),
    amplitude: String(settings?.amplitude ?? ''),
    threadRadius: String(settings?.threadRadius ?? ''),
    threadSubdivisions: String(settings?.threadSubdivisions ?? ''),
    plyCount: String(settings?.plyCount ?? ''),
    plyRadius: String(settings?.plyRadius ?? ''),
    twistAmount: String(settings?.twistAmount ?? ''),
    plyResolution: String(settings?.plyResolution ?? ''),
    textureScaleU: String(settings?.textureScaleU ?? ''),
    textureScaleV: String(settings?.textureScaleV ?? ''),
    textureOffsetV: String(settings?.textureOffsetV ?? ''),
    textureSideFlatten: String(settings?.textureSideFlatten ?? ''),
    lumpStrength: String(settings?.lumpStrength ?? ''),
    lumpScale: String(settings?.lumpScale ?? ''),
    fiberDensity: String(settings?.fiberDensity ?? ''),
    fiberLength: String(settings?.fiberLength ?? ''),
    fiberThickness: String(settings?.fiberThickness ?? ''),
    fiberFrizz: String(settings?.fiberFrizz ?? ''),
    fiberSubdivs: String(settings?.fiberSubdivs ?? ''),
    seed: String(settings?.seed ?? ''),
    fillRatio: String(settings?.fillRatio ?? ''),
  };
}

function parseStagedSettings(values: RenderSettingsInputState): Partial<DraftRenderSettings> {
  const entries = Object.entries(values).flatMap(([key, rawValue]) => {
    const normalized = rawValue.trim();
    if (!normalized) {
      return [];
    }
    const parsed = Number(normalized);
    if (!Number.isFinite(parsed)) {
      return [];
    }
    return [[key, parsed] as const];
  });

  return Object.fromEntries(entries) as Partial<DraftRenderSettings>;
}

function formatPreviewTimestamp(value?: string | null) {
  if (!value) {
    return 'Pending';
  }

  const timestamp = Date.parse(value);
  if (Number.isNaN(timestamp)) {
    return value;
  }

  return new Intl.DateTimeFormat(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  }).format(new Date(timestamp));
}

export default function RenderPanel(props: RenderPanelProps) {
  const [stagedSettings, setStagedSettings] = useState<RenderSettingsInputState>(() => toInputState(props.draft));

  useEffect(() => {
    setStagedSettings(toInputState(props.draft));
  }, [props.draft]);

  const liveMode = 'onUpdatePreview' in props;
  const previewBusy = liveMode ? props.previewBusy : props.renderBusy;
  const previewImageUrl = liveMode ? props.livePreview?.imageUrl : props.renderJob?.imageUrl;
  const previewStatus = liveMode ? props.livePreview?.status : props.renderJob?.status;
  const previewTarget = liveMode ? props.livePreview?.targetObjectName : props.renderJob?.targetObjectName;
  const previewResolution =
    liveMode && props.livePreview?.width && props.livePreview?.height
      ? `${props.livePreview.width} × ${props.livePreview.height}`
      : null;

  const hasStagedChanges = useMemo(() => {
    const next = parseStagedSettings(stagedSettings);
    const current = props.draft.renderSettings || {};
    return Object.entries(next).some(([key, value]) => current[key as RenderSettingsKey] !== value);
  }, [props.draft.renderSettings, stagedSettings]);

  const handleUpdateClick = () => {
    const nextSettings = parseStagedSettings(stagedSettings);
    if (liveMode) {
      props.onUpdatePreview(nextSettings);
      return;
    }
    props.onApplyRenderSettings(nextSettings);
    props.onRenderPreview();
  };

  const handleApplyControls = () => {
    if (liveMode) {
      props.onUpdatePreview(parseStagedSettings(stagedSettings));
      return;
    }
    props.onApplyRenderSettings(parseStagedSettings(stagedSettings));
  };

  const buttonLabel = liveMode
    ? previewBusy
      ? 'Updating Preview…'
      : 'Update Preview'
    : previewBusy
      ? 'Rendering Preview…'
      : 'Render Preview';

  return (
    <section className="card render-panel" data-testid="render-panel">
      <div className="render-panel__header">
        <div>
          <p className="eyebrow">{props.stepLabel || 'Step 2'}</p>
          <h2>{props.title || (liveMode ? 'Blender Material Preview' : 'Render Preview')}</h2>
          <p className="render-panel__summary">
            {props.summaryText ||
              props.importMessage ||
              'Adjust the Blender controls and review the latest swatch preview here.'}
          </p>
        </div>

        <div className="render-panel__actions">
          <button
            className="button button--accent"
            onClick={handleUpdateClick}
            disabled={previewBusy || Boolean(props.renderDisabled)}
            data-testid="render-preview-button"
          >
            {buttonLabel}
          </button>
          <button className="button" onClick={props.onExportCanonical} data-testid="export-canonical-button">
            Export Draft JSON
          </button>
          <button className="button" onClick={props.onExportBlender} data-testid="export-blender-button">
            Export Blender Map
          </button>
        </div>
      </div>

      {props.statusMessage ? (
        <p className="muted" data-testid="render-status-message">
          {props.statusMessage}
        </p>
      ) : null}

      <div className="render-panel__body">
        <div className="render-panel__controls">
          <div className="board-section__heading">
            <div>
              <h3>{liveMode ? 'Geometry Controls' : 'Blender Controls'}</h3>
              <p>
                {liveMode
                  ? 'These inputs stay local until you click Update Preview, so you can batch several geometry-node adjustments together.'
                  : 'Apply the staged values before rerendering the headless Blender preview.'}
              </p>
            </div>
          </div>

          <div className="render-panel__control-groups">
            {CONTROL_GROUPS.map((group) => (
              <section className="section-editor render-panel__control-group" key={group.title}>
                <div className="section-editor__header">
                  <div>
                    <h3>{group.title}</h3>
                    <p>{group.description}</p>
                  </div>
                </div>
                <div className="render-settings">
                  {group.fields.map((field) => (
                    <label className="field field--compact" key={field.key}>
                      <span>{field.label}</span>
                      <input
                        value={stagedSettings[field.key]}
                        type="number"
                        step={field.step ?? 'any'}
                        onChange={(event) =>
                          setStagedSettings((current) => ({
                            ...current,
                            [field.key]: event.target.value,
                          }))
                        }
                      />
                    </label>
                  ))}
                </div>
              </section>
            ))}
          </div>

          <div className="section-editor__row">
            {!liveMode ? (
              <button className="button" onClick={handleApplyControls} data-testid="apply-render-settings-button">
                Apply Blender Controls
              </button>
            ) : null}
            <p className="muted render-panel__lazy-note" data-testid="render-controls-note">
              {liveMode
                ? hasStagedChanges
                  ? 'You have local control edits waiting to be sent to Blender.'
                  : 'No unsent control edits right now.'
                : 'The preview image keeps the current draft orientation so it reads closer to the draft board.'}
            </p>
          </div>
        </div>

        <div className="render-panel__preview">
          <div className="render-preview render-preview--panel">
            {previewImageUrl ? (
              <img
                className={`render-preview__image${liveMode ? '' : ' render-preview__image--draft-aligned'}`}
                src={previewImageUrl}
                alt={liveMode ? 'Blender material preview' : `Rendered preview of ${props.renderJob?.draftTitle || 'the current draft'}`}
              />
            ) : (
              <div className="render-preview__placeholder">
                <strong>{liveMode ? 'No Blender preview yet' : 'No preview yet'}</strong>
                <span>
                  {liveMode
                    ? 'Assign yarns, adjust the controls, then click Update Preview to capture the next camera preview.'
                    : 'The next successful Blender render will appear here.'}
                </span>
              </div>
            )}
          </div>

          {liveMode ? (
            props.livePreview ? (
              <div className="inspector__facts inspector__facts--render">
                <div>
                  <span>Status</span>
                  <strong>{previewStatus || 'idle'}</strong>
                </div>
                <div>
                  <span>Target</span>
                  <strong>{previewTarget || 'ParametricWeave'}</strong>
                </div>
                <div>
                  <span>Session</span>
                  <strong>{props.livePreview.sessionId}</strong>
                </div>
                <div>
                  <span>Resolution</span>
                  <strong>{previewResolution || 'Pending'}</strong>
                </div>
                <div>
                  <span>Updated</span>
                  <strong>{formatPreviewTimestamp(props.livePreview.updatedAt)}</strong>
                </div>
              </div>
            ) : null
          ) : props.renderJob ? (
            <div className="inspector__facts inspector__facts--render">
              <div>
                <span>Status</span>
                <strong>{props.renderJob.status}</strong>
              </div>
              <div>
                <span>Target</span>
                <strong>{props.renderJob.targetObjectName}</strong>
              </div>
              <div>
                <span>Draft</span>
                <strong>{props.renderJob.draftTitle}</strong>
              </div>
            </div>
          ) : null}

          {!liveMode && props.renderJob?.logTail?.length ? (
            <details className="render-preview__logs">
              <summary>Recent Blender Log</summary>
              <pre>{props.renderJob.logTail.join('\n')}</pre>
            </details>
          ) : null}
        </div>
      </div>
    </section>
  );
}
