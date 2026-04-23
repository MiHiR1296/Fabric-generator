from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app.atlas import AtlasBundle  # noqa: E402
from app.models import YarnAsset  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.render_jobs import (  # noqa: E402
    DEFAULT_BLEND_FILE,
    DEFAULT_BLENDER_BINARY,
    build_headless_render_command,
    build_headless_render_script,
    load_headless_blender_config,
    submit_project_render_job,
)


class RenderJobTests(unittest.TestCase):
    def test_load_headless_blender_config_uses_defaults(self) -> None:
        with patch.dict("os.environ", {}, clear=False):
            config = load_headless_blender_config()

        self.assertEqual(config.blender_binary, DEFAULT_BLENDER_BINARY)
        self.assertEqual(config.blend_file, DEFAULT_BLEND_FILE)

    def test_build_headless_render_script_embeds_render_path_and_target(self) -> None:
        script = build_headless_render_script(
            {
                "title": "Unit Test Draft",
                "drawdown": [
                    [1, 0],
                    [0, 1],
                ],
                "warpColors": ["#ffffff", "#111111"],
                "weftColors": ["#aa0000", "#00aa00"],
            },
            render_path="/tmp/unit-preview.png",
            target_object_name="PreviewWeave",
            draft_object_name="PreviewDraft",
        )

        self.assertIn("Weave From Draft", script)
        self.assertIn("PreviewWeave", script)
        self.assertIn("PreviewDraft", script)
        self.assertIn("/tmp/unit-preview.png", script)
        self.assertIn("bpy.ops.render.render(write_still=True)", script)

    def test_build_headless_render_script_can_override_render_engine_and_samples(self) -> None:
        script = build_headless_render_script(
            {
                "title": "Render Override Draft",
                "drawdown": [[1]],
                "warpColors": ["#ffffff"],
                "weftColors": ["#111111"],
            },
            render_path="/tmp/unit-preview.png",
            render_engine="CYCLES",
            render_samples=12,
        )

        self.assertIn('render_engine_override = "CYCLES"', script)
        self.assertIn("render_samples_override = 12", script)
        self.assertIn("scene.render.engine = render_engine_override", script)
        self.assertIn("scene.cycles.samples = max(1, int(render_samples_override))", script)

    def test_build_headless_render_script_supports_atlas_preview_material(self) -> None:
        atlas = AtlasBundle(
            diffuse_path=Path("/tmp/diffuse_atlas.png"),
            alpha_path=Path("/tmp/alpha_atlas.png"),
            rows=5,
            tile_width=64,
            tile_height=32,
            asset_rows={"asset-1": 0, "asset-2": 1},
        )
        script = build_headless_render_script(
            {
                "title": "Atlas Test Draft",
                "drawdown": [[1, 0], [0, 1]],
                "warpColors": ["#ffffff", "#111111"],
                "weftColors": ["#aa0000", "#00aa00"],
            },
            render_path="/tmp/unit-preview.png",
            atlas_bundle=atlas,
            warp_material_ids=[0, 1],
            weft_material_ids=[1, 0],
        )

        self.assertIn("ensure_atlas_preview_material", script)
        self.assertIn("FabricStudioAtlasMaterial", script)
        self.assertIn("atlas_rows = 5", script)
        self.assertIn("colour_id", script)
        self.assertIn("warp_material_ids = [0, 1]", script)

    def test_build_headless_render_script_supports_template_material_preview(self) -> None:
        script = build_headless_render_script(
            {
                "title": "Template Material Draft",
                "drawdown": [[1, 0], [0, 1]],
                "warpColors": ["#ffffff", "#111111"],
                "weftColors": ["#aa0000", "#00aa00"],
            },
            render_path="/tmp/unit-preview.png",
            warp_material_ids=[0, 1],
            weft_material_ids=[1, 0],
            material_assets=[
                {
                    "id": "asset-red",
                    "diffuse_path": "/tmp/red.png",
                    "alpha_path": "/tmp/red-alpha.png",
                },
                {
                    "id": "asset-black",
                    "diffuse_path": "/tmp/black.png",
                    "alpha_path": "/tmp/black-alpha.png",
                },
            ],
        )

        self.assertIn("build_template_preview_materials", script)
        self.assertIn("MAterial_01", script)
        self.assertIn("ensure_colour_material_chain", script)
        self.assertIn("Render Material Match", script)
        self.assertIn("colour_id", script)
        self.assertIn('"diffusePath": "/tmp/red.png"', script)

    def test_build_headless_render_script_supports_preview_only_material_view(self) -> None:
        script = build_headless_render_script(
            {
                "title": "Preview Only Draft",
                "drawdown": [[1, 0], [0, 1]],
                "warpColors": ["#ffffff"],
                "weftColors": ["#111111"],
            },
            render_path="/tmp/live-preview.png",
            material_assets=[
                {
                    "id": "asset-red",
                    "diffuse_path": "/tmp/red.png",
                    "alpha_path": "/tmp/red-alpha.png",
                }
            ],
            preview_only=True,
        )

        self.assertIn("ensure_material_camera_view", script)
        self.assertIn("bpy.ops.view3d.view_camera()", script)
        self.assertIn("space.shading.type = 'MATERIAL'", script)
        self.assertIn("'status': 'preview_ready'", script)
        self.assertNotIn("bpy.ops.render.render(write_still=True)", script)

    def test_build_headless_render_command_points_to_blend_file_and_script(self) -> None:
        fake_binary = ROOT / "tests" / "fixtures" / "blender-bin"
        fake_blend = ROOT / "tests" / "fixtures" / "preview.blend"
        fake_binary.parent.mkdir(parents=True, exist_ok=True)
        fake_binary.write_text("", encoding="utf-8")
        fake_blend.write_text("", encoding="utf-8")

        config = load_headless_blender_config()
        config = config.__class__(
            blender_binary=fake_binary,
            blend_file=fake_blend,
            runtime_root=ROOT / "tests" / "fixtures" / "runtime",
        )

        command = build_headless_render_command(config, script_path="/tmp/render-script.py")
        self.assertEqual(
            command,
            [
                str(fake_binary),
                "-b",
                str(fake_blend),
                "--python",
                "/tmp/render-script.py",
            ],
        )

    def test_submit_project_render_job_builds_project_payload_and_material_ids(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            runtime_root = root / "render_jobs"
            projects_root = root / "projects"
            yarn_root = root / "yarn_assets"
            captured: dict[str, object] = {}

            def fake_build_yarn_atlas(asset_images, output_dir):
                captured["atlas_entries"] = asset_images
                output_dir.mkdir(parents=True, exist_ok=True)
                diffuse_path = output_dir / "diffuse_atlas.png"
                alpha_path = output_dir / "alpha_atlas.png"
                diffuse_path.write_bytes(b"diffuse")
                alpha_path.write_bytes(b"alpha")
                return AtlasBundle(
                    diffuse_path=diffuse_path,
                    alpha_path=alpha_path,
                    rows=2,
                    tile_width=32,
                    tile_height=32,
                    asset_rows={"asset-red": 0, "asset-black": 1},
                )

            def fake_create_render_job(
                draft_title,
                target_object_name,
                draft_object_name,
                job_dir,
                script_text,
                payload,
            ):
                captured["draft_title"] = draft_title
                captured["target_object_name"] = target_object_name
                captured["draft_object_name"] = draft_object_name
                captured["job_dir"] = job_dir
                captured["script_text"] = script_text
                captured["payload"] = payload
                return {
                    "id": job_dir.name,
                    "status": "queued",
                    "message": "queued",
                    "draftTitle": draft_title,
                    "targetObjectName": target_object_name,
                    "draftObjectName": draft_object_name,
                    "createdAt": "2026-04-22T00:00:00Z",
                    "imageUrl": None,
                    "logTail": [],
                }

            class FakeUuid:
                hex = "jobabc123def456789"

            assets_lookup = {
                "asset-red": YarnAsset(
                    id="asset-red",
                    label="Red Yarn",
                    status="ready",
                    sourceFilename="source.png",
                    sourceUrl="/api/yarn/assets/asset-red/files/source.png",
                    diffuseFilename="processed/red.png",
                    diffuseUrl="/api/yarn/assets/asset-red/files/processed/red.png",
                    alphaFilename="processed/red-alpha.png",
                    alphaUrl="/api/yarn/assets/asset-red/files/processed/red-alpha.png",
                ),
                "asset-black": YarnAsset(
                    id="asset-black",
                    label="Black Yarn",
                    status="ready",
                    sourceFilename="source.png",
                    sourceUrl="/api/yarn/assets/asset-black/files/source.png",
                    diffuseFilename="processed/black.png",
                    diffuseUrl="/api/yarn/assets/asset-black/files/processed/black.png",
                    alphaFilename="processed/black-alpha.png",
                    alphaUrl="/api/yarn/assets/asset-black/files/processed/black-alpha.png",
                ),
            }

            project_payload = {
                "draft": {
                    "title": "Atlas Project",
                    "drawdown": [[1, 0], [0, 1]],
                    "warpColors": ["#ffffff", "#000000"],
                    "weftColors": ["#000000", "#ffffff"],
                },
                "colorBindings": [
                    {"scope": "warp", "colorHex": "#ffffff", "yarnAssetId": "asset-red"},
                    {"scope": "warp", "colorHex": "#000000", "yarnAssetId": "asset-black"},
                    {"scope": "weft", "colorHex": "#000000", "yarnAssetId": "asset-black"},
                    {"scope": "weft", "colorHex": "#ffffff", "yarnAssetId": "asset-red"},
                ],
            }

            with patch("app.render_jobs.DEFAULT_RUNTIME_ROOT", runtime_root), patch(
                "app.render_jobs.PROJECTS_ROOT",
                projects_root,
            ), patch("app.render_jobs.YARN_ASSETS_ROOT", yarn_root), patch(
                "app.render_jobs.ensure_runtime_dirs",
                lambda: None,
            ), patch(
                "app.render_jobs.get_ready_yarn_assets_lookup",
                return_value=assets_lookup,
            ), patch(
                "app.render_jobs.build_yarn_atlas",
                side_effect=fake_build_yarn_atlas,
            ), patch(
                "app.render_jobs._create_render_job",
                side_effect=fake_create_render_job,
            ), patch("app.render_jobs.uuid.uuid4", return_value=FakeUuid()):
                snapshot = submit_project_render_job(project_payload)
                self.assertEqual(snapshot["id"], "jobabc123def")
                self.assertEqual(snapshot["status"], "queued")
                self.assertEqual(captured["draft_title"], "Atlas Project")
                self.assertEqual(captured["payload"]["warpMaterialIds"], [0, 1])
                self.assertEqual(captured["payload"]["weftMaterialIds"], [1, 0])
                self.assertEqual(captured["payload"]["atlas"]["rows"], 2)
                self.assertEqual(len(captured["payload"]["materialAssets"]), 2)
                self.assertTrue((captured["job_dir"] / "project.json").exists())
                self.assertTrue((projects_root / "jobabc123def.json").exists())
                self.assertIn("build_template_preview_materials", captured["script_text"])
                self.assertIn("MAterial_01", captured["script_text"])
                self.assertEqual(
                    captured["atlas_entries"],
                    [
                        {
                            "id": "asset-red",
                            "diffuse_path": yarn_root / "asset-red" / "processed/red.png",
                            "alpha_path": yarn_root / "asset-red" / "processed/red-alpha.png",
                        },
                        {
                            "id": "asset-black",
                            "diffuse_path": yarn_root / "asset-black" / "processed/black.png",
                            "alpha_path": yarn_root / "asset-black" / "processed/black-alpha.png",
                        },
                    ],
                )


if __name__ == "__main__":
    unittest.main()
