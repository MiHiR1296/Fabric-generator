import { useEffect, useMemo, useRef, useState } from 'react';
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
  deleteLibraryYarn,
  deleteYarnAsset,
  fetchDraftRenderJob,
  importYarnFromLibrary,
  listYarnAssets,
  listYarnLibrary,
  pushProjectBandmeta,
  requestProjectRender,
  requestProjectTileRender,
  retryYarnAsset,
  uploadYarnAssets,
  type LibraryYarnEntry,
  type YarnOrientation,
} from './utils/parserApi';

type WizardStep = 0 | 1 | 2 | 3;
type PreviewMode = 'render' | 'tile';

const STEPS: { title: string; eyebrow: string }[] = [
  { eyebrow: 'Step 1', title: 'Yarn Library' },
  { eyebrow: 'Step 2', title: 'Pattern Builder' },
  { eyebrow: 'Step 3', title: 'Render Preview' },
  { eyebrow: 'Step 4', title: 'Try On 3D' },
];

function buildLivePushSignature(draft: DraftDocument, colorBindings: ColorBinding[]) {
  return JSON.stringify({
    w: draft.warpColors,
    f: draft.weftColors,
    r: draft.renderSettings,
    b: colorBindings.map((b) => [b.scope, b.colorHex, b.yarnAssetId]),
  });
}

export default function App() {
  const [step, setStep] = useState<WizardStep>(0);
  const [draft, setDraft] = useState<DraftDocument>(loadDraftFromStorage() || presets[0].document);
  const [yarnAssets, setYarnAssets] = useState<YarnAsset[]>([]);
  const [libraryYarns, setLibraryYarns] = useState<LibraryYarnEntry[]>([]);
  const [importingYarnId, setImportingYarnId] = useState<string | null>(null);
  const [assetBusy, setAssetBusy] = useState(false);
  const [assetMessage, setAssetMessage] = useState(
    'Import a yarn from your yarnseamless library, or upload a raw scan to process locally.',
  );
  const [colorBindings, setColorBindings] = useState<ColorBinding[]>([]);
  const [renderJob, setRenderJob] = useState<BlenderRenderJob | null>(null);
  const [renderBusy, setRenderBusy] = useState(false);
  const [liveBlenderBusy, setLiveBlenderBusy] = useState(false);
  const [renderMessage, setRenderMessage] = useState(
    'Assign each warp and weft color slot to a processed yarn asset, then start the Blender preview.',
  );
  const [tileJob, setTileJob] = useState<BlenderRenderJob | null>(null);
  const [tileBusy, setTileBusy] = useState(false);
  const [tileMessage, setTileMessage] = useState(
    'Build a seam-repaired tile texture after the preview settings feel right.',
  );
  const [activePreviewMode, setActivePreviewMode] = useState<PreviewMode>('render');

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

  const refreshLibrary = async () => {
    try {
      setLibraryYarns(await listYarnLibrary());
    } catch (error) {
      setAssetMessage(
        error instanceof Error ? error.message : 'Unable to read the yarn library.',
      );
    }
  };

  const handleImportFromLibrary = async (yarnId: string) => {
    setImportingYarnId(yarnId);
    try {
      const imported = (await importYarnFromLibrary(yarnId)) as YarnAsset;
      const newAssetId = imported.id;
      console.log('[import] yarn imported:', yarnId, '→ asset', newAssetId, 'label:', imported.label);
      setAssetMessage(`Imported "${imported.label || yarnId}" as working yarn.`);
      await refreshAssets();
      // "Use as working image" flow per user 2026-05-13:
      //   Importing a yarn into the project IS the advance action. It:
      //     (a) sets the new yarn as the default for every warp + weft color
      //         binding (so Pattern Builder is ready to draft immediately),
      //     (b) navigates the wizard to Step 2 (Pattern Builder).
      //   The wizard Back/Next footer is removed; this chain replaces it.
      if (newAssetId) {
        setColorBindings((prev) => prev.map((b) => ({ ...b, yarnAssetId: newAssetId })));
        setStep(1);
      }
    } catch (error) {
      setAssetMessage(
        error instanceof Error ? error.message : 'Unable to import that library yarn.',
      );
    } finally {
      setImportingYarnId(null);
    }
  };

  useEffect(() => {
    refreshAssets();
    refreshLibrary();
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

  // Step 1 — poll the library + assets while the yarnseamless editor is open.
  // When MFE writes a new yarn to `yarn_library/` via Save-to-Library, this
  // brings it into the library strip without requiring a manual refresh.
  useEffect(() => {
    if (step !== 0) return undefined;
    const interval = window.setInterval(() => {
      refreshLibrary();
      refreshAssets();
    }, 3000);
    return () => window.clearInterval(interval);
  }, [step]);

  // Auto-import: when a NEW library entry appears (saved from inside MFE)
  // that isn't already imported into this project, kick off the import
  // automatically. Result: a single click of "+ Save to Library" inside the
  // editor → the yarn appears in the library strip AND becomes an importable
  // asset for Pattern Builder. No second "Import" click required.
  const knownLibraryIdsRef = useRef<Set<string> | null>(null);
  useEffect(() => {
    if (libraryYarns.length === 0) return;
    const currentIds = new Set<string>();
    for (const y of libraryYarns) {
      if (typeof y.id === 'string') currentIds.add(y.id);
    }
    // First time we see the library — capture as the baseline, do not auto-import
    // anything that already existed before the user started.
    if (knownLibraryIdsRef.current === null) {
      knownLibraryIdsRef.current = currentIds;
      return;
    }
    if (importingYarnId != null) return; // single-flight
    const importedSet = new Set<string>();
    for (const asset of yarnAssets) {
      const id = (asset as any)?.bandMeta?.library_yarn_id;
      if (typeof id === 'string') importedSet.add(id);
    }
    for (const id of currentIds) {
      if (!knownLibraryIdsRef.current.has(id) && !importedSet.has(id)) {
        handleImportFromLibrary(id);
        break; // import one per cycle to avoid races
      }
    }
    knownLibraryIdsRef.current = currentIds;
  }, [libraryYarns, yarnAssets, importingYarnId]);

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

  useEffect(() => {
    if (!tileJob || (tileJob.status !== 'queued' && tileJob.status !== 'running')) {
      return undefined;
    }

    const timeoutId = window.setTimeout(async () => {
      try {
        const nextJob = await fetchDraftRenderJob(tileJob.id);
        setTileJob(nextJob);
        setTileMessage(nextJob.message);
      } catch {
        // keep the current tile state visible if polling fails transiently
      }
    }, 1400);

    return () => window.clearTimeout(timeoutId);
  }, [tileJob]);

  // Phase 3f — live-push bandMeta to Blender whenever a complete set of
  // warp+weft yarn bindings exists. The backend's
  // /api/blender/push-project-bandmeta endpoint reuses the same slot ordering
  // rule as render-project, so Material N here matches Material N at render
  // time. We debounce 300ms so dropdown/control drags don't fire 10 requests,
  // and skip repeats by hashing the bindings + render-settings signature.
  // Render settings matter here: the setup-owned Material N Texture Scale U
  // multiplier depends on zoom/spacing/fillRatio/textureUCalibration.
  const lastPushedSignatureRef = useRef<string | null>(null);
  useEffect(() => {
    if (step < 1) return undefined;          // only Pattern Builder onward
    if (!allBindingsAssigned) return undefined;
    const signature = buildLivePushSignature(draft, colorBindings);
    if (signature === lastPushedSignatureRef.current) return undefined;
    const timeoutId = window.setTimeout(() => {
      lastPushedSignatureRef.current = signature;
      pushProjectBandmeta(draft, colorBindings).catch((err) => {
        // Reset signature so the next dependency change retries.
        lastPushedSignatureRef.current = null;
        console.warn('[push-bandmeta] failed:', err instanceof Error ? err.message : err);
      });
    }, 300);
    return () => window.clearTimeout(timeoutId);
  }, [step, allBindingsAssigned, draft, colorBindings]);

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

  // Step 1 (Yarn Library) hosts the full yarnseamless app — which wants its
  // own full-page layout, not the viewport-locked wizard layout. Mark the
  // shell so CSS can opt out of `height: 100vh; overflow: hidden` just for
  // that step. The other three steps keep the existing locked layout.
  const shellMode = step === 0 ? 'studio-shell fabric-shell step-yarnseamless' : 'studio-shell fabric-shell';

  return (
    <div className={shellMode} data-testid="fabric-studio-app">
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
                // Allow jumping to ANY step. The wizard footer's Back/Next
                // pair was removed (Phase 2e v10), so the stepper IS the
                // navigation. Forcing the user to advance via Save-to-Library
                // alone leaves them stuck if the auto-flow fails — let them
                // jump.
                setStep(idx as WizardStep);
              }}
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
            library={libraryYarns}
            importingYarnId={importingYarnId}
            onImportFromLibrary={handleImportFromLibrary}
            onDeleteFromLibrary={async (yarnId: string) => {
              try {
                const result = await deleteLibraryYarn(yarnId);
                const cascade = result.removedAssetIds || [];
                setAssetMessage(
                  cascade.length
                    ? `Removed "${yarnId}" from the yarn library and ${cascade.length} imported project asset${cascade.length === 1 ? '' : 's'}.`
                    : `Removed "${yarnId}" from the yarn library.`,
                );
                // Drop the deleted id from the polling baseline so it doesn't
                // count as a "new" entry if it reappears (it won't, but tidy).
                if (knownLibraryIdsRef.current) {
                  knownLibraryIdsRef.current.delete(yarnId);
                }
                if (cascade.length) {
                  // Clear bindings that pointed at the now-deleted assets so
                  // Pattern Builder doesn't keep a stale yarnAssetId on a slot.
                  const cascadeSet = new Set(cascade);
                  setColorBindings((current) =>
                    current.map((b) =>
                      b.yarnAssetId && cascadeSet.has(b.yarnAssetId)
                        ? { ...b, yarnAssetId: null }
                        : b,
                    ),
                  );
                }
                await Promise.all([refreshLibrary(), refreshAssets()]);
              } catch (error) {
                setAssetMessage(
                  error instanceof Error ? error.message : 'Unable to delete that library yarn.',
                );
              }
            }}
            onRefreshLibrary={refreshLibrary}
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
            liveBlenderBusy={liveBlenderBusy}
            tileJob={tileJob}
            tileBusy={tileBusy}
            activePreviewMode={activePreviewMode}
            renderMessage={renderMessage}
            tileMessage={tileMessage}
            onRenderPreview={async () => {
              setActivePreviewMode('render');
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
            onSendToLiveBlender={async () => {
              setActivePreviewMode('render');
              setLiveBlenderBusy(true);
              setRenderMessage('Sending the current design draft to live Blender...');
              try {
                const result = await pushProjectBandmeta(normalizeDraft(draft), colorBindings);
                lastPushedSignatureRef.current = buildLivePushSignature(draft, colorBindings);
                const pushed = Number(result?.pushed ?? 0);
                const materialLabel = pushed === 1 ? 'material slot' : 'material slots';
                setRenderMessage(
                  `Sent the current design draft to live Blender (${pushed} ${materialLabel}) on ${result?.target || 'ParametricWeave'}.`,
                );
              } catch (error) {
                setRenderMessage(
                  error instanceof Error ? error.message : 'Unable to send the design draft to live Blender.',
                );
              } finally {
                setLiveBlenderBusy(false);
              }
            }}
            onRenderTiles={async (options) => {
              setActivePreviewMode('tile');
              setTileBusy(true);
              try {
                const job = await requestProjectTileRender(
                  buildFabricProject(normalizeDraft(draft), yarnAssets, colorBindings),
                  options,
                );
                setTileJob(job);
                setTileMessage(job.message);
              } catch (error) {
                setTileMessage(
                  error instanceof Error ? error.message : 'Unable to start the tile texture export.',
                );
              } finally {
                setTileBusy(false);
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

      {/* Wizard Back/Next footer REMOVED 2026-05-13 per user direction.
       *  The footer's confusion outweighed its utility once each step became
       *  its own full-page app (see architecture.md → floating chrome).
       *  Forward navigation:
       *    Step 1 → Step 2: triggered by handleImportFromLibrary (clicking
       *                     Import on a library card, OR auto-import after
       *                     MFE's + Save to Library). Sets every warp+weft
       *                     binding to the new yarn and advances the wizard.
       *    Step 2 → Step 3: ColorMappingStep's existing "Render Preview" CTA
       *                     transitions to the Render Preview step.
       *    Step 3 → Step 4: Render Preview's existing "Try on 3D" CTA.
       *  Backward navigation: click any earlier step in the wizard-stepper
       *                       at the top (the 4 breadcrumb buttons).
       */}
    </div>
  );
}
