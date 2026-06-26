import type {
  HookBookPatternEntry,
  HookChain,
  HookGaugeSettings,
  HookMaterialBinding,
  HookPatternAccess,
  HookPatternBook,
  HookPatternDocument,
  HookPatternSource,
  HookRepeatUnit,
  HookProject,
  HookRenderSettings,
  HookRowDirection,
  HookStitchArchetype,
  HookStitchLegendEntry,
  HookStructureFamily,
  YarnAsset,
} from './types';

export const DEFAULT_HOOK_ROWS = 15;
export const DEFAULT_HOOK_COLUMNS = 21;
export const MAX_HOOK_MATERIAL_SLOTS = 16;
const LOCAL_HOOK_PATTERN_BOOKS_KEY = 'weaving-draft-studio/local-hook-pattern-books';

export const DEFAULT_HOOK_RENDER_SETTINGS: HookRenderSettings = {
  hookScale: 0.07,
  legWidth: 0.67,
  loopHeight: 2.2,
  handleScale: 0.6,
  legZOffset: 0.218,
  tubeRadius: 0.25,
  curveResolution: 7,
  tubeResolution: 11,
  textureScaleU: 1.06,
  textureScaleV: 0.93,
  textureOffsetV: -0.44,
  textureSideFlatten: 0,
  arc1VPadding: 0,
  fillRatio: 1,
  seed: 1,
};

export const DEFAULT_HOOK_STITCH_LEGEND: HookStitchLegendEntry[] = [
  {
    code: 0,
    symbol: 'empty',
    abbreviation: 'empty',
    label: 'Empty / no stitch',
    archetype: 'empty',
    supported: true,
  },
  {
    code: 1,
    symbol: 'loop',
    abbreviation: 'hk',
    label: 'Standard interlocking hook loop',
    archetype: 'standard_hook_loop',
    supported: true,
  },
  {
    code: 2,
    symbol: 'ch',
    abbreviation: 'ch',
    label: 'Chain / foundation',
    archetype: 'chain_foundation',
    supported: false,
    fallbackCode: 1,
  },
  {
    code: 3,
    symbol: 'sl st',
    abbreviation: 'sl st',
    label: 'Slip stitch',
    archetype: 'slip_stitch',
    supported: false,
    fallbackCode: 1,
  },
  {
    code: 4,
    symbol: 'sc',
    abbreviation: 'sc',
    label: 'Single crochet',
    archetype: 'single_crochet',
    supported: false,
    fallbackCode: 1,
  },
  {
    code: 5,
    symbol: 'dc',
    abbreviation: 'dc',
    label: 'Double crochet',
    archetype: 'double_crochet',
    supported: false,
    fallbackCode: 1,
  },
  {
    code: 6,
    symbol: 'V',
    abbreviation: 'k',
    label: 'Knit V',
    archetype: 'knit_v',
    supported: false,
    fallbackCode: 1,
  },
  {
    code: 7,
    symbol: 'p',
    abbreviation: 'p',
    label: 'Purl bump',
    archetype: 'purl_bump',
    supported: false,
    fallbackCode: 1,
  },
  {
    code: 8,
    symbol: 'yo',
    abbreviation: 'yo',
    label: 'Yarn-over / open hole',
    archetype: 'yarn_over_open',
    supported: false,
    fallbackCode: 1,
  },
  {
    code: 9,
    symbol: 'tuck',
    abbreviation: 'tuck',
    label: 'Tuck stitch',
    archetype: 'tuck',
    supported: false,
    fallbackCode: 1,
  },
  {
    code: 10,
    symbol: 'miss',
    abbreviation: 'miss',
    label: 'Miss / float',
    archetype: 'miss_float',
    supported: false,
    fallbackCode: 1,
  },
  {
    code: 11,
    symbol: 'cable',
    abbreviation: 'cable',
    label: 'Cable / crossing',
    archetype: 'cable_crossing',
    supported: false,
    fallbackCode: 1,
  },
];

export interface HookPresetDefinition {
  id: string;
  label: string;
  summary: string;
  document: HookPatternDocument;
}

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

function intOrFallback(value: unknown, fallback: number) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? Math.round(parsed) : fallback;
}

function numberOrFallback(value: unknown, fallback: number) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function stringChoice<T extends string>(value: unknown, fallback: T, allowed: readonly T[]) {
  return allowed.includes(value as T) ? value as T : fallback;
}

function normalizeRepeatUnit(value: unknown): HookRepeatUnit | undefined {
  const raw = typeof value === 'object' && value !== null ? value as Partial<HookRepeatUnit> : null;
  if (!raw) return undefined;
  const rows = clamp(intOrFallback(raw.rows, 0), 1, 400);
  const columns = clamp(intOrFallback(raw.columns, 0), 1, 400);
  if (!rows || !columns) return undefined;
  return { mode: 'tile', rows, columns };
}

function matrixValueAt(
  source: unknown[],
  row: number,
  col: number,
  repeat: HookRepeatUnit | undefined,
) {
  const sourceRowIndex = repeat?.mode === 'tile' ? row % repeat.rows : row;
  const sourceColIndex = repeat?.mode === 'tile' ? col % repeat.columns : col;
  const sourceRow = Array.isArray(source[sourceRowIndex]) ? source[sourceRowIndex] as unknown[] : [];
  return sourceRow[sourceColIndex];
}

function normalizeMatrix(
  value: unknown,
  rows: number,
  columns: number,
  fallback: (row: number, col: number) => number,
  repeat?: HookRepeatUnit,
) {
  const source = Array.isArray(value) ? value : [];
  return Array.from({ length: rows }, (_, row) => {
    return Array.from({ length: columns }, (_, col) => {
      const parsed = Number(matrixValueAt(source, row, col, repeat));
      return Number.isFinite(parsed) ? Math.round(parsed) : fallback(row, col);
    });
  });
}

function normalizeStitchLegend(value: unknown): HookStitchLegendEntry[] {
  const byCode = new Map(DEFAULT_HOOK_STITCH_LEGEND.map((entry) => [entry.code, entry]));
  if (Array.isArray(value)) {
    value.forEach((entry) => {
      if (typeof entry !== 'object' || entry === null) return;
      const raw = entry as Partial<HookStitchLegendEntry>;
      const code = clamp(intOrFallback(raw.code, -1), 0, 999);
      if (code < 0) return;
      const fallback = byCode.get(code);
      const archetype = stringChoice<HookStitchArchetype>(
        raw.archetype,
        fallback?.archetype || 'reserved',
        [
          'empty',
          'standard_hook_loop',
          'chain_foundation',
          'slip_stitch',
          'single_crochet',
          'double_crochet',
          'knit_v',
          'purl_bump',
          'yarn_over_open',
          'tuck',
          'miss_float',
          'cable_crossing',
          'reserved',
        ],
      );
      byCode.set(code, {
        code,
        symbol: String(raw.symbol || fallback?.symbol || `code-${code}`),
        abbreviation: raw.abbreviation ? String(raw.abbreviation) : fallback?.abbreviation,
        label: String(raw.label || fallback?.label || `Reserved stitch ${code}`),
        archetype,
        supported: raw.supported === true || code <= 1,
        fallbackCode: raw.fallbackCode == null ? fallback?.fallbackCode : clamp(intOrFallback(raw.fallbackCode, 1), 0, 999),
        notes: raw.notes ? String(raw.notes) : fallback?.notes,
      });
    });
  }
  return Array.from(byCode.values()).sort((a, b) => a.code - b.code);
}

function normalizeHookGauge(value: unknown): HookGaugeSettings | undefined {
  const raw = typeof value === 'object' && value !== null ? value as Partial<HookGaugeSettings> : null;
  if (!raw) return undefined;
  const gauge: HookGaugeSettings = {
    unit: stringChoice(raw.unit, 'bu', ['bu', 'cm', 'in']),
  };
  const optionalKeys: Array<keyof Omit<HookGaugeSettings, 'unit'>> = [
    'stitchesPerUnit',
    'rowsPerUnit',
    'density',
    'openness',
    'loopHeight',
    'tension',
  ];
  optionalKeys.forEach((key) => {
    const parsed = Number(raw[key]);
    if (Number.isFinite(parsed)) {
      gauge[key] = parsed;
    }
  });
  return gauge;
}

function normalizeHookSource(value: unknown, title?: string, sourceLabel?: string): HookPatternSource {
  const raw = typeof value === 'object' && value !== null ? value as Partial<HookPatternSource> : {};
  return {
    kind: stringChoice<HookPatternSource['kind']>(
      raw.kind,
      'builtin',
      ['builtin', 'generated', 'literal', 'user-authored', 'imported', 'catalog-reference'],
    ),
    access: stringChoice<HookPatternAccess>(
      raw.access,
      'builtin',
      ['builtin', 'public-domain', 'catalog', 'local', 'linked'],
    ),
    title: raw.title ? String(raw.title) : title,
    author: raw.author ? String(raw.author) : undefined,
    site: raw.site ? String(raw.site) : undefined,
    book: raw.book ? String(raw.book) : undefined,
    url: raw.url ? String(raw.url) : undefined,
    note: raw.note ? String(raw.note) : sourceLabel,
  };
}

export function normalizeHookRenderSettings(value: unknown): HookRenderSettings {
  const raw = typeof value === 'object' && value !== null ? value as Partial<HookRenderSettings> : {};
  const fallback = DEFAULT_HOOK_RENDER_SETTINGS;
  return {
    hookScale: clamp(numberOrFallback(raw.hookScale, fallback.hookScale), 0.001, 10),
    legWidth: clamp(numberOrFallback(raw.legWidth, fallback.legWidth), 0.05, 10),
    loopHeight: clamp(numberOrFallback(raw.loopHeight, fallback.loopHeight), 0.05, 20),
    handleScale: clamp(numberOrFallback(raw.handleScale, fallback.handleScale), 0.01, 10),
    legZOffset: clamp(numberOrFallback(raw.legZOffset, fallback.legZOffset), -10, 10),
    tubeRadius: clamp(numberOrFallback(raw.tubeRadius, fallback.tubeRadius), 0.001, 2),
    curveResolution: clamp(intOrFallback(raw.curveResolution, fallback.curveResolution), 3, 96),
    tubeResolution: clamp(intOrFallback(raw.tubeResolution, fallback.tubeResolution), 3, 64),
    textureScaleU: clamp(numberOrFallback(raw.textureScaleU, fallback.textureScaleU), 0.0001, 100),
    textureScaleV: clamp(numberOrFallback(raw.textureScaleV, fallback.textureScaleV), 0.0001, 100),
    textureOffsetV: clamp(numberOrFallback(raw.textureOffsetV, fallback.textureOffsetV), -100, 100),
    textureSideFlatten: clamp(numberOrFallback(raw.textureSideFlatten, fallback.textureSideFlatten), 0, 1),
    arc1VPadding: clamp(numberOrFallback(raw.arc1VPadding, fallback.arc1VPadding), 0, 0.5),
    fillRatio: clamp(numberOrFallback(raw.fillRatio, fallback.fillRatio), 0.1, 1),
    seed: clamp(intOrFallback(raw.seed, fallback.seed), 0, 9999),
  };
}

export function normalizeHookPattern(value: unknown): HookPatternDocument {
  const raw = typeof value === 'object' && value !== null ? value as Partial<HookPatternDocument> : {};
  const rows = clamp(intOrFallback(raw.rows, DEFAULT_HOOK_ROWS), 1, 200);
  const columns = clamp(intOrFallback(raw.columns, DEFAULT_HOOK_COLUMNS), 1, 200);
  const repeat = normalizeRepeatUnit(raw.repeat);
  const stitchCodes = normalizeMatrix(raw.stitchCodes, rows, columns, () => 1, repeat)
    .map((row) => row.map((code) => clamp(code, 0, 999)));
  const chainIds = normalizeMatrix(raw.chainIds, rows, columns, (_row, col) => col, repeat)
    .map((row) => row.map((chainId) => Math.max(0, chainId)));
  const courseIds = normalizeMatrix(raw.courseIds, rows, columns, (row) => row, repeat)
    .map((row) => row.map((courseId) => Math.max(0, courseId)));
  const waleIds = normalizeMatrix(raw.waleIds, rows, columns, (_row, col) => col, repeat)
    .map((row) => row.map((waleId) => Math.max(0, waleId)));

  const chains = new Map<number, HookChain>();
  if (Array.isArray(raw.chains)) {
    raw.chains.forEach((chain) => {
      const id = Math.max(0, intOrFallback(chain?.id, chains.size));
      chains.set(id, {
        id,
        materialSlot: clamp(intOrFallback(chain?.materialSlot, 0), 0, MAX_HOOK_MATERIAL_SLOTS - 1),
        direction: stringChoice(chain?.direction, 'vertical', ['vertical', 'horizontal', 'course', 'wale']),
        label: chain?.label,
      });
    });
  }

  for (const row of chainIds) {
    for (const id of row) {
      if (!chains.has(id)) {
        chains.set(id, {
          id,
          materialSlot: 0,
          direction: 'vertical',
          label: `Chain ${id + 1}`,
        });
      }
    }
  }

  return {
    version: 1,
    structureType: 'hook',
    structureFamily: stringChoice<HookStructureFamily>(
      raw.structureFamily,
      'crochet_hook',
      ['crochet_hook', 'knit_chart', 'machine_knit', 'generic_loop_grid'],
    ),
    rowDirection: stringChoice<HookRowDirection>(
      raw.rowDirection,
      'alternating',
      ['right_to_left', 'left_to_right', 'alternating', 'in_the_round'],
    ),
    rows,
    columns,
    ...(repeat ? { repeat } : {}),
    stitchCodes,
    chainIds,
    courseIds,
    waleIds,
    chains: Array.from(chains.values()).sort((a, b) => a.id - b.id),
    stitchLegend: normalizeStitchLegend(raw.stitchLegend),
    gauge: normalizeHookGauge(raw.gauge),
    source: normalizeHookSource(raw.source, raw.title, raw.sourceLabel),
    title: raw.title || 'Hook Pattern',
    sourceLabel: raw.sourceLabel || 'Hook preset',
    renderSettings: normalizeHookRenderSettings(raw.renderSettings),
  };
}

export function buildStandardHookPreset(
  rows = DEFAULT_HOOK_ROWS,
  columns = DEFAULT_HOOK_COLUMNS,
): HookPatternDocument {
  return normalizeHookPattern({
    version: 1,
    structureType: 'hook',
    rows,
    columns,
    stitchCodes: Array.from({ length: rows }, () => Array.from({ length: columns }, () => 1)),
    chainIds: Array.from({ length: rows }, () => Array.from({ length: columns }, (_value, col) => col)),
    chains: Array.from({ length: columns }, (_value, col) => ({
      id: col,
      materialSlot: 0,
      direction: 'vertical',
      label: `Chain ${col + 1}`,
    })),
    title: `Classic Hook Wale ${rows}x${columns}`,
    sourceLabel: 'Starter Hook Structures',
    renderSettings: DEFAULT_HOOK_RENDER_SETTINGS,
    source: {
      kind: 'builtin',
      access: 'builtin',
      title: 'Classic Hook Wale Structure',
      note: 'Dense generated hook-wale baseline based on the Pre-V2 Blender prototype.',
    },
  });
}

function buildBalancedInterlockHookPreset(): HookPatternDocument {
  const rows = 16;
  const columns = 18;
  return normalizeHookPattern({
    version: 1,
    structureType: 'hook',
    structureFamily: 'crochet_hook',
    rowDirection: 'alternating',
    rows,
    columns,
    repeat: { mode: 'tile', rows: 8, columns: 6 },
    stitchCodes: [
      [1, 1, 1, 1, 1, 1],
      [1, 1, 0, 1, 1, 1],
      [1, 1, 1, 1, 0, 1],
      [1, 0, 1, 1, 1, 1],
      [1, 1, 1, 0, 1, 1],
      [1, 1, 1, 1, 1, 1],
      [1, 0, 1, 1, 1, 1],
      [1, 1, 1, 1, 0, 1],
    ],
    chainIds: Array.from({ length: rows }, (_value, row) =>
      Array.from({ length: columns }, (_cell, col) => col + (row % 2) * columns),
    ),
    chains: Array.from({ length: columns * 2 }, (_value, id) => ({
      id,
      materialSlot: 0,
      direction: 'vertical',
      label: `Interlock ${id + 1}`,
    })),
    title: 'Balanced Interlock Hook 16x18',
    sourceLabel: 'Starter Hook Structures',
    renderSettings: {
      ...DEFAULT_HOOK_RENDER_SETTINGS,
      legWidth: 0.62,
      loopHeight: 1.86,
      handleScale: 0.72,
      tubeRadius: 0.19,
      textureScaleU: 0.92,
      textureScaleV: 0.78,
      textureOffsetV: -0.36,
    },
    gauge: {
      unit: 'bu',
      density: 0.78,
      openness: 0.28,
      tension: 0.52,
    },
    source: {
      kind: 'generated',
      access: 'builtin',
      title: 'Balanced Interlock Hook',
      note: 'Generated look-dev starter pattern with staggered rows and modest openings.',
    },
  });
}

function buildSparseHookPreset(): HookPatternDocument {
  const rows = 15;
  const columns = 21;
  return normalizeHookPattern({
    version: 1,
    structureType: 'hook',
    rows,
    columns,
    stitchCodes: Array.from({ length: rows }, (_value, row) =>
      Array.from({ length: columns }, (_cell, col) => ((row + col) % 4 === 0 ? 0 : 1)),
    ),
    chainIds: Array.from({ length: rows }, () => Array.from({ length: columns }, (_value, col) => col)),
    chains: Array.from({ length: columns }, (_value, col) => ({
      id: col,
      materialSlot: 0,
      direction: 'vertical',
      label: `Chain ${col + 1}`,
    })),
    title: 'Open Hook Mesh 15x21',
    sourceLabel: 'Starter Hook Structures',
    renderSettings: {
      ...DEFAULT_HOOK_RENDER_SETTINGS,
      tubeRadius: 0.21,
      loopHeight: 2.16,
    },
  });
}

function buildColumnRibHookPreset(): HookPatternDocument {
  const rows = 15;
  const columns = 21;
  return normalizeHookPattern({
    version: 1,
    structureType: 'hook',
    rows,
    columns,
    stitchCodes: Array.from({ length: rows }, (_value, row) =>
      Array.from({ length: columns }, (_cell, col) => (col % 5 === 4 && row % 2 === 1 ? 0 : 1)),
    ),
    chainIds: Array.from({ length: rows }, () => Array.from({ length: columns }, (_value, col) => col)),
    chains: Array.from({ length: columns }, (_value, col) => ({
      id: col,
      materialSlot: 0,
      direction: 'vertical',
      label: `Rib ${col + 1}`,
    })),
    title: 'Column Rib Hook 15x21',
    sourceLabel: 'Starter Hook Structures',
    renderSettings: {
      ...DEFAULT_HOOK_RENDER_SETTINGS,
      legWidth: 0.78,
      handleScale: 0.68,
    },
  });
}

function buildTwoSlotStripeHookPreset(): HookPatternDocument {
  const rows = 15;
  const columns = 21;
  return normalizeHookPattern({
    version: 1,
    structureType: 'hook',
    rows,
    columns,
    stitchCodes: Array.from({ length: rows }, () => Array.from({ length: columns }, () => 1)),
    chainIds: Array.from({ length: rows }, () => Array.from({ length: columns }, (_value, col) => col)),
    chains: Array.from({ length: columns }, (_value, col) => ({
      id: col,
      materialSlot: Math.floor(col / 2) % 2,
      direction: 'vertical',
      label: `Stripe ${col + 1}`,
    })),
    title: 'Two Yarn Hook Stripe 15x21',
    sourceLabel: 'Starter Hook Structures',
    renderSettings: {
      ...DEFAULT_HOOK_RENDER_SETTINGS,
      tubeRadius: 0.23,
    },
  });
}

function buildFiletGridPreset(): HookPatternDocument {
  const rows = 18;
  const columns = 24;
  return normalizeHookPattern({
    version: 1,
    structureType: 'hook',
    structureFamily: 'crochet_hook',
    rowDirection: 'alternating',
    rows,
    columns,
    repeat: { mode: 'tile', rows: 6, columns: 6 },
    stitchCodes: [
      [1, 1, 1, 1, 1, 1],
      [1, 0, 0, 1, 0, 1],
      [1, 0, 1, 1, 0, 1],
      [1, 1, 1, 0, 0, 1],
      [1, 0, 1, 0, 1, 1],
      [1, 1, 1, 1, 1, 1],
    ],
    chains: Array.from({ length: columns }, (_value, col) => ({
      id: col,
      materialSlot: 0,
      direction: 'vertical',
      label: `Filet ${col + 1}`,
    })),
    title: 'Crochet Filet Grid 18x24',
    sourceLabel: 'Crochet Symbol Charts',
    source: {
      kind: 'generated',
      access: 'builtin',
      title: 'Generated filet-style chart',
      note: 'Generated structural sample; not a literal external pattern.',
    },
  });
}

function buildCrochetSymbolSamplerPreset(): HookPatternDocument {
  const rows = 12;
  const columns = 18;
  return normalizeHookPattern({
    version: 1,
    structureType: 'hook',
    structureFamily: 'crochet_hook',
    rowDirection: 'right_to_left',
    rows,
    columns,
    repeat: { mode: 'tile', rows: 4, columns: 6 },
    stitchCodes: [
      [2, 1, 1, 2, 1, 1],
      [4, 0, 5, 4, 0, 5],
      [1, 8, 1, 1, 8, 1],
      [3, 1, 1, 3, 1, 1],
    ],
    stitchLegend: DEFAULT_HOOK_STITCH_LEGEND,
    title: 'Crochet Symbol Sampler 12x18',
    sourceLabel: 'Crochet Symbol Charts',
    source: {
      kind: 'generated',
      access: 'builtin',
      title: 'Generated crochet-symbol chart',
      note: 'Stores reserved crochet stitch intent while Blender V1 renders active stitches with the standard hook loop.',
    },
  });
}

function buildKnitTextureCheckerPreset(): HookPatternDocument {
  const rows = 16;
  const columns = 24;
  return normalizeHookPattern({
    version: 1,
    structureType: 'hook',
    structureFamily: 'knit_chart',
    rowDirection: 'alternating',
    rows,
    columns,
    repeat: { mode: 'tile', rows: 4, columns: 4 },
    stitchCodes: [
      [6, 6, 7, 7],
      [6, 6, 7, 7],
      [7, 7, 6, 6],
      [7, 7, 6, 6],
    ],
    title: 'Knit/Purl Checker 16x24',
    sourceLabel: 'Knit Texture Charts',
    source: {
      kind: 'generated',
      access: 'builtin',
      title: 'Generated knit texture chart',
      note: 'Generated chart storing knit/purl intent for future Blender archetypes.',
    },
  });
}

function buildMachineKnitPunchcardPreset(): HookPatternDocument {
  const rows = 30;
  const columns = 24;
  return normalizeHookPattern({
    version: 1,
    structureType: 'hook',
    structureFamily: 'machine_knit',
    rowDirection: 'left_to_right',
    rows,
    columns,
    repeat: { mode: 'tile', rows: 6, columns: 24 },
    stitchCodes: Array.from({ length: 6 }, (_row, row) =>
      Array.from({ length: 24 }, (_cell, col) => ((row * 5 + col * 7) % 11 < 5 ? 1 : 0)),
    ),
    title: '24-Stitch Punchcard Dot Repeat',
    sourceLabel: 'Machine Knit Repeat Grids',
    source: {
      kind: 'generated',
      access: 'builtin',
      title: 'Generated 24-stitch punchcard repeat',
      note: 'Generated machine-knit repeat sample inspired by 24-stitch punchcard constraints.',
    },
  });
}

export const hookPresetDefinitions: HookPresetDefinition[] = [
  {
    id: 'hook-standard-15x21',
    label: 'Classic Hook Wale',
    summary: 'Dense rounded vertical hook wales using the Pre-V2 Blender visual baseline.',
    document: buildStandardHookPreset(),
  },
  {
    id: 'hook-balanced-interlock-16x18',
    label: 'Balanced Interlock',
    summary: 'A staggered hook fabric with moderate openings for later look exploration.',
    document: buildBalancedInterlockHookPreset(),
  },
  {
    id: 'hook-open-mesh-15x21',
    label: 'Open Hook Mesh',
    summary: 'Sparse active cells with deterministic chain U travel across holes.',
    document: buildSparseHookPreset(),
  },
  {
    id: 'hook-column-rib-15x21',
    label: 'Column Rib Hook',
    summary: 'Mostly dense vertical chains with intermittent rib openings.',
    document: buildColumnRibHookPreset(),
  },
  {
    id: 'hook-two-yarn-stripe-15x21',
    label: 'Two Yarn Stripe',
    summary: 'Alternating column-pair material slots for testing multi-yarn hooks.',
    document: buildTwoSlotStripeHookPreset(),
  },
  {
    id: 'hook-crochet-filet-grid',
    label: 'Crochet Filet Grid',
    summary: 'Generated open crochet chart with tiled repeat metadata.',
    document: buildFiletGridPreset(),
  },
  {
    id: 'hook-crochet-symbol-sampler',
    label: 'Crochet Symbol Sampler',
    summary: 'Stores crochet stitch-symbol intent while falling back to the V1 loop archetype.',
    document: buildCrochetSymbolSamplerPreset(),
  },
  {
    id: 'hook-knit-purl-checker',
    label: 'Knit/Purl Checker',
    summary: 'Generated knit texture chart with reserved knit and purl stitch codes.',
    document: buildKnitTextureCheckerPreset(),
  },
  {
    id: 'hook-machine-knit-punchcard',
    label: '24-Stitch Punchcard',
    summary: 'Machine-knit style repeat grid using a 24-column punchcard width.',
    document: buildMachineKnitPunchcardPreset(),
  },
];

export const hookPresets: HookPatternDocument[] = [
  ...hookPresetDefinitions.map((preset) => preset.document),
];

function hookPatternEntryFromPreset(preset: HookPresetDefinition): HookBookPatternEntry {
  return {
    id: preset.id,
    title: preset.label,
    summary: preset.summary,
    tags: [
      'builtin',
      preset.document.structureFamily || 'crochet_hook',
      preset.document.sourceLabel || 'hook',
    ],
    status: 'loadable',
    pattern: preset.document,
    source: preset.document.source,
    note: preset.document.source?.note,
  };
}

function hookBook(
  id: string,
  title: string,
  summary: string,
  sourceLabel: string,
  patterns: HookPresetDefinition[],
  tags: string[],
): HookPatternBook {
  return {
    id,
    title,
    summary,
    sourceLabel,
    access: 'builtin',
    tags,
    patternCount: patterns.length,
    patterns: patterns.map(hookPatternEntryFromPreset),
  };
}

export const builtinHookPatternBooks: HookPatternBook[] = [
  hookBook(
    'starter-hook-structures',
    'Starter Hook Structures',
    'Baseline hook structures for Blender look development and yarn material checks.',
    'Built-in starter hooks',
    hookPresetDefinitions.slice(0, 5),
    ['starter', 'hook', 'blender-baseline'],
  ),
  hookBook(
    'crochet-symbol-charts',
    'Crochet Symbol Charts',
    'Generated crochet-style charts that preserve symbol and legend intent.',
    'Generated crochet chart shelf',
    hookPresetDefinitions.slice(5, 7),
    ['crochet', 'symbols', 'generated'],
  ),
  hookBook(
    'knit-texture-charts',
    'Knit Texture Charts',
    'Generated knit texture grids for future knit/purl/cable archetypes.',
    'Generated knit chart shelf',
    hookPresetDefinitions.slice(7, 8),
    ['knit', 'texture', 'generated'],
  ),
  hookBook(
    'machine-knit-repeat-grids',
    'Machine Knit Repeat Grids',
    'Generated repeat grids including 24-stitch punchcard-style samples.',
    'Generated machine-knit chart shelf',
    hookPresetDefinitions.slice(8, 9),
    ['machine-knit', 'punchcard', 'repeat'],
  ),
];

function slugify(value: string) {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 80);
}

function normalizeHookBookPatternEntry(pattern: any, fallbackIndex: number): HookBookPatternEntry {
  const rawPattern = pattern?.pattern || pattern?.document || pattern?.hookPattern;
  const normalizedPattern = rawPattern ? normalizeHookPattern(rawPattern) : undefined;
  return {
    id: String(pattern?.id || `hook-pattern-${fallbackIndex + 1}`),
    title: String(pattern?.title || normalizedPattern?.title || `Hook Pattern ${fallbackIndex + 1}`),
    summary: String(pattern?.summary || 'Imported hook/knit pattern.'),
    tags: Array.isArray(pattern?.tags) ? pattern.tags.map(String) : ['imported', 'hook'],
    status: normalizedPattern ? 'loadable' : 'pending',
    pattern: normalizedPattern,
    source: pattern?.source ? normalizeHookSource(pattern.source, pattern?.title, pattern?.summary) : normalizedPattern?.source,
    note: pattern?.note ? String(pattern.note) : normalizedPattern?.source?.note,
    previewImage: pattern?.previewImage ? String(pattern.previewImage) : undefined,
  };
}

export function normalizeHookPatternBook(value: unknown): HookPatternBook {
  const raw = typeof value === 'object' && value !== null ? value as any : {};
  const title = String(raw.title || 'Imported Hook Pattern Book').trim() || 'Imported Hook Pattern Book';
  const patterns = Array.isArray(raw.patterns)
    ? raw.patterns.map(normalizeHookBookPatternEntry)
    : [];
  if (!patterns.length) {
    throw new Error('This hook pattern-book JSON does not contain any patterns.');
  }
  return {
    id: String(raw.id || slugify(title) || 'imported-hook-pattern-book'),
    title,
    summary: String(raw.summary || 'Locally imported hook/knit pattern book.'),
    sourceLabel: String(raw.sourceLabel || 'Local hook pattern book'),
    access: stringChoice<HookPatternAccess>(
      raw.access,
      'local',
      ['builtin', 'public-domain', 'catalog', 'local', 'linked'],
    ),
    tags: Array.isArray(raw.tags) ? raw.tags.map(String) : ['local', 'imported', 'hook'],
    patterns,
    patternCount: Number(raw.patternCount) || patterns.length,
    author: raw.author ? String(raw.author) : undefined,
    year: raw.year ? String(raw.year) : undefined,
    note: raw.note ? String(raw.note) : 'Loaded from a local hook pattern-book JSON file.',
  };
}

export function parseHookPatternBookJson(text: string): HookPatternBook {
  let raw: unknown;
  try {
    raw = JSON.parse(text);
  } catch {
    throw new Error('The selected hook pattern-book file is not valid JSON.');
  }
  if (typeof raw === 'object' && raw !== null && (raw as any).type && !['hook-pattern-book', 'pattern-book'].includes((raw as any).type)) {
    throw new Error('Expected a hook-pattern-book JSON file.');
  }
  return normalizeHookPatternBook(raw);
}

export function loadLocalHookPatternBooks(): HookPatternBook[] {
  if (typeof localStorage === 'undefined') {
    return [];
  }
  const raw = localStorage.getItem(LOCAL_HOOK_PATTERN_BOOKS_KEY);
  if (!raw) {
    return [];
  }
  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.map(normalizeHookPatternBook) : [];
  } catch {
    return [];
  }
}

export function saveLocalHookPatternBooks(books: HookPatternBook[]) {
  if (typeof localStorage === 'undefined') {
    return;
  }
  localStorage.setItem(LOCAL_HOOK_PATTERN_BOOKS_KEY, JSON.stringify(books, null, 2));
}

export function upsertLocalHookPatternBook(book: HookPatternBook): HookPatternBook[] {
  const books = loadLocalHookPatternBooks();
  const nextBooks = [
    book,
    ...books.filter((entry) => entry.id !== book.id),
  ];
  saveLocalHookPatternBooks(nextBooks);
  return nextBooks;
}

export function buildHookMaterialBindings(pattern: HookPatternDocument): HookMaterialBinding[] {
  const slots = getHookMaterialSlots(pattern);
  return slots.map((materialSlot) => ({ materialSlot, yarnAssetId: null }));
}

export function syncHookMaterialBindings(
  pattern: HookPatternDocument,
  current: HookMaterialBinding[],
  defaultYarnAssetId: string | null = null,
): HookMaterialBinding[] {
  const currentBySlot = new Map(
    current.map((binding) => [binding.materialSlot, binding.yarnAssetId]),
  );
  return getHookMaterialSlots(pattern).map((materialSlot) => ({
    materialSlot,
    yarnAssetId: currentBySlot.has(materialSlot)
      ? currentBySlot.get(materialSlot) || null
      : defaultYarnAssetId,
  }));
}

export function missingHookMaterialBindings(
  pattern: HookPatternDocument,
  bindings: HookMaterialBinding[],
): number[] {
  const boundSlots = new Map(bindings.map((binding) => [binding.materialSlot, binding.yarnAssetId]));
  return getHookMaterialSlots(pattern).filter((slot) => !boundSlots.get(slot));
}

export function getHookMaterialSlots(pattern: HookPatternDocument): number[] {
  const activeChains = new Set<number>();
  pattern.stitchCodes.forEach((row, rowIndex) => {
    row.forEach((code, colIndex) => {
      if (code !== 0) activeChains.add(pattern.chainIds[rowIndex]?.[colIndex] ?? colIndex);
    });
  });
  return Array.from(new Set(
    pattern.chains
      .filter((chain) => activeChains.has(chain.id))
      .map((chain) => chain.materialSlot),
  )).sort((a, b) => a - b);
}

export function buildHookProject(
  pattern: HookPatternDocument,
  yarnAssets: YarnAsset[],
  materialBindings: HookMaterialBinding[],
): HookProject {
  return {
    version: 1,
    pattern: normalizeHookPattern(pattern),
    yarnAssets,
    materialBindings,
  };
}
