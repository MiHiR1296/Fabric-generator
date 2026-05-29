from __future__ import annotations

import sys
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
