import { normalizeDraft } from './draft.ts';
import type { BookPatternEntry, PatternBook } from './types.ts';

const BOOK_LIBRARY_STORAGE_KEY = 'weaving-draft-studio/local-pattern-books';

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
