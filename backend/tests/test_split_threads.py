from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.yarnseamless.multithread_flow import split_threads  # noqa: E402


def _scan(width: int, height: int, bg: tuple[int, int, int]) -> np.ndarray:
    img = np.empty((height, width, 3), dtype=np.uint8)
    img[:, :] = np.array(bg, dtype=np.uint8)
    return img


def _draw_vertical_threads(
    img: np.ndarray,
    xs: list[int],
    color: tuple[int, int, int],
    half_width: int = 3,
) -> np.ndarray:
    for x in xs:
        x0 = max(0, x - half_width)
        x1 = min(img.shape[1], x + half_width + 1)
        img[:, x0:x1] = np.array(color, dtype=np.uint8)
    return img


def _assert_peaks_close(testcase: unittest.TestCase, peaks: np.ndarray, expected: list[int]) -> None:
    testcase.assertEqual(len(peaks), len(expected))
    for got, want in zip(peaks.tolist(), expected):
        testcase.assertLessEqual(abs(got - want), 3)


class SplitThreadsTests(unittest.TestCase):
    def test_detects_bright_threads_on_dark_card(self) -> None:
        img = _scan(240, 160, (30, 30, 30))
        _draw_vertical_threads(img, [45, 120, 195], (230, 230, 230))

        peaks, _profile = split_threads.detect_thread_columns(img, n_threads=3)

        _assert_peaks_close(self, peaks, [45, 120, 195])

    def test_detects_dark_threads_on_light_card(self) -> None:
        img = _scan(240, 160, (185, 185, 180))
        _draw_vertical_threads(img, [45, 120, 195], (24, 24, 24))

        peaks, _profile = split_threads.detect_thread_columns(img, n_threads=3)

        _assert_peaks_close(self, peaks, [45, 120, 195])

    def test_detects_coloured_threads_with_weak_luma_contrast(self) -> None:
        img = _scan(240, 160, (150, 60, 60))
        _draw_vertical_threads(img, [70, 170], (50, 83, 160))

        peaks, _profile = split_threads.detect_thread_columns(img, n_threads=2)

        _assert_peaks_close(self, peaks, [70, 170])

    def test_auto_detect_does_not_invent_border_peaks(self) -> None:
        img = _scan(180, 120, (190, 190, 185))
        _draw_vertical_threads(img, [90], (20, 20, 20))

        peaks, _profile = split_threads.detect_thread_columns(img, n_threads=None)

        _assert_peaks_close(self, peaks, [90])

    def test_auto_merges_two_edges_of_one_wide_thread(self) -> None:
        img = _scan(320, 180, (185, 185, 180))
        _draw_vertical_threads(img, [55, 160], (25, 25, 25), half_width=3)
        img[:, 245:250] = np.array((20, 20, 20), dtype=np.uint8)
        img[:, 251:255] = np.array((90, 90, 90), dtype=np.uint8)
        img[:, 256:261] = np.array((20, 20, 20), dtype=np.uint8)

        peaks, _profile = split_threads.detect_thread_columns(img, n_threads=None)

        _assert_peaks_close(self, peaks, [55, 160, 254])

    def test_expected_count_can_recover_weak_partial_thread(self) -> None:
        img = _scan(320, 240, (170, 55, 60))
        _draw_vertical_threads(img, [55, 265], (35, 85, 160), half_width=3)
        for y0 in range(0, img.shape[0], 48):
            img[y0:y0 + 28, 158:164] = np.array((75, 92, 130), dtype=np.uint8)

        peaks, _profile = split_threads.detect_thread_columns(img, n_threads=3)

        _assert_peaks_close(self, peaks, [55, 161, 265])

    def test_split_with_layout_recenters_slanted_thread(self) -> None:
        img = _scan(180, 260, (155, 58, 62))
        fg_mask = np.zeros(img.shape[:2], dtype=bool)
        fg_score = np.zeros(img.shape[:2], dtype=np.float32)
        for y in range(img.shape[0]):
            x = int(round(35 + 0.24 * y))
            img[y, max(0, x - 4):min(img.shape[1], x + 5)] = np.array((232, 232, 226), dtype=np.uint8)
            fg_mask[y, max(0, x - 4):min(img.shape[1], x + 5)] = True
            fg_score[y, max(0, x - 4):min(img.shape[1], x + 5)] = 1.0

        layout = SimpleNamespace(
            foreground_mask=fg_mask,
            foreground_score=fg_score,
            bg_rgb=[155.0, 58.0, 62.0],
            candidates=[SimpleNamespace(width=9)],
        )
        strips = split_threads.split_into_strips(img, np.asarray([66], dtype=int), layout=layout)

        self.assertEqual(len(strips), 1)
        _x0, _x1, strip = strips[0]
        self.assertEqual(strip.shape[0], img.shape[0])
        luma = (0.2126 * strip[..., 0] + 0.7152 * strip[..., 1] + 0.0722 * strip[..., 2])
        mask = luma > 180
        row_has = mask.sum(axis=1) > 0
        centers = []
        xs = np.arange(strip.shape[1], dtype=np.float32)
        for row in np.where(row_has)[0]:
            w = mask[row].astype(np.float32)
            centers.append(float((xs * w).sum() / max(float(w.sum()), 1e-6)))

        self.assertGreater(len(centers), 200)
        self.assertLess(max(centers) - min(centers), 4.0)


if __name__ == "__main__":
    unittest.main()
