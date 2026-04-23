from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vendor.yarn_pipeline import seamless_converter  # noqa: E402


class SeamlessConverterTests(unittest.TestCase):
    def test_fit_result_to_target_shape_handles_shorter_inpaint_output(self) -> None:
        inpainted = np.zeros((43, 2499, 3), dtype=np.uint8)

        fitted = seamless_converter.fit_result_to_target_shape(
            inpainted,
            (86, 2499, 3),
        )

        self.assertEqual(fitted.shape, (86, 2499, 3))

    def test_process_image_adapts_to_short_source_dimensions(self) -> None:
        source = np.full((86, 2499, 3), 0.5, dtype=np.float32)
        saved_shapes: dict[str, tuple[int, ...]] = {}

        def fake_inpaint(cropped_img_rest, _cropped_mask_rest):
            crop_height, crop_width = cropped_img_rest.shape[:2]
            return np.full(
                (max(1, crop_height // 2), crop_width, 3),
                255,
                dtype=np.uint8,
            )

        def fake_imsave(path, image):
            saved_shapes[Path(path).name] = np.asarray(image).shape

        with TemporaryDirectory() as tmpdir, patch.object(
            seamless_converter,
            "imread",
            return_value=source,
        ), patch.object(
            seamless_converter,
            "imsave",
            side_effect=fake_imsave,
        ), patch.object(
            seamless_converter,
            "inpaint",
            side_effect=fake_inpaint,
        ):
            seamless_converter.process_image(
                str(Path(tmpdir) / "short_source.png"),
                tmpdir,
            )

        self.assertEqual(saved_shapes["short_source_seamless.png"], source.shape)


if __name__ == "__main__":
    unittest.main()
