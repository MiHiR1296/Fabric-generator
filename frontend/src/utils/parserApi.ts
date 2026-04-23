import { normalizeDraft, parseLooseTextDraft } from '../domain/draft';
import type {
  BlenderLivePreview,
  BlenderRenderJob,
  FabricProject,
  DraftDocument,
  ImportResult,
  ParserStatus,
  YarnAsset,
} from '../domain/types';

async function parseJson(response: Response) {
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.detail || data.error || 'Parser request failed.');
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

export async function requestLivePreview(
  project: FabricProject,
  options?: {
    targetObjectName?: string;
    draftObjectName?: string;
    sessionId?: string;
    maxSize?: number;
  },
): Promise<BlenderLivePreview> {
  const response = await fetch('/api/blender/live-preview', {
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
      session_id: options?.sessionId || 'default',
      max_size: options?.maxSize || 1400,
    }),
  });
  return parseJson(response);
}

export async function fetchDraftRenderJob(jobId: string): Promise<BlenderRenderJob> {
  const response = await fetch(`/api/blender/render-jobs/${jobId}`);
  return parseJson(response);
}

export async function listYarnAssets(): Promise<YarnAsset[]> {
  const response = await fetch('/api/yarn/assets');
  return parseJson(response);
}

export async function uploadYarnAssets(files: File[]): Promise<YarnAsset[]> {
  const formData = new FormData();
  files.forEach((file) => formData.append('files', file));
  const response = await fetch('/api/yarn/assets', {
    method: 'POST',
    body: formData,
  });
  return parseJson(response);
}

export async function retryYarnAsset(assetId: string): Promise<YarnAsset> {
  const response = await fetch(`/api/yarn/assets/${assetId}/retry`, {
    method: 'POST',
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
