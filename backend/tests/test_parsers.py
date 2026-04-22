from __future__ import annotations

import io
import sys
import unittest
from pathlib import Path

import cv2
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core import compute_drawdown
from app.image_parser import parse_image_bytes
from app.text_parser import parse_text_payload
from app.wif_parser import parse_wif_text


def _threading_display_matrix(threading: list[int], shaft_count: int) -> list[list[int]]:
    matrix = [[0 for _ in threading] for _ in range(shaft_count)]
    for col_index, shaft in enumerate(threading):
        matrix[shaft_count - shaft][col_index] = 1
    return matrix


def _tieup_display_matrix(tie_up: list[list[bool]]) -> list[list[int]]:
    shaft_count = len(tie_up)
    treadle_count = len(tie_up[0])
    matrix = [[0 for _ in range(treadle_count)] for _ in range(shaft_count)]
    for display_row in range(shaft_count):
        shaft_index = shaft_count - display_row - 1
        for col_index in range(treadle_count):
            matrix[display_row][col_index] = 1 if tie_up[shaft_index][col_index] else 0
    return matrix


def _treadling_display_matrix(treadling: list[int], treadle_count: int) -> list[list[int]]:
    matrix = [[0 for _ in range(treadle_count)] for _ in treadling]
    for row_index, treadle in enumerate(treadling):
        matrix[row_index][treadle - 1] = 1
    return matrix


def _draw_grid(canvas: np.ndarray, origin: tuple[int, int], matrix: list[list[int]], cell_size: int, line_color: int, fill_color: int) -> None:
    x0, y0 = origin
    rows = len(matrix)
    cols = len(matrix[0])

    for row_index in range(rows):
        for col_index in range(cols):
            left = x0 + col_index * cell_size
            top = y0 + row_index * cell_size
            if matrix[row_index][col_index]:
                cv2.rectangle(
                    canvas,
                    (left + 3, top + 3),
                    (left + cell_size - 3, top + cell_size - 3),
                    fill_color,
                    -1,
                )

    for col_index in range(cols + 1):
        x = x0 + col_index * cell_size
        cv2.line(canvas, (x, y0), (x, y0 + rows * cell_size), line_color, 2)

    for row_index in range(rows + 1):
        y = y0 + row_index * cell_size
        cv2.line(canvas, (x0, y), (x0 + cols * cell_size, y), line_color, 2)


def build_standard_fixture(low_contrast: bool = False, crop: bool = False) -> bytes:
    shaft_count = 4
    treadle_count = 4
    threading = [1, 2, 3, 4, 1, 2, 3, 4]
    tie_up = [
        [True, False, False, True],
        [True, True, False, False],
        [False, True, True, False],
        [False, False, True, True],
    ]
    treadling = [1, 2, 3, 4, 1, 2, 3, 4]
    drawdown = compute_drawdown(threading, tie_up, treadling)

    line_color = 90 if low_contrast else 0
    fill_color = 130 if low_contrast else 20
    canvas = np.full((520, 640), 255, dtype=np.uint8)
    cell_size = 24
    drawdown_origin = (40, 180)
    threading_origin = (40, 40)
    tieup_origin = (280, 40)
    treadling_origin = (280, 180)

    _draw_grid(canvas, drawdown_origin, drawdown, cell_size, line_color, fill_color)
    _draw_grid(canvas, threading_origin, _threading_display_matrix(threading, shaft_count), cell_size, line_color, fill_color)
    _draw_grid(canvas, tieup_origin, _tieup_display_matrix(tie_up), cell_size, line_color, fill_color)
    _draw_grid(canvas, treadling_origin, _treadling_display_matrix(treadling, treadle_count), cell_size, line_color, fill_color)

    if crop:
        canvas = canvas[10:-12, 8:-16]

    success, encoded = cv2.imencode(".png", canvas)
    if not success:
        raise RuntimeError("Could not encode test image.")
    return encoded.tobytes()


class DraftParserTests(unittest.TestCase):
    def test_parse_wif_text(self) -> None:
        document = parse_wif_text(
            """
            [WEAVING]
            Shafts=4
            Treadles=4

            [THREADING]
            1=1
            2=2
            3=3
            4=4

            [TIEUP]
            1=1 2
            2=2 3
            3=3 4
            4=4 1

            [TREADLING]
            1=1
            2=2
            3=3
            4=4
            """
        )

        self.assertEqual(document.sourceType, "wif")
        self.assertEqual(document.shaftCount, 4)
        self.assertEqual(document.threading[:4], [1, 2, 3, 4])
        self.assertEqual(document.treadling[:4], [1, 2, 3, 4])

    def test_parse_text_payload_labelled(self) -> None:
        document = parse_text_payload(
            """
            shafts: 4
            treadles: 4
            threading: 1 2 3 4 1 2 3 4
            tieup:
            1 0 0 1
            1 1 0 0
            0 1 1 0
            0 0 1 1
            treadling: 1 2 3 4
            """
        )

        self.assertEqual(document.sourceType, "text")
        self.assertEqual(document.shaftCount, 4)
        self.assertEqual(document.threading[0], 1)
        self.assertEqual(document.drawdown[0][0], 1)

    def test_parse_binary_matrix_text(self) -> None:
        document = parse_text_payload(
            """
            1010
            0101
            1010
            0101
            """
        )

        self.assertEqual(document.sourceType, "text")
        self.assertEqual(len(document.drawdown), 4)
        self.assertTrue(document.warnings)

    def test_rejects_malformed_text(self) -> None:
        with self.assertRaises(ValueError):
            parse_text_payload("this is not a draft")

    def test_parse_image_fixture(self) -> None:
        document = parse_image_bytes(build_standard_fixture(), filename="clean.png")
        self.assertEqual(document.sourceType, "image")
        self.assertEqual(document.shaftCount, 4)
        self.assertEqual(document.treadleCount, 4)
        self.assertEqual(document.threading[:4], [1, 2, 3, 4])
        self.assertEqual(document.treadling[:4], [1, 2, 3, 4])
        self.assertEqual(document.drawdown[0][:4], [1, 1, 0, 0])

    def test_parse_low_contrast_fixture(self) -> None:
        document = parse_image_bytes(build_standard_fixture(low_contrast=True), filename="low-contrast.png")
        self.assertEqual(document.sourceType, "image")
        self.assertGreaterEqual(document.parseConfidence, 0.25)

    def test_parse_partial_crop_fixture(self) -> None:
        document = parse_image_bytes(build_standard_fixture(crop=True), filename="partial.png")
        self.assertEqual(document.sourceType, "image")
        self.assertEqual(document.threading[0], 1)


if __name__ == "__main__":
    unittest.main()
