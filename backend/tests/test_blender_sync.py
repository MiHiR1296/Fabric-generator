from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.blender_sync import build_blender_sync_code, validate_drawdown_matrix  # noqa: E402


class BlenderSyncTests(unittest.TestCase):
    def test_validate_drawdown_matrix_rejects_ragged_rows(self) -> None:
        with self.assertRaises(ValueError):
            validate_drawdown_matrix([[1, 0], [1]])

    def test_build_sync_code_includes_render_settings_and_material_logic(self) -> None:
        code = build_blender_sync_code(
            {
                "title": "Sync Test",
                "drawdown": [[1, 0], [0, 1]],
                "warpColors": ["#111111"],
                "weftColors": ["#cc8844"],
                "renderSettings": {
                    "warpThreads": 120,
                    "weftThreads": 96,
                    "spacing": 0.03,
                    "amplitude": 0.005,
                    "textureScaleV": 0.5,
                    "fillRatio": 1,
                },
            }
        )

        self.assertIn("ensure_web_draft_material", code)
        self.assertIn("'Warp Threads'", code)
        self.assertIn("'Weft Threads'", code)
        self.assertIn("warp_threads_override = 120", code)
        self.assertIn("weft_threads_override = 96", code)
        self.assertIn("fill_ratio_override = 1.0", code)
        self.assertIn("Texture Scale V", code)

    def test_build_sync_code_embeds_draft_material_sampling_when_assignments_are_present(self) -> None:
        code = build_blender_sync_code(
            {
                "title": "Material Sync Test",
                "drawdown": [[1, 0], [0, 1]],
                "warpColors": ["#ffffff", "#000000"],
                "weftColors": ["#000000", "#ffffff"],
            },
            warp_material_ids=[0, 2],
            weft_material_ids=[1, 3],
            material_count=4,
        )

        self.assertIn("warp_material_ids = [0, 2]", code)
        self.assertIn("weft_material_ids = [1, 3]", code)
        self.assertIn("material_count_override = 4", code)
        self.assertIn("warp_material_id", code)
        self.assertIn("weft_material_id", code)
        self.assertIn("ensure_draft_colour_id_sampling", code)


if __name__ == "__main__":
    unittest.main()
