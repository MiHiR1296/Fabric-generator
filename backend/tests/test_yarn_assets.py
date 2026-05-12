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
        def fake_run_pipeline(*, input_path, output_dir, keep_intermediate, verbose):
            processed_dir = Path(output_dir)
            processed_dir.mkdir(parents=True, exist_ok=True)
            seamless = processed_dir / "seamless.png"
            alpha = processed_dir / "alpha.png"
            preprocessed = processed_dir / "preprocessed.png"
            Image.new("RGB", (8, 4), (120, 80, 40)).save(seamless)
            Image.new("L", (8, 4), 255).save(alpha)
            Image.new("RGB", (8, 4), (160, 120, 80)).save(preprocessed)
            return {
                "seamless": str(seamless),
                "alpha": str(alpha),
                "preprocessed": str(preprocessed),
                "preprocess_meta": {"keptIntermediate": keep_intermediate},
                "alpha_meta": {"verbose": verbose},
            }

        def fake_segment_yarn_bands(rgb_path, alpha_path, output_dir, name, verbose):
            band_dir = Path(output_dir) / name
            band_dir.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (8, 4), (128, 128, 255)).save(band_dir / "normal.png")
            Image.new("L", (8, 4), 180).save(band_dir / "roughness.png")
            Image.new("RGB", (8, 4), (255, 0, 0)).save(band_dir / "overlay.png")
            meta = {
                "image_size_px": [8, 4],
                "bands_v_norm": {
                    "core": [0.4, 0.6],
                    "fiber_top": [0.6, 0.8],
                    "fiber_bot": [0.2, 0.4],
                },
                "twist": {"twist_period_px": 2.0, "confidence": 0.8},
            }
            (band_dir / "meta.json").write_text("{}", encoding="utf-8")
            return meta

        with patch.object(yarn_assets.threading, "Thread", _ImmediateThread), patch.object(
            yarn_assets,
            "run_pipeline",
            side_effect=fake_run_pipeline,
        ), patch.object(
            yarn_assets,
            "segment_yarn_bands",
            side_effect=fake_segment_yarn_bands,
        ):
            created = yarn_assets.create_yarn_assets([("Striped Yarn.png", b"source-bytes")])

        asset = yarn_assets.get_yarn_asset(created[0]["id"])

        self.assertIsNotNone(asset)
        self.assertEqual(asset.status, "ready")
        self.assertEqual(asset.diffuseFilename, "processed/seamless.png")
        self.assertEqual(asset.alphaFilename, "processed/alpha.png")
        self.assertEqual(asset.preprocessedFilename, "processed/preprocessed.png")
        self.assertEqual(asset.renderDiffuseFilename, "processed/seamless.png")
        self.assertEqual(asset.renderAlphaFilename, "processed/alpha.png")
        self.assertEqual(asset.normalFilename, "processed/bands/analysis/normal.png")
        self.assertEqual(asset.roughnessFilename, "processed/bands/analysis/roughness.png")
        self.assertEqual(asset.overlayFilename, "processed/bands/analysis/overlay.png")
        self.assertEqual(asset.bandMetaFilename, "processed/bands/analysis/meta.json")
        self.assertEqual(asset.preprocessMeta, {"keptIntermediate": True})
        self.assertEqual(asset.alphaMeta, {"verbose": False})
        self.assertEqual(asset.bandMeta["image_size_px"], [8, 4])


if __name__ == "__main__":
    unittest.main()
