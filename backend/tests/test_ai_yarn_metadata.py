from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.ai_yarn_metadata import (  # noqa: E402
    AI_U_SCALE_STRATEGY,
    detect_ai_yarn_bands,
    estimate_ai_texture_scale_u,
    save_ai_yarn_to_library,
)


class AiYarnMetadataTests(unittest.TestCase):
    def test_alpha_mass_u_scale_boosts_core_only_scale_without_exploding(self) -> None:
        alpha = np.zeros((100, 200), dtype=np.uint8)
        alpha[45:55, :] = 255
        alpha[35:45, :] = 128
        alpha[55:65, :] = 128

        result = estimate_ai_texture_scale_u(alpha, core_height_px=10, image_height_px=100)

        self.assertEqual(result["strategy"], AI_U_SCALE_STRATEGY)
        self.assertGreater(result["texture_scale_u"], result["texture_scale_u_previous_core_only"])
        self.assertLessEqual(
            result["texture_scale_u"],
            result["texture_scale_u_previous_core_only"] * result["max_boost"],
        )

    def test_detect_ai_yarn_bands_uses_dense_core_and_wider_arc2_support(self) -> None:
        alpha = np.zeros((100, 200), dtype=np.uint8)
        alpha[45:55, :] = 255
        alpha[35:65, :20] = 255

        detected = detect_ai_yarn_bands(alpha)

        self.assertEqual(detected["ai_core"], [45, 54])
        self.assertEqual(detected["ai_arc2_extent"], [35, 64])
        self.assertEqual(detected["ai_width_px"], 10)

    def test_save_ai_yarn_to_library_writes_v2_u_scale_metadata(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            library = root / "library"
            source.mkdir()
            rgba = np.zeros((100, 200, 4), dtype=np.uint8)
            rgba[45:55, :, :3] = [200, 180, 150]
            rgba[45:55, :, 3] = 255
            rgba[35:45, :, :3] = [200, 180, 150]
            rgba[35:45, :, 3] = 128
            rgba[55:65, :, :3] = [200, 180, 150]
            rgba[55:65, :, 3] = 128
            image_path = source / "tinted_rgba.png"
            Image.fromarray(rgba).save(image_path)
            measurements = {
                "dpi": 1600.0,
                "image_size_px": [200, 100],
                "length": {"px": 200},
                "c_band": {"top_y": 45, "bottom_y": 54, "height": 9},
                "d_band": {"top_y": 35, "bottom_y": 64, "height": 29},
                "width": {"px": 10},
            }
            measurements_path = source / "measurements.json"
            measurements_path.write_text(json.dumps(measurements), encoding="utf-8")

            saved = save_ai_yarn_to_library(
                image_path,
                measurements_path=measurements_path,
                label="AI Test",
                library_root=library,
                yarn_id="20260611_120000_abcd",
                sync_runtime=False,
            )

            metadata = json.loads((library / "20260611_120000_abcd" / "metadata.json").read_text())
            index = json.loads((library / "index.json").read_text())
            self.assertTrue(saved["ok"])
            self.assertEqual(metadata["blender"]["texture_scale_u_strategy"], AI_U_SCALE_STRATEGY)
            self.assertGreater(
                metadata["blender"]["texture_scale_u"],
                metadata["blender"]["texture_scale_u_previous_core_only"],
            )
            self.assertEqual(index["yarns"][0]["id"], "20260611_120000_abcd")


if __name__ == "__main__":
    unittest.main()
