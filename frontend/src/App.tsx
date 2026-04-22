import { useEffect, useMemo, useState } from 'react';
import ColorMappingStep from './components/ColorMappingStep';
import PatternBuilderStep from './components/PatternBuilderStep';
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
} from './utils/parserApi';

export default function App() {
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

  return (
    <div className="studio-shell fabric-shell" data-testid="fabric-studio-app">
      <div className="studio-shell__texture" />
      <header className="fabric-hero">
        <div>
          <p className="eyebrow">One-Point Fabric Studio</p>
          <h1>Yarn Processing, Draft Building, and Blender Preview in One Flow</h1>
          <p className="fabric-hero__summary">
            Build the yarn library, map processed yarns to draft colors, and render the final swatch without jumping between separate tools.
          </p>
        </div>
        <div className="fabric-hero__facts">
          <div className="status-pill status-pill--source">Draft Colors: {slots.length}</div>
          <div className="status-pill status-pill--online">
            Ready Yarns: {yarnAssets.filter((asset) => asset.status === 'ready').length}
          </div>
          <div className={`status-pill status-pill--${renderJob?.status === 'failed' ? 'offline' : 'checking'}`}>
            Render: {renderJob?.status || 'idle'}
          </div>
        </div>
      </header>

      <main className="fabric-step-stack">
        <YarnLibraryStep
          assets={yarnAssets}
          busy={assetBusy}
          message={assetMessage}
          onUpload={async (files) => {
            setAssetBusy(true);
            try {
              const created = await uploadYarnAssets(files);
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
          onRetry={async (assetId) => {
            try {
              await retryYarnAsset(assetId);
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

        <PatternBuilderStep draft={draft} setDraft={setDraft} />

        <ColorMappingStep
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
      </main>
    </div>
  );
}
