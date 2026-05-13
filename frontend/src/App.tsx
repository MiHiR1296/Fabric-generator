import { useEffect, useMemo, useState } from 'react';
import ColorMappingStep from './components/ColorMappingStep';
import PatternBuilderStep from './components/PatternBuilderStep';
import TryOn3DStep from './components/TryOn3DStep';
import YarnLibraryStep from './components/YarnLibraryStep';
import {
  buildBlenderHandoff,
  downloadTextFile,
  loadDraftFromStorage,
  normalizeDraft,
  saveDraftToStorage,
  serializeBlenderHandoff,
  serializeDraft,
  updateRenderSettings,
} from './domain/draft';
import { buildFabricProject, deriveColorBindingSlots, syncColorBindings } from './domain/project';
import { presets } from './domain/presets';
import type { BlenderRenderJob, ColorBinding, DraftDocument, YarnAsset } from './domain/types';
import {
  deleteYarnAsset,
  fetchDraftRenderJob,
  listYarnAssets,
  requestProjectRender,
  retryYarnAsset,
  uploadYarnAssets,
  type YarnOrientation,
} from './utils/parserApi';

type WizardStep = 0 | 1 | 2 | 3;

const STEPS: { title: string; eyebrow: string }[] = [
  { eyebrow: 'Step 1', title: 'Yarn Library' },
  { eyebrow: 'Step 2', title: 'Pattern Builder' },
  { eyebrow: 'Step 3', title: 'Render Preview' },
  { eyebrow: 'Step 4', title: 'Try On 3D' },
];

export default function App() {
  const [step, setStep] = useState<WizardStep>(0);
  const [draft, setDraft] = useState<DraftDocument>(loadDraftFromStorage() || presets[0].document);
  const [yarnAssets, setYarnAssets] = useState<YarnAsset[]>([]);
  const [assetBusy, setAssetBusy] = useState(false);
  const [assetMessage, setAssetMessage] = useState(
    'Upload yarn references first. The backend will generate seamless diffuse and alpha maps automatically.',
  );
  const [colorBindings, setColorBindings] = useState<ColorBinding[]>([]);
  const [renderJob, setRenderJob] = useState<BlenderRenderJob | null>(null);
  const [renderBusy, setRenderBusy] = useState(false);
  const [renderMessage, setRenderMessage] = useState(
    'Assign each warp and weft color slot to a processed yarn asset, then start the Blender preview.',
  );

  const slots = useMemo(() => deriveColorBindingSlots(draft), [draft]);
  const readyAssets = useMemo(
    () => yarnAssets.filter((asset) => asset.status === 'ready'),
    [yarnAssets],
  );
  const allBindingsAssigned = useMemo(
    () => colorBindings.length > 0 && colorBindings.every((b) => Boolean(b.yarnAssetId)),
    [colorBindings],
  );

  useEffect(() => {
    saveDraftToStorage(draft);
  }, [draft]);

  useEffect(() => {
    setColorBindings((current) => syncColorBindings(slots, current));
  }, [slots]);

  const refreshAssets = async () => {
    try {
      setYarnAssets(await listYarnAssets());
    } catch (error) {
      setAssetMessage(error instanceof Error ? error.message : 'Unable to load yarn assets.');
    }
  };

  useEffect(() => {
    refreshAssets();
  }, []);

  useEffect(() => {
    if (!yarnAssets.some((asset) => asset.status === 'queued' || asset.status === 'processing')) {
      return undefined;
    }
    const timeoutId = window.setTimeout(() => {
      refreshAssets();
    }, 1500);
    return () => window.clearTimeout(timeoutId);
  }, [yarnAssets]);

  // Inject the floating-yarn background script once the hero canvas is mounted.
  useEffect(() => {
    if (document.querySelector('script[data-yarn-canvas-bg]')) return;
    const script = document.createElement('script');
    script.src = '/yarn-canvas-bg.js';
    script.async = true;
    script.dataset.yarnCanvasBg = 'true';
    document.body.appendChild(script);
  }, []);

  useEffect(() => {
    if (!renderJob || (renderJob.status !== 'queued' && renderJob.status !== 'running')) {
      return undefined;
    }

    const timeoutId = window.setTimeout(async () => {
      try {
        const nextJob = await fetchDraftRenderJob(renderJob.id);
        setRenderJob(nextJob);
        setRenderMessage(nextJob.message);
      } catch {
        // keep the current render state visible if polling fails transiently
      }
    }, 1200);

    return () => window.clearTimeout(timeoutId);
  }, [renderJob]);

  const hasPalette = draft.warpColors.length > 0 && draft.weftColors.length > 0;

  const canAdvance = (() => {
    if (step === 0) return readyAssets.length > 0;
    if (step === 1) return hasPalette && allBindingsAssigned;
    return false;
  })();

  const advanceHint = (() => {
    if (step === 0 && readyAssets.length === 0)
      return 'Upload at least one yarn so the backend can finish processing it.';
    if (step === 1 && !hasPalette)
      return 'Set warp and weft colors before continuing to render preview.';
    if (step === 1 && !allBindingsAssigned)
      return 'Assign every warp and weft color slot to a yarn asset.';
    return '';
  })();

  return (
    <div className="studio-shell fabric-shell" data-testid="fabric-studio-app">
      <div className="studio-shell__texture" />
      <a className="studio-back-link" href="/">&larr; Back to infiknit</a>

      <header className="fabric-hero">
        <canvas id="heroYarnCanvas" className="fabric-hero__canvas" aria-hidden="true" />
        <div className="fabric-hero__content">
          <p className="eyebrow">
            Step {step + 1} of {STEPS.length} · infiknit Fabric Studio
          </p>
          <h1>{STEPS[step].title}</h1>
          <p className="fabric-hero__summary">
            Yarn → Pattern → Render → Try On. Four steps to digitise and dress your fabric.
          </p>
        </div>
        <div className="fabric-hero__facts">
          <div className="status-pill status-pill--source">Draft Colors: {slots.length}</div>
          <div className="status-pill status-pill--online">Ready Yarns: {readyAssets.length}</div>
          <div className={`status-pill status-pill--${renderJob?.status === 'failed' ? 'offline' : 'checking'}`}>
            Render: {renderJob?.status || 'idle'}
          </div>
        </div>
      </header>

      <nav className="wizard-stepper" aria-label="Studio steps">
        {STEPS.map((s, idx) => {
          const state = idx < step ? 'done' : idx === step ? 'active' : 'pending';
          return (
            <button
              key={idx}
              type="button"
              className={`wizard-stepper__item wizard-stepper__item--${state}`}
              onClick={() => {
                // allow jumping to completed or current steps freely
                if (idx <= step) setStep(idx as WizardStep);
              }}
              disabled={idx > step}
              data-testid={`wizard-step-${idx}`}
            >
              <span className="wizard-stepper__num">{idx + 1}</span>
              <span className="wizard-stepper__label">{s.title}</span>
            </button>
          );
        })}
      </nav>

      <main className="fabric-step-stack wizard-page">
        {step === 0 ? (
          <YarnLibraryStep
            assets={yarnAssets}
            busy={assetBusy}
            message={assetMessage}
            onUpload={async (files, orientation: YarnOrientation) => {
              setAssetBusy(true);
              try {
                const created = await uploadYarnAssets(files, orientation);
                setAssetMessage(
                  `Queued ${created.length} yarn asset${created.length === 1 ? '' : 's'} for seamless + alpha processing.`,
                );
                await refreshAssets();
              } catch (error) {
                setAssetMessage(error instanceof Error ? error.message : 'Unable to upload yarn images.');
              } finally {
                setAssetBusy(false);
              }
            }}
            onRetry={async (assetId, orientation) => {
              try {
                await retryYarnAsset(assetId, orientation);
                setAssetMessage('Queued the yarn asset for processing again.');
                await refreshAssets();
              } catch (error) {
                setAssetMessage(error instanceof Error ? error.message : 'Unable to retry that yarn asset.');
              }
            }}
            onDelete={async (assetId) => {
              try {
                await deleteYarnAsset(assetId);
                setAssetMessage('Removed the yarn asset from the local project runtime.');
                await refreshAssets();
              } catch (error) {
                setAssetMessage(error instanceof Error ? error.message : 'Unable to delete that yarn asset.');
              }
            }}
            onRefresh={refreshAssets}
          />
        ) : null}

        {step === 1 ? (
          <PatternBuilderStep
            draft={draft}
            setDraft={setDraft}
            yarnAssets={yarnAssets}
            colorBindings={colorBindings}
            setColorBindings={setColorBindings}
          />
        ) : null}

        {step === 2 ? (
          <ColorMappingStep
            showBindings={false}
            draft={draft}
            yarnAssets={yarnAssets}
            colorBindings={colorBindings}
            setColorBindings={setColorBindings}
            renderJob={renderJob}
            renderBusy={renderBusy}
            renderMessage={renderMessage}
            onRenderPreview={async () => {
              setRenderBusy(true);
              try {
                const job = await requestProjectRender(
                  buildFabricProject(normalizeDraft(draft), yarnAssets, colorBindings),
                );
                setRenderJob(job);
                setRenderMessage(job.message);
              } catch (error) {
                setRenderMessage(
                  error instanceof Error ? error.message : 'Unable to start the Blender render preview.',
                );
              } finally {
                setRenderBusy(false);
              }
            }}
            onExportCanonical={() => {
              downloadTextFile('fabric-studio-draft.json', serializeDraft(draft));
            }}
            onExportBlender={() => {
              buildBlenderHandoff(draft);
              downloadTextFile('fabric-studio-blender-map.json', serializeBlenderHandoff(draft));
            }}
            onApplyRenderSettings={(settings) => {
              setDraft((current) => updateRenderSettings(current, settings));
            }}
          />
        ) : null}

        {step === 3 ? <TryOn3DStep renderJob={renderJob} /> : null}
      </main>

      <footer className="wizard-footer">
        <button
          type="button"
          className="button button--ghost"
          onClick={() => setStep((s) => Math.max(0, (s - 1) as WizardStep) as WizardStep)}
          disabled={step === 0}
          data-testid="wizard-back"
        >
          &larr; Back
        </button>
        <span className="wizard-footer__hint">{advanceHint}</span>
        {step < 2 ? (
          <button
            type="button"
            className="button button--accent"
            onClick={() => setStep((s) => Math.min(3, (s + 1) as WizardStep) as WizardStep)}
            disabled={!canAdvance}
            data-testid="wizard-next"
          >
            Next &rarr;
          </button>
        ) : step === 2 ? (
          <div className="wizard-footer__actions">
            <a
              className="button button--accent"
              href={renderJob?.imageUrl || '#'}
              download={
                renderJob?.imageUrl
                  ? `${(renderJob.draftTitle || 'fabric').replace(/\s+/g, '-').toLowerCase()}.png`
                  : undefined
              }
              aria-disabled={!renderJob?.imageUrl}
              onClick={(event) => {
                if (!renderJob?.imageUrl) event.preventDefault();
              }}
              data-testid="wizard-finish"
            >
              Download Fabric &darr;
            </a>
            <button
              type="button"
              className="button button--accent"
              onClick={() => setStep(3)}
              disabled={!renderJob?.imageUrl}
              data-testid="wizard-try-on-3d"
            >
              Try on 3D &rarr;
            </button>
          </div>
        ) : (
          <a
            className="button button--accent"
            href={renderJob?.imageUrl || '#'}
            download={
              renderJob?.imageUrl
                ? `${(renderJob.draftTitle || 'fabric').replace(/\s+/g, '-').toLowerCase()}.png`
                : undefined
            }
            aria-disabled={!renderJob?.imageUrl}
            onClick={(event) => {
              if (!renderJob?.imageUrl) event.preventDefault();
            }}
            data-testid="wizard-finish"
          >
            Download Fabric &darr;
          </a>
        )}
      </footer>
    </div>
  );
}
