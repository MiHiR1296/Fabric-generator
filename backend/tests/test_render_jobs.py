from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from PIL import Image

from app.atlas import AtlasBundle  # noqa: E402
from app.models import YarnAsset  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.render_jobs import (  # noqa: E402
    DEFAULT_BLEND_FILE,
    DEFAULT_BLENDER_BINARY,
    DEFAULT_PREVIEW_RENDER_RESOLUTION,
    DEFAULT_PREVIEW_RENDER_SAMPLES,
    build_project_material_payloads,
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
        self.assertIn(f"_PW_PREVIEW_RENDER_RESOLUTION = {DEFAULT_PREVIEW_RENDER_RESOLUTION!r}", script)
        self.assertIn(f"_PW_PREVIEW_RENDER_SAMPLES = {DEFAULT_PREVIEW_RENDER_SAMPLES!r}", script)
        self.assertIn("scene.render.resolution_x = int(_PW_PREVIEW_RENDER_RESOLUTION)", script)
        self.assertIn("scene.cycles.samples = int(_PW_PREVIEW_RENDER_SAMPLES)", script)
        self.assertIn("bpy.ops.render.render(write_still=True)", script)

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

    def test_build_headless_render_script_prefers_direct_material_slots(self) -> None:
        atlas = AtlasBundle(
            diffuse_path=Path("/tmp/diffuse_atlas.png"),
            alpha_path=Path("/tmp/alpha_atlas.png"),
            rows=2,
            tile_width=64,
            tile_height=32,
            asset_rows={"asset-red": 0, "asset-blue": 1},
        )
        script = build_headless_render_script(
            {
                "title": "Direct Material Test",
                "drawdown": [[1, 0], [0, 1]],
                "warpColors": ["#ffffff", "#111111"],
                "weftColors": ["#aa0000", "#00aa00"],
            },
            render_path="/tmp/unit-preview.png",
            atlas_bundle=atlas,
            warp_material_ids=[0, 1],
            weft_material_ids=[1, 0],
            material_assets=[
                {
                    "id": "asset-red",
                    "diffuse_path": "/tmp/red.png",
                    "alpha_path": "/tmp/red-alpha.png",
                    "image_width_px": 100,
                    "core_v_min": 0.25,
                    "core_v_max": 0.75,
                },
                {
                    "id": "asset-blue",
                    "diffuse_path": "/tmp/blue.png",
                    "alpha_path": "/tmp/blue-alpha.png",
                    "image_width_px": 200,
                    "core_v_min": 0.2,
                    "core_v_max": 0.8,
                },
            ],
        )

        self.assertIn("preview_materials = build_generated_preview_materials(_PW_MATERIAL_ASSETS)", script)
        self.assertIn("FabricStudioMaterial_", script)
        self.assertIn("texture_node.interpolation = 'Linear'", script)
        self.assertIn("set_modifier_input(modifier, node_group, f'Material {index}', material)", script)
        self.assertIn("apply_material_cycle_inputs(modifier, node_group, 'Warp', weft_ids)", script)
        self.assertIn("_PW_TEXTURE_SCALE_U_MULTIPLIER = float(globals().get('material_texture_scale_u', 1.0))", script)
        self.assertIn("socket_value *= texture_scale_u_multiplier", script)
        self.assertIn("/tmp/red.png", script)

    def test_build_headless_render_script_can_skip_render_for_live_setup(self) -> None:
        script = build_headless_render_script(
            {
                "title": "Setup Only",
                "drawdown": [[1]],
                "warpColors": ["#ffffff"],
                "weftColors": ["#111111"],
            },
            render_path="/tmp/setup-only.png",
            material_assets=[
                {
                    "id": "asset-one",
                    "diffuse_path": "/tmp/one.png",
                    "alpha_path": "/tmp/one-alpha.png",
                },
            ],
            warp_material_ids=[0],
            weft_material_ids=[0],
            render_still=False,
        )

        self.assertIn("setup_only_render_skipped", script)
        self.assertIn("'status': \"setup_ready\"", script)
        self.assertNotIn("bpy.ops.render.render(write_still=True)", script)

    def test_build_headless_render_script_supports_udim_tiled_materials(self) -> None:
        script = build_headless_render_script(
            {
                "title": "UDIM Test",
                "drawdown": [[1]],
                "warpColors": ["#ffffff"],
                "weftColors": ["#111111"],
            },
            render_path="/tmp/udim-preview.png",
            material_assets=[
                {
                    "id": "asset-wide",
                    "diffuse_path": "/tmp/cycles-safe/albedo.png",
                    "alpha_path": "/tmp/cycles-safe/alpha.png",
                    "texture_mode": "udim_tiled",
                    "texture_tile_count": 3,
                    "diffuse_tile_pattern": "/tmp/tiles/albedo_<UDIM>.png",
                    "alpha_tile_pattern": "/tmp/tiles/alpha_<UDIM>.png",
                },
            ],
            warp_material_ids=[0],
            weft_material_ids=[0],
        )

        self.assertIn("ensure_udim_image", script)
        self.assertIn("asset_entry.get('texture_mode') == 'udim_tiled'", script)
        self.assertIn("u_fract.operation = 'FRACT'", script)
        self.assertIn("u_tile_scale.operation = 'MULTIPLY'", script)
        self.assertIn("\"diffuse_tile_pattern\": \"/tmp/tiles/albedo_<UDIM>.png\"", script)

    def test_build_project_material_payloads_generates_udim_tiles_for_wide_assets(self) -> None:
        with TemporaryDirectory() as tmpdir:
            yarn_root = Path(tmpdir)
            asset_dir = yarn_root / "wide-asset"
            asset_dir.mkdir(parents=True)
            Image.new("RGB", (16385, 4), (255, 0, 0)).save(asset_dir / "albedo.png")
            Image.new("L", (16385, 4), 255).save(asset_dir / "alpha.png")
            asset = YarnAsset(
                id="wide-asset",
                label="Wide Asset",
                status="ready",
                sourceFilename="source.png",
                sourceUrl="/source.png",
                diffuseFilename="albedo.png",
                alphaFilename="alpha.png",
            )

            with patch("app.render_jobs.YARN_ASSETS_ROOT", yarn_root):
                _atlas_entries, material_assets = build_project_material_payloads([asset])

            self.assertEqual(material_assets[0]["texture_mode"], "udim_tiled")
            self.assertEqual(material_assets[0]["texture_tile_count"], 2)
            self.assertTrue((asset_dir / "cycles_tiled" / "albedo_1001.png").exists())
            self.assertIn("<UDIM>", material_assets[0]["diffuse_tile_pattern"])

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
                self.assertTrue((captured["job_dir"] / "project.json").exists())
                self.assertTrue((projects_root / "jobabc123def.json").exists())
                self.assertIn("build_generated_preview_materials(_PW_MATERIAL_ASSETS)", captured["script_text"])
                self.assertIn("set_modifier_input(modifier, node_group, f'Material {index}', material)", captured["script_text"])
                self.assertIn('"diffuse_path":', captured["script_text"])
                self.assertNotIn("FabricStudioAtlasMaterial", captured["script_text"])
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
