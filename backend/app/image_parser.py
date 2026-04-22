from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import cv2
import numpy as np

from .core import clamp, make_document, synthesize_from_drawdown
from .models import ReviewCell


@dataclass
class GridRegion:
    x: int
    y: int
    w: int
    h: int
    score: float

    @property
    def area(self) -> int:
        return self.w * self.h

    @property
    def aspect(self) -> float:
        return self.w / max(self.h, 1)

    @property
    def center(self) -> tuple[float, float]:
        return (self.x + self.w / 2, self.y + self.h / 2)


def _preprocess(gray: np.ndarray) -> np.ndarray:
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    return cv2.adaptiveThreshold(
        blurred,
        255,
        cv2.ADAPTIVE_THRESH_MEAN_C,
        cv2.THRESH_BINARY_INV,
        31,
        15,
    )


def _group_indices(indices: Iterable[int]) -> list[int]:
    grouped: list[list[int]] = []
    current: list[int] = []
    for index in indices:
        if not current or index - current[-1] <= 3:
            current.append(int(index))
        else:
            grouped.append(current)
            current = [int(index)]
    if current:
        grouped.append(current)
    return [int(round(sum(group) / len(group))) for group in grouped]


def _detect_grid_regions(gray: np.ndarray) -> list[GridRegion]:
    threshold = _preprocess(gray)
    height, width = gray.shape

    horizontal_kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT,
        (max(18, width // 18), 1),
    )
    vertical_kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT,
        (1, max(18, height // 18)),
    )

    horizontal = cv2.morphologyEx(threshold, cv2.MORPH_OPEN, horizontal_kernel)
    vertical = cv2.morphologyEx(threshold, cv2.MORPH_OPEN, vertical_kernel)
    grid = cv2.add(horizontal, vertical)

    contours, _ = cv2.findContours(grid, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidates: list[GridRegion] = []
    minimum_area = max(3000, (width * height) // 250)

    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        area = w * h
        if area < minimum_area:
            continue
        fill_ratio = float(np.count_nonzero(grid[y:y + h, x:x + w])) / max(area, 1)
        candidates.append(GridRegion(x=x, y=y, w=w, h=h, score=area * (0.6 + fill_ratio)))

    return sorted(candidates, key=lambda candidate: candidate.score, reverse=True)


def _overlap_ratio(a_start: int, a_end: int, b_start: int, b_end: int) -> float:
    overlap = max(0, min(a_end, b_end) - max(a_start, b_start))
    base = max(1, min(a_end - a_start, b_end - b_start))
    return overlap / base


def _select_layout_regions(candidates: list[GridRegion], image_shape: tuple[int, int]) -> dict[str, GridRegion]:
    if not candidates:
        raise ValueError("No grid regions were detected in the image.")

    _, width = image_shape
    drawdown = max(
        candidates,
        key=lambda candidate: candidate.area * (1.2 if candidate.center[0] < width * 0.7 else 1.0),
    )

    def best_threading(candidate: GridRegion) -> float:
        return (
            candidate.w
            * _overlap_ratio(candidate.x, candidate.x + candidate.w, drawdown.x, drawdown.x + drawdown.w)
            * (1.6 if candidate.y + candidate.h <= drawdown.y + drawdown.h * 0.35 else 0.7)
            * (1.3 if candidate.aspect > 1.3 else 0.8)
        )

    def best_treadling(candidate: GridRegion) -> float:
        return (
            candidate.h
            * _overlap_ratio(candidate.y, candidate.y + candidate.h, drawdown.y, drawdown.y + drawdown.h)
            * (1.6 if candidate.x >= drawdown.x + drawdown.w * 0.45 else 0.7)
            * (1.3 if candidate.aspect < 0.9 else 0.8)
        )

    def best_tieup(candidate: GridRegion) -> float:
        square_bias = 1.4 if 0.7 <= candidate.aspect <= 1.3 else 0.7
        top_right_bias = 1.5 if candidate.center[0] > drawdown.center[0] and candidate.center[1] < drawdown.center[1] else 0.7
        return candidate.area * square_bias * top_right_bias

    others = [candidate for candidate in candidates if candidate is not drawdown]
    threading = max(others or [drawdown], key=best_threading)
    treadling = max([candidate for candidate in others if candidate is not threading] or [drawdown], key=best_treadling)
    tie_up = max(
        [candidate for candidate in others if candidate is not threading and candidate is not treadling] or [drawdown],
        key=best_tieup,
    )

    return {
        "drawdown": drawdown,
        "threading": threading,
        "treadling": treadling,
        "tieUp": tie_up,
    }


def _extract_grid_matrix(crop_gray: np.ndarray) -> tuple[list[list[int]], list[ReviewCell]]:
    threshold = _preprocess(crop_gray)
    height, width = crop_gray.shape
    x_projection = threshold.sum(axis=0)
    y_projection = threshold.sum(axis=1)

    x_indices = np.where(x_projection >= x_projection.max() * 0.68)[0]
    y_indices = np.where(y_projection >= y_projection.max() * 0.68)[0]
    x_lines = _group_indices(x_indices)
    y_lines = _group_indices(y_indices)

    if len(x_lines) < 2 or len(y_lines) < 2:
        raise ValueError("The image region did not expose enough grid lines to infer cells.")

    x_gap = int(np.median(np.diff(x_lines))) if len(x_lines) > 1 else width
    y_gap = int(np.median(np.diff(y_lines))) if len(y_lines) > 1 else height

    if x_lines[0] > max(2, int(x_gap * 0.55)):
        x_lines = [0, *x_lines]
    if y_lines[0] > max(2, int(y_gap * 0.55)):
        y_lines = [0, *y_lines]
    if (width - 1) - x_lines[-1] > max(2, int(x_gap * 0.55)):
        x_lines = [*x_lines, width - 1]
    if (height - 1) - y_lines[-1] > max(2, int(y_gap * 0.55)):
        y_lines = [*y_lines, height - 1]

    matrix: list[list[int]] = []
    review_cells: list[ReviewCell] = []
    fill_threshold = 0.18

    for row_index in range(len(y_lines) - 1):
        row: list[int] = []
        for col_index in range(len(x_lines) - 1):
            y0 = y_lines[row_index] + 1
            y1 = y_lines[row_index + 1] - 1
            x0 = x_lines[col_index] + 1
            x1 = x_lines[col_index + 1] - 1
            if y1 <= y0 or x1 <= x0:
                continue

            region = threshold[y0:y1, x0:x1]
            fill_ratio = float(np.count_nonzero(region)) / max(region.size, 1)
            value = 1 if fill_ratio >= fill_threshold else 0
            row.append(value)

            confidence = min(1.0, abs(fill_ratio - fill_threshold) / 0.3)
            if confidence < 0.4:
                review_cells.append(
                    ReviewCell(
                        section="drawdown",
                        row=row_index,
                        col=col_index,
                        confidence=confidence,
                        reason="The cell fill level was close to the image threshold.",
                    )
                )
        if row:
            matrix.append(row)

    if not matrix:
        raise ValueError("The region did not yield any populated cells.")

    width = min(len(row) for row in matrix)
    matrix = [row[:width] for row in matrix]
    return matrix, review_cells


def _threading_from_matrix(matrix: list[list[int]]) -> tuple[list[int], list[ReviewCell]]:
    rows = len(matrix)
    cols = len(matrix[0])
    threading: list[int] = []
    review_cells: list[ReviewCell] = []
    for col_index in range(cols):
        column = [matrix[row_index][col_index] for row_index in range(rows)]
        active_rows = [row_index for row_index, value in enumerate(column) if value]
        if not active_rows:
            threading.append((col_index % rows) + 1)
            review_cells.append(
                ReviewCell(
                    section="threading",
                    row=0,
                    col=col_index,
                    confidence=0.15,
                    reason="No explicit threading mark was detected in this column.",
                )
            )
            continue
        chosen_row = active_rows[0]
        if len(active_rows) > 1:
            review_cells.append(
                ReviewCell(
                    section="threading",
                    row=rows - chosen_row - 1,
                    col=col_index,
                    confidence=0.3,
                    reason="Multiple threading marks were detected in this column.",
                )
            )
        threading.append(rows - chosen_row)
    return threading, review_cells


def _treadling_from_matrix(matrix: list[list[int]]) -> tuple[list[int], list[ReviewCell]]:
    treadling: list[int] = []
    review_cells: list[ReviewCell] = []
    cols = len(matrix[0])
    for row_index, row in enumerate(matrix):
        active = [col_index for col_index, value in enumerate(row) if value]
        if not active:
            treadling.append((row_index % cols) + 1)
            review_cells.append(
                ReviewCell(
                    section="treadling",
                    row=row_index,
                    col=0,
                    confidence=0.15,
                    reason="No explicit treadling mark was detected in this row.",
                )
            )
            continue
        treadling.append(active[0] + 1)
        if len(active) > 1:
            review_cells.append(
                ReviewCell(
                    section="treadling",
                    row=row_index,
                    col=active[0],
                    confidence=0.3,
                    reason="Multiple treadling marks were detected in this row.",
                )
            )
    return treadling, review_cells


def _tie_up_from_matrix(matrix: list[list[int]]) -> list[list[bool]]:
    rows = len(matrix)
    cols = len(matrix[0])
    tie_up = [[False for _ in range(cols)] for _ in range(rows)]
    for display_row, row in enumerate(matrix):
        shaft_index = rows - display_row - 1
        for col_index, value in enumerate(row):
            tie_up[shaft_index][col_index] = bool(value)
    return tie_up


def parse_image_bytes(data: bytes, filename: str = "upload"):
    buffer = np.frombuffer(data, dtype=np.uint8)
    image = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("The uploaded image could not be decoded.")

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    regions = _select_layout_regions(_detect_grid_regions(gray), gray.shape)
    warnings: list[str] = []
    review_cells: list[ReviewCell] = []

    matrices: dict[str, list[list[int]]] = {}
    for section, region in regions.items():
        try:
            crop = gray[region.y:region.y + region.h, region.x:region.x + region.w]
            matrix, region_reviews = _extract_grid_matrix(crop)
            matrices[section] = matrix
            review_cells.extend(region_reviews)
        except Exception as exc:
            warnings.append(f"Could not fully decode the {section} region: {exc}")

    if "threading" not in matrices and "drawdown" not in matrices:
        raise ValueError("The screenshot did not expose enough draft structure to parse.")

    if "drawdown" not in matrices:
        raise ValueError("The screenshot did not expose a readable drawdown.")

    drawdown = matrices["drawdown"]

    if "threading" in matrices:
        threading, threading_reviews = _threading_from_matrix(matrices["threading"])
        review_cells.extend(threading_reviews)
        shaft_count = len(matrices["threading"])
    else:
        warnings.append("Threading could not be isolated, so the parser synthesized a threading repeat from the drawdown.")
        synthesized = synthesize_from_drawdown(
            drawdown,
            source_type="image",
            warnings=warnings,
            title="Image Draft",
            source_label=filename,
        )
        synthesized.lowConfidenceCells.extend(review_cells)
        synthesized.parseConfidence = 0.32
        return synthesized

    if "treadling" in matrices:
        treadling, treadling_reviews = _treadling_from_matrix(matrices["treadling"])
        review_cells.extend(treadling_reviews)
        treadle_count = len(matrices["treadling"][0])
    else:
        treadle_count = clamp(len(drawdown), 2, 16)
        treadling = [(index % treadle_count) + 1 for index in range(len(drawdown))]
        warnings.append("Treadling could not be isolated, so the parser synthesized a repeating treadling sequence.")

    if "tieUp" in matrices:
        tie_up = _tie_up_from_matrix(matrices["tieUp"])
    else:
        tie_up = [[False for _ in range(treadle_count)] for _ in range(shaft_count)]
        warnings.append("Tie-up could not be isolated, so the parser derived a compatible tie-up from the drawdown.")
        for pick_index, row in enumerate(drawdown):
            for end_index, cell in enumerate(row):
                if not cell:
                    continue
                shaft_index = threading[end_index] - 1
                treadle_index = treadling[pick_index] - 1
                tie_up[shaft_index][treadle_index] = True

    document = make_document(
        source_type="image",
        shaft_count=shaft_count,
        treadle_count=treadle_count,
        threading=threading,
        tie_up=tie_up,
        treadling=treadling,
        parse_confidence=max(0.25, 1.0 - len(warnings) * 0.18 - len(review_cells) * 0.02),
        warnings=warnings,
        low_confidence_cells=review_cells,
        title="Image Draft",
        source_label=filename,
    )
    document.drawdown = drawdown
    return document
