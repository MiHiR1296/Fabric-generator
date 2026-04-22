from __future__ import annotations

from typing import Iterable

from .models import DraftDocument, ReviewCell


DEFAULT_WARP_COLOR = "#f3ede2"
DEFAULT_WEFT_COLOR = "#b85e3c"


def clamp(value: int | float, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, int(round(value))))


def cycle_values(length: int, max_value: int) -> list[int]:
    return [index % max_value + 1 for index in range(length)]


def compute_drawdown(
    threading: list[int],
    tie_up: list[list[bool]],
    treadling: list[int],
) -> list[list[int]]:
    drawdown: list[list[int]] = []
    for treadle in treadling:
        row: list[int] = []
        for shaft in threading:
            shaft_index = shaft - 1
            treadle_index = treadle - 1
            row.append(1 if tie_up[shaft_index][treadle_index] else 0)
        drawdown.append(row)
    return drawdown


def normalize_threading(threading: Iterable[int] | None, shaft_count: int, warp_ends: int) -> list[int]:
    values = list(threading or [])
    if not values:
        return cycle_values(warp_ends, shaft_count)

    return [
        clamp(values[index] if index < len(values) else values[index % len(values)], 1, shaft_count)
        for index in range(warp_ends)
    ]


def normalize_treadling(
    treadling: Iterable[int] | None,
    treadle_count: int,
    picks: int,
) -> list[int]:
    values = list(treadling or [])
    if not values:
        return cycle_values(picks, treadle_count)

    return [
        clamp(values[index] if index < len(values) else values[index % len(values)], 1, treadle_count)
        for index in range(picks)
    ]


def normalize_tie_up(
    tie_up: Iterable[Iterable[bool]] | None,
    shaft_count: int,
    treadle_count: int,
) -> list[list[bool]]:
    rows = [list(row) for row in tie_up or []]
    normalized: list[list[bool]] = []
    for shaft_index in range(shaft_count):
        row = rows[shaft_index] if shaft_index < len(rows) else []
        normalized.append(
            [bool(row[treadle_index]) if treadle_index < len(row) else False for treadle_index in range(treadle_count)]
        )
    return normalized


def normalize_palette(colors: Iterable[str] | None, fallback: str) -> list[str]:
    values = [str(value).strip() for value in (colors or []) if str(value).strip()]
    return values or [fallback]


def make_document(
    *,
    source_type: str,
    shaft_count: int,
    treadle_count: int,
    threading: Iterable[int] | None = None,
    tie_up: Iterable[Iterable[bool]] | None = None,
    treadling: Iterable[int] | None = None,
    warp_colors: Iterable[str] | None = None,
    weft_colors: Iterable[str] | None = None,
    parse_confidence: float = 1.0,
    warnings: Iterable[str] | None = None,
    low_confidence_cells: Iterable[ReviewCell] | None = None,
    title: str | None = None,
    source_label: str | None = None,
) -> DraftDocument:
    shaft_count = clamp(shaft_count, 2, 32)
    treadle_count = clamp(treadle_count, 2, 32)
    threading_values = list(threading or [])
    treadling_values = list(treadling or [])
    warp_ends = clamp(len(threading_values) or 24, 4, 256)
    picks = clamp(len(treadling_values) or 24, 4, 256)
    normalized_threading = normalize_threading(threading_values, shaft_count, warp_ends)
    normalized_treadling = normalize_treadling(treadling_values, treadle_count, picks)
    normalized_tie_up = normalize_tie_up(tie_up, shaft_count, treadle_count)
    drawdown = compute_drawdown(normalized_threading, normalized_tie_up, normalized_treadling)

    return DraftDocument(
        version=1,
        sourceType=source_type,
        shaftCount=shaft_count,
        treadleCount=treadle_count,
        threading=normalized_threading,
        tieUp=normalized_tie_up,
        treadling=normalized_treadling,
        drawdown=drawdown,
        warpColors=normalize_palette(warp_colors, DEFAULT_WARP_COLOR),
        weftColors=normalize_palette(weft_colors, DEFAULT_WEFT_COLOR),
        parseConfidence=max(0.0, min(1.0, float(parse_confidence))),
        warnings=list(warnings or []),
        lowConfidenceCells=list(low_confidence_cells or []),
        title=title,
        sourceLabel=source_label,
    )


def normalize_document(raw: dict, source_type: str | None = None) -> DraftDocument:
    low_confidence = [
        ReviewCell(
            section=str(cell.get("section", "drawdown")),
            row=int(cell.get("row", 0)),
            col=int(cell.get("col", 0)),
            confidence=float(cell.get("confidence", 0.5)),
            reason=str(cell.get("reason", "Review this inferred cell.")),
        )
        for cell in raw.get("lowConfidenceCells", [])
        if isinstance(cell, dict)
    ]

    return make_document(
        source_type=source_type or str(raw.get("sourceType", "json")),
        shaft_count=int(raw.get("shaftCount", 4)),
        treadle_count=int(raw.get("treadleCount", 4)),
        threading=raw.get("threading") or [],
        tie_up=raw.get("tieUp") or [],
        treadling=raw.get("treadling") or [],
        warp_colors=raw.get("warpColors") or [],
        weft_colors=raw.get("weftColors") or [],
        parse_confidence=float(raw.get("parseConfidence", 1.0)),
        warnings=[str(item) for item in raw.get("warnings", [])],
        low_confidence_cells=low_confidence,
        title=raw.get("title"),
        source_label=raw.get("sourceLabel"),
    )


def synthesize_from_drawdown(
    drawdown: list[list[int]],
    *,
    source_type: str,
    warnings: Iterable[str] | None = None,
    title: str | None = None,
    source_label: str | None = None,
) -> DraftDocument:
    if not drawdown or not drawdown[0]:
        raise ValueError("Drawdown is empty.")

    picks = len(drawdown)
    warp_ends = len(drawdown[0])
    shaft_count = clamp(min(8, max(4, warp_ends // 2 or 4)), 2, 32)
    treadle_count = clamp(min(8, max(4, picks // 2 or 4)), 2, 32)
    threading = cycle_values(warp_ends, shaft_count)
    treadling = cycle_values(picks, treadle_count)
    tie_up = normalize_tie_up(None, shaft_count, treadle_count)

    for pick_index, row in enumerate(drawdown):
        for end_index, cell in enumerate(row):
            if int(cell) != 1:
                continue
            shaft_index = threading[end_index] - 1
            treadle_index = treadling[pick_index] - 1
            tie_up[shaft_index][treadle_index] = True

    document = make_document(
        source_type=source_type,
        shaft_count=shaft_count,
        treadle_count=treadle_count,
        threading=threading,
        tie_up=tie_up,
        treadling=treadling,
        parse_confidence=0.35,
        warnings=[
            "This source did not expose a full threading/tie-up/treadling layout, so the parser synthesized a compatible draft from the detected drawdown.",
            *(warnings or []),
        ],
        title=title,
        source_label=source_label,
    )
    document.drawdown = drawdown
    return document
