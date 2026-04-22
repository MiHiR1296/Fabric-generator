from __future__ import annotations

import json
import re

from .core import make_document, normalize_document, synthesize_from_drawdown


def _parse_numbers(chunk: str) -> list[int]:
    return [int(part) for part in re.findall(r"-?\d+", chunk)]


def _parse_labeled_text(text: str):
    sections: dict[str, list[str]] = {"root": []}
    current = "root"

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        match = re.match(r"^(threading|tieup|tie-up|treadling|shafts|treadles)\s*:\s*(.*)$", line, re.IGNORECASE)
        if match:
            current = match.group(1).lower().replace("tie-up", "tieup")
            sections.setdefault(current, [])
            if match.group(2):
                sections[current].append(match.group(2))
            continue

        sections.setdefault(current, [])
        sections[current].append(line)

    shaft_count = max(2, (_parse_numbers(" ".join(sections.get("shafts", ["4"])))[:1] or [4])[0])
    treadle_count = max(2, (_parse_numbers(" ".join(sections.get("treadles", ["4"])))[:1] or [4])[0])
    threading = _parse_numbers(" ".join(sections.get("threading", [])))
    treadling = _parse_numbers(" ".join(sections.get("treadling", [])))
    tie_up_rows = [_parse_numbers(row) for row in sections.get("tieup", [])]
    tie_up = [[bool(value) for value in row] for row in tie_up_rows]

    return make_document(
        source_type="text",
        shaft_count=shaft_count,
        treadle_count=treadle_count,
        threading=threading,
        tie_up=tie_up,
        treadling=treadling,
        parse_confidence=0.78,
        warnings=["Parsed from loose labeled text. Confirm the inferred counts before exporting."],
        title="Text Draft",
        source_label="Labeled text parser",
    )


def _parse_binary_matrix(text: str):
    rows = []
    for line in text.splitlines():
        cleaned = line.strip()
        if not cleaned:
            continue
        row = [int(part) for part in re.findall(r"[01]", cleaned)]
        if row:
            rows.append(row)

    if not rows:
        raise ValueError("No binary matrix found in text.")

    width = max(len(row) for row in rows)
    normalized = [row + [0] * (width - len(row)) for row in rows]

    return synthesize_from_drawdown(
        normalized,
        source_type="text",
        warnings=["The text looked like a binary matrix, so it was treated as a drawdown-first source."],
        title="Matrix Draft",
        source_label="Binary matrix parser",
    )


def parse_text_payload(text: str):
    stripped = text.strip()
    if not stripped:
        raise ValueError("Input text is empty.")

    if stripped.startswith("{"):
        return normalize_document(json.loads(stripped), source_type="json")

    if any(token in stripped.lower() for token in ("threading:", "tieup:", "tie-up:", "treadling:", "shafts:", "treadles:")):
        return _parse_labeled_text(stripped)

    return _parse_binary_matrix(stripped)
