from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.tile_inpaint_repair import (  # noqa: E402
    _color_match_masked_pixels,
    build_cross_mask,
    paste_only_retile_preview,
    repair_center_cross_once,
    repair_tile_with_two_pass_inpaint,
    roll_image,
)


class TileInpaintRepairTests(unittest.TestCase):
    def test_build_cross_mask_marks_center_bands(self) -> None:
        mask = build_cross_mask((10, 8), seam_x=5, seam_y=4, radius_px=1)

        self.assertEqual(mask.getpixel((5, 0)), 255)
        self.assertEqual(mask.getpixel((0, 4)), 255)
        self.assertEqual(mask.getpixel((0, 0)), 0)
        self.assertEqual(mask.getpixel((9, 7)), 0)

    def test_roll_image_wraps_pixels(self) -> None:
        image = Image.new("RGBA", (3, 1), (0, 0, 0, 255))
        image.putpixel((0, 0), (255, 0, 0, 255))
        image.putpixel((1, 0), (0, 255, 0, 255))
        image.putpixel((2, 0), (0, 0, 255, 255))

        rolled = roll_image(image, dx=1, dy=0)

        self.assertEqual(rolled.getpixel((0, 0)), (0, 0, 255, 255))
        self.assertEqual(rolled.getpixel((1, 0)), (255, 0, 0, 255))
        self.assertEqual(rolled.getpixel((2, 0)), (0, 255, 0, 255))

    def test_paste_only_retile_preview_repeats_image(self) -> None:
        image = Image.new("RGBA", (2, 2), (0, 0, 0, 255))
        image.putpixel((1, 1), (255, 255, 255, 255))

        preview = paste_only_retile_preview(image, repetitions=2)

        self.assertEqual(preview.size, (4, 4))
        self.assertEqual(preview.getpixel((1, 1)), (255, 255, 255, 255))
        self.assertEqual(preview.getpixel((3, 3)), (255, 255, 255, 255))

    def test_repair_center_cross_uses_inpaint_function_on_masked_windows(self) -> None:
        image = Image.new("RGBA", (12, 12), (10, 20, 30, 255))
        calls: list[tuple[tuple[int, int], tuple[int, int] | None]] = []

        def fake_inpaint(crop: Image.Image, mask: Image.Image) -> Image.Image:
            calls.append((crop.size, mask.getbbox()))
            out = crop.convert("RGB").copy()
            out.paste(Image.new("RGB", crop.size, (200, 100, 50)), (0, 0), mask)
            return out

        repaired, mask = repair_center_cross_once(
            image,
            seam_radius_px=1,
            context_px=4,
            inpaint_fn=fake_inpaint,
        )

        self.assertEqual(len(calls), 2)
        self.assertIsNotNone(mask.getbbox())
        self.assertEqual(repaired.getpixel((6, 6)), (200, 100, 50, 255))
        self.assertEqual(repaired.getpixel((0, 0)), (10, 20, 30, 255))

    def test_color_match_lifts_dark_inpaint_pixels_toward_local_ring(self) -> None:
        original = Image.new("RGB", (20, 20), (180, 178, 176))
        result = Image.new("RGB", (20, 20), (180, 178, 176))
        mask = Image.new("L", (20, 20), 0)

        for y in range(8, 12):
            for x in range(8, 12):
                result.putpixel((x, y), (45, 44, 43))
                mask.putpixel((x, y), 255)

        matched = _color_match_masked_pixels(original, result, mask, strength=1.0, ring_px=3)

        self.assertGreater(matched.getpixel((10, 10))[0], 150)
        self.assertEqual(matched.getpixel((0, 0)), (180, 178, 176))

    def test_color_match_can_overdrive_past_exact_match(self) -> None:
        original = Image.new("RGB", (20, 20), (180, 180, 180))
        result = Image.new("RGB", (20, 20), (180, 180, 180))
        mask = Image.new("L", (20, 20), 0)

        for y in range(8, 12):
            for x in range(8, 12):
                result.putpixel((x, y), (120, 120, 120))
                mask.putpixel((x, y), 255)

        exact = _color_match_masked_pixels(original, result, mask, strength=1.0, ring_px=3)
        overdriven = _color_match_masked_pixels(original, result, mask, strength=1.2, ring_px=3)

        self.assertGreater(overdriven.getpixel((10, 10))[0], exact.getpixel((10, 10))[0])
        self.assertLessEqual(overdriven.getpixel((10, 10))[0], 255)

    def test_two_pass_repair_can_save_only_final_output(self) -> None:
        def fake_inpaint(crop: Image.Image, mask: Image.Image) -> Image.Image:
            out = crop.convert("RGB").copy()
            out.paste(Image.new("RGB", crop.size, (120, 130, 140)), (0, 0), mask)
            return out

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            input_path = root / "input.png"
            output_path = root / "final.png"
            Image.new("RGBA", (20, 20), (10, 20, 30, 255)).save(input_path)

            result = repair_tile_with_two_pass_inpaint(
                input_path,
                output_path,
                seam_radius_px=1,
                context_px=8,
                inpaint_fn=fake_inpaint,
                save_debug_outputs=False,
                save_retile_preview=False,
            )

            self.assertTrue(output_path.exists())
            self.assertIsNone(result.pass_a_mask_path)
            self.assertIsNone(result.pass_b_rolled_output_path)
            self.assertEqual(sorted(path.name for path in root.iterdir()), ["final.png", "input.png"])


if __name__ == "__main__":
    unittest.main()
