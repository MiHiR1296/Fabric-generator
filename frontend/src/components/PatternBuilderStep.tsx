import { useEffect, useMemo, useRef, useState } from 'react';
import type { Dispatch, SetStateAction } from 'react';
import ColorBindingGrid from './ColorBindingGrid';
import DraftBoard from './DraftBoard';
import InspectorPanel from './InspectorPanel';
import PatternPickerPanel from './PatternPickerPanel';
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
import {
  builtinHookPatternBooks,
  getHookMaterialSlots,
  loadLocalHookPatternBooks,
  missingHookMaterialBindings,
  normalizeHookPattern,
  parseHookPatternBookJson,
  syncHookMaterialBindings,
  upsertLocalHookPatternBook,
} from '../domain/hook';
import { saveDraftAsLocalPattern } from '../domain/bookLibrary';
import { presets } from '../domain/presets';
import type {
  ColorBinding,
  DraftCounts,
  DraftDocument,
  FabricStructureType,
  FocusedDrawdownCell,
  HookMaterialBinding,
  HookPatternBook,
  HookPatternDocument,
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
  structureType: FabricStructureType;
  setStructureType: Dispatch<SetStateAction<FabricStructureType>>;
  hookPattern: HookPatternDocument;
  setHookPattern: Dispatch<SetStateAction<HookPatternDocument>>;
  hookMaterialBindings: HookMaterialBinding[];
  setHookMaterialBindings: Dispatch<SetStateAction<HookMaterialBinding[]>>;
}

const HOOK_SLOT_COLORS = [
  '#d9b66f',
  '#6bb6d9',
  '#c485d9',
  '#81c784',
  '#d98282',
  '#e0d96f',
];

function hookStats(pattern: HookPatternDocument) {
  let activeCells = 0;
  pattern.stitchCodes.forEach((row) => {
    row.forEach((code) => {
      if (code !== 0) activeCells += 1;
    });
  });
  return {
    activeCells,
    materialSlots: getHookMaterialSlots(pattern),
    chainCount: pattern.chains.length,
  };
}

function HookPatternPreview({ pattern }: { pattern: HookPatternDocument }) {
  const materialByChain = new Map(pattern.chains.map((chain) => [chain.id, chain.materialSlot]));
  return (
    <div
      className="hook-pattern-preview"
      style={{ gridTemplateColumns: `repeat(${pattern.columns}, minmax(0, 1fr))` }}
      aria-label={`${pattern.title || 'Hook pattern'} preview`}
    >
      {pattern.stitchCodes.flatMap((row, rowIndex) =>
        row.map((code, colIndex) => {
          const chainId = pattern.chainIds[rowIndex]?.[colIndex] ?? colIndex;
          const materialSlot = materialByChain.get(chainId) ?? 0;
          return (
            <span
              key={`${rowIndex}-${colIndex}`}
              className={`hook-pattern-preview__cell${
                code === 0 ? ' hook-pattern-preview__cell--empty' : ''
              }`}
              style={{
                backgroundColor:
                  code === 0
                    ? 'transparent'
                    : HOOK_SLOT_COLORS[materialSlot % HOOK_SLOT_COLORS.length],
              }}
              title={`Row ${rowIndex + 1}, column ${colIndex + 1}`}
            />
          );
        }),
      )}
    </div>
  );
}

function HookPatternWorkspace({
  pattern,
  yarnAssets,
  materialBindings,
  setMaterialBindings,
  onLoadPattern,
}: {
  pattern: HookPatternDocument;
  yarnAssets: YarnAsset[];
  materialBindings: HookMaterialBinding[];
  setMaterialBindings: Dispatch<SetStateAction<HookMaterialBinding[]>>;
  onLoadPattern: (pattern: HookPatternDocument, label: string, summary: string) => void;
}) {
  const stats = hookStats(pattern);
  const readyAssets = yarnAssets.filter((asset) => asset.status === 'ready');
  const missingSlots = missingHookMaterialBindings(pattern, materialBindings);
  const [query, setQuery] = useState('');
  const [localHookBooks, setLocalHookBooks] = useState<HookPatternBook[]>(() => loadLocalHookPatternBooks());
  const [selectedBookId, setSelectedBookId] = useState(builtinHookPatternBooks[0]?.id || '');
  const [importState, setImportState] = useState('');
  const hookBookInputRef = useRef<HTMLInputElement | null>(null);
  const hookBooks = useMemo(
    () => [...localHookBooks, ...builtinHookPatternBooks],
    [localHookBooks],
  );
  const filteredHookBooks = useMemo(() => {
    const search = query.trim().toLowerCase();
    if (!search) return hookBooks;
    return hookBooks.filter((book) =>
      [
        book.title,
        book.summary,
        book.author,
        book.year,
        book.tags.join(' '),
        ...book.patterns.map((entry) => `${entry.title} ${entry.summary} ${entry.tags.join(' ')}`),
      ]
        .filter(Boolean)
        .join(' ')
        .toLowerCase()
        .includes(search),
    );
  }, [hookBooks, query]);
  const selectedBook = filteredHookBooks.find((book) => book.id === selectedBookId)
    || filteredHookBooks[0]
    || null;
  const selectedBookPatterns = selectedBook?.patterns || [];
  const selectedPatternId = selectedBookPatterns.find((entry) => entry.pattern?.title === pattern.title)?.id || '';

  useEffect(() => {
    if (selectedBook && selectedBook.id !== selectedBookId) {
      setSelectedBookId(selectedBook.id);
    }
  }, [selectedBook, selectedBookId]);

  const loadHookPatternEntry = (entry: HookPatternBook['patterns'][number]) => {
    if (entry.status !== 'loadable' || !entry.pattern) return;
    onLoadPattern(entry.pattern, entry.title, entry.summary);
  };

  const handleHookBookImport = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    try {
      const text = await file.text();
      const book = parseHookPatternBookJson(text);
      const nextBooks = upsertLocalHookPatternBook(book);
      setLocalHookBooks(nextBooks);
      setSelectedBookId(book.id);
      setImportState(`Imported ${book.title} with ${book.patterns.length} hook patterns.`);
    } catch (error) {
      setImportState(error instanceof Error ? error.message : 'Could not import that hook pattern book.');
    } finally {
      event.target.value = '';
    }
  };

  return (
    <section className="card fabric-step-card hook-pattern-workspace" data-testid="hook-pattern-workspace">
      <input
        ref={hookBookInputRef}
        type="file"
        className="hidden"
        accept=".json"
        onChange={handleHookBookImport}
      />
      <div className="fabric-step-card__header">
        <div>
          <p className="eyebrow">Knit / Hook Workflow</p>
          <h2>{pattern.title || 'Hook Pattern'}</h2>
          <p className="fabric-step-card__summary">
            Load a hook or knit pattern source, then render it with the yarn selected in your project.
          </p>
        </div>
        <div className="fabric-step-card__actions">
          <div className="status-pill status-pill--source">
            {pattern.rows} x {pattern.columns}
          </div>
          <div className="status-pill status-pill--online">{stats.activeCells} active</div>
        </div>
      </div>

      <div className="hook-workspace-grid">
        <section className="hook-control-section hook-control-section--library">
          <div className="hook-section-heading">
            <div>
              <p className="eyebrow">Pattern Source</p>
              <h3>Library</h3>
            </div>
            <button type="button" className="button button--tiny" onClick={() => hookBookInputRef.current?.click()}>
              Import JSON
            </button>
          </div>

          <div className="hook-control-grid">
            <label className="field field--compact">
              <span>Book</span>
              <select
                value={selectedBook?.id || ''}
                onChange={(event) => setSelectedBookId(event.target.value)}
              >
                {filteredHookBooks.map((book) => (
                  <option key={book.id} value={book.id}>
                    {book.title}
                  </option>
                ))}
              </select>
            </label>
            <label className="field field--compact">
              <span>Search</span>
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="starter, crochet, knit"
              />
            </label>
          </div>

          <div className="hook-book-list" role="list" aria-label="Hook pattern books">
            {filteredHookBooks.map((book) => (
              <button
                key={book.id}
                type="button"
                className={`hook-book-card${selectedBook?.id === book.id ? ' hook-book-card--active' : ''}`}
                onClick={() => setSelectedBookId(book.id)}
              >
                <span>{book.title}</span>
                <small>{book.patternCount || book.patterns.length} patterns · {book.access}</small>
              </button>
            ))}
          </div>
          {importState ? <p className="muted hook-import-state">{importState}</p> : null}
        </section>

        <section className="hook-control-section hook-control-section--patterns">
          <div className="hook-section-heading">
            <div>
              <p className="eyebrow">Preset</p>
              <h3>Pattern</h3>
            </div>
            <span className="status-pill status-pill--source">{selectedBookPatterns.length} options</span>
          </div>

          <label className="field field--compact">
            <span>Selected Pattern</span>
            <select
              value={selectedPatternId}
              onChange={(event) => {
                const entry = selectedBookPatterns.find((item) => item.id === event.target.value);
                if (entry) loadHookPatternEntry(entry);
              }}
            >
              <option value="" disabled>
                Choose pattern
              </option>
              {selectedBookPatterns.map((entry) => (
                <option
                  key={entry.id}
                  value={entry.id}
                  disabled={entry.status !== 'loadable' || !entry.pattern}
                >
                  {entry.title}
                </option>
              ))}
            </select>
          </label>

          <div className="hook-preset-list" role="list" aria-label="Hook presets">
            {selectedBookPatterns.map((entry) => {
              const selected = entry.pattern?.title === pattern.title;
              return (
                <button
                  key={entry.id}
                  type="button"
                  className={`hook-preset-card${selected ? ' hook-preset-card--active' : ''}`}
                  onClick={() => loadHookPatternEntry(entry)}
                  disabled={entry.status !== 'loadable' || !entry.pattern}
                  data-testid={`hook-preset-${entry.id}`}
                >
                  <span>{entry.title}</span>
                  <small>{entry.summary}</small>
                </button>
              );
            })}
          </div>
        </section>

        <section className="hook-control-section hook-control-section--preview">
          <div className="hook-section-heading">
            <div>
              <p className="eyebrow">Chart</p>
              <h3>Preview</h3>
            </div>
            <div className="fabric-step-card__actions">
              <span className="status-pill status-pill--source">{stats.materialSlots.length} slots</span>
              <span className="status-pill status-pill--online">{stats.chainCount} chains</span>
            </div>
          </div>

          <HookPatternPreview pattern={pattern} />
        </section>
      </div>

      <section className="hook-control-section hook-material-section">
        <div className="board-section__heading">
          <div>
            <p className="eyebrow">Materials</p>
            <h2>Hook Yarn Slots</h2>
          </div>
          <div className="fabric-step-card__actions">
            <div className="status-pill status-pill--source">Slots: {stats.materialSlots.length}</div>
            <div className="status-pill status-pill--online">Ready Yarns: {readyAssets.length}</div>
          </div>
        </div>

        <div className="color-binding-grid color-binding-grid--compact">
          {stats.materialSlots.map((materialSlot) => {
            const binding = materialBindings.find((entry) => entry.materialSlot === materialSlot);
            const selectedAsset = binding?.yarnAssetId
              ? yarnAssets.find((asset) => asset.id === binding.yarnAssetId)
              : null;
            const previewUrl = selectedAsset?.diffuseUrl || selectedAsset?.sourceUrl;
            return (
              <label className="color-binding-card" key={materialSlot}>
                <span className="color-binding-card__label">
                  <span
                    className="color-binding-card__swatch"
                    style={{ background: HOOK_SLOT_COLORS[materialSlot % HOOK_SLOT_COLORS.length] }}
                  />
                  <span>Material {materialSlot + 1}</span>
                </span>
                <div className="color-binding-card__yarn">
                  {previewUrl ? (
                    <img
                      className="color-binding-card__preview"
                      src={previewUrl}
                      alt={`${selectedAsset?.label || 'Yarn'} preview`}
                      title={selectedAsset?.label}
                    />
                  ) : (
                    <span
                      className="color-binding-card__preview color-binding-card__preview--empty"
                      aria-hidden="true"
                    />
                  )}
                  <select
                    value={binding?.yarnAssetId || ''}
                    data-testid={`hook-material-select-${materialSlot}`}
                    onChange={(event) => {
                      const yarnAssetId = event.target.value || null;
                      setMaterialBindings((current) =>
                        syncHookMaterialBindings(pattern, current).map((entry) =>
                          entry.materialSlot === materialSlot ? { ...entry, yarnAssetId } : entry,
                        ),
                      );
                    }}
                  >
                    <option value="">Select processed yarn</option>
                    {readyAssets.map((asset) => (
                      <option key={asset.id} value={asset.id}>
                        {asset.label}
                      </option>
                    ))}
                  </select>
                </div>
              </label>
            );
          })}
        </div>

        <p className="muted" data-testid="hook-binding-status-message">
          {missingSlots.length
            ? `${missingSlots.length} hook material slot${missingSlots.length === 1 ? '' : 's'} still need yarn assignments before rendering.`
            : 'Every hook material slot is assigned to a processed yarn asset.'}
        </p>
      </section>
    </section>
  );
}

function HookPatternInspector({ pattern }: { pattern: HookPatternDocument }) {
  const stats = hookStats(pattern);
  const unsupportedCodes = (pattern.stitchLegend || [])
    .filter((entry) => !entry.supported)
    .map((entry) => entry.code);
  return (
    <aside className="inspector" data-testid="hook-pattern-inspector">
      <section className="inspector__card">
        <h2>Hook Pattern</h2>
        <div className="inspector__facts">
          <div>
            <span>Rows</span>
            <strong>{pattern.rows}</strong>
          </div>
          <div>
            <span>Columns</span>
            <strong>{pattern.columns}</strong>
          </div>
          <div>
            <span>Active Cells</span>
            <strong>{stats.activeCells}</strong>
          </div>
          <div>
            <span>Chains</span>
            <strong>{stats.chainCount}</strong>
          </div>
          <div>
            <span>Material Slots</span>
            <strong>{stats.materialSlots.map((slot) => slot + 1).join(', ')}</strong>
          </div>
          <div>
            <span>Family</span>
            <strong>{pattern.structureFamily || 'crochet_hook'}</strong>
          </div>
          <div>
            <span>Direction</span>
            <strong>{pattern.rowDirection || 'alternating'}</strong>
          </div>
          <div>
            <span>Source</span>
            <strong>{pattern.source?.access || 'builtin'}</strong>
          </div>
        </div>
        {unsupportedCodes.length ? (
          <p className="muted">
            Reserved stitch codes stored for later Blender archetypes: {unsupportedCodes.join(', ')}.
          </p>
        ) : null}
      </section>
    </aside>
  );
}

export default function PatternBuilderStep({
  draft,
  setDraft,
  yarnAssets,
  colorBindings,
  setColorBindings,
  structureType,
  setStructureType,
  hookPattern,
  setHookPattern,
  hookMaterialBindings,
  setHookMaterialBindings,
}: PatternBuilderStepProps) {
  const [focus, setFocus] = useState<FocusedDrawdownCell | null>(null);
  const [activeColor, setActiveColor] = useState(
    draft.warpColors[0] || draft.weftColors[0] || '#f3ede2',
  );
  const [showPicker, setShowPicker] = useState(false);
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
  const isHookWorkflow = structureType === 'hook';

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

  const handleHookPatternLoad = (
    nextPattern: HookPatternDocument,
    label: string,
    summary: string,
  ) => {
    setHookPattern(normalizeHookPattern(nextPattern));
    setFocus(null);
    setImportMessage(`Loaded ${label}. ${summary}`);
  };

  const handleSavePattern = () => {
    const fallbackTitle = draft.title?.trim() || 'Untitled Pattern';
    const title = window.prompt('Pattern name', fallbackTitle);
    if (title === null) {
      return;
    }
    const cleanedTitle = title.trim();
    if (!cleanedTitle) {
      setImportMessage('Pattern name is required before saving.');
      return;
    }
    const { pattern } = saveDraftAsLocalPattern(draft, cleanedTitle);
    setImportMessage(`Saved "${pattern.title}" to Saved Pattern Drafts.`);
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
          exploreOpen={showPicker}
          onPresetChange={handlePresetChange}
          onToggleExplore={() => setShowPicker((current) => !current)}
          onCountsChange={handleCountsChange}
          onSavePattern={handleSavePattern}
          onImportClick={() => fileInputRef.current?.click()}
          onReset={() => {
            setDraft(createBlankDraft({ sourceType: 'manual', title: 'Untitled Draft' }));
            setFocus(null);
            setImportMessage('Started a fresh manual draft.');
          }}
          structureType={structureType}
          onStructureTypeChange={(nextStructureType) => {
            setStructureType(nextStructureType);
            setFocus(null);
            setImportMessage(
              nextStructureType === 'hook'
                ? `Selected Knit / Hook workflow with ${hookPattern.title || 'the current hook preset'}.`
                : 'Selected Weave workflow.',
            );
          }}
          showDraftControls={!isHookWorkflow}
          stepLabel="Step 2"
          title={isHookWorkflow ? 'Knit / Hook Pattern Builder' : 'Pattern Builder'}
          summaryText={
            isHookWorkflow
              ? 'Choose the hook structure that will drive the render stage.'
              : 'Shape the weave structure and color strips for your draft.'
          }
        />

        <div className="studio-editor__center">
          {isHookWorkflow ? (
            <HookPatternWorkspace
              pattern={hookPattern}
              yarnAssets={yarnAssets}
              materialBindings={hookMaterialBindings}
              setMaterialBindings={setHookMaterialBindings}
              onLoadPattern={handleHookPatternLoad}
            />
          ) : (
          <>
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
          </>
          )}
        </div>

        {isHookWorkflow ? (
          <HookPatternInspector pattern={hookPattern} />
        ) : (
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
        )}
      </div>

      {!isHookWorkflow && showPicker ? (
        <PatternPickerPanel
          presets={presets}
          onLoadPreset={(presetId) => {
            handlePresetChange(presetId);
            setShowPicker(false);
          }}
          onLoadDraft={(nextDraft, label) => {
            setDraft({
              ...normalizeDraft(nextDraft),
              title: nextDraft.title || label,
              sourceLabel: label,
            });
            setFocus(null);
            setImportMessage(`Loaded ${label} from the local book library.`);
            setShowPicker(false);
          }}
          onClose={() => setShowPicker(false)}
        />
      ) : null}
    </section>
  );
}
