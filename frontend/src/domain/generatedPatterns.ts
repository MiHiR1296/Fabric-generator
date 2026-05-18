/**
 * Generated pattern library.
 *
 * Produces hundreds of valid weaving drafts from deterministic weave-family
 * generators (twills, satins, baskets, herringbones, broken twills, ribs,
 * color-and-weave). Each entry is tagged with weaveType and source-book id,
 * and computed exactly by computeDrawdown via normalizeDraft.
 *
 * These are NOT literal page transcriptions. They are structural
 * reconstructions in each book's published taxonomy — the kind of family
 * sample chart you would find in their pattern chapters. Honest notes on
 * every entry call this out.
 *
 * See docs/PatternBuilderRevamp/import-panel-spec.md.
 */

import { normalizeDraft } from './draft';
import type { BookPatternEntry, WeaveType } from './types';

// ---------- helpers ---------------------------------------------------------

const WARP_PALETTES = [
  ['#f1ead9', '#a85f3a'],
  ['#efe5d2', '#3c5a6d'],
  ['#f5ecd8', '#7b3f3b'],
  ['#ede4cf', '#5c6b3a'],
  ['#f6ecda', '#684a85'],
  ['#e8dbc2', '#8d4c33'],
  ['#f4eadb', '#244e6b'],
];

const WEFT_PALETTES = [
  '#8f5136',
  '#2e4a3a',
  '#7a4b8f',
  '#b75a2c',
  '#3c6b8f',
  '#a85f3a',
  '#594028',
];

function palette(seed: number): { warp: string; weft: string } {
  const w = WARP_PALETTES[seed % WARP_PALETTES.length];
  const f = WEFT_PALETTES[seed % WEFT_PALETTES.length];
  return { warp: w[0], weft: f };
}

function gcd(a: number, b: number): number {
  return b === 0 ? Math.abs(a) : gcd(b, a % b);
}

function makeBlankTieUp(shafts: number, treadles: number): boolean[][] {
  return Array.from({ length: shafts }, () =>
    Array.from({ length: treadles }, () => false),
  );
}

interface BuildParams {
  bookId: string;
  bookSlug: string;
  family: string;
  variantLabel: string;
  weaveType: WeaveType;
  tags: string[];
  shafts: number;
  treadles: number;
  threading: number[];
  treadling: number[];
  tieUp: boolean[][];
  paletteSeed: number;
  warpColors?: string[];
  weftColors?: string[];
  note?: string;
}

function buildEntry(params: BuildParams): BookPatternEntry {
  const { warp, weft } = palette(params.paletteSeed);
  const draft = normalizeDraft({
    version: 1,
    sourceType: 'manual',
    shaftCount: params.shafts,
    treadleCount: params.treadles,
    threading: params.threading,
    tieUp: params.tieUp,
    treadling: params.treadling,
    warpColors: params.warpColors ?? [warp],
    weftColors: params.weftColors ?? [weft],
    parseConfidence: 1,
    warnings: [],
    title: `${params.family}: ${params.variantLabel}`,
    sourceLabel: `Generated · ${params.bookSlug}`,
  });
  const id = `${params.bookId}-${params.family.toLowerCase().replace(/[^a-z0-9]+/g, '-')}-${params.variantLabel
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')}`;
  return {
    id,
    title: `${params.family} — ${params.variantLabel}`,
    summary: `${params.shafts}-shaft ${params.family.toLowerCase()} reconstruction · ${params.variantLabel}.`,
    tags: Array.from(new Set(['generated', ...params.tags])),
    weaveType: params.weaveType,
    status: 'loadable',
    note:
      params.note ??
      `Generated structural reconstruction in the ${params.bookSlug} taxonomy. Not a literal page transcription.`,
    draft,
  };
}

// ---------- twill family ----------------------------------------------------

/**
 * 2/2-style straight twills. `warpFloat` = how many shafts lift together;
 * `weftFloat` = how many shafts stay down. Length warpFloat + weftFloat
 * cycles around the shafts.
 */
function makeStraightTwillTieUp(
  shafts: number,
  warpFloat: number,
  weftFloat: number,
): boolean[][] {
  const cycle = warpFloat + weftFloat;
  const treadles = shafts;
  const tieUp = makeBlankTieUp(shafts, treadles);
  for (let treadle = 0; treadle < treadles; treadle += 1) {
    for (let k = 0; k < warpFloat; k += 1) {
      const shaft = (treadle + k) % shafts;
      tieUp[shaft][treadle] = true;
    }
    // weft floats are the rest of the cycle (no lift) — already false.
    void cycle;
  }
  return tieUp;
}

function straightThreading(shafts: number, repeats: number): number[] {
  const out: number[] = [];
  for (let r = 0; r < repeats; r += 1) {
    for (let s = 1; s <= shafts; s += 1) out.push(s);
  }
  return out;
}

function straightTreadling(treadles: number, repeats: number): number[] {
  return straightThreading(treadles, repeats);
}

function pointedThreading(shafts: number, repeats: number): number[] {
  const ramp: number[] = [];
  for (let s = 1; s <= shafts; s += 1) ramp.push(s);
  for (let s = shafts - 1; s >= 2; s -= 1) ramp.push(s);
  const out: number[] = [];
  for (let r = 0; r < repeats; r += 1) out.push(...ramp);
  return out;
}

interface TwillVariant {
  warpFloat: number;
  weftFloat: number;
  shafts: number;
  label: string;
  tags: string[];
}

const TWILL_VARIANTS: TwillVariant[] = [
  { warpFloat: 1, weftFloat: 1, shafts: 3, label: '1/2 twill on 3', tags: ['twill', '3 shafts'] },
  { warpFloat: 2, weftFloat: 1, shafts: 3, label: '2/1 twill on 3', tags: ['twill', '3 shafts', 'warp-faced'] },
  { warpFloat: 2, weftFloat: 2, shafts: 4, label: '2/2 twill on 4', tags: ['twill', '4 shafts'] },
  { warpFloat: 3, weftFloat: 1, shafts: 4, label: '3/1 twill on 4', tags: ['twill', '4 shafts', 'warp-faced'] },
  { warpFloat: 1, weftFloat: 3, shafts: 4, label: '1/3 twill on 4', tags: ['twill', '4 shafts', 'weft-faced'] },
  { warpFloat: 2, weftFloat: 2, shafts: 6, label: '2/2 twill on 6', tags: ['twill', '6 shafts'] },
  { warpFloat: 3, weftFloat: 3, shafts: 6, label: '3/3 twill on 6', tags: ['twill', '6 shafts'] },
  { warpFloat: 4, weftFloat: 2, shafts: 6, label: '4/2 twill on 6', tags: ['twill', '6 shafts'] },
  { warpFloat: 2, weftFloat: 2, shafts: 8, label: '2/2 twill on 8', tags: ['twill', '8 shafts'] },
  { warpFloat: 3, weftFloat: 3, shafts: 8, label: '3/3 twill on 8', tags: ['twill', '8 shafts'] },
  { warpFloat: 4, weftFloat: 4, shafts: 8, label: '4/4 twill on 8', tags: ['twill', '8 shafts'] },
  { warpFloat: 5, weftFloat: 3, shafts: 8, label: '5/3 twill on 8', tags: ['twill', '8 shafts'] },
  { warpFloat: 3, weftFloat: 5, shafts: 8, label: '3/5 twill on 8', tags: ['twill', '8 shafts'] },
  { warpFloat: 2, weftFloat: 2, shafts: 12, label: '2/2 twill on 12', tags: ['twill', '12 shafts'] },
];

function generateTwills(bookId: string, bookSlug: string, seedOffset = 0): BookPatternEntry[] {
  return TWILL_VARIANTS.map((variant, idx) => {
    const { shafts, warpFloat, weftFloat, label, tags } = variant;
    const tieUp = makeStraightTwillTieUp(shafts, warpFloat, weftFloat);
    const threading = straightThreading(shafts, Math.max(2, Math.ceil(24 / shafts)));
    const treadling = straightTreadling(shafts, Math.max(2, Math.ceil(24 / shafts)));
    return buildEntry({
      bookId,
      bookSlug,
      family: 'Straight twill',
      variantLabel: label,
      weaveType: 'twill',
      tags,
      shafts,
      treadles: shafts,
      threading,
      treadling,
      tieUp,
      paletteSeed: seedOffset + idx,
    });
  });
}

// ---------- pointed / herringbone twills ------------------------------------

const HERRINGBONE_VARIANTS: TwillVariant[] = [
  { warpFloat: 2, weftFloat: 2, shafts: 4, label: '2/2 herringbone on 4', tags: ['twill', 'pointed', 'herringbone'] },
  { warpFloat: 3, weftFloat: 1, shafts: 4, label: '3/1 herringbone on 4', tags: ['twill', 'pointed', 'warp-faced'] },
  { warpFloat: 2, weftFloat: 2, shafts: 6, label: '2/2 herringbone on 6', tags: ['twill', 'pointed', 'herringbone'] },
  { warpFloat: 2, weftFloat: 2, shafts: 8, label: '2/2 herringbone on 8', tags: ['twill', 'pointed', 'herringbone'] },
  { warpFloat: 4, weftFloat: 4, shafts: 8, label: '4/4 herringbone on 8', tags: ['twill', 'pointed'] },
  { warpFloat: 3, weftFloat: 3, shafts: 6, label: '3/3 herringbone on 6', tags: ['twill', 'pointed'] },
];

function generateHerringbones(
  bookId: string,
  bookSlug: string,
  seedOffset = 0,
): BookPatternEntry[] {
  return HERRINGBONE_VARIANTS.map((variant, idx) => {
    const { shafts, warpFloat, weftFloat, label, tags } = variant;
    const tieUp = makeStraightTwillTieUp(shafts, warpFloat, weftFloat);
    const threading = pointedThreading(shafts, Math.max(2, Math.ceil(20 / (shafts * 2 - 2))));
    const treadling = pointedThreading(shafts, Math.max(2, Math.ceil(20 / (shafts * 2 - 2))));
    return buildEntry({
      bookId,
      bookSlug,
      family: 'Pointed twill',
      variantLabel: label,
      weaveType: 'twill',
      tags,
      shafts,
      treadles: shafts,
      threading,
      treadling,
      tieUp,
      paletteSeed: seedOffset + idx + 11,
    });
  });
}

// ---------- broken twills ---------------------------------------------------

function generateBrokenTwills(
  bookId: string,
  bookSlug: string,
  seedOffset = 0,
): BookPatternEntry[] {
  const brokenVariants: { shafts: number; warpFloat: number; weftFloat: number; label: string }[] =
    [
      { shafts: 4, warpFloat: 2, weftFloat: 2, label: 'broken 2/2 on 4' },
      { shafts: 4, warpFloat: 3, weftFloat: 1, label: 'broken 3/1 on 4' },
      { shafts: 6, warpFloat: 3, weftFloat: 3, label: 'broken 3/3 on 6' },
      { shafts: 8, warpFloat: 4, weftFloat: 4, label: 'broken 4/4 on 8' },
      { shafts: 8, warpFloat: 5, weftFloat: 3, label: 'broken 5/3 on 8' },
    ];
  return brokenVariants.map((variant, idx) => {
    const { shafts, warpFloat, weftFloat, label } = variant;
    const tieUp = makeStraightTwillTieUp(shafts, warpFloat, weftFloat);
    // broken threading: alternate ascending halves with a shift between them
    const half = Math.max(2, Math.floor(shafts / 2));
    const repeats = Math.max(2, Math.ceil(20 / shafts));
    const threading: number[] = [];
    for (let r = 0; r < repeats; r += 1) {
      for (let s = 1; s <= half; s += 1) threading.push(s);
      for (let s = half + 1; s <= shafts; s += 1) threading.push(s);
      // skip / break
      for (let s = shafts; s >= half + 1; s -= 1) threading.push(s);
      for (let s = half; s >= 1; s -= 1) threading.push(s);
    }
    const treadling = straightTreadling(shafts, Math.max(2, Math.ceil(24 / shafts)));
    return buildEntry({
      bookId,
      bookSlug,
      family: 'Broken twill',
      variantLabel: label,
      weaveType: 'twill',
      tags: ['twill', 'broken', `${shafts} shafts`],
      shafts,
      treadles: shafts,
      threading,
      treadling,
      tieUp,
      paletteSeed: seedOffset + idx + 22,
    });
  });
}

// ---------- satin family ----------------------------------------------------

interface SatinVariant {
  ends: number;
  step: number;
  label: string;
}

const SATIN_VARIANTS: SatinVariant[] = [
  { ends: 5, step: 2, label: '5-end step-2 satin' },
  { ends: 5, step: 3, label: '5-end step-3 satin' },
  { ends: 7, step: 2, label: '7-end step-2 satin' },
  { ends: 7, step: 3, label: '7-end step-3 satin' },
  { ends: 7, step: 4, label: '7-end step-4 satin' },
  { ends: 7, step: 5, label: '7-end step-5 satin' },
  { ends: 8, step: 3, label: '8-end step-3 satin' },
  { ends: 8, step: 5, label: '8-end step-5 satin' },
  { ends: 10, step: 3, label: '10-end step-3 satin' },
  { ends: 10, step: 7, label: '10-end step-7 satin' },
  { ends: 12, step: 5, label: '12-end step-5 satin' },
  { ends: 12, step: 7, label: '12-end step-7 satin' },
];

function generateSatins(bookId: string, bookSlug: string, seedOffset = 0): BookPatternEntry[] {
  return SATIN_VARIANTS.filter((variant) => gcd(variant.ends, variant.step) === 1).map(
    (variant, idx) => {
      const { ends, step, label } = variant;
      const shafts = ends;
      const treadles = ends;
      const tieUp = makeBlankTieUp(shafts, treadles);
      for (let i = 0; i < ends; i += 1) {
        const shaft = i;
        const treadle = (i * step) % ends;
        tieUp[shaft][treadle] = true;
      }
      const threading = straightThreading(shafts, Math.max(2, Math.ceil(20 / shafts)));
      const treadling = straightTreadling(treadles, Math.max(2, Math.ceil(20 / treadles)));
      return buildEntry({
        bookId,
        bookSlug,
        family: 'Satin',
        variantLabel: label,
        weaveType: 'satin',
        tags: ['satin', `${ends} ends`, 'reference'],
        shafts,
        treadles,
        threading,
        treadling,
        tieUp,
        paletteSeed: seedOffset + idx + 33,
      });
    },
  );
}

// ---------- basket family ---------------------------------------------------

interface BasketVariant {
  warp: number;
  weft: number;
  label: string;
}

const BASKET_VARIANTS: BasketVariant[] = [
  { warp: 2, weft: 2, label: '2×2 basket' },
  { warp: 3, weft: 3, label: '3×3 basket' },
  { warp: 4, weft: 4, label: '4×4 basket' },
  { warp: 2, weft: 3, label: '2×3 irregular basket' },
  { warp: 3, weft: 4, label: '3×4 irregular basket' },
  { warp: 2, weft: 4, label: '2×4 half basket' },
];

function generateBaskets(bookId: string, bookSlug: string, seedOffset = 0): BookPatternEntry[] {
  return BASKET_VARIANTS.map((variant, idx) => {
    const { warp, weft, label } = variant;
    const shafts = 4;
    const treadles = 4;
    // basket: shafts 1+2 lift on treadle 1 (for `warp` picks), 3+4 lift on treadle 2 (for `weft` picks)
    const tieUp = makeBlankTieUp(shafts, treadles);
    tieUp[0][0] = true;
    tieUp[1][0] = true;
    tieUp[2][1] = true;
    tieUp[3][1] = true;

    const threadingUnit: number[] = [];
    for (let i = 0; i < warp; i += 1) threadingUnit.push(1, 2);
    for (let i = 0; i < weft; i += 1) threadingUnit.push(3, 4);
    const repeats = Math.max(2, Math.ceil(24 / threadingUnit.length));
    const threading: number[] = [];
    for (let r = 0; r < repeats; r += 1) threading.push(...threadingUnit);

    const treadlingUnit: number[] = [];
    for (let i = 0; i < warp; i += 1) treadlingUnit.push(1);
    for (let i = 0; i < weft; i += 1) treadlingUnit.push(2);
    const trepeats = Math.max(2, Math.ceil(24 / treadlingUnit.length));
    const treadling: number[] = [];
    for (let r = 0; r < trepeats; r += 1) treadling.push(...treadlingUnit);

    return buildEntry({
      bookId,
      bookSlug,
      family: 'Basket',
      variantLabel: label,
      weaveType: 'basket',
      tags: ['basket', 'foundation'],
      shafts,
      treadles,
      threading,
      treadling,
      tieUp,
      paletteSeed: seedOffset + idx + 44,
    });
  });
}

// ---------- rib family ------------------------------------------------------

interface RibVariant {
  type: 'warp' | 'weft';
  picks: number;
  label: string;
}

const RIB_VARIANTS: RibVariant[] = [
  { type: 'warp', picks: 2, label: 'warp rib 1/1×2' },
  { type: 'warp', picks: 3, label: 'warp rib 1/1×3' },
  { type: 'warp', picks: 4, label: 'warp rib 1/1×4' },
  { type: 'weft', picks: 2, label: 'weft rib 1/1×2' },
  { type: 'weft', picks: 3, label: 'weft rib 1/1×3' },
  { type: 'weft', picks: 4, label: 'weft rib 1/1×4' },
];

function generateRibs(bookId: string, bookSlug: string, seedOffset = 0): BookPatternEntry[] {
  return RIB_VARIANTS.map((variant, idx) => {
    const shafts = 4;
    const treadles = 4;
    const tieUp = makeBlankTieUp(shafts, treadles);
    // Plain-weave tie-up on a 4-shaft, 4-treadle frame
    tieUp[0][0] = true;
    tieUp[2][0] = true;
    tieUp[1][1] = true;
    tieUp[3][1] = true;
    const threading = straightThreading(shafts, 6);
    const treadling: number[] = [];
    const repeats = Math.max(2, Math.ceil(24 / (variant.picks * 2)));
    for (let r = 0; r < repeats; r += 1) {
      if (variant.type === 'warp') {
        // emphasize warp by extending the same shed for multiple picks
        for (let i = 0; i < variant.picks; i += 1) treadling.push(1);
        for (let i = 0; i < variant.picks; i += 1) treadling.push(2);
      } else {
        treadling.push(1, 2);
      }
    }
    let threadingForRib = threading;
    if (variant.type === 'weft') {
      // emphasise weft by repeating warp ends
      threadingForRib = [];
      for (let r = 0; r < 8; r += 1) {
        for (let i = 0; i < variant.picks; i += 1) threadingForRib.push(1);
        for (let i = 0; i < variant.picks; i += 1) threadingForRib.push(2);
      }
    }
    return buildEntry({
      bookId,
      bookSlug,
      family: 'Rib',
      variantLabel: variant.label,
      weaveType: 'rib',
      tags: ['rib', variant.type === 'warp' ? 'warp-faced' : 'weft-faced'],
      shafts,
      treadles,
      threading: threadingForRib,
      treadling,
      tieUp,
      paletteSeed: seedOffset + idx + 55,
    });
  });
}

// ---------- plain & color-and-weave ----------------------------------------

function plainTieUp4(): boolean[][] {
  return [
    [true, false, true, false],
    [false, true, false, true],
    [true, false, true, false],
    [false, true, false, true],
  ];
}

function generateColorAndWeave(
  bookId: string,
  bookSlug: string,
  seedOffset = 0,
): BookPatternEntry[] {
  const variants: { label: string; warp: string[]; weft: string[]; tags: string[] }[] = [
    {
      label: 'Log Cabin (light/dark)',
      warp: ['#f4ecd8', '#3a3a4a'],
      weft: ['#f4ecd8', '#3a3a4a'],
      tags: ['color-and-weave', 'log cabin'],
    },
    {
      label: 'Houndstooth 2/2',
      warp: ['#1d1d24', '#1d1d24', '#f6ecd8', '#f6ecd8'],
      weft: ['#1d1d24', '#1d1d24', '#f6ecd8', '#f6ecd8'],
      tags: ['color-and-weave', 'houndstooth'],
    },
    {
      label: 'Glen check',
      warp: ['#28282f', '#28282f', '#f0e8d4', '#f0e8d4', '#28282f', '#f0e8d4'],
      weft: ['#28282f', '#28282f', '#f0e8d4', '#f0e8d4', '#28282f', '#f0e8d4'],
      tags: ['color-and-weave', 'glen check'],
    },
    {
      label: 'Shepherd check',
      warp: ['#2a2a32', '#2a2a32', '#2a2a32', '#2a2a32', '#f0e7d3', '#f0e7d3', '#f0e7d3', '#f0e7d3'],
      weft: ['#2a2a32', '#2a2a32', '#2a2a32', '#2a2a32', '#f0e7d3', '#f0e7d3', '#f0e7d3', '#f0e7d3'],
      tags: ['color-and-weave', 'shepherd check'],
    },
  ];
  return variants.map((variant, idx) => {
    const shafts = 4;
    const treadles = 4;
    const tieUp =
      idx === 0 || idx === 2 || idx === 3
        ? plainTieUp4()
        : makeStraightTwillTieUp(4, 2, 2);
    const threading = straightThreading(shafts, 6);
    const treadling = straightTreadling(treadles, 6);
    return buildEntry({
      bookId,
      bookSlug,
      family: 'Color-and-weave',
      variantLabel: variant.label,
      weaveType: idx === 1 ? 'twill' : 'plain',
      tags: variant.tags,
      shafts,
      treadles,
      threading,
      treadling,
      tieUp,
      paletteSeed: seedOffset + idx + 66,
      warpColors: variant.warp,
      weftColors: variant.weft,
    });
  });
}

// ---------- huck lace -------------------------------------------------------

function generateHuck(bookId: string, bookSlug: string, seedOffset = 0): BookPatternEntry[] {
  // Classic 4-shaft huck lace: blocks A (shafts 1,2) and B (shafts 3,4)
  const shafts = 4;
  const treadles = 4;
  const tieUp: boolean[][] = [
    [true, false, true, false], // shaft 1
    [false, false, true, false], // shaft 2 (lace shed)
    [true, false, true, false], // shaft 3
    [true, false, false, false], // shaft 4 (lace shed)
  ];
  const threading = [1, 2, 1, 2, 1, 3, 4, 3, 4, 3, 1, 2, 1, 2, 1, 3, 4, 3, 4, 3];
  const treadling = [1, 2, 1, 2, 1, 3, 4, 3, 4, 3, 1, 2, 1, 2, 1, 3, 4, 3, 4, 3];
  return [
    buildEntry({
      bookId,
      bookSlug,
      family: 'Huck lace',
      variantLabel: '4-shaft huck blocks A & B',
      weaveType: 'huck',
      tags: ['huck', 'lace', '4 shafts'],
      shafts,
      treadles,
      threading,
      treadling,
      tieUp,
      paletteSeed: seedOffset + 77,
    }),
  ];
}

// ---------- public API ------------------------------------------------------

/** Variant 'depth' for each book — how many family generators contribute. */
interface BookRecipe {
  bookId: string;
  bookSlug: string;
  emphasis: Array<'twill' | 'herringbone' | 'broken' | 'satin' | 'basket' | 'rib' | 'caw' | 'huck'>;
}

const RECIPES: BookRecipe[] = [
  {
    bookId: 'oelsner',
    bookSlug: 'Oelsner — A Handbook of Weaves',
    emphasis: ['twill', 'herringbone', 'broken', 'satin', 'basket', 'rib', 'caw', 'huck'],
  },
  {
    bookId: 'kastanek',
    bookSlug: 'Kastanek — A Manual of Weave Construction',
    emphasis: ['twill', 'satin', 'basket', 'rib'],
  },
  {
    bookId: 'posselt',
    bookSlug: 'Posselt — A Dictionary of Weaves',
    emphasis: ['twill', 'herringbone', 'broken', 'satin'],
  },
  {
    bookId: 'jansen',
    bookSlug: 'Jansen — Revised Textile Design Book',
    emphasis: ['twill', 'herringbone', 'caw', 'basket'],
  },
  {
    bookId: 'serrure',
    bookSlug: 'Serrure — Atlas de 4000 Armures',
    emphasis: ['twill', 'satin', 'broken', 'basket', 'rib'],
  },
  {
    bookId: 'fressinet',
    bookSlug: 'Fressinet — Atlas D’Armures Textiles',
    emphasis: ['twill', 'satin', 'broken', 'herringbone'],
  },
  {
    bookId: 'morath',
    bookSlug: 'Morath / Murllman — German Weaver’s Pattern Book',
    emphasis: ['twill', 'herringbone', 'basket'],
  },
  {
    bookId: 'thaller',
    bookSlug: 'Thaller Manuscript Drafts',
    emphasis: ['twill', 'herringbone'],
  },
  {
    bookId: 'watson',
    bookSlug: 'Watson — Textile Design and Colour',
    emphasis: ['caw', 'twill', 'satin', 'basket'],
  },
  {
    bookId: 'ashenhurst',
    bookSlug: 'Ashenhurst — An Album of Textile Designs',
    emphasis: ['twill', 'satin', 'herringbone', 'broken', 'basket', 'caw', 'rib'],
  },
];

function entriesForBook(recipe: BookRecipe, seed: number): BookPatternEntry[] {
  const out: BookPatternEntry[] = [];
  for (const emphasis of recipe.emphasis) {
    switch (emphasis) {
      case 'twill':
        out.push(...generateTwills(recipe.bookId, recipe.bookSlug, seed));
        break;
      case 'herringbone':
        out.push(...generateHerringbones(recipe.bookId, recipe.bookSlug, seed));
        break;
      case 'broken':
        out.push(...generateBrokenTwills(recipe.bookId, recipe.bookSlug, seed));
        break;
      case 'satin':
        out.push(...generateSatins(recipe.bookId, recipe.bookSlug, seed));
        break;
      case 'basket':
        out.push(...generateBaskets(recipe.bookId, recipe.bookSlug, seed));
        break;
      case 'rib':
        out.push(...generateRibs(recipe.bookId, recipe.bookSlug, seed));
        break;
      case 'caw':
        out.push(...generateColorAndWeave(recipe.bookId, recipe.bookSlug, seed));
        break;
      case 'huck':
        out.push(...generateHuck(recipe.bookId, recipe.bookSlug, seed));
        break;
    }
  }
  return out;
}

/**
 * Build the map of bookId → generated entries. Computed once at module load
 * time; deterministic so the picker shows the same set every session.
 */
export const generatedBookPatterns: Map<string, BookPatternEntry[]> = (() => {
  const map = new Map<string, BookPatternEntry[]>();
  RECIPES.forEach((recipe, idx) => {
    map.set(recipe.bookId, entriesForBook(recipe, idx * 7));
  });
  return map;
})();

export function generatedPatternsForBook(bookId: string): BookPatternEntry[] {
  return generatedBookPatterns.get(bookId) ?? [];
}
