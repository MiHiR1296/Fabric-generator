from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.yarnseamless import yarn_library  # noqa: E402


class YarnLibraryTests(unittest.TestCase):
    def test_save_to_library_records_physical_scale_confidence_from_source_scan_dpi(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            mf_dir = root / "mf"
            mt_dir = root / "mt"
            library_root = root / "library"
            mf_dir.mkdir()
            mt_dir.mkdir()

            rgb = Image.new("RGB", (20, 8), (20, 20, 20))
            alpha = Image.new("L", (20, 8), 0)
            for y in range(2, 6):
                for x in range(20):
                    rgb.putpixel((x, y), (220, 220, 220))
                    alpha.putpixel((x, y), 255)
            rgb.save(mf_dir / "export_assembled_final.png")
            alpha.save(mf_dir / "export_assembled_alpha.png")
            rgba = Image.merge("RGBA", (*rgb.split(), alpha))
            rgba.save(mf_dir / "export_assembled_rgba.png")

            scan = Image.new("RGB", (40, 100), (120, 120, 120))
            scan.save(mt_dir / "input.png", dpi=(1600, 1600))

            (mf_dir / "export_metadata.json").write_text(
                json.dumps(
                    {
                        "multithread_session_id": "mt",
                        "multifragment_session_id": "mf",
                        "dpi": 1600.0,
                        "width": {
                            "px": 2,
                            "mm": 0.0318,
                            "top_y_in_export": 3,
                            "bottom_y_in_export": 4,
                        },
                        "joins": [],
                        "threads_solid_band": [],
                    }
                ),
                encoding="utf-8",
            )

            entry = yarn_library.save_to_library(
                mf_dir,
                mt_dir,
                library_root=library_root,
                label="dpi-check",
            )

            meta = entry["metadata"]
            scale = meta["physical_scale"]
            self.assertEqual(scale["confidence"], "high")
            self.assertEqual(scale["declared_dpi"], 1600.0)
            self.assertEqual(scale["source_scan"]["filename"], "input.png")
            self.assertTrue(scale["source_scan"]["matches_declared_dpi"])
            self.assertIsNone(scale["processed_export"]["embedded_dpi"])
            self.assertIn("texture_world_width_m", scale)
            yarn_dir = library_root / entry["id"]
            self.assertFalse((yarn_dir / "rgb.png").exists())
            self.assertFalse((yarn_dir / "alpha.png").exists())
            self.assertTrue((yarn_dir / "rgba.png").exists())
            self.assertEqual(meta["files"]["rgba"], "rgba.png")


if __name__ == "__main__":
    unittest.main()
