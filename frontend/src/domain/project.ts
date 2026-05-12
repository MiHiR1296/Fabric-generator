import type { ColorBinding, ColorBindingSlot, DraftDocument, FabricProject, YarnAsset } from './types';
import { buildPreviewRenderSettings } from './draft.ts';

export function normalizeHexColor(value: string) {
  const raw = value.trim().toLowerCase();
  if (!raw) {
    return '#000000';
  }
  const withHash = raw.startsWith('#') ? raw : `#${raw}`;
  if (withHash.length === 4) {
    return `#${withHash[1]}${withHash[1]}${withHash[2]}${withHash[2]}${withHash[3]}${withHash[3]}`;
  }
  return withHash;
}

export function deriveColorBindingSlots(draft: DraftDocument): ColorBindingSlot[] {
  const slots: ColorBindingSlot[] = [];
  const appendSlots = (scope: 'warp' | 'weft', colors: string[]) => {
    const seen = new Set<string>();
    colors.forEach((value) => {
      const colorHex = normalizeHexColor(value);
      const key = `${scope}:${colorHex}`;
      if (seen.has(key)) {
        return;
      }
      seen.add(key);
      slots.push({
        key,
        scope,
        colorHex,
        label: `${scope === 'warp' ? 'Warp' : 'Weft'} ${colorHex.toUpperCase()}`,
      });
    });
  };

  appendSlots('warp', draft.warpColors);
  appendSlots('weft', draft.weftColors);
  return slots;
}

export function syncColorBindings(
  slots: ColorBindingSlot[],
  existing: ColorBinding[],
): ColorBinding[] {
  const lookup = new Map(existing.map((binding) => [`${binding.scope}:${normalizeHexColor(binding.colorHex)}`, binding]));
  return slots.map((slot) => {
    const current = lookup.get(slot.key);
    return {
      scope: slot.scope,
      colorHex: slot.colorHex,
      yarnAssetId: current?.yarnAssetId || null,
    };
  });
}

export function missingColorBindings(
  slots: ColorBindingSlot[],
  bindings: ColorBinding[],
) {
  const lookup = new Map(bindings.map((binding) => [`${binding.scope}:${normalizeHexColor(binding.colorHex)}`, binding]));
  return slots.filter((slot) => {
    const binding = lookup.get(slot.key);
    return !binding?.yarnAssetId;
  });
}

export function buildFabricProject(
  draft: DraftDocument,
  yarnAssets: YarnAsset[],
  colorBindings: ColorBinding[],
): FabricProject {
  const previewDraft: DraftDocument = {
    ...draft,
    renderSettings: buildPreviewRenderSettings(draft),
  };

  return {
    version: 1,
    draft: previewDraft,
    yarnAssets,
    colorBindings,
  };
}
