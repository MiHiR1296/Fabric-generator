from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.hook_sync import (  # noqa: E402
    build_hook_build_spec,
    build_hook_sync_code,
    compute_hook_face_attributes,
    normalize_hook_pattern,
    used_material_slots,
)


class HookSyncTests(unittest.TestCase):
    def test_normalize_hook_pattern_defaults_to_standard_grid(self) -> None:
        pattern = normalize_hook_pattern({})

        self.assertEqual(pattern["structureType"], "hook")
        self.assertEqual(pattern["structureFamily"], "crochet_hook")
        self.assertEqual(pattern["rows"], 15)
        self.assertEqual(pattern["columns"], 21)
        self.assertEqual(pattern["stitchCodes"][0][0], 1)
        self.assertEqual(pattern["chainIds"][0][3], 3)
        self.assertEqual(pattern["chains"][0]["materialSlot"], 0)
        self.assertEqual(pattern["renderSettings"]["textureScaleU"], 1.06)

    def test_sparse_cells_get_negative_chain_and_u_index(self) -> None:
        attrs = compute_hook_face_attributes({
            "rows": 2,
            "columns": 2,
            "stitchCodes": [[1, 0], [6, 11]],
            "chainIds": [[7, 7], [7, 8]],
            "chains": [
                {"id": 7, "materialSlot": 2},
                {"id": 8, "materialSlot": 3},
            ],
        })

        self.assertEqual(attrs["stitch_code"], [1, 0, 6, 11])
        self.assertEqual(attrs["chain_id"], [7, -1, 7, 8])
        self.assertEqual(attrs["chain_u_index"], [0, -1, 1, 0])
        self.assertEqual(attrs["chain_material_id"], [2, -1, 2, 3])
        self.assertEqual(attrs["course_id"], [0, -1, 1, 1])
        self.assertEqual(attrs["wale_id"], [0, -1, 0, 1])

    def test_repeat_tile_expands_matrices(self) -> None:
        pattern = normalize_hook_pattern({
            "rows": 3,
            "columns": 5,
            "repeat": {"mode": "tile", "rows": 2, "columns": 2},
            "stitchCodes": [[1, 0], [6, 7]],
            "source": {
                "kind": "user-authored",
                "access": "local",
                "title": "Local repeat",
            },
        })

        self.assertEqual(pattern["stitchCodes"], [
            [1, 0, 1, 0, 1],
            [6, 7, 6, 7, 6],
            [1, 0, 1, 0, 1],
        ])
        self.assertEqual(pattern["source"]["kind"], "user-authored")
        self.assertEqual(pattern["stitchLegend"][6]["archetype"], "knit_v")

    def test_material_slots_are_clamped_to_contract(self) -> None:
        pattern = normalize_hook_pattern({
            "rows": 1,
            "columns": 1,
            "chains": [{"id": 0, "materialSlot": 99}],
        })

        self.assertEqual(pattern["chains"][0]["materialSlot"], 15)
        self.assertEqual(used_material_slots(pattern), [15])

    def test_build_spec_resolves_frontend_intent_for_blender(self) -> None:
        spec = build_hook_build_spec({
            "rows": 2,
            "columns": 3,
            "structureFamily": "knit_chart",
            "rowDirection": "right_to_left",
            "stitchCodes": [[1, 0, 6], [11, 1, 0]],
            "chainIds": [[0, 0, 1], [1, 2, 2]],
            "chains": [
                {"id": 0, "materialSlot": 0},
                {"id": 1, "materialSlot": 2},
                {"id": 2, "materialSlot": 3},
            ],
            "source": {"kind": "user-authored", "access": "local", "title": "Intent sample"},
        })

        self.assertEqual(spec["buildMode"], "gn_reference_bridge_v1")
        self.assertEqual(spec["visualReference"]["role"], "calibration_reference_only")
        self.assertEqual(spec["frontendIntent"]["structureFamily"], "knit_chart")
        self.assertEqual(spec["frontendIntent"]["rowDirection"], "right_to_left")
        self.assertEqual(spec["grid"]["activeCells"], 4)
        self.assertEqual(spec["grid"]["emptyCells"], 2)
        self.assertEqual(spec["stitches"]["counts"], {"0": 2, "1": 2, "6": 1, "11": 1})
        self.assertEqual(spec["stitches"]["unsupportedCodes"], [6, 11])
        self.assertEqual(spec["stitches"]["fallbackCodes"], {"6": 1, "11": 1})
        self.assertEqual(spec["materials"]["usedSlots"], [0, 2, 3])
        self.assertTrue(spec["continuity"]["sparseCellsDoNotResetU"])

    def test_build_hook_sync_code_creates_hook_draft_and_sets_sockets(self) -> None:
        code = build_hook_sync_code({
            "rows": 1,
            "columns": 2,
            "stitchCodes": [[1, 0]],
            "chainIds": [[0, 1]],
            "chains": [{"id": 0, "materialSlot": 0}, {"id": 1, "materialSlot": 1}],
            "renderSettings": {"hookScale": 0.12, "tubeRadius": 0.2},
        })

        self.assertIn("HookDraft_Live", code)
        self.assertIn("stitch_code", code)
        self.assertIn("chain_u_index", code)
        self.assertIn("'Pattern Scale'", code)
        self.assertIn("'Half Tube Radius'", code)
        self.assertIn("'activeCells'", code)
        self.assertIn("'buildSpec'", code)
        self.assertIn("gn_reference_rows_columns_material_uv_v1", code)
        self.assertIn("pre_v2_calibration_reference_only", code)
        self.assertIn("evaluated_hook_geometry_summary", code)
        self.assertIn("gn_reference_rows_columns_material", code)
        self.assertIn("repair_hook_modifier_output", code)
        self.assertIn("remove_hook_socket_drivers", code)
        self.assertIn("'removedDrivers'", code)
        self.assertIn("'Texture Scale U'", code)
        self.assertIn("'Texture Side Flatten'", code)
        self.assertIn("'modifierOutput'", code)
        self.assertIn("'geometry'", code)
        self.assertIn("show_reference_hook_modifier", code)
        self.assertIn("'modifierDisplay'", code)
        self.assertIn("find_hook_material_adapter", code)
        self.assertIn("'materialAdapter'", code)
        self.assertIn("'Draft Object'", code)
        self.assertIn("'Draft Columns'", code)

    def test_build_hook_sync_code_handles_null_chain_labels(self) -> None:
        code = build_hook_sync_code({
            "rows": 1,
            "columns": 1,
            "chains": [{"id": 0, "materialSlot": 0}],
        })

        self.assertIn("pattern = json.loads", code)
        compile(code, "<hook_sync>", "exec")


if __name__ == "__main__":
    unittest.main()
