import { normalizeDraft } from './draft.ts';
import type { PresetDefinition } from './types.ts';

function repeatColor(color: string, count: number) {
  return Array.from({ length: count }, () => color);
}

function plainThreading(length: number) {
  return Array.from({ length }, (_, index) => (index % 4) + 1);
}

function plainTreadling(length: number) {
  return Array.from({ length }, (_, index) => (index % 2) + 1);
}

const plainTieUp = [
  [true, false, true, false],
  [false, true, false, true],
  [true, false, true, false],
  [false, true, false, true],
];

const chequesStripeRepeat = [
  ...repeatColor('#202625', 10),
  ...repeatColor('#4f5756', 7),
  ...repeatColor('#9da7a4', 3),
  ...repeatColor('#d9dedb', 2),
  ...repeatColor('#151918', 1),
  ...repeatColor('#d9dedb', 2),
  ...repeatColor('#7a8380', 2),
  ...repeatColor('#d9dedb', 4),
  ...repeatColor('#151918', 1),
  ...repeatColor('#d9dedb', 3),
  ...repeatColor('#aeb7b4', 4),
  ...repeatColor('#d9dedb', 14),
  ...repeatColor('#151918', 1),
  ...repeatColor('#d9dedb', 3),
  ...repeatColor('#aeb7b4', 2),
  ...repeatColor('#4f5756', 8),
  ...repeatColor('#202625', 11),
  ...repeatColor('#4f5756', 8),
  ...repeatColor('#9da7a4', 4),
  ...repeatColor('#d9dedb', 3),
  ...repeatColor('#151918', 1),
  ...repeatColor('#d9dedb', 2),
];

export const presets: PresetDefinition[] = [
  {
    id: 'testingv1-cheques',
    label: 'Testing V1 Cheques',
    summary: 'Plain-weave plaid reconstructed from the testingv1_cheques fabric scan, with broad dark/white checks and narrow pinstripes.',
    weaveType: 'plain',
    document: normalizeDraft({
      version: 1,
      sourceType: 'image',
      shaftCount: 4,
      treadleCount: 4,
      threading: plainThreading(chequesStripeRepeat.length),
      tieUp: plainTieUp,
      treadling: plainTreadling(chequesStripeRepeat.length),
      warpColors: chequesStripeRepeat,
      weftColors: chequesStripeRepeat,
      parseConfidence: 0.86,
      warnings: [
        'Reconstructed from fabric_scan20260527_13591460.png as a colour-order plaid on plain weave.',
      ],
      title: 'Testing V1 Cheques',
      sourceLabel: 'thread_epson_scans/testingv1_cheques',
    }),
  },
  {
    id: 'plain',
    label: 'Plain Weave',
    summary: 'Balanced over-under repeat with a stable checker drawdown.',
    weaveType: 'plain',
    document: normalizeDraft({
      version: 1,
      sourceType: 'manual',
      shaftCount: 4,
      treadleCount: 4,
      threading: [1, 2, 3, 4, 1, 2, 3, 4],
      tieUp: [
        [true, false, true, false],
        [false, true, false, true],
        [true, false, true, false],
        [false, true, false, true],
      ],
      treadling: [1, 2, 1, 2, 1, 2, 1, 2],
      warpColors: ['#f1ead9'],
      weftColors: ['#af5f3f'],
      parseConfidence: 1,
      warnings: [],
      title: 'Plain Weave',
      sourceLabel: 'Preset',
    }),
  },
  {
    id: 'basket',
    label: 'Basket Weave',
    summary: 'Grouped ends and picks create paired over-under blocks.',
    weaveType: 'basket',
    document: normalizeDraft({
      version: 1,
      sourceType: 'manual',
      shaftCount: 4,
      treadleCount: 4,
      threading: [1, 1, 2, 2, 3, 3, 4, 4],
      tieUp: [
        [true, false, false, false],
        [true, false, false, false],
        [false, true, false, false],
        [false, true, false, false],
      ],
      treadling: [1, 1, 2, 2, 1, 1, 2, 2],
      warpColors: ['#e8dbc2'],
      weftColors: ['#8d4c33'],
      parseConfidence: 1,
      warnings: [],
      title: 'Basket Weave',
      sourceLabel: 'Preset',
    }),
  },
  {
    id: 'twill',
    label: '2/2 Twill',
    summary: 'Classic diagonal twill progression across four shafts.',
    weaveType: 'twill',
    document: normalizeDraft({
      version: 1,
      sourceType: 'manual',
      shaftCount: 4,
      treadleCount: 4,
      threading: [1, 2, 3, 4, 1, 2, 3, 4],
      tieUp: [
        [true, false, false, true],
        [true, true, false, false],
        [false, true, true, false],
        [false, false, true, true],
      ],
      treadling: [1, 2, 3, 4, 1, 2, 3, 4],
      warpColors: ['#f6ebda'],
      weftColors: ['#c46538'],
      parseConfidence: 1,
      warnings: [],
      title: '2/2 Twill',
      sourceLabel: 'Preset',
    }),
  },
  {
    id: 'satin',
    label: '5-End Satin',
    summary: 'Longer floats with a smoother, more lustrous surface pattern.',
    weaveType: 'satin',
    document: normalizeDraft({
      version: 1,
      sourceType: 'manual',
      shaftCount: 5,
      treadleCount: 5,
      threading: [1, 2, 3, 4, 5, 1, 2, 3, 4, 5],
      tieUp: [
        [true, false, false, false, false],
        [false, false, true, false, false],
        [false, false, false, false, true],
        [false, true, false, false, false],
        [false, false, false, true, false],
      ],
      treadling: [1, 2, 3, 4, 5, 1, 2, 3, 4, 5],
      warpColors: ['#f5eee1'],
      weftColors: ['#b75a2c'],
      parseConfidence: 1,
      warnings: [],
      title: '5-End Satin',
      sourceLabel: 'Preset',
    }),
  },
  {
    id: 'warp-rib',
    label: 'Warp Rib',
    summary: 'Dense warp grouping with restrained treadling for bold ribs.',
    weaveType: 'rib',
    document: normalizeDraft({
      version: 1,
      sourceType: 'manual',
      shaftCount: 4,
      treadleCount: 4,
      threading: [1, 1, 2, 2, 3, 3, 4, 4],
      tieUp: [
        [true, false, false, false],
        [false, false, true, false],
        [false, true, false, false],
        [false, false, false, true],
      ],
      treadling: [1, 1, 1, 2, 2, 2, 3, 3],
      warpColors: ['#efe7d7'],
      weftColors: ['#975737'],
      parseConfidence: 1,
      warnings: [],
      title: 'Warp Rib',
      sourceLabel: 'Preset',
    }),
  },
];
