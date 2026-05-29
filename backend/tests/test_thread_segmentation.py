from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.yarnseamless.multithread_flow import alpha_pipeline  # noqa: E402
from app.yarnseamless import thread_segmentation as seg  # noqa: E402


def _scan(width: int, height: int, bg: tuple[int, int, int]) -> np.ndarray:
    img = np.empty((height, width, 3), dtype=np.uint8)
    img[:, :] = np.array(bg, dtype=np.uint8)
    return img


def _draw_vertical(img: np.ndarray, x: int, color: tuple[int, int, int], half: int = 3) -> None:
    x0 = max(0, x - half)
    x1 = min(img.shape[1], x + half + 1)
    img[:, x0:x1] = np.array(color, dtype=np.uint8)


class ThreadSegmentationTests(unittest.TestCase):
    def test_detects_dark_threads_after_background_colour_change(self) -> None:
        img = _scan(260, 180, (176, 182, 171))
        for x in (45, 130, 218):
            _draw_vertical(img, x, (25, 28, 26), half=3)

        result = seg.detect_threads(img)

        self.assertIsNone(result.failure_reason)
        self.assertEqual(len(result.peaks), 3)
        for got, want in zip(result.peaks, [45, 130, 218]):
            self.assertLessEqual(abs(got - want), 4)

    def test_detects_weak_chroma_threads_with_similar_luma(self) -> None:
        img = _scan(260, 180, (150, 58, 62))
        for x in (52, 132, 215):
            _draw_vertical(img, x, (70, 92, 150), half=3)

        result = seg.detect_threads(img)

        self.assertIsNone(result.failure_reason)
        self.assertEqual(len(result.peaks), 3)

    def test_auto_merges_duplicate_edges_of_one_thick_thread(self) -> None:
        img = _scan(320, 180, (178, 180, 170))
        _draw_vertical(img, 70, (35, 35, 35), half=4)
        img[:, 195:201] = np.array((25, 25, 25), dtype=np.uint8)
        img[:, 202:210] = np.array((95, 95, 95), dtype=np.uint8)
        img[:, 211:217] = np.array((25, 25, 25), dtype=np.uint8)

        result = seg.detect_threads(img)

        self.assertIsNone(result.failure_reason)
        self.assertEqual(len(result.peaks), 2)
        self.assertLessEqual(abs(result.peaks[0] - 70), 4)
        self.assertLessEqual(abs(result.peaks[1] - 206), 8)

    def test_rejects_plaid_fabric_as_out_of_domain(self) -> None:
        img = _scan(360, 260, (130, 132, 130))
        img[35:70, :] = np.array((40, 42, 42), dtype=np.uint8)
        img[145:180, :] = np.array((45, 45, 45), dtype=np.uint8)
        img[:, 70:95] = np.array((220, 220, 214), dtype=np.uint8)
        img[:, 220:250] = np.array((35, 36, 36), dtype=np.uint8)

        result = seg.detect_threads(img, n_threads=3)

        self.assertEqual(result.peaks, [])
        self.assertIn("woven fabric", result.failure_reason or "")

    def test_segmentation_alpha_gates_noisy_background_without_greying_blue(self) -> None:
        img = _scan(220, 80, (166, 58, 60))
        img[33:47, :] = np.array((55, 110, 210), dtype=np.uint8)
        base_alpha = np.random.default_rng(4).integers(0, 24, size=(80, 220), dtype=np.uint8)
        base_alpha[33:47, :] = 230
        base_alpha[24:33, 40:180] = 36
        base_alpha[47:56, 50:175] = 32

        result = seg.segment_thread_alpha(img, base_alpha)

        self.assertLess(result.quality["background_alpha_p95"], 8)
        self.assertGreater(result.quality["foreground_alpha_p50"], 200)
        self.assertGreater(result.alpha_u8[26:31, 80:160].mean(), 20)
        self.assertLess(result.alpha_u8[5:12, 20:180].mean(), 5)
        self.assertIsNone(result.quality["failure_reason"])

    def test_density_band_quality_returns_legacy_shape_and_metrics(self) -> None:
        alpha = np.zeros((80, 240), dtype=np.uint8)
        alpha[30:48, :] = 255
        alpha[20:30, 30:220] = 26
        alpha[48:61, 35:210] = 28
        alpha[4:10, 2:238] = 30

        result = seg.detect_band_quality(alpha)

        self.assertGreaterEqual(result["c_band"]["top_y"], 30)
        self.assertLessEqual(result["c_band"]["bottom_y"], 48)
        self.assertLessEqual(result["c_band"]["fiber_top_y"], 20)
        self.assertGreaterEqual(result["c_band"]["fiber_bot_y"], 60)
        self.assertGreater(result["quality"]["peak_density"], 0.95)
        self.assertEqual(result["quality"]["fiber_top_height"], result["c_band"]["top_y"] - result["c_band"]["fiber_top_y"])
        self.assertIsNone(result["quality"]["failure_reason"])

    def test_band_quality_uses_connected_thick_core_not_disconnected_haze_band(self) -> None:
        alpha = np.zeros((96, 300), dtype=np.uint8)
        # A long disconnected semitransparent row band should not become the
        # red core-thickness bracket.
        alpha[10:32, :] = 180
        alpha[42:58, 20:280] = 235
        alpha[36:42, 50:250] = 34
        alpha[58:69, 45:255] = 30

        result = seg.detect_band_quality(alpha)

        self.assertGreaterEqual(result["c_band"]["top_y"], 40)
        self.assertLessEqual(result["c_band"]["top_y"], 44)
        self.assertGreaterEqual(result["c_band"]["bottom_y"], 55)
        self.assertLessEqual(result["c_band"]["bottom_y"], 59)
        self.assertEqual(result["quality"]["raw_fwhm_core"], [10, 31])
        self.assertIsNone(result["quality"]["failure_reason"])

    def test_level_and_crop_rotates_subdegree_tilt(self) -> None:
        height, width = 80, 320
        img = np.zeros((height, width, 3), dtype=np.uint8)
        slope = 0.010
        center_y = 36.0
        for x in range(width):
            y = int(round(center_y + slope * (x - width / 2)))
            img[max(0, y - 4):min(height, y + 5), x] = 230

        _cropped, meta = alpha_pipeline.level_and_crop(img, invert=False)

        self.assertGreater(abs(float(meta["angle_deg"])), 0.3)
        self.assertLess(abs(float(meta["angle_deg"])), 0.9)


class ThreadSegmentationFixtureTests(unittest.TestCase):
    FIXTURE_ROOT = Path("/Users/mihirbotle/Desktop/Impetus/3D Fabric/thread_epson_scans/testingv1_cheques")

    @unittest.skipUnless(FIXTURE_ROOT.is_dir(), "local Epson cheque scan fixtures are unavailable")
    def test_testingv1_cheques_valid_scans_auto_detect_three_threads(self) -> None:
        Image.MAX_IMAGE_PIXELS = None
        valid = [
            "black_cheques_testing20260527_13010491.png",
            "blue_cheques_testing20260527_12021799.png",
            "furry20260527_13122209.png",
            "light_blue_cheques_testing20260527_12355228.png",
            "light_blue_cheques_testing20260527_12411603.png",
            "white_cheques_testing20260527_12205286.png",
        ]
        for name in valid:
            with self.subTest(name=name):
                arr = np.asarray(Image.open(self.FIXTURE_ROOT / name).convert("RGB"))
                result = seg.detect_threads(arr)
                self.assertIsNone(result.failure_reason)
                self.assertEqual(len(result.peaks), 3)

    @unittest.skipUnless(FIXTURE_ROOT.is_dir(), "local Epson cheque scan fixtures are unavailable")
    def test_testingv1_cheques_fabric_scan_is_rejected(self) -> None:
        Image.MAX_IMAGE_PIXELS = None
        arr = np.asarray(Image.open(self.FIXTURE_ROOT / "fabric_scan20260527_13591460.png").convert("RGB"))
        result = seg.detect_threads(arr, n_threads=3)
        self.assertEqual(result.peaks, [])
        self.assertIn("woven fabric", result.failure_reason or "")


if __name__ == "__main__":
    unittest.main()
