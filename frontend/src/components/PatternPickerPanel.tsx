import { useEffect, useMemo, useRef, useState, type ChangeEvent } from 'react';
import {
  loadLocalPatternBooks,
  parsePatternBookJson,
  upsertLocalPatternBook,
} from '../domain/bookLibrary';
import { referenceBooks } from '../domain/exploreCatalog';
import type {
  BookPatternEntry,
  DraftDocument,
  PatternBook,
  PresetDefinition,
  WeaveType,
} from '../domain/types';

interface PatternPickerPanelProps {
  presets: PresetDefinition[];
  onLoadPreset: (presetId: string) => void;
  onLoadDraft: (draft: DraftDocument, label: string) => void;
  onClose: () => void;
}

interface PatternRow {
  book: PatternBook;
  pattern: BookPatternEntry;
  weaveType: WeaveType | 'untyped';
  shaftCount: number | null;
  searchBlob: string;
}

const WEAVE_TYPE_LABEL: Record<WeaveType | 'untyped', string> = {
  plain: 'Plain',
  twill: 'Twill',
  satin: 'Satin',
  basket: 'Basket',
  rib: 'Rib',
  compound: 'Compound',
  lace: 'Lace',
  double: 'Double',
  huck: 'Huck',
  other: 'Other',
  untyped: 'Untyped',
};

const SHAFT_BUCKETS = [2, 4, 6, 8, 12, 16, 24] as const;

function inferWeaveTypeFromTags(tags: string[]): WeaveType | undefined {
  const blob = tags.join(' ').toLowerCase();
  if (blob.includes('plain')) return 'plain';
  if (blob.includes('basket')) return 'basket';
  if (blob.includes('satin')) return 'satin';
  if (blob.includes('twill') || blob.includes('herringbone')) return 'twill';
  if (blob.includes('rib')) return 'rib';
  if (blob.includes('lace')) return 'lace';
  if (blob.includes('huck')) return 'huck';
  if (blob.includes('double')) return 'double';
  if (blob.includes('compound')) return 'compound';
  return undefined;
}

function resolveWeaveType(
  entry: { weaveType?: WeaveType; tags?: string[] },
): WeaveType | 'untyped' {
  if (entry.weaveType) return entry.weaveType;
  const inferred = inferWeaveTypeFromTags(entry.tags ?? []);
  return inferred ?? 'untyped';
}

function nearestShaftBucket(value: number | null): number | null {
  if (value === null) return null;
  let best = SHAFT_BUCKETS[0] as number;
  let bestGap = Math.abs(best - value);
  for (const bucket of SHAFT_BUCKETS) {
    const gap = Math.abs(bucket - value);
    if (gap < bestGap) {
      best = bucket;
      bestGap = gap;
    }
  }
  return value > 24 ? 24 : best;
}

function drawdownToDataUrl(draft: DraftDocument | undefined, size = 64): string | null {
  if (!draft || !draft.drawdown || draft.drawdown.length === 0) return null;
  if (typeof document === 'undefined') return null;
  const rows = draft.drawdown.length;
  const cols = draft.drawdown[0]?.length ?? 0;
  if (rows === 0 || cols === 0) return null;
  const canvas = document.createElement('canvas');
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext('2d');
  if (!ctx) return null;

  const cellW = size / cols;
  const cellH = size / rows;
  const warpColors = draft.warpColors.length ? draft.warpColors : ['#f1ead9'];
  const weftColors = draft.weftColors.length ? draft.weftColors : ['#8f5136'];

  for (let r = 0; r < rows; r += 1) {
    const row = draft.drawdown[r];
    for (let c = 0; c < cols; c += 1) {
      const isWarpOver = row[c] === 1;
      ctx.fillStyle = isWarpOver
        ? warpColors[c % warpColors.length]
        : weftColors[r % weftColors.length];
      ctx.fillRect(
        Math.floor(c * cellW),
        Math.floor(r * cellH),
        Math.ceil(cellW) + 1,
        Math.ceil(cellH) + 1,
      );
    }
  }
  return canvas.toDataURL('image/png');
}

function describeMeta(book: PatternBook, pattern: BookPatternEntry): string {
  const fragments: string[] = [book.title];
  const ref = [pattern.referenceCode, pattern.referencePage].filter(Boolean).join(' · ');
  if (ref) fragments.push(ref);
  return fragments.join(' · ');
}

export default function PatternPickerPanel({
  presets,
  onLoadPreset,
  onLoadDraft,
  onClose,
}: PatternPickerPanelProps) {
  const [localBooks, setLocalBooks] = useState<PatternBook[]>(() => loadLocalPatternBooks());
  const [query, setQuery] = useState('');
  const [debouncedQuery, setDebouncedQuery] = useState('');
  const [bookFilter, setBookFilter] = useState<Set<string>>(() => new Set());
  const [weaveFilter, setWeaveFilter] = useState<Set<WeaveType | 'untyped'>>(() => new Set());
  const [shaftFilter, setShaftFilter] = useState<number | null>(null);
  const [tagFilter, setTagFilter] = useState<Set<string>>(() => new Set());
  const [loadableOnly, setLoadableOnly] = useState(true);
  const [importState, setImportState] = useState('');
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const previewCacheRef = useRef<Map<string, string | null>>(new Map());

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedQuery(query.trim().toLowerCase()), 150);
    return () => window.clearTimeout(timer);
  }, [query]);

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [onClose]);

  const books = useMemo<PatternBook[]>(
    () => [
      {
        id: 'starter-book',
        title: 'Prototype Starter Drafts',
        summary: 'Bundled presets that load instantly into the editor.',
        sourceLabel: 'Prototype library',
        access: 'builtin',
        tags: ['preset', 'instant load', 'starter'],
        patterns: presets.map<BookPatternEntry>((preset) => ({
          id: preset.id,
          title: preset.label,
          summary: preset.summary,
          tags: ['preset', 'starter'],
          presetId: preset.id,
          status: 'loadable',
          weaveType: preset.weaveType,
          previewImage: preset.previewImage,
        })),
      },
      ...localBooks,
      ...referenceBooks,
    ],
    [localBooks, presets],
  );

  const allRows = useMemo<PatternRow[]>(() => {
    const rows: PatternRow[] = [];
    for (const book of books) {
      for (const pattern of book.patterns) {
        const draft =
          pattern.draft ??
          (pattern.presetId ? presets.find((p) => p.id === pattern.presetId)?.document : undefined);
        const shaftCount = draft?.shaftCount ?? null;
        const weaveType = resolveWeaveType(pattern);
        const searchBlob = [
          pattern.title,
          pattern.summary,
          pattern.referenceCode,
          pattern.referencePage,
          pattern.tags.join(' '),
          weaveType,
          book.title,
          book.author,
          book.year,
        ]
          .filter(Boolean)
          .join(' ')
          .toLowerCase();
        rows.push({ book, pattern, weaveType, shaftCount, searchBlob });
      }
    }
    return rows;
  }, [books, presets]);

  const filteredRows = useMemo(() => {
    return allRows.filter((row) => {
      if (loadableOnly && row.pattern.status !== 'loadable') return false;
      if (bookFilter.size > 0 && !bookFilter.has(row.book.id)) return false;
      if (weaveFilter.size > 0 && !weaveFilter.has(row.weaveType)) return false;
      if (shaftFilter !== null) {
        const bucket = nearestShaftBucket(row.shaftCount);
        if (bucket !== shaftFilter) return false;
      }
      if (tagFilter.size > 0) {
        const tagSet = new Set(row.pattern.tags);
        let matched = false;
        for (const tag of tagFilter) {
          if (tagSet.has(tag)) {
            matched = true;
            break;
          }
        }
        if (!matched) return false;
      }
      if (debouncedQuery && !row.searchBlob.includes(debouncedQuery)) return false;
      return true;
    });
  }, [allRows, loadableOnly, bookFilter, weaveFilter, shaftFilter, tagFilter, debouncedQuery]);

  const availableWeaveTypes = useMemo(() => {
    const set = new Set<WeaveType | 'untyped'>();
    for (const row of allRows) set.add(row.weaveType);
    return Array.from(set).sort((a, b) =>
      WEAVE_TYPE_LABEL[a].localeCompare(WEAVE_TYPE_LABEL[b]),
    );
  }, [allRows]);

  const availableTags = useMemo(() => {
    const counts = new Map<string, number>();
    for (const row of filteredRows) {
      for (const tag of row.pattern.tags) {
        counts.set(tag, (counts.get(tag) ?? 0) + 1);
      }
    }
    return Array.from(counts.entries())
      .sort((a, b) => b[1] - a[1])
      .slice(0, 18)
      .map(([tag]) => tag);
  }, [filteredRows]);

  const visibleBookCount = useMemo(() => {
    const set = new Set<string>();
    for (const row of filteredRows) set.add(row.book.id);
    return set.size;
  }, [filteredRows]);

  const toggleSetMember = <T,>(
    current: Set<T>,
    value: T,
    setter: (next: Set<T>) => void,
  ) => {
    const next = new Set(current);
    if (next.has(value)) {
      next.delete(value);
    } else {
      next.add(value);
    }
    setter(next);
  };

  const resetFilters = () => {
    setQuery('');
    setBookFilter(new Set());
    setWeaveFilter(new Set());
    setShaftFilter(null);
    setTagFilter(new Set());
  };

  const handleLoad = (row: PatternRow) => {
    if (row.pattern.presetId) {
      onLoadPreset(row.pattern.presetId);
      return;
    }
    if (row.pattern.draft) {
      onLoadDraft(row.pattern.draft, `${row.book.title}: ${row.pattern.title}`);
    }
  };

  const handleImportBook = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    try {
      const text = await file.text();
      const book = parsePatternBookJson(text);
      const nextBooks = upsertLocalPatternBook(book);
      setLocalBooks(nextBooks);
      setImportState(`Imported ${book.title} with ${book.patterns.length} patterns.`);
    } catch (error) {
      setImportState(
        error instanceof Error ? error.message : 'Could not import that pattern-book JSON.',
      );
    } finally {
      event.target.value = '';
    }
  };

  const previewFor = (row: PatternRow): string | null => {
    if (row.pattern.previewImage) return row.pattern.previewImage;
    const cache = previewCacheRef.current;
    if (cache.has(row.pattern.id)) return cache.get(row.pattern.id) ?? null;
    const draft =
      row.pattern.draft ??
      (row.pattern.presetId
        ? presets.find((p) => p.id === row.pattern.presetId)?.document
        : undefined);
    const url = drawdownToDataUrl(draft);
    cache.set(row.pattern.id, url);
    return url;
  };

  const activeFilterCount =
    bookFilter.size +
    weaveFilter.size +
    tagFilter.size +
    (shaftFilter !== null ? 1 : 0) +
    (debouncedQuery ? 1 : 0);

  return (
    <aside
      className="pattern-picker"
      role="complementary"
      aria-label="Pattern Library"
      data-testid="pattern-picker-panel"
    >
      <header className="pattern-picker__header">
        <div>
          <p className="eyebrow">Pattern Library</p>
          <h2>Browse &amp; load patterns</h2>
          <p className="muted">
            {filteredRows.length.toLocaleString()} patterns · {visibleBookCount} book
            {visibleBookCount === 1 ? '' : 's'}
          </p>
        </div>
        <button
          type="button"
          className="button button--ghost pattern-picker__close"
          onClick={onClose}
          aria-label="Close pattern library"
        >
          ×
        </button>
      </header>

      <div className="pattern-picker__body">
      <div className="pattern-picker__search">
        <label className="field">
          <span>Search patterns, books, refs</span>
          <input
            type="text"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="e.g. twill, OEL-P016, Oelsner, herringbone"
            data-testid="pattern-picker-search"
          />
        </label>
      </div>

      <div className="pattern-picker__filters">
        <details className="pattern-picker__filter-group" open>
          <summary>
            Books{bookFilter.size > 0 ? ` · ${bookFilter.size} selected` : ''}
          </summary>
          <div className="pattern-picker__chips">
            {books.map((book) => {
              const active = bookFilter.has(book.id);
              return (
                <button
                  key={book.id}
                  type="button"
                  className={`chip${active ? ' chip--active' : ''}`}
                  onClick={() => toggleSetMember(bookFilter, book.id, setBookFilter)}
                >
                  {book.title}
                  <span className="chip__count">{book.patterns.length}</span>
                </button>
              );
            })}
          </div>
        </details>

        <details className="pattern-picker__filter-group" open>
          <summary>
            Weave type{weaveFilter.size > 0 ? ` · ${weaveFilter.size} selected` : ''}
          </summary>
          <div className="pattern-picker__chips">
            {availableWeaveTypes.map((type) => {
              const active = weaveFilter.has(type);
              return (
                <button
                  key={type}
                  type="button"
                  className={`chip${active ? ' chip--active' : ''}`}
                  onClick={() => toggleSetMember(weaveFilter, type, setWeaveFilter)}
                >
                  {WEAVE_TYPE_LABEL[type]}
                </button>
              );
            })}
          </div>
        </details>

        <details className="pattern-picker__filter-group">
          <summary>Shafts{shaftFilter !== null ? ` · ${shaftFilter}` : ''}</summary>
          <div className="pattern-picker__chips">
            <button
              type="button"
              className={`chip${shaftFilter === null ? ' chip--active' : ''}`}
              onClick={() => setShaftFilter(null)}
            >
              Any
            </button>
            {SHAFT_BUCKETS.map((bucket) => (
              <button
                key={bucket}
                type="button"
                className={`chip${shaftFilter === bucket ? ' chip--active' : ''}`}
                onClick={() => setShaftFilter(shaftFilter === bucket ? null : bucket)}
              >
                {bucket}
              </button>
            ))}
          </div>
        </details>

        {availableTags.length > 0 ? (
          <details className="pattern-picker__filter-group">
            <summary>Tags{tagFilter.size > 0 ? ` · ${tagFilter.size} selected` : ''}</summary>
            <div className="pattern-picker__chips">
              {availableTags.map((tag) => {
                const active = tagFilter.has(tag);
                return (
                  <button
                    key={tag}
                    type="button"
                    className={`chip${active ? ' chip--active' : ''}`}
                    onClick={() => toggleSetMember(tagFilter, tag, setTagFilter)}
                  >
                    {tag}
                  </button>
                );
              })}
            </div>
          </details>
        ) : null}

        <div className="pattern-picker__filter-row">
          <label className="pattern-picker__toggle">
            <input
              type="checkbox"
              checked={loadableOnly}
              onChange={(event) => setLoadableOnly(event.target.checked)}
            />
            <span>Loadable only</span>
          </label>
          {activeFilterCount > 0 ? (
            <button type="button" className="button button--ghost" onClick={resetFilters}>
              Clear filters ({activeFilterCount})
            </button>
          ) : null}
        </div>

        <div className="pattern-picker__filter-row">
          <input
            ref={fileInputRef}
            type="file"
            className="hidden"
            accept=".json"
            onChange={handleImportBook}
          />
          <button
            type="button"
            className="button button--ghost"
            onClick={() => fileInputRef.current?.click()}
          >
            Import book JSON
          </button>
          {importState ? <span className="muted">{importState}</span> : null}
        </div>
      </div>

      <div className="pattern-picker__list" data-testid="pattern-picker-list">
        {filteredRows.length === 0 ? (
          <div className="pattern-picker__empty">
            <strong>No patterns match these filters.</strong>
            <p className="muted">Clear a filter or broaden the search to see more.</p>
          </div>
        ) : (
          filteredRows.map((row) => {
            const previewUrl = previewFor(row);
            const loadable = row.pattern.status === 'loadable';
            return (
              <article
                key={`${row.book.id}::${row.pattern.id}`}
                className={`pattern-card${loadable ? '' : ' pattern-card--pending'}`}
              >
                <div className="pattern-card__preview">
                  {previewUrl ? (
                    <img src={previewUrl} alt="" width={64} height={64} />
                  ) : (
                    <div className="pattern-card__preview-placeholder" aria-hidden="true">
                      <span>{(row.pattern.title || '?').slice(0, 1)}</span>
                    </div>
                  )}
                </div>
                <div className="pattern-card__body">
                  <header className="pattern-card__header">
                    <h3>{row.pattern.title}</h3>
                    <span
                      className={`status-pill pattern-card__status pattern-card__status--${
                        loadable ? 'loadable' : 'pending'
                      }`}
                    >
                      {loadable ? 'Loadable' : 'Pending'}
                    </span>
                  </header>
                  <p className="pattern-card__meta">{describeMeta(row.book, row.pattern)}</p>
                  <div className="pattern-card__chips">
                    <span className="chip chip--static">{WEAVE_TYPE_LABEL[row.weaveType]}</span>
                    {row.shaftCount !== null ? (
                      <span className="chip chip--static">{row.shaftCount} shafts</span>
                    ) : null}
                  </div>
                  <p className="pattern-card__summary">{row.pattern.summary}</p>
                  <div className="pattern-card__actions">
                    <button
                      type="button"
                      className="button button--accent"
                      onClick={() => handleLoad(row)}
                      disabled={!loadable || (!row.pattern.presetId && !row.pattern.draft)}
                    >
                      Load Pattern
                    </button>
                  </div>
                </div>
              </article>
            );
          })
        )}
      </div>
      </div>
    </aside>
  );
}
