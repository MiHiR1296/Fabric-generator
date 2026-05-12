from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from unittest.mock import patch

from app.blender_sync import build_blender_sync_code, send_blender_command, validate_drawdown_matrix  # noqa: E402


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
                    "spacing": 0.5,
                    "patternNoiseX": 0.5,
                    "patternNoiseY": 1,
                    "amplitude": 0.008,
                    "threadRadius": 0.028,
                    "textureScaleU": 8,
                    "textureScaleV": 0.5,
                    "textureOffsetV": 0.12,
                    "fiberDensity": 0.3,
                    "fillRatio": 1,
                },
            }
        )

        self.assertIn("ensure_web_draft_material", code)
        self.assertIn("'Warp Threads'", code)
        self.assertIn("'Weft Threads'", code)
        self.assertIn("warp_threads_override = 180", code)
        self.assertIn("weft_threads_override = 180", code)
        self.assertIn("spacing_override = 0.065", code)
        self.assertIn("pattern_noise_x_override = 0.015", code)
        self.assertIn("pattern_noise_y_override = 0.03", code)
        self.assertIn("amplitude_override = 0.008", code)
        self.assertIn("thread_radius_override = 0.028", code)
        self.assertIn("texture_scale_u_override = 8.0", code)
        self.assertIn("fill_ratio_override = 1.0", code)
        self.assertIn("texture_offset_v_override = 0.12", code)
        self.assertIn("fiber_density_override = 0.3", code)
        self.assertIn("Texture Scale U", code)
        self.assertIn("Texture Scale V", code)
        self.assertIn("'Sub Texture Scale V', 0.0", code)
        self.assertIn("'Sub Texture Offset V', 0.0", code)
        self.assertIn("Pattern Noise X", code)
        self.assertIn("Pattern Noise Y", code)
        self.assertIn("ensure_scan_knotty_draft_sampling", code)
        self.assertIn("PW Draft Warp Sample", code)
        self.assertIn("PW Draft Weft Sample", code)
        self.assertIn("warp_sample_sign.inputs[1].default_value = -2.0", code)
        self.assertIn("weft_sample_sign.inputs[1].default_value = 2.0", code)
        self.assertIn("uses_scan_knotty_group", code)

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

    def test_send_blender_command_restarts_managed_session_after_transport_failure(self) -> None:
        with patch("app.blender_sync.begin_blender_command"), patch(
            "app.blender_sync.finish_blender_command"
        ), patch(
            "app.blender_sync.managed_session_enabled",
            return_value=True,
        ), patch(
            "app.blender_sync.restart_blender_session"
        ) as restart_mock, patch(
            "app.blender_sync._send_socket_command",
            side_effect=[
                {"status": "error", "message": "Timed out after 30.0 seconds waiting for Blender at 127.0.0.1:9875."},
                {"status": "success", "result": {"ok": True}},
            ],
        ):
            response = send_blender_command("get_scene_info")

        self.assertEqual(response, {"status": "success", "result": {"ok": True}})
        restart_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
