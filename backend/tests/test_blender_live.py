from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import blender_live  # noqa: E402


class BlenderLiveTests(unittest.TestCase):
    def test_build_material_asset_entry_projects_raw_arc1_core_v_range(self) -> None:
        asset = SimpleNamespace(
            id="asset-one",
            label="Asset One",
            bandMeta={
                "blender": {
                    "core_v_min": 0.3,
                    "core_v_max": 0.6,
                    "fiber_bot_v_min": 0.0,
                    "fiber_top_v_max": 1.0,
                }
            },
        )

        entry = blender_live.build_material_asset_entry(asset)

        self.assertAlmostEqual(entry["core_v_min"], 0.3)
        self.assertAlmostEqual(entry["core_v_max"], 0.6)

    def test_build_material_asset_entry_keeps_arc2_bounds_raw_for_blender_padding(self) -> None:
        asset = SimpleNamespace(
            id="asset-one",
            label="Asset One",
            bandMeta={
                "blender": {
                    "core_v_min": 0.48,
                    "core_v_max": 0.52,
                    "fiber_bot_v_min": 0.46,
                    "fiber_top_v_max": 0.54,
                }
            },
        )

        entry = blender_live.build_material_asset_entry(asset)

        self.assertAlmostEqual(entry["core_v_min"], 0.48)
        self.assertAlmostEqual(entry["core_v_max"], 0.52)
        self.assertAlmostEqual(entry["fiber_bot_v_min"], 0.46)
        self.assertAlmostEqual(entry["fiber_top_v_max"], 0.54)

    def test_apply_metadata_multiplies_per_material_texture_scale_u_when_requested(self) -> None:
        self.assertIn("_PW_TEXTURE_SCALE_U_MULTIPLIER", blender_live.APPLY_METADATA_PY)
        self.assertIn("socket_value *= texture_scale_u_multiplier", blender_live.APPLY_METADATA_PY)


if __name__ == "__main__":
    unittest.main()
