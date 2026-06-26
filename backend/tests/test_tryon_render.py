import json
import tempfile
import unittest
from pathlib import Path

from app import tryon_render as tr


class TryonTargetsTest(unittest.TestCase):
    def test_default_catalog_has_required_fields(self):
        targets = tr.load_tryon_targets()
        self.assertTrue(targets)
        ids = {t["id"] for t in targets}
        self.assertIn("draped_cloth", ids)
        for target in targets:
            for key in ("id", "label", "description", "collections", "camera", "fabricMaterial"):
                self.assertIn(key, target)
            self.assertIsInstance(target["collections"], list)
            self.assertTrue(target["collections"])

    def test_public_targets_is_minimal_shape(self):
        public = tr.public_targets()
        self.assertTrue(public)
        self.assertEqual(set(public[0].keys()), {"id", "label", "description"})

    def test_get_tryon_target(self):
        self.assertIsNotNone(tr.get_tryon_target("draped_cloth"))
        self.assertIsNone(tr.get_tryon_target("does_not_exist"))

    def test_override_file_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            override = Path(tmp) / "targets.json"
            override.write_text(
                json.dumps(
                    {
                        "targets": [
                            {
                                "id": "only_one",
                                "label": "Only One",
                                "collections": ["SomeCollection"],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            import os

            prev = os.environ.get("TRYON_TARGETS_FILE")
            os.environ["TRYON_TARGETS_FILE"] = str(override)
            try:
                targets = tr.load_tryon_targets()
            finally:
                if prev is None:
                    os.environ.pop("TRYON_TARGETS_FILE", None)
                else:
                    os.environ["TRYON_TARGETS_FILE"] = prev
            self.assertEqual([t["id"] for t in targets], ["only_one"])
            self.assertEqual(targets[0]["fabricMaterial"], tr.DEFAULT_FABRIC_MATERIAL)


class TryonScriptTest(unittest.TestCase):
    def test_script_embeds_target_and_paths(self):
        target = tr.get_tryon_target("cushion")
        script = tr.build_tryon_render_script(
            target,
            fabric_diffuse="/tmp/diffuse.png",
            render_path="/tmp/out.png",
            resolution=1200,
            samples=64,
        )
        # The script inlines a JSON config consumed by `_TRYON = json.loads(...)`.
        self.assertIn("_TRYON = json.loads(", script)
        self.assertIn("bpy.ops.render.render(write_still=True)", script)
        self.assertIn("world neutral fallback", script)
        # Decode the embedded config and check the wiring.
        import ast

        marker = "_TRYON = json.loads("
        start = script.index(marker) + len(marker)
        end = script.index(")\n", start)
        # The script embeds repr(json.dumps(config)): a Python string literal
        # whose content is the JSON config.
        config = json.loads(ast.literal_eval(script[start:end]))
        self.assertEqual(config["targetId"], "cushion")
        self.assertEqual(config["fabricDiffuse"], "/tmp/diffuse.png")
        self.assertEqual(config["renderPath"], "/tmp/out.png")
        self.assertEqual(config["resolution"], 1200)
        self.assertEqual(config["samples"], 64)
        self.assertIsNone(config["fabricNormal"])

    def test_clamps_resolution_and_samples(self):
        self.assertEqual(tr._clamp(99999, tr.DEFAULT_RESOLUTION, tr.MIN_RESOLUTION, tr.MAX_RESOLUTION), tr.MAX_RESOLUTION)
        self.assertEqual(tr._clamp(0, tr.DEFAULT_SAMPLES, tr.MIN_SAMPLES, tr.MAX_SAMPLES), tr.MIN_SAMPLES)
        self.assertEqual(tr._clamp("bad", tr.DEFAULT_SAMPLES, tr.MIN_SAMPLES, tr.MAX_SAMPLES), tr.DEFAULT_SAMPLES)


class TryonSourceTest(unittest.TestCase):
    def test_resolve_missing_source_raises(self):
        with self.assertRaises(ValueError):
            tr.resolve_source_image("no_such_job_id")


if __name__ == "__main__":
    unittest.main()
