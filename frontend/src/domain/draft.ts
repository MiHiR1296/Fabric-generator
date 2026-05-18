import type {
  BlenderHandoff,
  DraftCounts,
  DraftDocument,
  DraftRenderSettings,
  DraftSection,
  FocusedDrawdownCell,
  ReviewCell,
  SourceType,
} from './types';

export const DEFAULT_WARP_COLOR = '#f3ede2';
export const DEFAULT_WEFT_COLOR = '#b85e3c';
export const STORAGE_KEY = 'weaving-draft-studio/current-draft';
export const WEAVE_ZOOM_THREAD_LEVELS = [80, 120, 160, 200] as const;
export const DEFAULT_ARC1_V_PADDING = 0.008;
const PHYSICAL_SPACING_MIN = 0.026;
const PHYSICAL_SPACING_MAX = 0.1;

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

function cycleValues(length: number, maxValue: number) {
  return Array.from({ length }, (_, index) => (index % maxValue) + 1);
}

function normalizeThreading(threading: unknown, shaftCount: number, warpEnds: number) {
  if (!Array.isArray(threading)) {
    return cycleValues(warpEnds, shaftCount);
  }

  return Array.from({ length: warpEnds }, (_, index) => {
    const raw = Number(threading[index] ?? threading[index % Math.max(threading.length, 1)] ?? 1);
    return clamp(Math.round(raw || 1), 1, shaftCount);
  });
}

function normalizeTreadling(treadling: unknown, treadleCount: number, picks: number) {
  if (!Array.isArray(treadling)) {
    return cycleValues(picks, treadleCount);
  }

  return Array.from({ length: picks }, (_, index) => {
    const raw = Number(treadling[index] ?? treadling[index % Math.max(treadling.length, 1)] ?? 1);
    return clamp(Math.round(raw || 1), 1, treadleCount);
  });
}

function normalizeTieUp(tieUp: unknown, shaftCount: number, treadleCount: number) {
  return Array.from({ length: shaftCount }, (_, shaftIndex) => {
    const row = Array.isArray(tieUp) ? tieUp[shaftIndex] : null;
    return Array.from({ length: treadleCount }, (_, treadleIndex) => {
      if (!Array.isArray(row)) {
        return false;
      }
      return Boolean(row[treadleIndex]);
    });
  });
}

function normalizeColorSequence(colors: unknown, fallback: string, length: number) {
  const palette = Array.isArray(colors)
    ? colors
        .map((value) => String(value || '').trim())
        .filter(Boolean)
    : [];

  if (palette.length === 0) {
    return Array.from({ length }, () => fallback);
  }

  return Array.from({ length }, (_, index) => palette[index % palette.length]);
}

// Shape and defaults mirror v2 (Fabric-generator-codex-fabric-generator-v2/frontend/src/domain/draft.ts).
// Spacing / pattern-noise controls exposed on the web UI are forced to 0 per
// product decision (2026-05-14). v2's spacing default of 0.29 is intentionally
// overridden here so the input fields start at 0 in tryon.
// Non-exposed fields keep v2's geometric defaults so unedited renders still look right.
function numberOrFallback(value: unknown, fallback: number) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function integerOrFallback(value: unknown, fallback: number) {
  return Math.round(numberOrFallback(value, fallback));
}

function normalizeUnitControl(value: unknown, fallback: number) {
  return clamp(numberOrFallback(value, fallback), 0, 1);
}

function normalizeRenderThreadCount(value: unknown, fallback: number, draftCount: number) {
  const minThreads = Math.max(draftCount, WEAVE_ZOOM_THREAD_LEVELS[0]);
  const maxThreads = Math.max(minThreads, WEAVE_ZOOM_THREAD_LEVELS[WEAVE_ZOOM_THREAD_LEVELS.length - 1]);
  return clamp(integerOrFallback(value, fallback), minThreads, maxThreads);
}

function normalizeSpacingControl(
  raw: Partial<DraftRenderSettings>,
  fallback: DraftRenderSettings,
) {
  const value = numberOrFallback(raw.spacing, fallback.spacing);
  const hasUnitControls =
    Object.prototype.hasOwnProperty.call(raw, 'patternNoiseX') ||
    Object.prototype.hasOwnProperty.call(raw, 'patternNoiseY');

  // Legacy physical-spacing values (0.005..0.2) get remapped onto the 0..1
  // unit scale the v2 backend now expects. Once both patternNoise controls
  // are present we trust the value is already on the unit scale.
  if (!hasUnitControls && Number.isFinite(value) && value >= 0.005 && value <= 0.2) {
    return Math.round(
      clamp((value - PHYSICAL_SPACING_MIN) / (PHYSICAL_SPACING_MAX - PHYSICAL_SPACING_MIN), 0, 1) * 100,
    ) / 100;
  }

  return clamp(value, 0, 1);
}

function buildDefaultRenderSettings(warpEnds: number, picks: number): DraftRenderSettings {
  return {
    warpThreads: Math.max(warpEnds, WEAVE_ZOOM_THREAD_LEVELS[0]),
    weftThreads: Math.max(picks, WEAVE_ZOOM_THREAD_LEVELS[0]),
    // Exposed on the web UI — defaults pinned to 0.
    spacing: 0,
    patternNoiseX: 0,
    patternNoiseY: 0,
    // Non-exposed — v2 geometric defaults.
    amplitude: 0.008,
    threadRadius: 0.028,
    threadSubdivisions: 8,
    plyCount: 3,
    plyRadius: 0.013,
    twistAmount: 16,
    plyResolution: 5,
    textureScaleU: 8,
    textureUCalibration: 0.1,
    textureScaleV: 0.5,
    textureOffsetV: 0,
    textureSideFlatten: 0.7,
    arc1VPadding: DEFAULT_ARC1_V_PADDING,
    lumpStrength: 0.0015,
    lumpScale: 6,
    fiberDensity: 0,
    fiberLength: 0.04,
    fiberThickness: 0.15,
    fiberFrizz: 0.02,
    fiberSubdivs: 4,
    seed: 0,
    fillRatio: 1,
    // Per-strand texture U-shift. 1 = baseline scatter (default), 0 = lock,
    // 20 = strong scatter. Exposed in the web UI alongside Spacing /
    // Pattern Noise. Pushed to the global 'UV Random U' modifier socket.
    uvRandomU: 1,
  };
}

function normalizeRenderSettings(
  settings: unknown,
  warpEnds: number,
  picks: number,
): DraftRenderSettings {
  const fallback = buildDefaultRenderSettings(warpEnds, picks);
  const raw = typeof settings === 'object' && settings !== null ? settings as Partial<DraftRenderSettings> : {};

  return {
    warpThreads: normalizeRenderThreadCount(raw.warpThreads, fallback.warpThreads, warpEnds),
    weftThreads: normalizeRenderThreadCount(raw.weftThreads, fallback.weftThreads, picks),
    spacing: normalizeSpacingControl(raw, fallback),
    patternNoiseX: normalizeUnitControl(raw.patternNoiseX, fallback.patternNoiseX),
    patternNoiseY: normalizeUnitControl(raw.patternNoiseY, fallback.patternNoiseY),
    amplitude: clamp(numberOrFallback(raw.amplitude, fallback.amplitude), 0.001, 0.1),
    threadRadius: clamp(numberOrFallback(raw.threadRadius, fallback.threadRadius), 0.001, 0.2),
    threadSubdivisions: clamp(
      numberOrFallback(raw.threadSubdivisions, fallback.threadSubdivisions),
      3,
      64,
    ),
    plyCount: clamp(integerOrFallback(raw.plyCount, fallback.plyCount), 1, 16),
    plyRadius: clamp(numberOrFallback(raw.plyRadius, fallback.plyRadius), 0.001, 0.1),
    twistAmount: clamp(numberOrFallback(raw.twistAmount, fallback.twistAmount), 0, 128),
    plyResolution: clamp(integerOrFallback(raw.plyResolution, fallback.plyResolution), 2, 24),
    textureScaleU: clamp(numberOrFallback(raw.textureScaleU, fallback.textureScaleU), 0.1, 64),
    textureUCalibration: clamp(numberOrFallback(raw.textureUCalibration, fallback.textureUCalibration), 0.01, 2),
    textureScaleV: clamp(numberOrFallback(raw.textureScaleV, fallback.textureScaleV), 0.05, 5),
    textureOffsetV: clamp(numberOrFallback(raw.textureOffsetV, fallback.textureOffsetV), -2, 2),
    textureSideFlatten: clamp(
      numberOrFallback(raw.textureSideFlatten, fallback.textureSideFlatten),
      0,
      1,
    ),
    arc1VPadding: clamp(numberOrFallback(raw.arc1VPadding, fallback.arc1VPadding), 0, 0.25),
    lumpStrength: clamp(numberOrFallback(raw.lumpStrength, fallback.lumpStrength), 0, 0.1),
    lumpScale: clamp(numberOrFallback(raw.lumpScale, fallback.lumpScale), 0.1, 50),
    fiberDensity: clamp(numberOrFallback(raw.fiberDensity, fallback.fiberDensity), 0, 5),
    fiberLength: clamp(numberOrFallback(raw.fiberLength, fallback.fiberLength), 0, 1),
    fiberThickness: clamp(numberOrFallback(raw.fiberThickness, fallback.fiberThickness), 0, 1),
    fiberFrizz: clamp(numberOrFallback(raw.fiberFrizz, fallback.fiberFrizz), 0, 1),
    fiberSubdivs: clamp(integerOrFallback(raw.fiberSubdivs, fallback.fiberSubdivs), 0, 24),
    seed: clamp(integerOrFallback(raw.seed, fallback.seed), 0, 1000000),
    fillRatio: clamp(numberOrFallback(raw.fillRatio, fallback.fillRatio), 0.6, 1),
    uvRandomU: clamp(numberOrFallback(raw.uvRandomU, fallback.uvRandomU), 0, 20),
  };
}

export function getThreadingIndexFromDrawdownColumn(threadingLength: number, endIndex: number) {
  return threadingLength - endIndex - 1;
}

export function computeDrawdown(
  threading: number[],
  tieUp: boolean[][],
  treadling: number[],
) {
  return treadling.map((treadle) =>
    Array.from({ length: threading.length }, (_, endIndex) => {
      const shaft = threading[getThreadingIndexFromDrawdownColumn(threading.length, endIndex)];
      const shaftIndex = shaft - 1;
      const treadleIndex = treadle - 1;
      return tieUp[shaftIndex]?.[treadleIndex] ? 1 : 0;
    }),
  );
}

export function parseSequenceText(text: string) {
  return text
    .split(/[\s,;|]+/)
    .map((part) => Number(part))
    .filter((part) => Number.isFinite(part))
    .map((part) => Math.round(part));
}

function parseTieUpToken(token: string) {
  const normalized = token.trim().toLowerCase();
  return normalized === '1' || normalized === 'x' || normalized === 'true' || normalized === 't';
}

export function parseTieUpEditorText(text: string) {
  const visualRows = text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => line.split(/[\s,;|]+/).filter(Boolean).map(parseTieUpToken));

  return visualRows.slice().reverse();
}

export function serializeSequenceText(values: number[]) {
  return values.join(' ');
}

export function parseColorSequenceText(text: string) {
  return text
    .split(/[\s,;|]+/)
    .map((part) => part.trim())
    .filter(Boolean);
}

export function serializeColorSequenceText(values: string[]) {
  return values.join(' ');
}

export function serializeTieUpEditorText(tieUp: boolean[][]) {
  return tieUp
    .slice()
    .reverse()
    .map((row) => row.map((value) => (value ? '1' : '0')).join(' '))
    .join('\n');
}

export function serializeDrawdownText(drawdown: number[][]) {
  return drawdown.map((row) => row.join(' ')).join('\n');
}

export function getDraftCounts(draft: DraftDocument): DraftCounts {
  return {
    shaftCount: draft.shaftCount,
    treadleCount: draft.treadleCount,
    warpEnds: draft.threading.length,
    picks: draft.treadling.length,
  };
}

export function createBlankDraft(options?: Partial<DraftCounts> & {
  sourceType?: SourceType;
  title?: string;
  sourceLabel?: string;
}) {
  const shaftCount = clamp(Math.round(options?.shaftCount || 4), 2, 32);
  const treadleCount = clamp(Math.round(options?.treadleCount || 4), 2, 32);
  const warpEnds = clamp(Math.round(options?.warpEnds || 24), 4, 256);
  const picks = clamp(Math.round(options?.picks || 24), 4, 256);
  const threading = cycleValues(warpEnds, shaftCount);
  const treadling = cycleValues(picks, treadleCount);
  const tieUp = normalizeTieUp(null, shaftCount, treadleCount);
  const drawdown = computeDrawdown(threading, tieUp, treadling);

  return {
    version: 1 as const,
    sourceType: options?.sourceType || 'manual',
    shaftCount,
    treadleCount,
    threading,
    tieUp,
    treadling,
    drawdown,
    warpColors: normalizeColorSequence([DEFAULT_WARP_COLOR], DEFAULT_WARP_COLOR, warpEnds),
    weftColors: normalizeColorSequence([DEFAULT_WEFT_COLOR], DEFAULT_WEFT_COLOR, picks),
    parseConfidence: options?.sourceType === 'manual' ? 1 : 0,
    warnings: [],
    lowConfidenceCells: [],
    title: options?.title || 'Untitled Draft',
    sourceLabel: options?.sourceLabel || 'Manual draft',
    renderSettings: buildDefaultRenderSettings(warpEnds, picks),
  };
}

export function normalizeDraft(raw: Partial<DraftDocument> | DraftDocument) {
  const shaftCount = clamp(Math.round(Number(raw.shaftCount) || 4), 2, 32);
  const treadleCount = clamp(Math.round(Number(raw.treadleCount) || 4), 2, 32);
  const warpEnds = clamp(
    Array.isArray(raw.threading) ? raw.threading.length : 24,
    4,
    256,
  );
  const picks = clamp(
    Array.isArray(raw.treadling) ? raw.treadling.length : 24,
    4,
    256,
  );
  const threading = normalizeThreading(raw.threading, shaftCount, warpEnds);
  const treadling = normalizeTreadling(raw.treadling, treadleCount, picks);
  const tieUp = normalizeTieUp(raw.tieUp, shaftCount, treadleCount);
  const drawdown = computeDrawdown(threading, tieUp, treadling);

  return {
    version: 1 as const,
    sourceType: (raw.sourceType || 'manual') as SourceType,
    shaftCount,
    treadleCount,
    threading,
    tieUp,
    treadling,
    drawdown,
    warpColors: normalizeColorSequence(raw.warpColors, DEFAULT_WARP_COLOR, warpEnds),
    weftColors: normalizeColorSequence(raw.weftColors, DEFAULT_WEFT_COLOR, picks),
    parseConfidence: clamp(Number(raw.parseConfidence ?? 1), 0, 1),
    warnings: Array.isArray(raw.warnings) ? raw.warnings.map(String) : [],
    lowConfidenceCells: Array.isArray(raw.lowConfidenceCells)
      ? raw.lowConfidenceCells.map((cell) => ({
          section: cell.section,
          row: Number(cell.row),
          col: Number(cell.col),
          confidence: Number(cell.confidence),
          reason: String(cell.reason),
        }))
      : [],
    title: raw.title || 'Imported Draft',
    sourceLabel: raw.sourceLabel || 'Imported source',
    renderSettings: normalizeRenderSettings(raw.renderSettings, warpEnds, picks),
  };
}

export function serializeDraft(draft: DraftDocument) {
  return JSON.stringify(normalizeDraft(draft), null, 2);
}

export function buildBlenderHandoff(draft: DraftDocument): BlenderHandoff {
  const normalized = normalizeDraft(draft);
  return {
    repeatCols: normalized.threading.length,
    repeatRows: normalized.treadling.length,
    cellCodeMatrix: normalized.drawdown,
    cellCodeLegend: {
      0: 'weft_over',
      1: 'warp_over',
    },
  };
}

export function serializeBlenderHandoff(draft: DraftDocument) {
  return JSON.stringify(buildBlenderHandoff(draft), null, 2);
}

function removeReviewCell(
  lowConfidenceCells: ReviewCell[] | undefined,
  section: DraftSection,
  row: number,
  col: number,
) {
  return (lowConfidenceCells || []).filter(
    (cell) => !(cell.section === section && cell.row === row && cell.col === col),
  );
}

export function updateDraftCounts(draft: DraftDocument, counts: Partial<DraftCounts>) {
  const nextCounts = {
    shaftCount: clamp(Math.round(counts.shaftCount || draft.shaftCount), 2, 32),
    treadleCount: clamp(Math.round(counts.treadleCount || draft.treadleCount), 2, 32),
    warpEnds: clamp(Math.round(counts.warpEnds || draft.threading.length), 4, 256),
    picks: clamp(Math.round(counts.picks || draft.treadling.length), 4, 256),
  };

  const threading = normalizeThreading(draft.threading, nextCounts.shaftCount, nextCounts.warpEnds);
  const treadling = normalizeTreadling(draft.treadling, nextCounts.treadleCount, nextCounts.picks);
  const tieUp = normalizeTieUp(draft.tieUp, nextCounts.shaftCount, nextCounts.treadleCount);
  const drawdown = computeDrawdown(threading, tieUp, treadling);
  const warpColors = normalizeColorSequence(
    draft.warpColors,
    draft.warpColors[0] || DEFAULT_WARP_COLOR,
    nextCounts.warpEnds,
  );
  const weftColors = normalizeColorSequence(
    draft.weftColors,
    draft.weftColors[0] || DEFAULT_WEFT_COLOR,
    nextCounts.picks,
  );

  return {
    ...draft,
    shaftCount: nextCounts.shaftCount,
    treadleCount: nextCounts.treadleCount,
    threading,
    tieUp,
    treadling,
    drawdown,
    warpColors,
    weftColors,
    renderSettings: normalizeRenderSettings(draft.renderSettings, nextCounts.warpEnds, nextCounts.picks),
    lowConfidenceCells: (draft.lowConfidenceCells || []).filter((cell) => {
      if (cell.section === 'threading') {
        return cell.col < nextCounts.warpEnds && cell.row < nextCounts.shaftCount;
      }
      if (cell.section === 'treadling') {
        return cell.row < nextCounts.picks && cell.col < nextCounts.treadleCount;
      }
      if (cell.section === 'tieUp') {
        return cell.row < nextCounts.shaftCount && cell.col < nextCounts.treadleCount;
      }
      return cell.row < nextCounts.picks && cell.col < nextCounts.warpEnds;
    }),
  };
}

export function applyStructuredPatternEdit(
  draft: DraftDocument,
  edits: {
    threadingText?: string;
    tieUpText?: string;
    treadlingText?: string;
  },
) {
  const parsedThreading =
    edits.threadingText && edits.threadingText.trim()
      ? parseSequenceText(edits.threadingText)
      : null;
  const parsedTreadling =
    edits.treadlingText && edits.treadlingText.trim()
      ? parseSequenceText(edits.treadlingText)
      : null;
  const parsedTieUp =
    edits.tieUpText && edits.tieUpText.trim()
      ? parseTieUpEditorText(edits.tieUpText)
      : null;

  const tieUpRowCount = parsedTieUp?.length || 0;
  const tieUpColCount = Math.max(...(parsedTieUp || [[]]).map((row) => row.length), 0);
  const nextShaftCount = clamp(
    Math.max(
      draft.shaftCount,
      tieUpRowCount,
      ...(parsedThreading && parsedThreading.length > 0 ? parsedThreading : [draft.shaftCount]),
    ),
    2,
    32,
  );
  const nextTreadleCount = clamp(
    Math.max(
      draft.treadleCount,
      tieUpColCount,
      ...(parsedTreadling && parsedTreadling.length > 0 ? parsedTreadling : [draft.treadleCount]),
    ),
    2,
    32,
  );
  const nextWarpEnds = clamp(parsedThreading?.length || draft.threading.length, 4, 256);
  const nextPicks = clamp(parsedTreadling?.length || draft.treadling.length, 4, 256);
  const threading = normalizeThreading(parsedThreading || draft.threading, nextShaftCount, nextWarpEnds);
  const treadling = normalizeTreadling(parsedTreadling || draft.treadling, nextTreadleCount, nextPicks);
  const tieUp = normalizeTieUp(parsedTieUp || draft.tieUp, nextShaftCount, nextTreadleCount);
  const warpColors = normalizeColorSequence(
    draft.warpColors,
    draft.warpColors[0] || DEFAULT_WARP_COLOR,
    nextWarpEnds,
  );
  const weftColors = normalizeColorSequence(
    draft.weftColors,
    draft.weftColors[0] || DEFAULT_WEFT_COLOR,
    nextPicks,
  );

  return {
    ...draft,
    sourceType: 'manual' as const,
    shaftCount: nextShaftCount,
    treadleCount: nextTreadleCount,
    threading,
    tieUp,
    treadling,
    drawdown: computeDrawdown(threading, tieUp, treadling),
    warpColors,
    weftColors,
    lowConfidenceCells: [],
    renderSettings: normalizeRenderSettings(draft.renderSettings, nextWarpEnds, nextPicks),
  };
}

export function applyColorSequenceEdit(
  draft: DraftDocument,
  edits: {
    warpColorsText?: string;
    weftColorsText?: string;
  },
) {
  const parsedWarpColors =
    edits.warpColorsText && edits.warpColorsText.trim()
      ? parseColorSequenceText(edits.warpColorsText)
      : null;
  const parsedWeftColors =
    edits.weftColorsText && edits.weftColorsText.trim()
      ? parseColorSequenceText(edits.weftColorsText)
      : null;

  return {
    ...draft,
    sourceType: 'manual' as const,
    warpColors: normalizeColorSequence(
      parsedWarpColors || draft.warpColors,
      draft.warpColors[0] || DEFAULT_WARP_COLOR,
      draft.threading.length,
    ),
    weftColors: normalizeColorSequence(
      parsedWeftColors || draft.weftColors,
      draft.weftColors[0] || DEFAULT_WEFT_COLOR,
      draft.treadling.length,
    ),
  };
}

export function setThreadingShaft(draft: DraftDocument, endIndex: number, shaft: number) {
  const threading = draft.threading.map((value, index) =>
    index === endIndex ? clamp(shaft, 1, draft.shaftCount) : value,
  );
  return {
    ...draft,
    sourceType: 'manual' as const,
    threading,
    drawdown: computeDrawdown(threading, draft.tieUp, draft.treadling),
    lowConfidenceCells: removeReviewCell(draft.lowConfidenceCells, 'threading', shaft - 1, endIndex),
  };
}

export function toggleTieUpCell(
  draft: DraftDocument,
  shaftIndex: number,
  treadleIndex: number,
  forcedValue?: boolean,
) {
  const tieUp = draft.tieUp.map((row, rowIndex) =>
    row.map((value, colIndex) => {
      if (rowIndex !== shaftIndex || colIndex !== treadleIndex) {
        return value;
      }
      return typeof forcedValue === 'boolean' ? forcedValue : !value;
    }),
  );

  return {
    ...draft,
    sourceType: 'manual' as const,
    tieUp,
    drawdown: computeDrawdown(draft.threading, tieUp, draft.treadling),
    lowConfidenceCells: removeReviewCell(draft.lowConfidenceCells, 'tieUp', shaftIndex, treadleIndex),
  };
}

export function setTreadlingTreadle(draft: DraftDocument, pickIndex: number, treadle: number) {
  const treadling = draft.treadling.map((value, index) =>
    index === pickIndex ? clamp(treadle, 1, draft.treadleCount) : value,
  );

  return {
    ...draft,
    sourceType: 'manual' as const,
    treadling,
    drawdown: computeDrawdown(draft.threading, draft.tieUp, treadling),
    lowConfidenceCells: removeReviewCell(draft.lowConfidenceCells, 'treadling', pickIndex, treadle - 1),
  };
}

export function resetSection(draft: DraftDocument, section: DraftSection) {
  if (section === 'threading') {
    const threading = cycleValues(draft.threading.length, draft.shaftCount);
    return {
      ...draft,
      threading,
      drawdown: computeDrawdown(threading, draft.tieUp, draft.treadling),
      lowConfidenceCells: [],
      sourceType: 'manual' as const,
    };
  }

  if (section === 'tieUp') {
    const tieUp = normalizeTieUp(null, draft.shaftCount, draft.treadleCount);
    return {
      ...draft,
      tieUp,
      drawdown: computeDrawdown(draft.threading, tieUp, draft.treadling),
      lowConfidenceCells: [],
      sourceType: 'manual' as const,
    };
  }

  if (section === 'treadling') {
    const treadling = cycleValues(draft.treadling.length, draft.treadleCount);
    return {
      ...draft,
      treadling,
      drawdown: computeDrawdown(draft.threading, draft.tieUp, treadling),
      lowConfidenceCells: [],
      sourceType: 'manual' as const,
    };
  }

  return {
    ...draft,
    drawdown: computeDrawdown(draft.threading, draft.tieUp, draft.treadling),
    lowConfidenceCells: [],
    sourceType: 'manual' as const,
  };
}

export function setWarpEndColor(draft: DraftDocument, endIndex: number, color: string) {
  const warpColors = draft.warpColors.map((value, index) =>
    index === endIndex ? color : value,
  );

  return {
    ...draft,
    sourceType: 'manual' as const,
    warpColors,
  };
}

export function setWeftPickColor(draft: DraftDocument, pickIndex: number, color: string) {
  const weftColors = draft.weftColors.map((value, index) =>
    index === pickIndex ? color : value,
  );

  return {
    ...draft,
    sourceType: 'manual' as const,
    weftColors,
  };
}

export function updateRenderSettings(
  draft: DraftDocument,
  settings: Partial<DraftRenderSettings>,
) {
  return {
    ...draft,
    sourceType: 'manual' as const,
    renderSettings: normalizeRenderSettings(
      {
        ...(draft.renderSettings || {}),
        ...settings,
      },
      draft.threading.length,
      draft.treadling.length,
    ),
  };
}

export function getDraftPalette(draft: DraftDocument) {
  return Array.from(new Set([...draft.warpColors, ...draft.weftColors])).slice(0, 24);
}

export function getReviewCell(
  draft: DraftDocument,
  section: DraftSection,
  row: number,
  col: number,
) {
  return (draft.lowConfidenceCells || []).find(
    (cell) => cell.section === section && cell.row === row && cell.col === col,
  );
}

export function getFocusSummary(draft: DraftDocument, focus: FocusedDrawdownCell | null) {
  if (!focus) {
    return {
      title: 'Hover the drawdown',
      body: 'Trace any cloth cell through threading, tie-up, and treadling.',
      warpOver: null as boolean | null,
      shaft: null as number | null,
      treadle: null as number | null,
    };
  }

  const threadingIndex = getThreadingIndexFromDrawdownColumn(
    draft.threading.length,
    focus.endIndex,
  );
  const shaft = draft.threading[threadingIndex];
  const treadle = draft.treadling[focus.pickIndex];
  const warpOver = draft.tieUp[shaft - 1]?.[treadle - 1] || false;

  return {
    title: `Pick ${focus.pickIndex + 1}, Warp End ${focus.endIndex + 1}`,
    body: warpOver
      ? `Warp end ${focus.endIndex + 1} is threaded on shaft ${shaft}. Pick ${focus.pickIndex + 1} uses treadle ${treadle}, and the tie-up lifts that shaft, so the warp passes over the weft here.`
      : `Warp end ${focus.endIndex + 1} is threaded on shaft ${shaft}. Pick ${focus.pickIndex + 1} uses treadle ${treadle}, but the tie-up does not lift that shaft, so the weft passes over the warp here.`,
    warpOver,
    shaft,
    treadle,
  };
}

export function downloadTextFile(filename: string, body: string) {
  const blob = new Blob([body], { type: 'application/json;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

export function loadDraftFromStorage() {
  const raw = localStorage.getItem(STORAGE_KEY);
  if (!raw) {
    return null;
  }

  try {
    return normalizeDraft(JSON.parse(raw));
  } catch {
    return null;
  }
}

export function saveDraftToStorage(draft: DraftDocument) {
  localStorage.setItem(STORAGE_KEY, serializeDraft(draft));
}

export function parseLooseTextDraft(text: string) {
  const trimmed = text.trim();

  if (!trimmed) {
    throw new Error('Paste draft text before parsing.');
  }

  if (trimmed.startsWith('{')) {
    return normalizeDraft(JSON.parse(trimmed));
  }

  const sections: Record<string, string[]> = {};
  let currentSection = 'root';
  sections[currentSection] = [];

  for (const line of trimmed.split(/\r?\n/)) {
    const clean = line.trim();
    if (!clean) {
      continue;
    }

    const header = clean.match(/^(threading|tieup|tie-up|treadling|shafts|treadles)\s*:/i);
    if (header) {
      currentSection = header[1].toLowerCase().replace('tie-up', 'tieup');
      sections[currentSection] = sections[currentSection] || [];
      const remainder = clean.slice(header[0].length).trim();
      if (remainder) {
        sections[currentSection].push(remainder);
      }
      continue;
    }

    sections[currentSection] = sections[currentSection] || [];
    sections[currentSection].push(clean);
  }

  const shaftCount = clamp(
    Number(sections.shafts?.[0]?.match(/\d+/)?.[0] || 4),
    2,
    32,
  );
  const treadleCount = clamp(
    Number(sections.treadles?.[0]?.match(/\d+/)?.[0] || 4),
    2,
    32,
  );

  const threading = normalizeThreading(
    parseSequenceText((sections.threading || []).join(' ')),
    shaftCount,
    Math.max(parseSequenceText((sections.threading || []).join(' ')).length, 4),
  );
  const treadling = normalizeTreadling(
    parseSequenceText((sections.treadling || []).join(' ')),
    treadleCount,
    Math.max(parseSequenceText((sections.treadling || []).join(' ')).length, 4),
  );
  const tieUpMatrix = (sections.tieup || []).map((row) => parseSequenceText(row).map(Boolean));
  const normalizedTieUp = normalizeTieUp(tieUpMatrix, shaftCount, treadleCount);

  return normalizeDraft({
    version: 1,
    sourceType: 'text',
    shaftCount,
    treadleCount,
    threading,
    tieUp: normalizedTieUp,
    treadling,
    warpColors: [DEFAULT_WARP_COLOR],
    weftColors: [DEFAULT_WEFT_COLOR],
    parseConfidence: 0.75,
    warnings: ['Parsed locally from pasted text. Review the draft before exporting.'],
    title: 'Pasted Draft',
    sourceLabel: 'Local text parser',
  });
}
