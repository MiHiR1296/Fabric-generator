from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.yarnseamless import dual_alpha_pipeline as dap  # noqa: E402


class DualAlphaPipelineTests(unittest.TestCase):
    def test_recover_rgb_foreground_from_alpha_preserves_chroma(self) -> None:
        background_srgb = np.array([170, 55, 60], dtype=np.float64) / 255.0
        foreground_srgb = np.array([70, 135, 225], dtype=np.float64) / 255.0
        alpha = np.full((2, 2), 0.72, dtype=np.float64)

        background_lin = dap.srgb_to_linear(background_srgb)
        foreground_lin = dap.srgb_to_linear(foreground_srgb)
        mixed_lin = alpha[..., None] * foreground_lin + (1.0 - alpha[..., None]) * background_lin
        mixed_u8 = (dap.linear_to_srgb(mixed_lin) * 255).round().astype(np.uint8)

        recovered = dap.recover_rgb_foreground_from_alpha(
            mixed_u8,
            (alpha * 255).round().astype(np.uint8),
            background_lin,
        )

        pixel = recovered[0, 0].astype(int)
        self.assertGreater(pixel[2], pixel[1])
        self.assertGreater(pixel[1], pixel[0])
        self.assertLess(abs(pixel[2] - 225), 4)
        self.assertLess(abs(pixel[0] - 70), 4)

    def test_recover_rgb_foreground_zeros_transparent_pixels(self) -> None:
        image = np.full((1, 1, 3), 128, dtype=np.uint8)
        recovered = dap.recover_rgb_foreground_from_alpha(
            image,
            np.zeros((1, 1), dtype=np.uint8),
            np.array([0.2, 0.2, 0.2], dtype=np.float64),
        )

        self.assertEqual(tuple(recovered[0, 0]), (0, 0, 0))

    def test_recover_rgb_foreground_stabilizes_low_alpha_red_card_halo(self) -> None:
        background_srgb = np.array([166, 58, 60], dtype=np.float64) / 255.0
        foreground_srgb = np.array([230, 232, 228], dtype=np.float64) / 255.0
        background_lin = dap.srgb_to_linear(background_srgb)
        foreground_lin = dap.srgb_to_linear(foreground_srgb)

        image = np.empty((3, 4, 3), dtype=np.uint8)
        image[:2] = (foreground_srgb * 255).round().astype(np.uint8)
        true_edge_alpha = 0.05
        mixed = true_edge_alpha * foreground_lin + (1.0 - true_edge_alpha) * background_lin
        image[2] = (dap.linear_to_srgb(mixed) * 255).round().astype(np.uint8)

        alpha = np.zeros((3, 4), dtype=np.uint8)
        alpha[:2] = 255
        alpha[2] = 64

        recovered = dap.recover_rgb_foreground_from_alpha(image, alpha, background_lin)
        edge = recovered[2, 0].astype(int)

        self.assertLess(abs(edge[0] - edge[1]), 35)
        self.assertLess(abs(edge[0] - edge[2]), 35)
        self.assertGreater(edge[1], 190)

    def test_recover_rgb_foreground_can_preserve_source_core_detail(self) -> None:
        image = np.array(
            [
                [[121, 132, 143], [151, 162, 173]],
                [[180, 80, 85], [181, 81, 86]],
            ],
            dtype=np.uint8,
        )
        alpha = np.array([[255, 230], [120, 0]], dtype=np.uint8)
        recovered = dap.recover_rgb_foreground_from_alpha(
            image,
            alpha,
            dap.srgb_to_linear(np.array([180, 80, 85], dtype=np.float64) / 255.0),
            source_blend_start_u8=160,
            preserve_source_above_u8=220,
        )

        self.assertEqual(tuple(recovered[0, 0]), (121, 132, 143))
        self.assertEqual(tuple(recovered[0, 1]), (151, 162, 173))
        self.assertEqual(tuple(recovered[1, 1]), (0, 0, 0))

    def test_hybrid_alpha_recovers_luminance_core_on_coloured_card(self) -> None:
        background = np.array([174, 181, 168], dtype=np.uint8)
        thread = np.array([42, 46, 43], dtype=np.uint8)
        image = np.empty((48, 160, 3), dtype=np.uint8)
        image[:, :] = background
        image[21:27, :] = thread

        background_lin = dap.srgb_to_linear(background.astype(np.float64) / 255.0)
        alpha = dap.closed_form_alpha_hybrid_lab_luma(image, background_lin)

        self.assertGreater((alpha[23] >= 100).mean(), 0.95)
        self.assertLess((alpha[5] >= 100).mean(), 0.05)


if __name__ == "__main__":
    unittest.main()
