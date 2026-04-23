from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.live_preview import get_preview_snapshot, update_project_preview  # noqa: E402
from app.models import YarnAsset  # noqa: E402


class LivePreviewTests(unittest.TestCase):
    def test_update_project_preview_captures_camera_preview(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            live_preview_root = root / "live_preview"
            yarn_root = root / "yarn_assets"
            asset_root = yarn_root / "asset-red" / "processed"
            asset_root.mkdir(parents=True, exist_ok=True)
            (asset_root / "diffuse.png").write_bytes(b"diffuse")
            (asset_root / "alpha.png").write_bytes(b"alpha")
            commands: list[tuple[str, dict]] = []

            def fake_send_blender_command(command_type: str, params: dict | None = None) -> dict:
                payload = params or {}
                commands.append((command_type, payload))
                if command_type == "execute_code":
                    return {"status": "success", "result": {"status": "preview_ready"}}
                if command_type == "get_viewport_screenshot":
                    filepath = Path(str(payload["filepath"]))
                    filepath.parent.mkdir(parents=True, exist_ok=True)
                    filepath.write_bytes(b"png")
                    return {
                        "status": "success",
                        "result": {
                            "filepath": str(filepath),
                            "width": 1024,
                            "height": 768,
                        },
                    }
                raise AssertionError(f"Unexpected Blender command: {command_type}")

            with patch("app.live_preview.ensure_runtime_dirs", lambda: None), patch(
                "app.live_preview.LIVE_PREVIEW_ROOT",
                live_preview_root,
            ), patch(
                "app.live_preview.YARN_ASSETS_ROOT",
                yarn_root,
            ), patch(
                "app.live_preview.get_ready_yarn_assets_lookup",
                return_value={
                    "asset-red": YarnAsset(
                        id="asset-red",
                        label="Red Yarn",
                        status="ready",
                        sourceFilename="source.png",
                        sourceUrl="/api/yarn/assets/asset-red/files/source.png",
                        diffuseFilename="processed/diffuse.png",
                        diffuseUrl="/api/yarn/assets/asset-red/files/processed/diffuse.png",
                        alphaFilename="processed/alpha.png",
                        alphaUrl="/api/yarn/assets/asset-red/files/processed/alpha.png",
                    )
                },
            ), patch(
                "app.live_preview.send_blender_command",
                side_effect=fake_send_blender_command,
            ):
                preview = update_project_preview(
                    {
                        "draft": {
                            "title": "Preview Draft",
                            "drawdown": [[1, 0], [0, 1]],
                            "warpColors": ["#ffffff", "#ffffff"],
                            "weftColors": ["#000000", "#000000"],
                        },
                        "colorBindings": [
                            {"scope": "warp", "colorHex": "#ffffff", "yarnAssetId": "asset-red"},
                            {"scope": "weft", "colorHex": "#000000", "yarnAssetId": "asset-red"},
                        ],
                    },
                    session_id="Preview Session 01",
                )

            self.assertEqual(preview["status"], "ready")
            self.assertEqual(preview["sessionId"], "Preview-Session-01")
            self.assertIn("/api/blender/live-preview/Preview-Session-01/image", preview["imageUrl"])
            self.assertEqual(preview["width"], 1024)
            self.assertEqual(preview["height"], 768)
            self.assertEqual(preview["message"], "Blender camera preview updated.")
            self.assertEqual(commands[0][0], "execute_code")
            self.assertIn("preview_ready", commands[0][1]["code"])
            self.assertIn("bpy.ops.view3d.view_camera()", commands[0][1]["code"])
            self.assertEqual(commands[1][0], "get_viewport_screenshot")
            self.assertTrue((live_preview_root / "Preview-Session-01" / "preview.png").exists())
            self.assertTrue((live_preview_root / "Preview-Session-01" / "project.json").exists())

            snapshot = get_preview_snapshot("Preview Session 01")
            self.assertEqual(snapshot["status"], "ready")
            self.assertEqual(snapshot["sessionId"], "Preview-Session-01")


if __name__ == "__main__":
    unittest.main()
