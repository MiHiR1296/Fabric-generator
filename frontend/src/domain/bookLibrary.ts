import { normalizeDraft } from './draft.ts';
import type { BookPatternEntry, DraftDocument, PatternBook } from './types.ts';

const BOOK_LIBRARY_STORAGE_KEY = 'weaving-draft-studio/local-pattern-books';
const SAVED_PATTERNS_BOOK_ID = 'saved-pattern-drafts';
export const PATTERN_LIBRARY_UPDATED_EVENT = 'pattern-library-updated';

function slugify(value: string) {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 80);
}

function normalizePattern(pattern: any, fallbackIndex: number): BookPatternEntry {
  const draft = pattern?.draft || pattern?.document || pattern?.draftDocument;

  return {
    id: String(pattern?.id || `pattern-${fallbackIndex + 1}`),
    title: String(pattern?.title || `Pattern ${fallbackIndex + 1}`),
    summary: String(pattern?.summary || 'Imported from a local pattern-book catalog.'),
    tags: Array.isArray(pattern?.tags) ? pattern.tags.map(String) : ['imported'],
    draft: draft ? normalizeDraft(draft) : undefined,
    status: draft ? 'loadable' : 'pending',
    note: pattern?.note ? String(pattern.note) : undefined,
  };
}

function normalizePatternBook(raw: any): PatternBook {
  const title = String(raw?.title || 'Imported Pattern Book').trim() || 'Imported Pattern Book';
  const patterns = Array.isArray(raw?.patterns) ? raw.patterns.map(normalizePattern) : [];

  if (patterns.length === 0) {
    throw new Error('This book JSON does not contain any patterns.');
  }

  return {
    id: String(raw?.id || slugify(title) || 'imported-pattern-book'),
    title,
    summary:
      String(raw?.summary || 'Locally imported pattern book for in-app browsing and loading.'),
    author: raw?.author ? String(raw.author) : undefined,
    year: raw?.year ? String(raw.year) : undefined,
    draftCount: Number(raw?.draftCount) || patterns.length,
    sourceLabel: String(raw?.sourceLabel || 'Local pattern book'),
    access: 'local',
    tags: Array.isArray(raw?.tags) ? raw.tags.map(String) : ['local', 'imported'],
    note: raw?.note ? String(raw.note) : 'Loaded from a local JSON pattern-book file.',
    patterns,
  };
}

export function parsePatternBookJson(text: string) {
  let raw: any;
  try {
    raw = JSON.parse(text);
  } catch {
    throw new Error('The selected file is not valid JSON.');
  }

  if (raw?.type && raw.type !== 'pattern-book') {
    throw new Error('Expected a pattern-book JSON file.');
  }

  return normalizePatternBook(raw);
}

export function loadLocalPatternBooks() {
  const raw = localStorage.getItem(BOOK_LIBRARY_STORAGE_KEY);
  if (!raw) {
    return [] as PatternBook[];
  }

  try {
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) {
      return [];
    }
    return parsed.map(normalizePatternBook);
  } catch {
    return [];
  }
}

export function saveLocalPatternBooks(books: PatternBook[]) {
  localStorage.setItem(BOOK_LIBRARY_STORAGE_KEY, JSON.stringify(books, null, 2));
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent(PATTERN_LIBRARY_UPDATED_EVENT));
  }
}

export function upsertLocalPatternBook(book: PatternBook) {
  const books = loadLocalPatternBooks();
  const nextBooks = [
    book,
    ...books.filter((entry) => entry.id !== book.id),
  ];
  saveLocalPatternBooks(nextBooks);
  return nextBooks;
}

export function saveDraftAsLocalPattern(draft: DraftDocument, title: string) {
  const cleanedTitle = title.trim() || draft.title?.trim() || 'Untitled Pattern';
  const now = new Date().toISOString();
  const normalizedDraft = normalizeDraft({
    ...draft,
    title: cleanedTitle,
    sourceType: 'manual',
    sourceLabel: 'Saved Pattern Drafts',
  });
  const pattern: BookPatternEntry = {
    id: `${slugify(cleanedTitle) || 'saved-pattern'}-${Date.now().toString(36)}`,
    title: cleanedTitle,
    summary: `Saved from Pattern Builder on ${now.slice(0, 10)}.`,
    tags: ['saved', 'local', 'pattern-builder'],
    draft: normalizedDraft,
    status: 'loadable',
    weaveType: 'other',
  };
  const books = loadLocalPatternBooks();
  const existingBook = books.find((book) => book.id === SAVED_PATTERNS_BOOK_ID);
  const savedBook: PatternBook = {
    id: SAVED_PATTERNS_BOOK_ID,
    title: 'Saved Pattern Drafts',
    summary: 'Patterns saved directly from the Pattern Builder.',
    sourceLabel: 'Pattern Builder',
    access: 'local',
    tags: ['saved', 'local', 'pattern-builder'],
    note: 'Created by the Pattern Builder Save Pattern button.',
    patterns: [pattern, ...(existingBook?.patterns ?? [])],
  };
  savedBook.draftCount = savedBook.patterns.length;

  const nextBooks = [
    savedBook,
    ...books.filter((book) => book.id !== SAVED_PATTERNS_BOOK_ID),
  ];
  saveLocalPatternBooks(nextBooks);
  return { book: savedBook, pattern, books: nextBooks };
}
