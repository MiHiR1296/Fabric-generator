import { useEffect, useMemo, useRef, useState } from 'react';
import DraftBoard from './DraftBoard';
import ExploreLibrary from './ExploreLibrary';
import InspectorPanel from './InspectorPanel';
import RenderPanel from './RenderPanel';
import StudioToolbar from './StudioToolbar';
import {
  applyColorSequenceEdit,
  applyStructuredPatternEdit,
  buildBlenderHandoff,
  createBlankDraft,
  downloadTextFile,
  getDraftCounts,
  loadDraftFromStorage,
  normalizeDraft,
  saveDraftToStorage,
  serializeBlenderHandoff,
  serializeDraft,
  setWarpEndColor,
  setThreadingShaft,
  updateRenderSettings,
  setWeftPickColor,
  setTreadlingTreadle,
  toggleTieUpCell,
  updateDraftCounts,
  resetSection,
} from '../domain/draft';
import { presets } from '../domain/presets';
import type {
  BlenderRenderJob,
  DraftCounts,
  FocusedDrawdownCell,
  ParserStatus,
} from '../domain/types';
import {
  checkParserStatus,
  describeImportSource,
  fetchDraftRenderJob,
  parseFileInput,
  parsePastedText,
  requestDraftRender,
} from '../utils/parserApi';

export default function DraftStudio() {
  const initialDraft = loadDraftFromStorage() || presets[0].document;
  const [draft, setDraft] = useState(initialDraft);
  const [focus, setFocus] = useState<FocusedDrawdownCell | null>(null);
  const [activeColor, setActiveColor] = useState(
    initialDraft.warpColors[0] || initialDraft.weftColors[0] || '#f3ede2',
  );
  const [showExplore, setShowExplore] = useState(false);
  const [parserStatus, setParserStatus] = useState<ParserStatus>('checking');
  const [busy, setBusy] = useState(false);
  const [renderBusy, setRenderBusy] = useState(false);
  const [renderJob, setRenderJob] = useState<BlenderRenderJob | null>(null);
  const [pastedText, setPastedText] = useState('');
  const [importMessage, setImportMessage] = useState(
    'Start from a preset, build manually, or import WIF, JSON, pasted text, and screenshots.',
  );
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const counts = useMemo(() => getDraftCounts(draft), [draft]);

  useEffect(() => {
    saveDraftToStorage(draft);
  }, [draft]);

  useEffect(() => {
    let alive = true;

    checkParserStatus().then((status) => {
      if (alive) {
        setParserStatus(status);
      }
    });

    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    if (!renderJob || (renderJob.status !== 'queued' && renderJob.status !== 'running')) {
      return undefined;
    }

    const timeoutId = window.setTimeout(async () => {
      try {
        const nextJob = await fetchDraftRenderJob(renderJob.id);
        setRenderJob(nextJob);

        if (nextJob.status === 'succeeded') {
          setImportMessage(
            `Rendered ${nextJob.draftTitle || 'current draft'} through headless Blender. The preview window now shows the latest swatch.`,
          );
        } else if (nextJob.status === 'failed') {
          setImportMessage(nextJob.message || 'Headless Blender could not finish the preview render.');
        }
      } catch (error) {
        setImportMessage(
          error instanceof Error ? error.message : 'Could not refresh the Blender render job status.',
        );
      }
    }, 1200);

    return () => {
      window.clearTimeout(timeoutId);
    };
  }, [renderJob]);

  const handleCountsChange = (field: keyof DraftCounts, value: number) => {
    setDraft((current) => {
      const currentCounts = getDraftCounts(current);
      return updateDraftCounts(current, {
        [field]: Number.isFinite(value) ? value : currentCounts[field],
      });
    });
  };

  const handlePresetChange = (presetId: string) => {
    const preset = presets.find((entry) => entry.id === presetId);
    if (!preset) {
      return;
    }
    setDraft({
      ...preset.document,
      warnings: [],
      parseConfidence: 1,
      sourceLabel: `Preset: ${preset.label}`,
    });
    setFocus(null);
    setImportMessage(`Loaded ${preset.label}. ${preset.summary}`);
  };

  const handleImportButton = () => {
    fileInputRef.current?.click();
  };

  const handleFileChange = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }

    setBusy(true);
    try {
      const result = await parseFileInput(file);
      setDraft(result.draft);
      setFocus(null);
      setImportMessage(describeImportSource(result.draft, result.mode));
    } catch (error) {
      setImportMessage(
        error instanceof Error ? error.message : 'Unable to import that file.',
      );
    } finally {
      setBusy(false);
      event.target.value = '';
    }
  };

  const handleParsePastedText = async () => {
    setBusy(true);
    try {
      const result = await parsePastedText(pastedText);
      setDraft(result.draft);
      setFocus(null);
      setImportMessage(describeImportSource(result.draft, result.mode));
    } catch (error) {
      setImportMessage(
        error instanceof Error ? error.message : 'Unable to parse the pasted content.',
      );
    } finally {
      setBusy(false);
    }
  };

  const handleExportCanonical = () => {
    downloadTextFile('weaving-draft.json', serializeDraft(draft));
  };

  const handleExportBlender = () => {
    buildBlenderHandoff(draft);
    downloadTextFile('weaving-draft-blender.json', serializeBlenderHandoff(draft));
  };

  const handleResetDraft = () => {
    setDraft(createBlankDraft({ sourceType: 'manual', title: 'Untitled Draft' }));
    setFocus(null);
    setImportMessage('Started a fresh manual draft.');
  };

  return (
    <div className="studio-shell" data-testid="draft-studio-app">
      <div className="studio-shell__texture" />
      <StudioToolbar
        counts={counts}
        draft={draft}
        parserStatus={parserStatus}
        presets={presets}
        busy={busy}
        exploreOpen={showExplore}
        onPresetChange={handlePresetChange}
        onToggleExplore={() => setShowExplore((current) => !current)}
        onCountsChange={handleCountsChange}
        onImportClick={handleImportButton}
        onReset={handleResetDraft}
      />

      {showExplore ? (
        <div className="studio-explore">
          <ExploreLibrary
            presets={presets}
            onLoadPreset={(presetId) => {
              handlePresetChange(presetId);
              setShowExplore(false);
            }}
            onLoadDraft={(nextDraft, label) => {
              setDraft({
                ...normalizeDraft(nextDraft),
                title: nextDraft.title || label,
                sourceLabel: label,
              });
              setFocus(null);
              setImportMessage(`Loaded ${label} from the local book library.`);
              setShowExplore(false);
            }}
            onClose={() => setShowExplore(false)}
          />
        </div>
      ) : null}

      <input
        ref={fileInputRef}
        type="file"
        className="hidden"
        data-testid="import-file-input"
        accept=".wif,.json,.txt,.draft,.png,.jpg,.jpeg,.webp,.bmp"
        onChange={handleFileChange}
      />

      <main className="studio-main">
        <section className="studio-editor">
          <DraftBoard
            draft={draft}
            focus={focus}
            activeColor={activeColor}
            onThreadingSelect={(endIndex, shaft) => {
              setDraft((current) => setThreadingShaft(current, endIndex, shaft));
            }}
            onTieUpToggle={(shaftIndex, treadleIndex, forcedValue) => {
              setDraft((current) => toggleTieUpCell(current, shaftIndex, treadleIndex, forcedValue));
            }}
            onTreadlingSelect={(pickIndex, treadle) => {
              setDraft((current) => setTreadlingTreadle(current, pickIndex, treadle));
            }}
            onWarpColorPaint={(endIndex, color) => {
              setDraft((current) => setWarpEndColor(current, endIndex, color));
            }}
            onWeftColorPaint={(pickIndex, color) => {
              setDraft((current) => setWeftPickColor(current, pickIndex, color));
            }}
            onFocusCell={(cell) => {
              setFocus((current) => (current?.pinned ? current : cell));
            }}
            onPinCell={(cell) => {
              setFocus((current) => {
                if (
                  current?.pinned &&
                  current.pickIndex === cell.pickIndex &&
                  current.endIndex === cell.endIndex
                ) {
                  return null;
                }
                return { ...cell, pinned: true };
              });
            }}
            onResetSection={(section) => {
              setDraft((current) => resetSection(current, section));
            }}
          />

          <InspectorPanel
            draft={draft}
            focus={focus}
            activeColor={activeColor}
            importMessage={importMessage}
            pastedText={pastedText}
            onPastedTextChange={setPastedText}
            onParsePastedText={handleParsePastedText}
            onActiveColorChange={setActiveColor}
            onApplyColorEdit={(edits) => {
              setDraft((current) => applyColorSequenceEdit(current, edits));
              setImportMessage('Applied warp and weft color sequences to the draft.');
            }}
            onApplyStructuredEdit={(edits) => {
              setDraft((current) => applyStructuredPatternEdit(current, edits));
              setImportMessage('Applied pattern text directly to the draft.');
            }}
          />
        </section>

        <RenderPanel
          draft={draft}
          importMessage={importMessage}
          renderJob={renderJob}
          renderBusy={renderBusy}
          onRenderPreview={async () => {
            setRenderBusy(true);
            try {
              const job = await requestDraftRender(normalizeDraft(draft));
              setRenderJob(job);
              setImportMessage(
                `Queued ${draft.title || 'current draft'} for a headless Blender preview render.`,
              );
            } catch (error) {
              setImportMessage(
                error instanceof Error
                  ? error.message
                  : 'Unable to start a headless Blender preview render.',
              );
            } finally {
              setRenderBusy(false);
            }
          }}
          onExportCanonical={handleExportCanonical}
          onExportBlender={handleExportBlender}
          onApplyRenderSettings={(settings) => {
            setDraft((current) => updateRenderSettings(current, settings));
            setImportMessage('Updated Blender render controls for the current draft.');
          }}
        />
      </main>
    </div>
  );
}
