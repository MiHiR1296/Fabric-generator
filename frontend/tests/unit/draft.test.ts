import test from 'node:test';
import assert from 'node:assert/strict';

import {
  applyColorSequenceEdit,
  applyStructuredPatternEdit,
  buildBlenderHandoff,
  computeDrawdown,
  createBlankDraft,
  getThreadingIndexFromDrawdownColumn,
  normalizeDraft,
  parseLooseTextDraft,
} from '../../src/domain/draft.ts';
import { parsePatternBookJson } from '../../src/domain/bookLibrary.ts';

test('computes a 4-shaft drawdown', () => {
  const drawdown = computeDrawdown(
    [1, 2, 3, 4],
    [
      [true, false, false, true],
      [true, true, false, false],
      [false, true, true, false],
      [false, false, true, true],
    ],
    [1, 2, 3, 4],
  );

  assert.deepEqual(drawdown, [
    [0, 0, 1, 1],
    [0, 1, 1, 0],
    [1, 1, 0, 0],
    [1, 0, 0, 1],
  ]);
});

test('computes an 8-shaft drawdown', () => {
  const threading = [1, 2, 3, 4, 5, 6, 7, 8];
  const tieUp = Array.from({ length: 8 }, (_, row) =>
    Array.from({ length: 8 }, (_, col) => row === col || row === (col + 1) % 8),
  );
  const treadling = [1, 2, 3, 4, 5, 6, 7, 8];
  const drawdown = computeDrawdown(threading, tieUp, treadling);

  assert.equal(drawdown.length, 8);
  assert.equal(drawdown[0][0], 0);
  assert.equal(drawdown[0][6], 1);
  assert.equal(drawdown[0][7], 1);
  assert.equal(drawdown[7][7], 1);
});

test('computes a 16-shaft drawdown', () => {
  const threading = Array.from({ length: 16 }, (_, index) => index + 1);
  const tieUp = Array.from({ length: 16 }, (_, row) =>
    Array.from({ length: 16 }, (_, col) => row === col),
  );
  const treadling = Array.from({ length: 16 }, (_, index) => index + 1);
  const drawdown = computeDrawdown(threading, tieUp, treadling);

  assert.equal(drawdown.length, 16);
  assert.equal(drawdown[5][10], 1);
  assert.equal(drawdown[5][9], 0);
});

test('builds a Blender handoff from the canonical draft', () => {
  const draft = normalizeDraft({
    version: 1,
    sourceType: 'json',
    shaftCount: 4,
    treadleCount: 4,
    threading: [1, 2, 3, 4],
    tieUp: [
      [true, false, false, true],
      [true, true, false, false],
      [false, true, true, false],
      [false, false, true, true],
    ],
    treadling: [1, 2, 3, 4],
    warpColors: ['#fff'],
    weftColors: ['#000'],
    parseConfidence: 1,
    warnings: [],
  });

  const handoff = buildBlenderHandoff(draft);
  assert.deepEqual(handoff.cellCodeLegend, { 0: 'weft_over', 1: 'warp_over' });
  assert.equal(handoff.repeatCols, 4);
  assert.equal(handoff.repeatRows, 4);
  assert.equal(handoff.cellCodeMatrix[0][0], 0);
  assert.equal(handoff.cellCodeMatrix[0][3], 1);
});

test('parses loose labeled text into a canonical draft', () => {
  const draft = parseLooseTextDraft(`
    shafts: 4
    treadles: 4
    threading: 1 2 3 4 1 2 3 4
    tieup:
    1 0 0 1
    1 1 0 0
    0 1 1 0
    0 0 1 1
    treadling: 1 2 3 4
  `);

  assert.equal(draft.sourceType, 'text');
  assert.equal(draft.threading.length, 8);
  assert.equal(draft.drawdown[0][0], 0);
  assert.equal(draft.drawdown[0][7], 1);
});

test('creates a blank draft with expected defaults', () => {
  const draft = createBlankDraft();
  assert.equal(draft.shaftCount, 4);
  assert.equal(draft.treadleCount, 4);
  assert.equal(draft.threading.length, 24);
  assert.equal(draft.treadling.length, 24);
});

test('applies structured pattern text edits without fighting counts', () => {
  const updated = applyStructuredPatternEdit(createBlankDraft(), {
    threadingText: '1 2 3 4 1 2',
    tieUpText: '0 0 1 1\n0 1 1 0\n1 1 0 0\n1 0 0 1',
    treadlingText: '1 2 3 4 1 2',
  });

  assert.equal(updated.threading.length, 6);
  assert.equal(updated.treadling.length, 6);
  assert.equal(updated.tieUp[0][0], true);
  assert.equal(updated.drawdown[0][0], 1);
  assert.equal(updated.drawdown[0][2], 0);
});

test('maps drawdown columns back to threading indices', () => {
  assert.equal(getThreadingIndexFromDrawdownColumn(8, 0), 7);
  assert.equal(getThreadingIndexFromDrawdownColumn(8, 7), 0);
});

test('applies warp and weft color edits as repeat sequences', () => {
  const updated = applyColorSequenceEdit(createBlankDraft({ warpEnds: 6, picks: 5 }), {
    warpColorsText: '#111111 #222222',
    weftColorsText: '#aaaaaa #bbbbbb #cccccc',
  });

  assert.deepEqual(updated.warpColors, [
    '#111111',
    '#222222',
    '#111111',
    '#222222',
    '#111111',
    '#222222',
  ]);
  assert.deepEqual(updated.weftColors, [
    '#aaaaaa',
    '#bbbbbb',
    '#cccccc',
    '#aaaaaa',
    '#bbbbbb',
  ]);
});

test('parses a local pattern-book json into loadable patterns', () => {
  const book = parsePatternBookJson(JSON.stringify({
    type: 'pattern-book',
    title: 'Local Oelsner Index',
    author: 'User Library',
    patterns: [
      {
        id: 'sample-1',
        title: 'Sample Pattern',
        summary: 'Imported sample draft',
        tags: ['imported', 'oelsner'],
        draft: {
          version: 1,
          sourceType: 'json',
          shaftCount: 4,
          treadleCount: 4,
          threading: [1, 2, 3, 4],
          tieUp: [
            [true, false, false, true],
            [true, true, false, false],
            [false, true, true, false],
            [false, false, true, true],
          ],
          treadling: [1, 2, 3, 4],
          warpColors: ['#fff'],
          weftColors: ['#000'],
          parseConfidence: 1,
          warnings: [],
        },
      },
    ],
  }));

  assert.equal(book.access, 'local');
  assert.equal(book.patterns.length, 1);
  assert.equal(book.patterns[0].status, 'loadable');
  assert.equal(book.patterns[0].draft?.drawdown[0][3], 1);
});
