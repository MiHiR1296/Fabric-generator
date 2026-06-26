from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.yarnseamless import dual_alpha_pipeline as dap  # noqa: E402
from app.yarnseamless_routes import _desaturate_background_spill_rgb, _reconstruct_model_from_chunks  # noqa: E402


class YarnseamlessRoutesTests(unittest.TestCase):
    def test_reconstruct_model_from_chunks_combines_parts(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            chunk_dir = root / "model_chunks"
            chunk_dir.mkdir()
            (chunk_dir / "big-lama.pt.part-000").write_bytes(b"big-")
            (chunk_dir / "big-lama.pt.part-001").write_bytes(b"lama")
            target = root / "big-lama.pt"

            result = _reconstruct_model_from_chunks(chunk_dir=chunk_dir, target_path=target)

            self.assertEqual(result, target)
            self.assertEqual(target.read_bytes(), b"big-lama")

    def test_background_spill_desaturation_only_touches_low_alpha_card_colour(self) -> None:
        rgb = np.array(
            [
                [
                    (220, 222, 218),  # high-alpha yarn core
                    (170, 55, 60),    # low-alpha red card spill
                    (170, 55, 60),    # opaque red yarn-like pixel
                    (40, 90, 180),    # unrelated low-alpha blue yarn colour
                ]
            ],
            dtype=np.uint8,
        )
        alpha = np.array([[255, 48, 252, 48]], dtype=np.uint8)
        background_linear = dap.srgb_to_linear(np.array([170, 55, 60], dtype=np.float64) / 255.0)

        out = np.asarray(
            _desaturate_background_spill_rgb(
                Image.fromarray(rgb, mode="RGB"),
                Image.fromarray(alpha, mode="L"),
                background_linear=background_linear,
            )
        )

        self.assertTrue(np.array_equal(out[0, 0], rgb[0, 0]))
        self.assertTrue(np.array_equal(out[0, 2], rgb[0, 2]))
        self.assertLessEqual(int(np.abs(out[0, 3].astype(int) - rgb[0, 3].astype(int)).max()), 2)

        before_red_excess = int(rgb[0, 1, 0]) - max(int(rgb[0, 1, 1]), int(rgb[0, 1, 2]))
        after_red_excess = int(out[0, 1, 0]) - max(int(out[0, 1, 1]), int(out[0, 1, 2]))
        self.assertLess(after_red_excess, before_red_excess // 3)
        self.assertLess(int(out[0, 1].max()) - int(out[0, 1].min()), 24)

    def test_background_spill_desaturation_catches_luma_variants_of_card_colour(self) -> None:
        rgb = np.array(
            [
                [
                    (100, 25, 28),    # dark red card shade
                    (235, 175, 178),  # light red card shade
                    (212, 158, 160),  # red mixed into pale yarn fringe
                    (45, 170, 70),    # unrelated low-alpha green yarn colour
                ]
            ],
            dtype=np.uint8,
        )
        alpha = np.array([[90, 90, 180, 90]], dtype=np.uint8)
        background_linear = dap.srgb_to_linear(np.array([170, 55, 60], dtype=np.float64) / 255.0)

        out = np.asarray(
            _desaturate_background_spill_rgb(
                Image.fromarray(rgb, mode="RGB"),
                Image.fromarray(alpha, mode="L"),
                background_linear=background_linear,
            )
        )

        for index in (0, 1, 2):
            before_spread = int(rgb[0, index].max()) - int(rgb[0, index].min())
            after_spread = int(out[0, index].max()) - int(out[0, index].min())
            self.assertLess(after_spread, before_spread)

        self.assertLessEqual(int(np.abs(out[0, 3].astype(int) - rgb[0, 3].astype(int)).max()), 2)

    def test_background_spill_desaturation_reaches_semitransparent_red_fringe(self) -> None:
        rgb = np.array([[(198, 128, 132), (198, 128, 132), (198, 128, 132)]], dtype=np.uint8)
        alpha = np.array([[210, 246, 252]], dtype=np.uint8)
        background_linear = dap.srgb_to_linear(np.array([170, 55, 60], dtype=np.float64) / 255.0)

        out = np.asarray(
            _desaturate_background_spill_rgb(
                Image.fromarray(rgb, mode="RGB"),
                Image.fromarray(alpha, mode="L"),
                background_linear=background_linear,
            )
        )

        def spread(pixel: np.ndarray) -> int:
            return int(pixel.max()) - int(pixel.min())

        self.assertLess(spread(out[0, 0]), spread(rgb[0, 0]))
        self.assertLessEqual(spread(out[0, 1]), spread(rgb[0, 1]))
        self.assertLessEqual(int(np.abs(out[0, 2].astype(int) - rgb[0, 2].astype(int)).max()), 2)


if __name__ == "__main__":
    unittest.main()
