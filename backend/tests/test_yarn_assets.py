from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import yarn_assets  # noqa: E402


class _NoopThread:
    def __init__(self, target, args=(), kwargs=None, **_):
        self._target = target
        self._args = args
        self._kwargs = kwargs or {}

    def start(self):
        return None


class _ImmediateThread(_NoopThread):
    def start(self):
        self._target(*self._args, **self._kwargs)


class YarnAssetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.assets_root = self.root / "yarn_assets"
        self.assets_root.mkdir(parents=True, exist_ok=True)
        yarn_assets._ASSETS.clear()

        def ensure_dirs() -> None:
            self.assets_root.mkdir(parents=True, exist_ok=True)

        self.patchers = [
            patch.object(yarn_assets, "YARN_ASSETS_ROOT", self.assets_root),
            patch.object(yarn_assets, "ensure_runtime_dirs", ensure_dirs),
        ]
        for patcher in self.patchers:
            patcher.start()

    def tearDown(self) -> None:
        for patcher in reversed(self.patchers):
            patcher.stop()
        yarn_assets._ASSETS.clear()
        self.tempdir.cleanup()

    def test_create_yarn_assets_persists_metadata_and_source_file(self) -> None:
        with patch.object(yarn_assets.threading, "Thread", _NoopThread):
            created = yarn_assets.create_yarn_assets([("Blue Wool.jpg", b"source-bytes")])

        asset_id = created[0]["id"]
        asset = yarn_assets.get_yarn_asset(asset_id)

        self.assertIsNotNone(asset)
        self.assertEqual(asset.status, "queued")
        self.assertTrue((self.assets_root / asset_id / asset.sourceFilename).exists())
        self.assertTrue((self.assets_root / asset_id / "asset.json").exists())
        self.assertEqual(len(yarn_assets.list_yarn_assets()), 1)
        self.assertIsNone(yarn_assets.get_yarn_asset_file_path(asset_id, "../escape.png"))

        yarn_assets.delete_yarn_asset(asset_id)
        self.assertFalse((self.assets_root / asset_id).exists())

    def test_create_yarn_assets_runs_pipeline_and_marks_assets_ready(self) -> None:
        def fake_run_pipeline(*, input_path, output_dir, orientation, keep_intermediate, verbose):
            processed_dir = Path(output_dir)
            processed_dir.mkdir(parents=True, exist_ok=True)
            seamless = processed_dir / "seamless.png"
            alpha = processed_dir / "alpha.png"
            preprocessed = processed_dir / "preprocessed.png"
            seamless.write_bytes(b"diffuse")
            alpha.write_bytes(b"alpha")
            preprocessed.write_bytes(b"pre")
            return {
                "seamless": str(seamless),
                "alpha": str(alpha),
                "preprocessed": str(preprocessed),
                "preprocess_meta": {"keptIntermediate": keep_intermediate, "orientation": orientation},
                "alpha_meta": {"verbose": verbose},
            }

        with patch.object(yarn_assets.threading, "Thread", _ImmediateThread), patch.object(
            yarn_assets,
            "run_pipeline",
            side_effect=fake_run_pipeline,
        ):
            created = yarn_assets.create_yarn_assets([("Striped Yarn.png", b"source-bytes")])

        asset = yarn_assets.get_yarn_asset(created[0]["id"])

        self.assertIsNotNone(asset)
        self.assertEqual(asset.status, "ready")
        self.assertEqual(asset.diffuseFilename, "processed/seamless.png")
        self.assertEqual(asset.alphaFilename, "processed/alpha.png")
        self.assertEqual(asset.preprocessedFilename, "processed/preprocessed.png")
        self.assertEqual(asset.preprocessMeta, {"keptIntermediate": True, "orientation": "auto"})
        self.assertEqual(asset.alphaMeta, {"verbose": False})

    def test_cycles_tiled_texture_set_slices_wide_strip_into_udims(self) -> None:
        diffuse_path = self.root / "albedo.png"
        alpha_path = self.root / "alpha.png"
        Image.new("RGB", (33, 4), (255, 0, 0)).save(diffuse_path)
        Image.new("L", (33, 4), 255).save(alpha_path)

        tiled = yarn_assets.ensure_cycles_tiled_texture_set(
            diffuse_path,
            alpha_path,
            self.root / "cycles_tiled",
            max_dimension=16,
        )

        self.assertIsNotNone(tiled)
        self.assertEqual(tiled["tile_count"], 3)
        self.assertEqual(tiled["tile_width_px"], 11)
        self.assertEqual(tiled["tile_height_px"], 4)
        self.assertEqual(tiled["diffuse_pattern"].name, "albedo_<UDIM>.png")
        self.assertEqual([path.name for path in tiled["diffuse_paths"]], [
            "albedo_1001.png",
            "albedo_1002.png",
            "albedo_1003.png",
        ])
        for tile_path in tiled["diffuse_paths"]:
            with Image.open(tile_path) as tile:
                self.assertLessEqual(tile.size[0], 16)
                self.assertEqual(tile.size[1], 4)


if __name__ == "__main__":
    unittest.main()
