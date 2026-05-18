import { generatedPatternsForBook } from './generatedPatterns';
import { oelsnerStarterPatterns } from './oelsnerPatterns';
import type { BookPatternEntry, PatternBook } from './types';

/**
 * Each book gets:
 *   1. its curated hand-authored entries (where available — currently only
 *      Oelsner), followed by
 *   2. a deterministic set of generated structural reconstructions from
 *      `generatedPatterns.ts` so the picker is meaningfully populated for
 *      every book in the reference shelf.
 *
 * Generated entries are tagged 'generated' and their note disclaims that
 * they're family-taxonomy reconstructions, not literal page transcriptions.
 */
function bookPatterns(bookId: string, curated: BookPatternEntry[] = []): BookPatternEntry[] {
  return [...curated, ...generatedPatternsForBook(bookId)];
}

export const referenceBooks: PatternBook[] = [
  {
    id: 'oelsner',
    title: 'A Handbook of Weaves',
    author: 'G. H. Oelsner',
    year: '1915',
    draftCount: 2257,
    summary:
      'Large structural reference across simple, derivative, and compound weaves. This first pass includes a curated starter shelf of common Oelsner weave families that load directly into the editor.',
    sourceLabel: 'Open Library 1915 edition',
    referenceUrl: 'https://openlibrary.org/books/OL7070771M/A_handbook_of_weaves',
    access: 'public-domain',
    tags: ['reference', 'twill', 'compound'],
    note:
      'Curated starter reconstructions are grounded in the 1915 public-domain Oelsner book and labeled by chapter page so users can read the source context. Additional entries are family-taxonomy reconstructions, not literal page transcriptions.',
    patterns: bookPatterns('oelsner', oelsnerStarterPatterns),
  },
  {
    id: 'kastanek',
    title: 'A Manual of Weave Construction',
    author: 'Ivo Kastanek',
    year: '1903 / 1914',
    draftCount: 517,
    summary:
      'Systematic foundation and derivative weave book that maps well to a book-first browsing workflow.',
    sourceLabel: 'Public-domain reference',
    access: 'public-domain',
    tags: ['foundation weaves', 'teaching', 'reference'],
    note: 'Book cataloged for local indexing. Bundled entries are family-taxonomy reconstructions matching the book’s emphasis, not literal page transcriptions.',
    patterns: bookPatterns('kastanek'),
  },
  {
    id: 'posselt',
    title: 'A Dictionary of Weaves',
    author: 'Emmanuel Anthony Posselt',
    year: '1914',
    draftCount: 1886,
    summary:
      'Dense 4- to 9-harness draft dictionary with a strong classification angle and a large pattern inventory.',
    sourceLabel: 'Catalog reference',
    access: 'catalog',
    tags: ['dictionary', '4 shafts', '8 shafts'],
    note: 'Cataloged as a source book. Bundled entries are family-taxonomy reconstructions emphasising 4-to-8-shaft twills/satins, not literal page transcriptions.',
    patterns: bookPatterns('posselt'),
  },
  {
    id: 'jansen',
    title: 'Revised Textile Design Book',
    author: 'Emil Jansen',
    year: '1898',
    draftCount: 1723,
    summary:
      'Historic design book with many draft plates that fits a page-indexed import pipeline well.',
    sourceLabel: 'Public-domain reference',
    access: 'public-domain',
    tags: ['design plates', 'historic', 'pattern book'],
    note: 'Book metadata is present. Bundled entries are family-taxonomy reconstructions in the book’s design-plate style, not literal page transcriptions.',
    patterns: bookPatterns('jansen'),
  },
  {
    id: 'serrure',
    title: 'Atlas de 4000 Armures',
    author: 'Louis Serrure',
    year: 'circa 1920',
    draftCount: 3212,
    summary:
      'Massive French weave atlas with a strong “browse by book, then by pattern” fit.',
    sourceLabel: 'Catalog reference',
    access: 'catalog',
    tags: ['atlas', 'french', 'large collection'],
    note: 'Source book is cataloged. Bundled entries are family-taxonomy reconstructions, not literal page transcriptions.',
    patterns: bookPatterns('serrure'),
  },
  {
    id: 'fressinet',
    title: "Atlas D'Armures Textiles",
    author: 'B. Fressinet',
    year: '1905',
    draftCount: 2904,
    summary:
      'Large French atlas with a rich range of structural drafting material.',
    sourceLabel: 'Catalog reference',
    access: 'catalog',
    tags: ['atlas', 'french', 'historic'],
    note: 'Prepared as a catalog entry. Bundled entries are family-taxonomy reconstructions, not literal page transcriptions.',
    patterns: bookPatterns('fressinet'),
  },
  {
    id: 'morath',
    title: "A German Weaver's Pattern Book, 1784 - 1810",
    author: 'Christian Morath, Joseph Murllman, and others',
    year: '1784-1810',
    draftCount: 297,
    summary:
      'Hand-penned manuscript drafts with strong archival value for a source-book shelf.',
    sourceLabel: 'Catalog reference',
    access: 'catalog',
    tags: ['manuscript', 'historic', 'german'],
    note: 'Manuscript source. Bundled entries are family-taxonomy reconstructions matching the manuscript’s emphasis, not literal transcriptions.',
    patterns: bookPatterns('morath'),
  },
  {
    id: 'thaller',
    title: 'Thaller Manuscript Drafts',
    author: 'Johann Georg Thaller and later contributors',
    year: '1748',
    draftCount: 128,
    summary:
      'Manuscript-based collection suitable for an archive-driven explore shelf.',
    sourceLabel: 'Catalog reference',
    access: 'catalog',
    tags: ['manuscript', 'archive', 'historic'],
    note: 'Archive manuscript. Bundled entries are family-taxonomy reconstructions, not literal page transcriptions.',
    patterns: bookPatterns('thaller'),
  },
  {
    id: 'watson',
    title: 'Textile Design and Colour',
    author: 'William Watson',
    year: '1912',
    draftCount: 1096,
    summary:
      'Broad weave and color reference that aligns especially well with the draft color editor.',
    sourceLabel: 'Public-domain reference',
    access: 'public-domain',
    tags: ['color', 'reference', 'historic'],
    note: 'Color-focused reference. Bundled entries emphasise color-and-weave variants and foundation structures, not literal page transcriptions.',
    patterns: bookPatterns('watson'),
  },
  {
    id: 'ashenhurst',
    title: 'An Album of Textile Designs',
    author: 'Thomas R. Ashenhurst',
    year: '1881',
    draftCount: 7000,
    summary:
      'Classic textile design volume known for a very large pattern inventory.',
    sourceLabel: 'Public-domain reference',
    access: 'public-domain',
    tags: ['7000 patterns', 'design reference', 'historic'],
    note: 'Large reference. Bundled entries are broad family-taxonomy reconstructions, not literal page transcriptions.',
    patterns: bookPatterns('ashenhurst'),
  },
];
