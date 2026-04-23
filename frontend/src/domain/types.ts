export type SourceType = 'manual' | 'wif' | 'json' | 'text' | 'image';
export type DraftSection = 'threading' | 'tieUp' | 'treadling' | 'drawdown';
export type ParserStatus = 'checking' | 'online' | 'offline';
export type BlenderRenderStatus = 'queued' | 'running' | 'succeeded' | 'failed';
export type YarnAssetStatus = 'queued' | 'processing' | 'ready' | 'failed';

export interface DraftRenderSettings {
  warpThreads: number;
  weftThreads: number;
  spacing: number;
  amplitude: number;
  threadRadius: number;
  threadSubdivisions: number;
  plyCount: number;
  plyRadius: number;
  twistAmount: number;
  plyResolution: number;
  textureScaleU: number;
  textureScaleV: number;
  textureOffsetV: number;
  textureSideFlatten: number;
  lumpStrength: number;
  lumpScale: number;
  fiberDensity: number;
  fiberLength: number;
  fiberThickness: number;
  fiberFrizz: number;
  fiberSubdivs: number;
  seed: number;
  fillRatio: number;
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

export interface PresetDefinition {
  id: string;
  label: string;
  summary: string;
  document: DraftDocument;
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
  logTail: string[];
}

export interface BlenderLivePreview {
  sessionId: string;
  status: 'idle' | 'ready';
  message: string;
  targetObjectName: string;
  draftObjectName: string;
  updatedAt?: string | null;
  imageUrl?: string | null;
  width?: number | null;
  height?: number | null;
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
