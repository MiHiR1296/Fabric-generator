import { normalizeDraft, parseLooseTextDraft } from '../domain/draft';
import type {
  BlenderRenderJob,
  FabricProject,
  DraftDocument,
  ImportResult,
  ParserStatus,
  TileRenderOptions,
  YarnAsset,
} from '../domain/types';

async function parseJson(response: Response) {
  const text = await response.text();
  let data: any = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      if (!response.ok) {
        throw new Error(
          `Request failed (${response.status} ${response.statusText}). ${text.slice(0, 200)}`,
        );
      }
      throw new Error('Server returned an unexpected non-JSON response.');
    }
  }
  if (!response.ok) {
    const detail = data && (data.detail || data.error);
    throw new Error(
      detail || `Request failed (${response.status} ${response.statusText || 'no body'}).`,
    );
  }
  return data;
}

export async function checkParserStatus(): Promise<ParserStatus> {
  try {
    const response = await fetch('/api/parser/health');
    if (!response.ok) {
      return 'offline';
    }
    return 'online';
  } catch {
    return 'offline';
  }
}

export async function parseFileInput(file: File): Promise<ImportResult> {
  try {
    const formData = new FormData();
    formData.append('file', file);

    const response = await fetch('/api/parser/parse-file', {
      method: 'POST',
      body: formData,
    });
    const payload = await parseJson(response);
    return {
      draft: normalizeDraft(payload),
      mode: 'service',
    };
  } catch (error) {
    const lower = file.name.toLowerCase();
    const text = await file.text();

    if (lower.endsWith('.json') || text.trim().startsWith('{')) {
      return {
        draft: normalizeDraft(JSON.parse(text)),
        mode: 'local',
      };
    }

    if (lower.endsWith('.txt') || lower.endsWith('.draft')) {
      return {
        draft: parseLooseTextDraft(text),
        mode: 'local',
      };
    }

    throw error instanceof Error
      ? error
      : new Error('Unable to import that file.');
  }
}

export async function parsePastedText(text: string): Promise<ImportResult> {
  try {
    const response = await fetch('/api/parser/parse-text', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ text }),
    });
    const payload = await parseJson(response);
    return {
      draft: normalizeDraft(payload),
      mode: 'service',
    };
  } catch {
    return {
      draft: parseLooseTextDraft(text),
      mode: 'local',
    };
  }
}

export async function syncDraftToBlender(
  draft: DraftDocument,
  options?: {
    targetObjectName?: string;
    draftObjectName?: string;
  },
) {
  const response = await fetch('/api/blender/sync-draft', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      draft,
      target_object_name: options?.targetObjectName || 'ParametricWeave',
      draft_object_name: options?.draftObjectName || 'WebDraft_Live',
    }),
  });
  return parseJson(response);
}

export async function requestDraftRender(
  draft: DraftDocument,
  options?: {
    targetObjectName?: string;
    draftObjectName?: string;
  },
): Promise<BlenderRenderJob> {
  const response = await fetch('/api/blender/render-draft', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      draft,
      target_object_name: options?.targetObjectName || 'ParametricWeave',
      draft_object_name: options?.draftObjectName || 'WebDraft_Live',
    }),
  });
  return parseJson(response);
}

export async function requestProjectRender(
  project: FabricProject,
  options?: {
    targetObjectName?: string;
    draftObjectName?: string;
  },
): Promise<BlenderRenderJob> {
  const response = await fetch('/api/blender/render-project', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      draft: project.draft,
      yarnAssets: project.yarnAssets,
      colorBindings: project.colorBindings,
      target_object_name: options?.targetObjectName || 'ParametricWeave',
      draft_object_name: options?.draftObjectName || 'WebDraft_Live',
    }),
  });
  return parseJson(response);
}

export async function requestProjectTileRender(
  project: FabricProject,
  tileOptions: TileRenderOptions,
  options?: {
    targetObjectName?: string;
    draftObjectName?: string;
  },
): Promise<BlenderRenderJob> {
  const response = await fetch('/api/blender/render-project-tiles', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      draft: project.draft,
      yarnAssets: project.yarnAssets,
      colorBindings: project.colorBindings,
      tileCount: tileOptions.tileCount,
      tileResolution: tileOptions.tileResolution,
      guardThreads: tileOptions.guardThreads,
      variationStrength: tileOptions.variationStrength,
      target_object_name: options?.targetObjectName || 'ParametricWeave',
      draft_object_name: options?.draftObjectName || 'WebDraft_Live',
    }),
  });
  return parseJson(response);
}

export async function fetchDraftRenderJob(jobId: string): Promise<BlenderRenderJob> {
  const response = await fetch(`/api/blender/render-jobs/${jobId}`);
  return parseJson(response);
}

// Push the current project setup to the LIVE Blender on MCP 9876. This includes
// bandMeta (per-yarn Arc 1/Arc 2 V Min/Max + Image Width Px) and render-setting
// context, so the setup-owned per-material Texture Scale U multiplier can be
// recalculated when zoom/spacing changes. Slot ordering matches render-project.
// Fire-and-forget from the UI: caller should not gate interaction on the response.
export async function pushProjectBandmeta(
  draft: DraftDocument,
  colorBindings: any[],
  options?: { targetObjectName?: string; modifierName?: string },
): Promise<any> {
  const response = await fetch('/api/blender/push-project-bandmeta', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      draft,
      colorBindings,
      target_object_name: options?.targetObjectName || 'ParametricWeave',
      modifier_name: options?.modifierName || 'Weave',
    }),
  });
  return parseJson(response);
}

export async function listYarnAssets(): Promise<YarnAsset[]> {
  const response = await fetch('/api/yarn/assets');
  return parseJson(response);
}

// Yarn library — entries written by yarnseamless to the shared yarn_library/.
// These are fully processed; import == copy + split RGBA + populate bandMeta.

export interface LibraryYarnEntry {
  id: string;
  label: string | null;
  createdAt: string | null;
  thumbnail: string | null;
  thumbnailUrl: string | null;
  widthPx?: number | null;
  widthMm?: number | null;
  lengthPx?: number | null;
  lengthMm?: number | null;
  dpi?: number | null;
}

export async function listYarnLibrary(): Promise<LibraryYarnEntry[]> {
  const response = await fetch('/api/yarn/library');
  const data = await parseJson(response);
  return Array.isArray(data?.yarns) ? data.yarns : [];
}

export async function importYarnFromLibrary(yarnId: string): Promise<YarnAsset> {
  const response = await fetch(`/api/yarn/library/${encodeURIComponent(yarnId)}/import`, {
    method: 'POST',
  });
  return parseJson(response);
}

export async function deleteLibraryYarn(
  yarnId: string,
): Promise<{ id: string; removed: boolean; removedAssetIds: string[] }> {
  const response = await fetch(`/api/yarn/library/${encodeURIComponent(yarnId)}`, {
    method: 'DELETE',
  });
  const payload = await parseJson(response);
  return {
    id: payload?.id ?? yarnId,
    removed: Boolean(payload?.removed),
    removedAssetIds: Array.isArray(payload?.removedAssetIds) ? payload.removedAssetIds : [],
  };
}

export type YarnOrientation = 'auto' | 'horizontal' | 'vertical';

export async function uploadYarnAssets(
  files: File[],
  orientation: YarnOrientation = 'auto',
): Promise<YarnAsset[]> {
  const formData = new FormData();
  files.forEach((file) => formData.append('files', file));
  formData.append('orientation', orientation);
  const response = await fetch('/api/yarn/assets', {
    method: 'POST',
    body: formData,
  });
  return parseJson(response);
}

export async function retryYarnAsset(
  assetId: string,
  orientation: YarnOrientation = 'auto',
): Promise<YarnAsset> {
  const formData = new FormData();
  formData.append('orientation', orientation);
  const response = await fetch(`/api/yarn/assets/${assetId}/retry`, {
    method: 'POST',
    body: formData,
  });
  return parseJson(response);
}

export async function deleteYarnAsset(assetId: string) {
  const response = await fetch(`/api/yarn/assets/${assetId}`, {
    method: 'DELETE',
  });
  return parseJson(response);
}

export function describeImportSource(draft: DraftDocument, mode: ImportResult['mode']) {
  const sourceLabel = draft.sourceLabel || 'Imported draft';
  if (mode === 'service') {
    return `${sourceLabel} via parser service`;
  }
  return `${sourceLabel} via local fallback`;
}
