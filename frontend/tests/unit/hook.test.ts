import test from 'node:test';
import assert from 'node:assert/strict';

import {
  buildHookMaterialBindings,
  buildHookProject,
  buildStandardHookPreset,
  builtinHookPatternBooks,
  hookPresetDefinitions,
  hookPresets,
  missingHookMaterialBindings,
  normalizeHookPattern,
  parseHookPatternBookJson,
  syncHookMaterialBindings,
} from '../../src/domain/hook.ts';

test('builds the default 15x21 hook preset', () => {
  const preset = buildStandardHookPreset();

  assert.equal(preset.structureType, 'hook');
  assert.equal(preset.structureFamily, 'crochet_hook');
  assert.equal(preset.rows, 15);
  assert.equal(preset.columns, 21);
  assert.equal(preset.stitchCodes[0][0], 1);
  assert.equal(preset.chainIds[3][7], 7);
  assert.equal(preset.chains.length, 21);
});

test('ships hook workflow catalog shelves', () => {
  assert.equal(hookPresetDefinitions.length >= 8, true);
  assert.equal(builtinHookPatternBooks.length >= 4, true);
  assert.equal(builtinHookPatternBooks[0].patterns[0].status, 'loadable');
  assert.equal(hookPresetDefinitions[0].document.structureType, 'hook');
  assert.equal(hookPresets.length, hookPresetDefinitions.length);
});

test('normalizes sparse cells, reserved stitch codes, and material slots', () => {
  const pattern = normalizeHookPattern({
    rows: 2,
    columns: 2,
    stitchCodes: [[1, 0], [6, 11]],
    chainIds: [[10, 10], [10, 11]],
    chains: [
      { id: 10, materialSlot: 2, direction: 'vertical' },
      { id: 11, materialSlot: 99, direction: 'vertical' },
    ],
  });

  assert.deepEqual(pattern.stitchCodes, [[1, 0], [6, 11]]);
  assert.equal(pattern.chains.find((chain) => chain.id === 11)?.materialSlot, 15);
  assert.equal(pattern.stitchLegend?.find((entry) => entry.code === 6)?.archetype, 'knit_v');
});

test('expands tiled hook repeat matrices', () => {
  const pattern = normalizeHookPattern({
    rows: 3,
    columns: 5,
    repeat: { mode: 'tile', rows: 2, columns: 2 },
    stitchCodes: [[1, 0], [6, 7]],
  });

  assert.deepEqual(pattern.stitchCodes, [
    [1, 0, 1, 0, 1],
    [6, 7, 6, 7, 6],
    [1, 0, 1, 0, 1],
  ]);
});

test('parses imported hook pattern books with source metadata', () => {
  const book = parseHookPatternBookJson(JSON.stringify({
    type: 'hook-pattern-book',
    title: 'Local Crochet Tests',
    access: 'local',
    patterns: [
      {
        id: 'local-open',
        title: 'Local Open Mesh',
        summary: 'A local repeat chart.',
        pattern: {
          rows: 2,
          columns: 3,
          repeat: { mode: 'tile', rows: 1, columns: 3 },
          stitchCodes: [[1, 0, 1]],
          source: {
            kind: 'user-authored',
            access: 'local',
            title: 'Local Open Mesh',
          },
        },
      },
    ],
  }));

  assert.equal(book.title, 'Local Crochet Tests');
  assert.equal(book.patterns[0].pattern?.source?.kind, 'user-authored');
  assert.deepEqual(book.patterns[0].pattern?.stitchCodes[1], [1, 0, 1]);
});

test('builds material bindings and hook projects', () => {
  const preset = hookPresets[0];
  const bindings = buildHookMaterialBindings(preset);
  const project = buildHookProject(preset, [], bindings);

  assert.deepEqual(bindings, [{ materialSlot: 0, yarnAssetId: null }]);
  assert.equal(project.version, 1);
  assert.equal(project.pattern.structureType, 'hook');
});

test('syncs hook material bindings to active preset slots', () => {
  const preset = hookPresetDefinitions.find((entry) => entry.id === 'hook-two-yarn-stripe-15x21')!.document;
  const bindings = syncHookMaterialBindings(preset, [{ materialSlot: 0, yarnAssetId: 'yarn-a' }], 'yarn-default');

  assert.deepEqual(bindings, [
    { materialSlot: 0, yarnAssetId: 'yarn-a' },
    { materialSlot: 1, yarnAssetId: 'yarn-default' },
  ]);
  assert.deepEqual(missingHookMaterialBindings(preset, bindings), []);
  assert.deepEqual(missingHookMaterialBindings(preset, [{ materialSlot: 0, yarnAssetId: 'yarn-a' }]), [1]);
});
