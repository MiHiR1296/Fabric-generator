from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.blender_sync import (  # noqa: E402
    DEFAULT_ARC1_V_PADDING,
    DEFAULT_SPACING,
    build_blender_sync_code,
    load_blender_socket_config,
    validate_drawdown_matrix,
)


class BlenderSyncTests(unittest.TestCase):
    def test_load_blender_socket_config_defaults_to_live_mcp_port(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            config = load_blender_socket_config()

        self.assertEqual(config.host, "127.0.0.1")
        self.assertEqual(config.port, 9876)

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
                    "arc1VPadding": 0.1,
                },
            }
        )

        self.assertIn("ensure_web_draft_material", code)
        self.assertIn("'Warp Threads'", code)
        self.assertIn("'Weft Threads'", code)
        self.assertIn("warp_threads_override = 120", code)
        self.assertIn("weft_threads_override = 96", code)
        self.assertIn("fill_ratio_override = 1.0", code)
        self.assertIn("arc1_v_padding_override = 0.1", code)
        self.assertIn("'Arc 1 V Padding'", code)
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
        self.assertIn("ensure_parametric_knotty_draft_contract", code)
        self.assertIn("('PW Draft Warp Col Mod', 0, 'Curve of Point', 'Curve Index')", code)
        self.assertIn("('PW Draft Warp Row Mod', 0, 'Curve of Point', 'Index in Curve')", code)
        self.assertIn("('PW Draft Weft Col Mod', 0, 'Curve of Point.001', 'Index in Curve')", code)
        self.assertIn("('PW Draft Weft Row Mod', 0, 'Curve of Point.001', 'Curve Index')", code)
        self.assertIn("('PW Draft Warp Sign', 1, 2.0)", code)
        self.assertIn("('PW Draft Warp Sign', 2, -1.0)", code)
        self.assertIn("('PW Draft Weft Sign', 1, -2.0)", code)
        self.assertIn("('PW Draft Weft Sign', 2, 1.0)", code)
        self.assertIn("warp_material_ids[cols - col - 1]", code)

    def test_parametric_knotty_keeps_isotropic_texture_scale_u(self) -> None:
        code = build_blender_sync_code(
            {
                "title": "Scale Test",
                "drawdown": [[1]],
                "warpColors": ["#ffffff"],
                "weftColors": ["#000000"],
            }
        )

        self.assertIn("weave_group.name.startswith('Parametric Weave knotty')", code)
        self.assertIn("root_texture_scale_u = 1.0", code)
        self.assertIn("material_texture_scale_u = 1.0", code)
        # Fit math was retired in favour of per-strand U stride; neither the
        # target-length divide nor the calibration multiply should remain.
        self.assertNotIn("target_length / source_strand_length", code)
        self.assertNotIn("float(texture_u_calibration)", code)
        # UV Random U default is 0 now; per-strand stride provides variation.
        self.assertIn(
            "'UV Random U', pick_value(uv_random_u_override, preserved.get('UV Random U'), 0.0)",
            code,
        )
        self.assertIn(
            "'Texture Offset V', 0.0",
            code,
        )
        self.assertIn(
            "'Sub Texture Scale V', 1.0",
            code,
        )
        self.assertIn(
            "'Sub Texture Offset V', 0.0",
            code,
        )
        self.assertIn("'Texture Scale U', root_texture_scale_u", code)
        self.assertIn(
            f"'Arc 1 V Padding', pick_value(arc1_v_padding_override, preserved.get('Arc 1 V Padding'), {DEFAULT_ARC1_V_PADDING!r})",
            code,
        )
        self.assertIn(
            f"'Spacing', spacing_value",
            code,
        )
        self.assertIn(
            f"spacing_value = pick_value(spacing_override, preserved.get('Spacing'), {DEFAULT_SPACING!r})",
            code,
        )
        self.assertEqual(DEFAULT_ARC1_V_PADDING, 0.008)
        self.assertEqual(DEFAULT_SPACING, 0.026)


if __name__ == "__main__":
    unittest.main()
