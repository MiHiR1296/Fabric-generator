import { useEffect, useMemo, useRef, useState, type ChangeEvent } from 'react';
import { loadLocalPatternBooks, parsePatternBookJson, upsertLocalPatternBook } from '../domain/bookLibrary';
import { referenceBooks } from '../domain/exploreCatalog';
import type { BookPatternEntry, DraftDocument, PatternBook, PresetDefinition } from '../domain/types';

interface ExploreLibraryProps {
  presets: PresetDefinition[];
  onLoadPreset: (presetId: string) => void;
  onLoadDraft: (draft: DraftDocument, label: string) => void;
  onClose: () => void;
}

function accessLabel(book: PatternBook) {
  if (book.access === 'builtin') {
    return 'Built In';
  }
  if (book.access === 'local') {
    return 'Local Library';
  }
  if (book.access === 'public-domain') {
    return 'Public Domain';
  }
  return 'Cataloged Source';
}

function formatDraftCount(draftCount?: number) {
  if (!draftCount) {
    return null;
  }
  return `${draftCount.toLocaleString()} patterns`;
}

function patternStatusLabel(pattern: BookPatternEntry) {
  return pattern.status === 'loadable' ? 'Loadable' : 'Pending';
}

export default function ExploreLibrary({
  presets,
  onLoadPreset,
  onLoadDraft,
  onClose,
}: ExploreLibraryProps) {
  const [query, setQuery] = useState('');
  const [localBooks, setLocalBooks] = useState<PatternBook[]>(() => loadLocalPatternBooks());
  const [selectedBookId, setSelectedBookId] = useState('starter-book');
  const [importState, setImportState] = useState('');
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const books = useMemo<PatternBook[]>(
    () => [
      {
        id: 'starter-book',
        title: 'Prototype Starter Drafts',
        summary:
          'A small bundled book of starter patterns that load instantly into the editor.',
        sourceLabel: 'Prototype library',
        access: 'builtin',
        tags: ['preset', 'instant load', 'starter'],
        patterns: presets.map((preset) => ({
          id: preset.id,
          title: preset.label,
          summary: preset.summary,
          tags: ['preset', 'starter'],
          presetId: preset.id,
          status: 'loadable',
        })),
      },
      ...localBooks,
      ...referenceBooks,
    ],
    [localBooks, presets],
  );

  const filteredBooks = useMemo(() => {
    const search = query.trim().toLowerCase();
    if (!search) {
      return books;
    }

    return books.filter((book) =>
      [
        book.title,
        book.summary,
        book.author,
        book.year,
        book.tags.join(' '),
        ...book.patterns.map(
          (pattern) =>
            `${pattern.referenceCode || ''} ${pattern.referencePage || ''} ${pattern.title} ${pattern.summary} ${pattern.tags.join(' ')}`,
        ),
      ]
        .filter(Boolean)
        .join(' ')
        .toLowerCase()
        .includes(search),
    );
  }, [books, query]);

  useEffect(() => {
    if (!filteredBooks.some((book) => book.id === selectedBookId)) {
      setSelectedBookId(filteredBooks[0]?.id || '');
    }
  }, [filteredBooks, selectedBookId]);

  const selectedBook = filteredBooks.find((book) => book.id === selectedBookId) || filteredBooks[0] || null;

  const handleImportBook = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }

    try {
      const text = await file.text();
      const book = parsePatternBookJson(text);
      const nextBooks = upsertLocalPatternBook(book);
      setLocalBooks(nextBooks);
      setSelectedBookId(book.id);
      setImportState(`Imported ${book.title} with ${book.patterns.length} patterns.`);
    } catch (error) {
      setImportState(error instanceof Error ? error.message : 'Could not import that pattern-book JSON.');
    } finally {
      event.target.value = '';
    }
  };

  return (
    <section className="card explore-library" data-testid="explore-library">
      <div className="explore-library__header">
        <div>
          <p className="eyebrow">Explore / Load</p>
          <h2>Browse source books, then load patterns into the editor</h2>
          <p className="muted">
            This shelf now opens books instead of sending you to outside sites. Only patterns that are
            locally present in the prototype or imported by you are loadable here.
          </p>
        </div>
        <button className="button button--ghost" onClick={onClose}>
          Close
        </button>
      </div>

      <div className="explore-library__toolbar">
        <label className="field explore-library__search">
          <span>Search books, authors, and patterns</span>
          <input
            type="text"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="e.g. Oelsner, twill, color, starter"
          />
        </label>

        <input
          ref={fileInputRef}
          type="file"
          className="hidden"
          accept=".json"
          onChange={handleImportBook}
        />

        <button className="button" onClick={() => fileInputRef.current?.click()}>
          Import Local Book JSON
        </button>
      </div>

      {importState ? <p className="muted">{importState}</p> : null}

      {filteredBooks.length === 0 ? (
        <div className="explore-library__empty">
          <strong>No matches yet.</strong>
          <p className="muted">Try a broader term like `historic`, `reference`, or `starter`.</p>
        </div>
      ) : (
        <div className="explore-browser">
          <aside className="explore-shelf">
            {filteredBooks.map((book) => {
              const isSelected = selectedBook?.id === book.id;
              return (
                <button
                  key={book.id}
                  className={[
                    'explore-shelf__book',
                    isSelected ? 'explore-shelf__book--selected' : '',
                  ].join(' ')}
                  onClick={() => setSelectedBookId(book.id)}
                >
                  <span className={`status-pill explore-card__pill explore-card__pill--${book.access}`}>
                    {accessLabel(book)}
                  </span>
                  <strong>{book.title}</strong>
                  {(book.author || book.year) ? (
                    <span className="explore-card__meta">
                      {[book.author, book.year].filter(Boolean).join(' · ')}
                    </span>
                  ) : null}
                  {formatDraftCount(book.draftCount || book.patterns.length) ? (
                    <span className="explore-card__count">
                      {formatDraftCount(book.draftCount || book.patterns.length)}
                    </span>
                  ) : null}
                </button>
              );
            })}
          </aside>

          {selectedBook ? (
            <section className="explore-book">
              <div className="explore-book__header">
                <div>
                  <span className={`status-pill explore-card__pill explore-card__pill--${selectedBook.access}`}>
                    {accessLabel(selectedBook)}
                  </span>
                  <h3>{selectedBook.title}</h3>
                  {(selectedBook.author || selectedBook.year) ? (
                    <p className="explore-card__meta">
                      {[selectedBook.author, selectedBook.year].filter(Boolean).join(' · ')}
                    </p>
                  ) : null}
                </div>
                {formatDraftCount(selectedBook.draftCount || selectedBook.patterns.length) ? (
                  <span className="explore-card__count">
                    {formatDraftCount(selectedBook.draftCount || selectedBook.patterns.length)}
                  </span>
                ) : null}
              </div>

              <p>{selectedBook.summary}</p>

              <div className="explore-card__tags">
                {selectedBook.tags.map((tag) => (
                  <span key={tag} className="explore-card__tag">
                    {tag}
                  </span>
                ))}
              </div>

              {selectedBook.note ? (
                <div className="explore-book__note">
                  <strong>Catalog note</strong>
                  <p>{selectedBook.note}</p>
                  {selectedBook.referenceUrl ? (
                    <p>
                      <a href={selectedBook.referenceUrl} target="_blank" rel="noreferrer">
                        Open book reference
                      </a>
                    </p>
                  ) : null}
                </div>
              ) : null}

              <div className="explore-book__patterns">
                <div className="explore-library__section-header">
                  <div>
                    <h3>Patterns</h3>
                    <p className="muted">
                      Select a pattern below when local data is available for loading.
                    </p>
                  </div>
                </div>

                {selectedBook.patterns.length === 0 ? (
                  <div className="explore-book__empty-patterns">
                    <strong>No bundled pattern index yet.</strong>
                    <p className="muted">
                      This book is cataloged as a source, but its pattern-by-pattern extraction is not
                      included in the prototype repository.
                    </p>
                  </div>
                ) : (
                  <div className="explore-patterns">
                    {selectedBook.patterns.map((pattern) => (
                      <article key={pattern.id} className="explore-pattern">
                        <div className="explore-pattern__header">
                          <div>
                            {pattern.referenceCode || pattern.referencePage ? (
                              <p className="explore-pattern__reference">
                                {[pattern.referenceCode, pattern.referencePage].filter(Boolean).join(' · ')}
                              </p>
                            ) : null}
                            <h4>{pattern.title}</h4>
                            <p>{pattern.summary}</p>
                          </div>
                          <span
                            className={[
                              'status-pill',
                              'explore-pattern__status',
                              pattern.status === 'loadable'
                                ? 'status-pill--online'
                                : 'status-pill--source',
                            ].join(' ')}
                          >
                            {patternStatusLabel(pattern)}
                          </span>
                        </div>

                        <div className="explore-card__tags">
                          {pattern.tags.map((tag) => (
                            <span key={tag} className="explore-card__tag">
                              {tag}
                            </span>
                          ))}
                        </div>

                        {pattern.note ? <p className="muted">{pattern.note}</p> : null}

                        {pattern.status === 'loadable' && pattern.presetId ? (
                          <button
                            className="button button--accent"
                            onClick={() => onLoadPreset(pattern.presetId!)}
                          >
                            Load Pattern
                          </button>
                        ) : null}

                        {pattern.status === 'loadable' && pattern.draft ? (
                          <button
                            className="button button--accent"
                            onClick={() => onLoadDraft(pattern.draft!, `${selectedBook.title}: ${pattern.title}`)}
                          >
                            Load Pattern
                          </button>
                        ) : null}
                      </article>
                    ))}
                  </div>
                )}
              </div>
            </section>
          ) : null}
        </div>
      )}
    </section>
  );
}
