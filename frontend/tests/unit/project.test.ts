import test from 'node:test';
import assert from 'node:assert/strict';

import { createBlankDraft, normalizeDraft } from '../../src/domain/draft.ts';
import {
  buildFabricProject,
  deriveColorBindingSlots,
  missingColorBindings,
  syncColorBindings,
} from '../../src/domain/project.ts';

test('derives unique warp and weft color binding slots separately', () => {
  const draft = normalizeDraft({
    ...createBlankDraft({ warpEnds: 4, picks: 4 }),
    warpColors: ['#fff', '#ffffff', '#112233', '#112233'],
    weftColors: ['#fff', '#445566', '#445566', '#fff'],
  });

  const slots = deriveColorBindingSlots(draft);

  assert.deepEqual(
    slots.map((slot) => slot.key),
    ['warp:#ffffff', 'warp:#112233', 'weft:#ffffff', 'weft:#445566'],
  );
});

test('syncs color bindings and preserves matching assignments only', () => {
  const draft = normalizeDraft({
    ...createBlankDraft({ warpEnds: 3, picks: 3 }),
    warpColors: ['#abcdef', '#abcdef', '#123456'],
    weftColors: ['#654321', '#654321', '#abcdef'],
  });

  const synced = syncColorBindings(deriveColorBindingSlots(draft), [
    { scope: 'warp', colorHex: '#ABCDEF', yarnAssetId: 'warp-main' },
    { scope: 'weft', colorHex: '#654321', yarnAssetId: 'weft-main' },
    { scope: 'warp', colorHex: '#000000', yarnAssetId: 'stale-binding' },
  ]);

  assert.deepEqual(synced, [
    { scope: 'warp', colorHex: '#abcdef', yarnAssetId: 'warp-main' },
    { scope: 'warp', colorHex: '#123456', yarnAssetId: null },
    { scope: 'weft', colorHex: '#654321', yarnAssetId: 'weft-main' },
    { scope: 'weft', colorHex: '#abcdef', yarnAssetId: null },
  ]);
});

test('reports missing bindings and builds a project snapshot', () => {
  const draft = createBlankDraft({ warpEnds: 2, picks: 2 });
  const slots = deriveColorBindingSlots(draft);
  const bindings = syncColorBindings(slots, [
    { scope: 'warp', colorHex: slots[0].colorHex, yarnAssetId: 'asset-1' },
  ]);

  const missing = missingColorBindings(slots, bindings);
  const project = buildFabricProject(draft, [{ id: 'asset-1', label: 'Cotton', status: 'ready', sourceUrl: '/asset.png' }], bindings);

  assert.equal(missing.length, 1);
  assert.equal(project.version, 1);
  assert.equal(project.colorBindings.length, 2);
  assert.equal(project.yarnAssets[0]?.label, 'Cotton');
});
