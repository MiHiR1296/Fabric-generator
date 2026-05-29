from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.atlas import build_yarn_atlas  # noqa: E402


class AtlasTests(unittest.TestCase):
    def test_build_yarn_atlas_packs_assets_into_vertical_rows(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            red_diffuse = root / "red_diffuse.png"
            red_alpha = root / "red_alpha.png"
            green_diffuse = root / "green_diffuse.png"
            green_alpha = root / "green_alpha.png"

            Image.new("RGB", (2, 2), (255, 0, 0)).save(red_diffuse)
            Image.new("L", (2, 2), 255).save(red_alpha)
            Image.new("RGB", (1, 3), (0, 255, 0)).save(green_diffuse)
            Image.new("L", (1, 3), 128).save(green_alpha)

            bundle = build_yarn_atlas(
                [
                    {
                        "id": "red",
                        "diffuse_path": red_diffuse,
                        "alpha_path": red_alpha,
                    },
                    {
                        "id": "green",
                        "diffuse_path": green_diffuse,
                        "alpha_path": green_alpha,
                    },
                ],
                root / "atlas",
            )

            diffuse = Image.open(bundle.diffuse_path)
            alpha = Image.open(bundle.alpha_path)

            self.assertEqual(bundle.rows, 2)
            self.assertEqual(bundle.tile_width, 2)
            self.assertEqual(bundle.tile_height, 3)
            self.assertEqual(bundle.asset_rows, {"red": 0, "green": 1})
            self.assertEqual(diffuse.size, (2, 6))
            self.assertEqual(alpha.size, (2, 6))
            self.assertEqual(diffuse.getpixel((0, 5)), (255, 0, 0))
            self.assertEqual(diffuse.getpixel((0, 0)), (0, 255, 0))
            self.assertEqual(alpha.getpixel((0, 5)), 255)
            self.assertEqual(alpha.getpixel((0, 0)), 128)

    def test_build_yarn_atlas_can_read_rgba_without_split_files(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            rgba_path = root / "rgba.png"
            Image.new("RGBA", (2, 2), (10, 20, 30, 128)).save(rgba_path)

            bundle = build_yarn_atlas(
                [
                    {
                        "id": "rgba",
                        "rgba_path": rgba_path,
                    },
                ],
                root / "atlas",
            )

            diffuse = Image.open(bundle.diffuse_path)
            alpha = Image.open(bundle.alpha_path)
            self.assertEqual(diffuse.getpixel((0, 0)), (10, 20, 30))
            self.assertEqual(alpha.getpixel((0, 0)), 128)


if __name__ == "__main__":
    unittest.main()
