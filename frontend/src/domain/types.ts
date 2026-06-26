export type SourceType = 'manual' | 'wif' | 'json' | 'text' | 'image';
export type DraftSection = 'threading' | 'tieUp' | 'treadling' | 'drawdown';
export type ParserStatus = 'checking' | 'online' | 'offline';
export type BlenderRenderStatus = 'queued' | 'running' | 'succeeded' | 'failed';
export type YarnAssetStatus = 'queued' | 'processing' | 'ready' | 'failed';
export type FabricStructureType = 'weave' | 'hook';
export type HookStructureFamily =
  | 'crochet_hook'
  | 'knit_chart'
  | 'machine_knit'
  | 'generic_loop_grid';
export type HookRowDirection =
  | 'right_to_left'
  | 'left_to_right'
  | 'alternating'
  | 'in_the_round';
export type HookPatternAccess = 'builtin' | 'public-domain' | 'catalog' | 'local' | 'linked';
export type HookPatternSourceKind =
  | 'builtin'
  | 'generated'
  | 'literal'
  | 'user-authored'
  | 'imported'
  | 'catalog-reference';
export type HookStitchArchetype =
  | 'empty'
  | 'standard_hook_loop'
  | 'chain_foundation'
  | 'slip_stitch'
  | 'single_crochet'
  | 'double_crochet'
  | 'knit_v'
  | 'purl_bump'
  | 'yarn_over_open'
  | 'tuck'
  | 'miss_float'
  | 'cable_crossing'
  | 'reserved';

export interface DraftRenderSettings {
  warpThreads: number;
  weftThreads: number;
  spacing: number;
  patternNoiseX: number;
  patternNoiseY: number;
  amplitude: number;
  threadRadius: number;
  threadSubdivisions: number;
  plyCount: number;
  plyRadius: number;
  twistAmount: number;
  plyResolution: number;
  textureScaleU: number;
  textureUCalibration: number;
  textureScaleV: number;
  textureOffsetV: number;
  textureSideFlatten: number;
  arc1VPadding: number;
  lumpStrength: number;
  lumpScale: number;
  fiberDensity: number;
  fiberLength: number;
  fiberThickness: number;
  fiberFrizz: number;
  fiberSubdivs: number;
  seed: number;
  fillRatio: number;
  // Per-strand U-offset randomization. 0 disables and is the default for
  // deterministic texture diagnostics; up to 20 produces strong staggering.
  // Pushed to the global 'UV Random U' modifier socket.
  uvRandomU: number;
}

export interface ReviewCell {
  section: DraftSection;
  row: number;
  col: number;
  confidence: number;
  reason: string;
}

export interface DraftDocument {
  version: 1;
  sourceType: SourceType;
  shaftCount: number;
  treadleCount: number;
  threading: number[];
  tieUp: boolean[][];
  treadling: number[];
  drawdown: number[][];
  warpColors: string[];
  weftColors: string[];
  parseConfidence: number;
  warnings: string[];
  lowConfidenceCells?: ReviewCell[];
  title?: string;
  sourceLabel?: string;
  renderSettings?: DraftRenderSettings;
}

export interface HookRenderSettings {
  hookScale: number;
  legWidth: number;
  loopHeight: number;
  handleScale: number;
  legZOffset: number;
  tubeRadius: number;
  curveResolution: number;
  tubeResolution: number;
  textureScaleU: number;
  textureScaleV: number;
  textureOffsetV: number;
  textureSideFlatten: number;
  arc1VPadding: number;
  fillRatio: number;
  seed: number;
}

export interface HookChain {
  id: number;
  materialSlot: number;
  direction: 'vertical' | 'horizontal' | 'course' | 'wale';
  label?: string;
}

export interface HookRepeatUnit {
  mode: 'tile';
  rows: number;
  columns: number;
}

export interface HookStitchLegendEntry {
  code: number;
  symbol: string;
  label: string;
  archetype: HookStitchArchetype;
  supported: boolean;
  fallbackCode?: number;
  abbreviation?: string;
  notes?: string;
}

export interface HookGaugeSettings {
  unit: 'bu' | 'cm' | 'in';
  stitchesPerUnit?: number;
  rowsPerUnit?: number;
  density?: number;
  openness?: number;
  loopHeight?: number;
  tension?: number;
}

export interface HookPatternSource {
  kind: HookPatternSourceKind;
  access: HookPatternAccess;
  title?: string;
  author?: string;
  site?: string;
  book?: string;
  url?: string;
  note?: string;
}

export interface HookPatternDocument {
  version: 1;
  structureType: 'hook';
  structureFamily?: HookStructureFamily;
  rowDirection?: HookRowDirection;
  rows: number;
  columns: number;
  repeat?: HookRepeatUnit;
  stitchCodes: number[][];
  chainIds: number[][];
  courseIds?: number[][];
  waleIds?: number[][];
  chains: HookChain[];
  stitchLegend?: HookStitchLegendEntry[];
  gauge?: HookGaugeSettings;
  source?: HookPatternSource;
  title?: string;
  sourceLabel?: string;
  renderSettings?: HookRenderSettings;
}

export interface HookBookPatternEntry {
  id: string;
  title: string;
  summary: string;
  tags: string[];
  status: 'loadable' | 'pending';
  pattern?: HookPatternDocument;
  source?: HookPatternSource;
  note?: string;
  previewImage?: string;
}

export interface HookPatternBook {
  id: string;
  title: string;
  summary: string;
  sourceLabel: string;
  access: HookPatternAccess;
  tags: string[];
  patterns: HookBookPatternEntry[];
  author?: string;
  year?: string;
  patternCount?: number;
  note?: string;
}

export interface BlenderHandoff {
  repeatCols: number;
  repeatRows: number;
  cellCodeMatrix: number[][];
  cellCodeLegend: {
    0: 'weft_over';
    1: 'warp_over';
  };
}

export interface FocusedDrawdownCell {
  pickIndex: number;
  endIndex: number;
  pinned?: boolean;
}

export interface DraftCounts {
  shaftCount: number;
  treadleCount: number;
  warpEnds: number;
  picks: number;
}

export type WeaveType =
  | 'plain'
  | 'twill'
  | 'satin'
  | 'basket'
  | 'rib'
  | 'compound'
  | 'lace'
  | 'double'
  | 'huck'
  | 'other';

export interface PresetDefinition {
  id: string;
  label: string;
  summary: string;
  document: DraftDocument;
  weaveType?: WeaveType;
  previewImage?: string;
}

export interface BookPatternEntry {
  id: string;
  title: string;
  summary: string;
  referenceCode?: string;
  referencePage?: string;
  tags: string[];
  presetId?: string;
  draft?: DraftDocument;
  status: 'loadable' | 'pending';
  note?: string;
  weaveType?: WeaveType;
  previewImage?: string;
}

export interface PatternBook {
  id: string;
  title: string;
  summary: string;
  author?: string;
  year?: string;
  draftCount?: number;
  sourceLabel: string;
  referenceUrl?: string;
  access: 'builtin' | 'catalog' | 'public-domain' | 'local';
  tags: string[];
  note?: string;
  patterns: BookPatternEntry[];
}

export interface ImportResult {
  draft: DraftDocument;
  mode: 'service' | 'local';
}

export interface BlenderRenderJob {
  id: string;
  status: BlenderRenderStatus;
  message: string;
  draftTitle: string;
  targetObjectName: string;
  draftObjectName: string;
  createdAt: string;
  startedAt?: string | null;
  finishedAt?: string | null;
  imageUrl?: string | null;
  tileSourceImageUrls?: string[];
  logTail: string[];
}

export interface TryonTarget {
  id: string;
  label: string;
  description: string;
}

export interface TryonRenderJobRef {
  targetId: string;
  label: string;
  jobId: string;
  status: BlenderRenderStatus;
}

export interface TryonRenderBatch {
  batchId: string;
  jobs: TryonRenderJobRef[];
}

export interface TileRenderOptions {
  tileCount: 4;
  tileResolution: number;
  guardThreads: number;
  variationStrength: number;
}

export interface YarnAsset {
  id: string;
  label: string;
  status: YarnAssetStatus;
  sourceUrl: string;
  diffuseUrl?: string | null;
  alphaUrl?: string | null;
  preprocessedUrl?: string | null;
  preprocessMeta?: Record<string, unknown>;
  alphaMeta?: Record<string, unknown>;
  error?: string | null;
  createdAt?: string | null;
  updatedAt?: string | null;
}

export interface ColorBinding {
  scope: 'warp' | 'weft';
  colorHex: string;
  yarnAssetId: string | null;
}

export interface ColorBindingSlot {
  key: string;
  scope: 'warp' | 'weft';
  colorHex: string;
  label: string;
}

export interface FabricProject {
  version: 1;
  draft: DraftDocument;
  yarnAssets: YarnAsset[];
  colorBindings: ColorBinding[];
}

export interface HookMaterialBinding {
  materialSlot: number;
  yarnAssetId: string | null;
}

export interface HookProject {
  version: 1;
  pattern: HookPatternDocument;
  yarnAssets: YarnAsset[];
  materialBindings: HookMaterialBinding[];
}

export interface HookBuildSpec {
  version: 1;
  buildMode: string;
  interpreter: string;
  productionObject?: string;
  draftObject?: string;
  visualReference?: {
    role: 'calibration_reference_only' | string;
    name?: string;
    expectedObjectName?: string;
    baselineSettings?: Partial<HookRenderSettings>;
  };
  frontendIntent?: {
    structureType?: 'hook';
    structureFamily?: HookStructureFamily;
    rowDirection?: HookRowDirection;
    repeat?: HookRepeatUnit | null;
    title?: string;
    source?: HookPatternSource;
    gauge?: HookGaugeSettings | null;
  };
  grid?: {
    rows: number;
    columns: number;
    totalCells: number;
    activeCells: number;
    emptyCells: number;
    visibleRows: number;
    visibleColumns: number;
  };
  stitches?: {
    counts: Record<string, number>;
    supportedCodes: number[];
    unsupportedCodes: number[];
    fallbackCodes: Record<string, number>;
    v1RenderedCodes: number[];
    v1GeometryArchetype: string;
  };
  continuity?: {
    chainModel: string;
    uIndexAttribute: string;
    chainIdAttribute: string;
    courseIdAttribute: string;
    waleIdAttribute: string;
    sparseCellsDoNotResetU: boolean;
    chains: Array<{
      id: number;
      materialSlot: number;
      direction: string;
      activeCells: number;
      uIndexRange: [number, number];
    }>;
  };
  materials?: {
    slotBase: number;
    maxSlots: number;
    usedSlots: number[];
    attribute: string;
    generatedMaterialIdAttribute: string;
  };
  renderSettings?: HookRenderSettings;
  attributes?: {
    faceAttributeCount: number;
    names: string[];
  };
}

export interface HookBlenderSyncPayload {
  status: string;
  target: string;
  draftObject: string;
  buildSpec?: HookBuildSpec;
  rows?: number;
  columns?: number;
  activeCells?: number;
  materialSlots?: number[];
  stitchCounts?: Record<string, number>;
  geometry?: {
    vertices: number;
    faces: number;
    components: number;
    construction: string;
  };
  [key: string]: unknown;
}

export interface HookBlenderSyncResponse {
  status?: string;
  result?: {
    executed?: boolean;
    result?: string | HookBlenderSyncPayload;
  };
  buildSpec?: HookBuildSpec;
  [key: string]: unknown;
}
