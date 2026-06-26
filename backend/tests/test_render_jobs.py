from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.atlas import AtlasBundle  # noqa: E402
from app.models import YarnAsset  # noqa: E402
from app.render_jobs import (  # noqa: E402
    DEFAULT_ALPHA_CURVE_GAMMA,
    DEFAULT_ALPHA_REMAP_ENABLED,
    DEFAULT_ALPHA_REMAP_HIGH,
    DEFAULT_ALPHA_REMAP_LOW,
    DEFAULT_BLEND_FILE,
    DEFAULT_BLENDER_BINARY,
    DEFAULT_CUTOUT_BLEND_METHOD,
    DEFAULT_PREVIEW_MATERIAL_ROUGHNESS,
    DEFAULT_PREVIEW_MATERIAL_SHEEN,
    DEFAULT_PREVIEW_RENDER_RESOLUTION,
    DEFAULT_PREVIEW_RENDER_SAMPLES,
    DEFAULT_SURFACE_RENDER_METHOD,
    DEFAULT_TEXTURE_INTERPOLATION,
    DEFAULT_TILE_ORTHO_SCALE,
    DEFAULT_TILE_REPAIR_COLOR_MATCH_STRENGTH,
    DEFAULT_TILE_REPAIR_SEAM_RADIUS,
    DEFAULT_TILE_RENDER_SAMPLES,
    RenderJob,
    _JOBS,
    build_project_material_payloads,
    build_headless_render_command,
    build_headless_render_script,
    get_tile_source_image_path,
    load_headless_blender_config,
    submit_hook_project_render_job,
    submit_project_render_job,
    _job_snapshot,
    _next_multiple,
    _normalize_tile_options,
    _stitch_tile_grid,
    _wrapped_segments,
)
from app.yarn_pbr import (  # noqa: E402
    PbrPreflightError,
    bake_pbr_map_set,
    build_asset_pbr_summary,
)


def _attach_pbr(asset: YarnAsset, asset_dir: Path, rgba_path: Path, *, max_dimension: int = 16384) -> None:
    manifest = bake_pbr_map_set(rgba_path, asset_dir / "pbr", max_dimension=max_dimension)
    asset.pbrMaps = build_asset_pbr_summary(asset_dir, manifest)


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
        self.assertIn(f"_PW_TEXTURE_INTERPOLATION = {DEFAULT_TEXTURE_INTERPOLATION!r}", script)
        self.assertIn(f"_PW_CUTOUT_BLEND_METHOD = {DEFAULT_CUTOUT_BLEND_METHOD!r}", script)
        self.assertIn(f"_PW_SURFACE_RENDER_METHOD = {DEFAULT_SURFACE_RENDER_METHOD!r}", script)
        self.assertIn(f"_PW_PREVIEW_MATERIAL_ROUGHNESS = {DEFAULT_PREVIEW_MATERIAL_ROUGHNESS!r}", script)
        self.assertIn(f"_PW_PREVIEW_MATERIAL_SHEEN = {DEFAULT_PREVIEW_MATERIAL_SHEEN!r}", script)
        self.assertIn("set_principled_input(shader, ('Roughness',), _PW_PREVIEW_MATERIAL_ROUGHNESS)", script)
        self.assertIn("set_principled_input(shader, ('Sheen Weight', 'Sheen'), _PW_PREVIEW_MATERIAL_SHEEN)", script)
        self.assertIn("texture_node.interpolation = _PW_TEXTURE_INTERPOLATION", script)
        self.assertIn("link_alpha_to_shader(nodes, links, alpha_output, shader.inputs['Alpha'])", script)
        self.assertIn("if not _PW_ALPHA_REMAP_ENABLED:", script)
        self.assertIn("links.new(alpha_output, shader_alpha_input)", script)
        self.assertIn(f"_PW_ALPHA_REMAP_ENABLED = {DEFAULT_ALPHA_REMAP_ENABLED!r}", script)
        self.assertIn(f"_PW_ALPHA_REMAP_LOW = {DEFAULT_ALPHA_REMAP_LOW!r}", script)
        self.assertIn(f"_PW_ALPHA_REMAP_HIGH = {DEFAULT_ALPHA_REMAP_HIGH!r}", script)
        self.assertIn(f"_PW_ALPHA_CURVE_GAMMA = {DEFAULT_ALPHA_CURVE_GAMMA!r}", script)
        self.assertIn("material.blend_method = _PW_CUTOUT_BLEND_METHOD", script)
        self.assertIn("material.surface_render_method = _PW_SURFACE_RENDER_METHOD", script)
        self.assertIn("set_modifier_input(modifier, node_group, f'Material {index}', material)", script)
        self.assertIn("apply_material_cycle_inputs(modifier, node_group, 'Warp', warp_ids)", script)
        self.assertIn("apply_material_cycle_inputs(modifier, node_group, 'Weft', weft_ids)", script)
        self.assertNotIn("apply_material_cycle_inputs(modifier, node_group, 'Warp', weft_ids)", script)
        self.assertIn("_PW_TEXTURE_SCALE_U_MULTIPLIER = float(globals().get('material_texture_scale_u', 1.0))", script)
        self.assertIn("_pw_resolved_texture_scale_u(entry, modifier, node_group) * texture_scale_u_multiplier", script)
        self.assertIn("/tmp/red.png", script)

    def test_build_headless_render_script_supports_alpha_remap_overrides(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "WEAVE_ALPHA_REMAP_ENABLED": "1",
                "WEAVE_ALPHA_REMAP_LOW": "0.04",
                "WEAVE_ALPHA_REMAP_HIGH": "0.55",
                "WEAVE_ALPHA_CURVE_GAMMA": "0.75",
            },
        ):
            script = build_headless_render_script(
                {
                    "title": "Alpha Override Test",
                    "drawdown": [[1]],
                    "warpColors": ["#ffffff"],
                    "weftColors": ["#111111"],
                },
                render_path="/tmp/unit-preview.png",
                material_assets=[
                    {
                        "id": "asset-one",
                        "diffuse_path": "/tmp/one.png",
                        "alpha_path": "/tmp/one-alpha.png",
                    },
                ],
                warp_material_ids=[0],
                weft_material_ids=[0],
            )

        self.assertIn("_PW_ALPHA_REMAP_ENABLED = True", script)
        self.assertIn("_PW_ALPHA_REMAP_LOW = 0.04", script)
        self.assertIn("_PW_ALPHA_REMAP_HIGH = 0.55", script)
        self.assertIn("_PW_ALPHA_CURVE_GAMMA = 0.75", script)
        self.assertIn("FabricStudioAlphaRemap", script)
        self.assertIn("FabricStudioAlphaCurve", script)

    def test_build_headless_render_script_loads_material_json_with_python_booleans(self) -> None:
        script = build_headless_render_script(
            {
                "title": "Boolean Payload Test",
                "drawdown": [[1]],
                "warpColors": ["#ffffff"],
                "weftColors": ["#111111"],
            },
            render_path="/tmp/unit-preview.png",
            material_assets=[
                {
                    "id": "asset-one",
                    "diffuse_path": "/tmp/one.png",
                    "alpha_path": "/tmp/one-alpha.png",
                    "texture_scale_u_is_auto": True,
                },
            ],
            warp_material_ids=[0],
            weft_material_ids=[0],
        )

        line = next(line for line in script.splitlines() if line.startswith("_PW_MATERIAL_ASSETS = "))
        namespace = {"json": json}
        exec(line, namespace)
        self.assertTrue(namespace["_PW_MATERIAL_ASSETS"][0]["texture_scale_u_is_auto"])

    def test_build_headless_render_script_supports_texture_interpolation_override(self) -> None:
        with patch.dict("os.environ", {"WEAVE_TEXTURE_INTERPOLATION": "Closest"}):
            script = build_headless_render_script(
                {
                    "title": "Sharp Texture Test",
                    "drawdown": [[1]],
                    "warpColors": ["#ffffff"],
                    "weftColors": ["#111111"],
                },
                render_path="/tmp/unit-preview.png",
                material_assets=[
                    {
                        "id": "asset-one",
                        "diffuse_path": "/tmp/one.png",
                        "alpha_path": "/tmp/one-alpha.png",
                    },
                ],
                warp_material_ids=[0],
                weft_material_ids=[0],
            )

        self.assertIn("_PW_TEXTURE_INTERPOLATION = 'Closest'", script)

    def test_build_headless_render_script_wires_packed_pbr_nodes(self) -> None:
        script = build_headless_render_script(
            {
                "title": "PBR Material Test",
                "drawdown": [[1]],
                "warpColors": ["#ffffff"],
                "weftColors": ["#111111"],
            },
            render_path="/tmp/unit-preview.png",
            material_assets=[
                {
                    "id": "asset-one",
                    "rgba_path": "/tmp/one-rgba.png",
                    "texture_mode": "rgba_single",
                    "pbr_texture_mode": "pbr_single",
                    "pbr_normal_height_path": "/tmp/normal_height.png",
                    "pbr_roughness_specular_path": "/tmp/roughness_specular.png",
                    "pbr_consumer_defaults": {
                        "normal_strength": 0.1,
                        "bump_strength": 1.0,
                        "bump_distance_bu": 0.0008,
                    },
                },
            ],
            warp_material_ids=[0],
            weft_material_ids=[0],
        )

        self.assertIn("FabricStudioNormalHeightNode", script)
        self.assertIn("FabricStudioRoughnessSpecularNode", script)
        self.assertIn("normal_map.inputs['Strength'].default_value = pbr_consumer_default(asset_entry, 'normal_strength', 0.1)", script)
        self.assertIn("bump.inputs['Strength'].default_value = pbr_consumer_default(asset_entry, 'bump_strength', 1.0)", script)
        self.assertIn("normal_map.space = 'OBJECT'", script)
        self.assertIn("links.new(normal_map.outputs['Normal'], bump.inputs['Normal'])", script)
        self.assertIn("links.new(normal_height_tex.outputs['Alpha'], bump.inputs['Height'])", script)
        self.assertIn("links.new(bump.outputs['Normal'], shader.inputs['Normal'])", script)
        self.assertIn("first_socket(shader.inputs, ('Specular IOR Level',))", script)

    def test_build_headless_render_script_supports_cutout_preview_overrides(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "WEAVE_CUTOUT_BLEND_METHOD": "HASHED",
                "WEAVE_SURFACE_RENDER_METHOD": "DITHERED",
            },
        ):
            script = build_headless_render_script(
                {
                    "title": "Cutout Preview Test",
                    "drawdown": [[1]],
                    "warpColors": ["#ffffff"],
                    "weftColors": ["#111111"],
                },
                render_path="/tmp/unit-preview.png",
                material_assets=[
                    {
                        "id": "asset-one",
                        "diffuse_path": "/tmp/one.png",
                        "alpha_path": "/tmp/one-alpha.png",
                    },
                ],
                warp_material_ids=[0],
                weft_material_ids=[0],
            )

        self.assertIn("_PW_CUTOUT_BLEND_METHOD = 'HASHED'", script)
        self.assertIn("_PW_SURFACE_RENDER_METHOD = 'DITHERED'", script)

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

    def test_build_headless_render_script_can_configure_tile_camera(self) -> None:
        normal_script = build_headless_render_script(
            {
                "title": "Normal",
                "drawdown": [[1]],
                "warpColors": ["#ffffff"],
                "weftColors": ["#111111"],
            },
            render_path="/tmp/normal-preview.png",
        )
        tile_script = build_headless_render_script(
            {
                "title": "Tile",
                "drawdown": [[1]],
                "warpColors": ["#ffffff"],
                "weftColors": ["#111111"],
            },
            render_path="/tmp/tile-preview.png",
            render_samples=DEFAULT_TILE_RENDER_SAMPLES,
            tile_render_mode=True,
            tile_ortho_scale=DEFAULT_TILE_ORTHO_SCALE,
        )

        self.assertNotIn("SeamlessTileCamera", normal_script)
        self.assertIn("SeamlessTileCamera", tile_script)
        self.assertIn(f"_PW_PREVIEW_RENDER_SAMPLES = {DEFAULT_TILE_RENDER_SAMPLES!r}", tile_script)
        self.assertIn(f"_PW_TILE_ORTHO_SCALE = {DEFAULT_TILE_ORTHO_SCALE!r}", tile_script)
        self.assertIn("camera_data.type = 'ORTHO'", tile_script)
        self.assertIn("camera_data.name = 'SeamlessTileCameraData'", tile_script)
        self.assertIn("scene.camera = camera_obj", tile_script)

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

    def test_build_headless_render_script_supports_rgba_udim_tiled_materials(self) -> None:
        atlas = AtlasBundle(
            diffuse_path=Path("/tmp/diffuse_atlas.png"),
            alpha_path=Path("/tmp/alpha_atlas.png"),
            rows=1,
            tile_width=64,
            tile_height=32,
            asset_rows={"asset-wide": 0},
        )
        script = build_headless_render_script(
            {
                "title": "RGBA UDIM Test",
                "drawdown": [[1]],
                "warpColors": ["#ffffff"],
                "weftColors": ["#111111"],
            },
            render_path="/tmp/rgba-udim-preview.png",
            atlas_bundle=atlas,
            material_assets=[
                {
                    "id": "asset-wide",
                    "texture_mode": "udim_rgba_tiled",
                    "texture_tile_count": 3,
                    "rgba_tile_pattern": "/tmp/tiles/rgba_<UDIM>.png",
                },
            ],
            warp_material_ids=[0],
            weft_material_ids=[0],
        )

        self.assertIn("use_rgba_tiled = (", script)
        self.assertIn("asset_entry.get('texture_mode') == 'udim_rgba_tiled'", script)
        self.assertIn("asset_entry['rgba_tile_pattern']", script)
        self.assertNotIn('f"{material_name}_RGBA_Alpha_UDIM"', script)
        self.assertIn("preview_materials = build_generated_preview_materials(_PW_MATERIAL_ASSETS)", script)
        self.assertNotIn("preview_materials = [ensure_atlas_preview_material", script)
        self.assertIn("alpha_output = diffuse_tex.outputs['Alpha'] if (use_rgba_tiled or use_rgba_single) else alpha_tex.outputs['Color']", script)
        self.assertIn("\"rgba_tile_pattern\": \"/tmp/tiles/rgba_<UDIM>.png\"", script)

    def test_build_headless_render_script_supports_rgba_single_materials(self) -> None:
        atlas = AtlasBundle(
            diffuse_path=Path("/tmp/diffuse_atlas.png"),
            alpha_path=Path("/tmp/alpha_atlas.png"),
            rows=1,
            tile_width=64,
            tile_height=32,
            asset_rows={"asset-rgba": 0},
        )
        script = build_headless_render_script(
            {
                "title": "RGBA Single Test",
                "drawdown": [[1]],
                "warpColors": ["#ffffff"],
                "weftColors": ["#111111"],
            },
            render_path="/tmp/rgba-single-preview.png",
            atlas_bundle=atlas,
            material_assets=[
                {
                    "id": "asset-rgba",
                    "texture_mode": "rgba_single",
                    "rgba_path": "/tmp/assets/rgba.png",
                },
            ],
            warp_material_ids=[0],
            weft_material_ids=[0],
        )

        self.assertIn("use_rgba_single = (", script)
        self.assertIn("asset_entry.get('texture_mode') == 'rgba_single'", script)
        self.assertIn("asset_entry['rgba_path']", script)
        self.assertIn("diffuse_tex.image = ensure_image(f\"{material_name}_RGBA\", asset_entry['rgba_path'], 'sRGB')", script)
        self.assertNotIn("alpha_tex.image = ensure_image(f\"{material_name}_RGBA_Alpha\", asset_entry['rgba_path'], 'Non-Color')", script)
        self.assertIn("bpy.data.images.load(image_path, check_existing=False)", script)
        self.assertIn("preview_materials = build_generated_preview_materials(_PW_MATERIAL_ASSETS)", script)
        self.assertNotIn("preview_materials = [ensure_atlas_preview_material", script)
        self.assertIn("alpha_output = diffuse_tex.outputs['Alpha'] if (use_rgba_tiled or use_rgba_single) else alpha_tex.outputs['Color']", script)

    def test_tile_helpers_align_repeats_and_wrap_segments(self) -> None:
        self.assertEqual(_next_multiple(81, 8), 88)
        self.assertEqual(_next_multiple(80, 8), 80)
        self.assertEqual(
            _wrapped_segments(5, -1, 4),
            [(0, 1, 3, 4), (1, 5, 0, 4)],
        )

    def test_stitch_tile_grid_pastes_zero_guard_tiles_without_blending(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            output_path = root / "stitched.png"
            colours = [
                (10, 0, 0, 255),
                (20, 0, 0, 255),
                (30, 0, 0, 255),
                (40, 0, 0, 255),
            ]
            tile_paths = []
            for index, colour in enumerate(colours):
                tile_path = root / f"tile_{index}.png"
                Image.new("RGBA", (1, 1), colour).save(tile_path)
                tile_paths.append(tile_path)

            _stitch_tile_grid(
                tile_paths,
                output_path=output_path,
                columns=2,
                rows=2,
                tile_resolution=1,
                guard_px=0,
            )

            with Image.open(output_path) as stitched:
                self.assertEqual(stitched.size, (2, 2))
                self.assertEqual(stitched.getpixel((0, 0)), colours[0])
                self.assertEqual(stitched.getpixel((1, 0)), colours[1])
                self.assertEqual(stitched.getpixel((0, 1)), colours[2])
                self.assertEqual(stitched.getpixel((1, 1)), colours[3])

    def test_stitch_tile_grid_rejects_mismatched_zero_guard_tile_size(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            tile_path = root / "tile.png"
            Image.new("RGBA", (2, 1), (10, 0, 0, 255)).save(tile_path)

            with self.assertRaises(ValueError):
                _stitch_tile_grid(
                    [tile_path],
                    output_path=root / "stitched.png",
                    columns=1,
                    rows=1,
                    tile_resolution=1,
                    guard_px=0,
                )

    def test_tile_options_default_to_2x2_seam_repair_flow(self) -> None:
        options = _normalize_tile_options(
            {
                "tileCount": 12,
                "tileResolution": 1200,
                "guardThreads": 0,
                "variationStrength": 0.25,
            }
        )

        self.assertEqual(options["tileCount"], 4)
        self.assertEqual(options["columns"], 2)
        self.assertEqual(options["rows"], 2)
        self.assertEqual(options["tileResolution"], 1200)
        self.assertEqual(options["guardThreads"], 0)
        self.assertEqual(options["variationStrength"], 0.0)
        self.assertEqual(DEFAULT_TILE_REPAIR_SEAM_RADIUS, 12)
        self.assertEqual(DEFAULT_TILE_REPAIR_COLOR_MATCH_STRENGTH, 1.2)

    def test_tile_source_artifacts_are_exposed_in_job_snapshot(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            final_path = root / "tile_export.png"
            source_path = root / "source_tile_01.png"
            Image.new("RGBA", (1, 1), (10, 20, 30, 255)).save(final_path)
            Image.new("RGBA", (1, 1), (40, 50, 60, 255)).save(source_path)
            job = RenderJob(
                id="tiles_test",
                status="succeeded",
                message="done",
                draft_title="Draft",
                target_object_name="ParametricWeave",
                draft_object_name="WebDraft_Live",
                created_at="2026-05-26T00:00:00Z",
                job_dir=root,
                render_path=final_path,
                script_path=root / "tile_export.json",
                stdout_path=root / "stdout.log",
                stderr_path=root / "stderr.log",
                tile_source_paths=[source_path],
            )

            snapshot = _job_snapshot(job)

            self.assertEqual(
                snapshot["tileSourceImageUrls"],
                ["/api/blender/render-jobs/tiles_test/tile-sources/1"],
            )

    def test_get_tile_source_image_path_returns_saved_artifact(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_path = root / "source_tile_01.png"
            Image.new("RGBA", (1, 1), (40, 50, 60, 255)).save(source_path)
            job = RenderJob(
                id="tiles_lookup",
                status="succeeded",
                message="done",
                draft_title="Draft",
                target_object_name="ParametricWeave",
                draft_object_name="WebDraft_Live",
                created_at="2026-05-26T00:00:00Z",
                job_dir=root,
                render_path=root / "tile_export.png",
                script_path=root / "tile_export.json",
                stdout_path=root / "stdout.log",
                stderr_path=root / "stderr.log",
                tile_source_paths=[source_path],
            )
            _JOBS[job.id] = job
            try:
                self.assertEqual(get_tile_source_image_path("tiles_lookup", 1), source_path)
                self.assertIsNone(get_tile_source_image_path("tiles_lookup", 2))
            finally:
                _JOBS.pop(job.id, None)

    def test_build_project_material_payloads_generates_udim_tiles_for_wide_assets(self) -> None:
        with TemporaryDirectory() as tmpdir:
            yarn_root = Path(tmpdir)
            asset_dir = yarn_root / "wide-asset"
            asset_dir.mkdir(parents=True)
            Image.new("RGB", (16385, 4), (255, 0, 0)).save(asset_dir / "albedo.png")
            Image.new("L", (16385, 4), 255).save(asset_dir / "alpha.png")
            Image.new("RGBA", (16385, 4), (255, 0, 0, 255)).save(asset_dir / "rgba.png")
            asset = YarnAsset(
                id="wide-asset",
                label="Wide Asset",
                status="ready",
                sourceFilename="source.png",
                sourceUrl="/source.png",
                diffuseFilename="albedo.png",
                alphaFilename="alpha.png",
            )
            _attach_pbr(asset, asset_dir, asset_dir / "rgba.png", max_dimension=16384)

            with patch("app.render_jobs.YARN_ASSETS_ROOT", yarn_root):
                _atlas_entries, material_assets = build_project_material_payloads([asset])

            self.assertEqual(material_assets[0]["texture_mode"], "udim_tiled")
            self.assertEqual(material_assets[0]["texture_tile_count"], 2)
            self.assertEqual(material_assets[0]["pbr_texture_mode"], "pbr_udim_tiled")
            self.assertTrue((asset_dir / "cycles_tiled" / "albedo_1001.png").exists())
            self.assertIn("<UDIM>", material_assets[0]["diffuse_tile_pattern"])

    def test_build_project_material_payloads_prefers_rgba_udim_tiles_for_wide_assets(self) -> None:
        with TemporaryDirectory() as tmpdir:
            yarn_root = Path(tmpdir)
            asset_dir = yarn_root / "wide-rgba-asset"
            asset_dir.mkdir(parents=True)
            Image.new("RGBA", (16385, 4), (255, 0, 0, 128)).save(asset_dir / "rgba.png")
            asset = YarnAsset(
                id="wide-rgba-asset",
                label="Wide RGBA Asset",
                status="ready",
                sourceFilename="rgba.png",
                sourceUrl="/rgba.png",
            )
            _attach_pbr(asset, asset_dir, asset_dir / "rgba.png", max_dimension=16384)

            with patch("app.render_jobs.YARN_ASSETS_ROOT", yarn_root):
                atlas_entries, material_assets = build_project_material_payloads([asset])

            self.assertEqual(atlas_entries[0]["rgba_path"], asset_dir / "rgba.png")
            self.assertEqual(material_assets[0]["texture_mode"], "udim_rgba_tiled")
            self.assertEqual(material_assets[0]["texture_tile_count"], 2)
            self.assertEqual(material_assets[0]["pbr_texture_mode"], "pbr_udim_tiled")
            self.assertTrue((asset_dir / "cycles_tiled" / "rgba_1001.png").exists())
            self.assertIn("<UDIM>", material_assets[0]["rgba_tile_pattern"])

    def test_build_project_material_payloads_supports_rgba_single_assets(self) -> None:
        with TemporaryDirectory() as tmpdir:
            yarn_root = Path(tmpdir)
            asset_dir = yarn_root / "rgba-single-asset"
            asset_dir.mkdir(parents=True)
            Image.new("RGBA", (32, 4), (255, 0, 0, 128)).save(asset_dir / "rgba.png")
            asset = YarnAsset(
                id="rgba-single-asset",
                label="RGBA Single Asset",
                status="ready",
                sourceFilename="rgba.png",
                sourceUrl="/rgba.png",
            )
            _attach_pbr(asset, asset_dir, asset_dir / "rgba.png", max_dimension=16384)

            with patch("app.render_jobs.YARN_ASSETS_ROOT", yarn_root):
                atlas_entries, material_assets = build_project_material_payloads([asset])

            self.assertEqual(atlas_entries[0]["rgba_path"], asset_dir / "rgba.png")
            self.assertEqual(material_assets[0]["texture_mode"], "rgba_single")
            self.assertEqual(material_assets[0]["pbr_texture_mode"], "pbr_single")
            self.assertEqual(material_assets[0]["rgba_path"], str(asset_dir / "rgba.png"))
            self.assertFalse((asset_dir / "albedo.png").exists())
            self.assertFalse((asset_dir / "alpha.png").exists())

    def test_build_project_material_payloads_fails_without_pbr_manifest(self) -> None:
        with TemporaryDirectory() as tmpdir:
            yarn_root = Path(tmpdir)
            asset_dir = yarn_root / "legacy-asset"
            asset_dir.mkdir(parents=True)
            Image.new("RGBA", (32, 4), (255, 0, 0, 128)).save(asset_dir / "rgba.png")
            asset = YarnAsset(
                id="legacy-asset",
                label="Legacy Asset",
                status="ready",
                sourceFilename="rgba.png",
                sourceUrl="/rgba.png",
            )

            with patch("app.render_jobs.YARN_ASSETS_ROOT", yarn_root):
                with self.assertRaises(PbrPreflightError) as ctx:
                    build_project_material_payloads([asset])

            self.assertEqual(ctx.exception.stale_reason, "missing_pbr_manifest")

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
            for asset, color in (
                (assets_lookup["asset-red"], (220, 24, 48)),
                (assets_lookup["asset-black"], (8, 8, 8)),
            ):
                asset_dir = yarn_root / asset.id
                processed_dir = asset_dir / "processed"
                processed_dir.mkdir(parents=True, exist_ok=True)
                source_path = asset_dir / asset.sourceFilename
                Image.new("RGBA", (16, 8), (*color, 255)).save(source_path)
                Image.new("RGB", (16, 8), color).save(asset_dir / asset.diffuseFilename)
                Image.new("L", (16, 8), 255).save(asset_dir / asset.alphaFilename)
                _attach_pbr(asset, asset_dir, source_path)

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

    def test_submit_hook_project_render_job_preserves_material_slot_alignment(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            runtime_root = root / "render_jobs"
            yarn_root = root / "yarn_assets"
            captured: dict[str, object] = {}

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
                    "createdAt": "2026-06-18T00:00:00Z",
                    "imageUrl": None,
                    "logTail": [],
                }

            class FakeUuid:
                hex = "hookjob123456789"

            assets_lookup = {
                "asset-a": YarnAsset(
                    id="asset-a",
                    label="Hook A",
                    status="ready",
                    sourceFilename="source.png",
                    sourceUrl="/api/yarn/assets/asset-a/files/source.png",
                    diffuseFilename="processed/a.png",
                    diffuseUrl="/api/yarn/assets/asset-a/files/processed/a.png",
                    alphaFilename="processed/a-alpha.png",
                    alphaUrl="/api/yarn/assets/asset-a/files/processed/a-alpha.png",
                ),
                "asset-b": YarnAsset(
                    id="asset-b",
                    label="Hook B",
                    status="ready",
                    sourceFilename="source.png",
                    sourceUrl="/api/yarn/assets/asset-b/files/source.png",
                    diffuseFilename="processed/b.png",
                    diffuseUrl="/api/yarn/assets/asset-b/files/processed/b.png",
                    alphaFilename="processed/b-alpha.png",
                    alphaUrl="/api/yarn/assets/asset-b/files/processed/b-alpha.png",
                ),
            }
            for asset, color in (
                (assets_lookup["asset-a"], (160, 130, 80)),
                (assets_lookup["asset-b"], (60, 90, 140)),
            ):
                asset_dir = yarn_root / asset.id
                processed_dir = asset_dir / "processed"
                processed_dir.mkdir(parents=True, exist_ok=True)
                source_path = asset_dir / asset.sourceFilename
                Image.new("RGBA", (16, 8), (*color, 255)).save(source_path)
                Image.new("RGB", (16, 8), color).save(asset_dir / asset.diffuseFilename)
                Image.new("L", (16, 8), 255).save(asset_dir / asset.alphaFilename)
                _attach_pbr(asset, asset_dir, source_path)

            hook_payload = {
                "pattern": {
                    "title": "Sparse Hook",
                    "rows": 1,
                    "columns": 3,
                    "stitchCodes": [[1, 0, 1]],
                    "chainIds": [[0, 1, 2]],
                    "chains": [
                        {"id": 0, "materialSlot": 0},
                        {"id": 2, "materialSlot": 2},
                    ],
                },
                "materialBindings": [
                    {"materialSlot": 0, "yarnAssetId": "asset-a"},
                    {"materialSlot": 2, "yarnAssetId": "asset-b"},
                ],
            }

            with patch("app.render_jobs.DEFAULT_RUNTIME_ROOT", runtime_root), patch(
                "app.render_jobs.YARN_ASSETS_ROOT",
                yarn_root,
            ), patch(
                "app.render_jobs.ensure_runtime_dirs",
                lambda: None,
            ), patch(
                "app.render_jobs.get_ready_yarn_assets_lookup",
                return_value=assets_lookup,
            ), patch(
                "app.render_jobs._create_render_job",
                side_effect=fake_create_render_job,
            ), patch("app.render_jobs.uuid.uuid4", return_value=FakeUuid()):
                snapshot = submit_hook_project_render_job(hook_payload)

            self.assertEqual(snapshot["id"], "hookjob12345")
            self.assertEqual(captured["draft_title"], "Sparse Hook")
            self.assertEqual(captured["target_object_name"], "ProceduralHook")
            self.assertEqual(captured["draft_object_name"], "HookDraft_Live")
            self.assertEqual(len(captured["payload"]["materialAssets"]), 3)
            self.assertEqual(captured["payload"]["materialAssets"][0]["id"], "asset-a")
            self.assertEqual(captured["payload"]["materialAssets"][2]["id"], "asset-b")
            self.assertIn("HookDraft_Live", captured["script_text"])
            self.assertIn("FabricStudioHookMaterial", captured["script_text"])
            self.assertIn("_pw_apply_modifier_material_metadata", captured["script_text"])
            self.assertIn("find_hook_material_adapter", captured["script_text"])
            self.assertIn("configure_hook_material_modifier", captured["script_text"])
            self.assertIn("ensure_udim_image", captured["script_text"])
            self.assertIn("texture_tile_count", captured["script_text"])
            self.assertIn("Image Width Px", captured["script_text"])
            self.assertIn("Arc 2 V Min", captured["script_text"])
            self.assertIn("cleared_unused", captured["script_text"])
            compile(captured["script_text"], "<hook-render-job>", "exec")


if __name__ == "__main__":
    unittest.main()
