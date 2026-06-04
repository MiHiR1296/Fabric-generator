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

from app.yarn_pbr import (  # noqa: E402
    GENERATOR_MAJOR,
    PbrPreflightError,
    bake_pbr_map_set,
    validate_asset_pbr,
    vertical_edge_extend_luma,
)


class YarnPbrTests(unittest.TestCase):
    def test_vertical_edge_extend_suppresses_top_bottom_boundary_steps(self) -> None:
        luma = np.zeros((5, 3), dtype=np.float32)
        luma[2, :] = 0.75
        support = np.zeros((5, 3), dtype=bool)
        support[2, :] = True

        filled = vertical_edge_extend_luma(luma, support)

        self.assertTrue(np.allclose(filled, 0.75))

    def test_bake_packs_maps_and_manifest(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            asset_dir = root / "asset"
            pbr_dir = asset_dir / "pbr"
            asset_dir.mkdir(parents=True)
            rgba_path = asset_dir / "rgba.png"
            rgba = Image.new("RGBA", (16, 8), (128, 128, 128, 0))
            for y in range(2, 6):
                for x in range(16):
                    rgba.putpixel((x, y), (80 + x, 90 + x, 100 + x, 255))
            rgba.save(rgba_path)

            manifest = bake_pbr_map_set(rgba_path, pbr_dir, max_dimension=64)

            self.assertTrue((pbr_dir / "manifest.json").exists())
            self.assertTrue((pbr_dir / "normal_height.png").exists())
            self.assertTrue((pbr_dir / "roughness_specular.png").exists())
            self.assertTrue((pbr_dir / "preview.png").exists())
            self.assertEqual(manifest["source_size_px"], [16, 8])
            self.assertEqual(manifest["normal_space"], "OBJECT")
            self.assertNotIn("base_color", manifest["maps"])
            self.assertEqual(manifest["maps"]["anisotropy_tangent"], None)
            with Image.open(pbr_dir / "normal_height.png") as normal_height:
                self.assertEqual(normal_height.mode, "RGBA")
                self.assertEqual(normal_height.getpixel((0, 0)), (128, 128, 255, 128))
            with Image.open(pbr_dir / "roughness_specular.png") as rough_spec:
                self.assertEqual(rough_spec.mode, "RGBA")
                self.assertEqual(rough_spec.getpixel((0, 0))[1], 0)

    def test_validate_fails_on_source_hash_mismatch(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            asset_dir = root / "asset"
            pbr_dir = asset_dir / "pbr"
            asset_dir.mkdir(parents=True)
            rgba_path = asset_dir / "rgba.png"
            Image.new("RGBA", (8, 4), (64, 64, 64, 255)).save(rgba_path)
            manifest = bake_pbr_map_set(rgba_path, pbr_dir, max_dimension=64)
            pbr_maps = {
                "manifestFilename": "pbr/manifest.json",
                "generatorMajor": GENERATOR_MAJOR,
                "sourceSha256": manifest["source_sha256"],
            }
            Image.new("RGBA", (8, 4), (65, 64, 64, 255)).save(rgba_path)

            with self.assertRaises(PbrPreflightError) as ctx:
                validate_asset_pbr(
                    asset_dir=asset_dir,
                    asset_id="asset",
                    asset_label="Asset",
                    pbr_maps=pbr_maps,
                    max_dimension=64,
                )

            self.assertEqual(ctx.exception.stale_reason, "source_sha256_mismatch")

    def test_bake_writes_udim_tiles_for_wide_maps(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            asset_dir = root / "asset"
            pbr_dir = asset_dir / "pbr"
            asset_dir.mkdir(parents=True)
            rgba_path = asset_dir / "rgba.png"
            Image.new("RGBA", (33, 4), (128, 128, 128, 255)).save(rgba_path)

            manifest = bake_pbr_map_set(rgba_path, pbr_dir, max_dimension=16)

            self.assertTrue(manifest["udim"]["enabled"])
            self.assertEqual(manifest["udim"]["tile_count"], 3)
            self.assertTrue((pbr_dir / "cycles_tiled" / "normal_height_1001.png").exists())
            self.assertTrue((pbr_dir / "cycles_tiled" / "roughness_specular_1003.png").exists())


if __name__ == "__main__":
    unittest.main()
