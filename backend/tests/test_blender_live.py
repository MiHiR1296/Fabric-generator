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
        self.assertAlmostEqual(entry["texture_scale_u"], 0.18)
        self.assertTrue(entry["texture_scale_u_is_auto"])

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
        self.assertEqual(blender_live.AUTO_TEXTURE_SCALE_U_CORE_FRACTION, 0.6)
        self.assertIn("_AUTO_TEXTURE_SCALE_U_CORE_FRACTION = 0.6", blender_live.APPLY_METADATA_PY)
        self.assertIn("core_span * _AUTO_TEXTURE_SCALE_U_CORE_FRACTION", blender_live.APPLY_METADATA_PY)
        self.assertIn("_pw_resolved_texture_scale_u(entry, modifier, node_group) * texture_scale_u_multiplier", blender_live.APPLY_METADATA_PY)
        self.assertIn("_pw_resolved_texture_scale_u(first, modifier, node_group) * texture_scale_u_multiplier", blender_live.APPLY_METADATA_PY)

    def test_pinned_v_offsets_are_neutral(self) -> None:
        self.assertIn(("Texture Scale U", 1.0), blender_live.PINNED_FOOTGUN_SOCKETS)
        self.assertIn(("Texture Offset V", 0.0), blender_live.PINNED_FOOTGUN_SOCKETS)
        self.assertIn(("Sub Texture Scale V", 1.0), blender_live.PINNED_FOOTGUN_SOCKETS)
        self.assertIn(("Sub Texture Offset V", 0.0), blender_live.PINNED_FOOTGUN_SOCKETS)

    def test_build_material_asset_entry_marks_explicit_texture_scale_u(self) -> None:
        asset = SimpleNamespace(
            id="asset-one",
            label="Asset One",
            bandMeta={
                "blender": {
                    "texture_scale_u": 0.25,
                    "core_v_min": 0.3,
                    "core_v_max": 0.6,
                }
            },
        )

        entry = blender_live.build_material_asset_entry(asset)

        self.assertAlmostEqual(entry["texture_scale_u"], 0.25)
        self.assertFalse(entry["texture_scale_u_is_auto"])


if __name__ == "__main__":
    unittest.main()
