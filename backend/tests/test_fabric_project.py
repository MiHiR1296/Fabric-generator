from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.fabric_project import derive_color_slots, normalize_color_bindings, validate_project_bindings  # noqa: E402
from app.models import YarnAsset  # noqa: E402


class FabricProjectTests(unittest.TestCase):
    def test_derive_color_slots_deduplicates_per_scope(self) -> None:
        draft = {
            "warpColors": ["#fff", "#ffffff", "#112233", "#112233"],
            "weftColors": ["#fff", "#445566", "#445566", "#fff"],
        }

        self.assertEqual(
            derive_color_slots(draft),
            [
                {"scope": "warp", "colorHex": "#ffffff"},
                {"scope": "warp", "colorHex": "#112233"},
                {"scope": "weft", "colorHex": "#ffffff"},
                {"scope": "weft", "colorHex": "#445566"},
            ],
        )

    def test_validate_project_bindings_keeps_warp_and_weft_slots_independent(self) -> None:
        bindings = normalize_color_bindings(
            [
                {"scope": "warp", "colorHex": "#ffffff", "yarnAssetId": "warp-asset"},
                {"scope": "weft", "colorHex": "#ffffff", "yarnAssetId": "weft-asset"},
                {"scope": "weft", "colorHex": "#000000", "yarnAssetId": "warp-asset"},
            ]
        )
        assets = {
            "warp-asset": YarnAsset(
                id="warp-asset",
                label="Warp Yarn",
                status="ready",
                sourceFilename="source.png",
                sourceUrl="/warp/source.png",
            ),
            "weft-asset": YarnAsset(
                id="weft-asset",
                label="Weft Yarn",
                status="ready",
                sourceFilename="source.png",
                sourceUrl="/weft/source.png",
            ),
        }

        _, warp_material_ids, weft_material_ids, ordered_assets = validate_project_bindings(
            {
                "warpColors": ["#ffffff"],
                "weftColors": ["#ffffff", "#000000"],
            },
            bindings,
            assets,
        )

        self.assertEqual(warp_material_ids, [0])
        self.assertEqual(weft_material_ids, [1, 0])
        self.assertEqual([asset.id for asset in ordered_assets], ["warp-asset", "weft-asset"])

    def test_validate_project_bindings_reports_missing_slots(self) -> None:
        bindings = normalize_color_bindings(
            [
                {"scope": "warp", "colorHex": "#ffffff", "yarnAssetId": "asset-1"},
            ]
        )
        assets = {
            "asset-1": YarnAsset(
                id="asset-1",
                label="Asset One",
                status="ready",
                sourceFilename="source.png",
                sourceUrl="/asset-1/source.png",
            ),
        }

        with self.assertRaisesRegex(ValueError, "Missing: weft #000000"):
            validate_project_bindings(
                {
                    "warpColors": ["#ffffff"],
                    "weftColors": ["#000000"],
                },
                bindings,
                assets,
            )


if __name__ == "__main__":
    unittest.main()
