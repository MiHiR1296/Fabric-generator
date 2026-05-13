import { useEffect, useMemo, useRef, useState } from 'react';
import type { Dispatch, SetStateAction } from 'react';
import ColorBindingGrid from './ColorBindingGrid';
import DraftBoard from './DraftBoard';
import ExploreLibrary from './ExploreLibrary';
import InspectorPanel from './InspectorPanel';
import StudioToolbar from './StudioToolbar';
import {
  applyColorSequenceEdit,
  applyStructuredPatternEdit,
  createBlankDraft,
  getDraftCounts,
  normalizeDraft,
  resetSection,
  setThreadingShaft,
  setTreadlingTreadle,
  setWarpEndColor,
  setWeftPickColor,
  toggleTieUpCell,
  updateDraftCounts,
} from '../domain/draft';
import { presets } from '../domain/presets';
import type {
  ColorBinding,
  DraftCounts,
  DraftDocument,
  FocusedDrawdownCell,
  ParserStatus,
  YarnAsset,
} from '../domain/types';
import {
  checkParserStatus,
  describeImportSource,
  parseFileInput,
  parsePastedText,
} from '../utils/parserApi';

interface PatternBuilderStepProps {
  draft: DraftDocument;
  setDraft: Dispatch<SetStateAction<DraftDocument>>;
  yarnAssets: YarnAsset[];
  colorBindings: ColorBinding[];
  setColorBindings: Dispatch<SetStateAction<ColorBinding[]>>;
}

export default function PatternBuilderStep({
  draft,
  setDraft,
  yarnAssets,
  colorBindings,
  setColorBindings,
}: PatternBuilderStepProps) {
  const [focus, setFocus] = useState<FocusedDrawdownCell | null>(null);
  const [activeColor, setActiveColor] = useState(
    draft.warpColors[0] || draft.weftColors[0] || '#f3ede2',
  );
  const [showExplore, setShowExplore] = useState(false);
  const [parserStatus, setParserStatus] = useState<ParserStatus>('checking');
  const [busy, setBusy] = useState(false);
  const [pastedText, setPastedText] = useState('');
  const [importMessage, setImportMessage] = useState(
    'Load a preset, import a file, or build the draft manually before assigning yarns to colors.',
  );
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const counts = useMemo(() => getDraftCounts(draft), [draft]);
  const paletteSignature = useMemo(
    () => [...draft.warpColors, ...draft.weftColors].join('|'),
    [draft.warpColors, draft.weftColors],
  );

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
    const nextColor = draft.warpColors[0] || draft.weftColors[0] || '#f3ede2';
    if (!activeColor || ![...draft.warpColors, ...draft.weftColors].includes(activeColor)) {
      setActiveColor(nextColor);
    }
  }, [activeColor, draft.warpColors, draft.weftColors, paletteSignature]);

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
      setImportMessage(error instanceof Error ? error.message : 'Unable to import that file.');
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

  return (
    <section className="fabric-step-panel" data-testid="pattern-builder-step">
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

      <div className="studio-editor">
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
          onImportClick={() => fileInputRef.current?.click()}
          onReset={() => {
            setDraft(createBlankDraft({ sourceType: 'manual', title: 'Untitled Draft' }));
            setFocus(null);
            setImportMessage('Started a fresh manual draft.');
          }}
          stepLabel="Step 2"
          title="Pattern Builder"
          summaryText="Shape the weave structure and color strips for your draft."
        />

        <div className="studio-editor__center">
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

          <ColorBindingGrid
            draft={draft}
            yarnAssets={yarnAssets}
            colorBindings={colorBindings}
            setColorBindings={setColorBindings}
            eyebrow="Yarn Mapping"
            title="Warp & Weft → Yarn"
            compact
          />
        </div>

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
      </div>
    </section>
  );
}
