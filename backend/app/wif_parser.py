from __future__ import annotations

from .core import make_document


def _parse_wif_sections(text: str) -> dict[str, dict[str, str]]:
    sections: dict[str, dict[str, str]] = {}
    current = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(";"):
            continue

        if line.startswith("[") and line.endswith("]"):
            current = line[1:-1].strip().upper()
            sections.setdefault(current, {})
            continue

        if "=" in line and current:
            key, value = line.split("=", 1)
            sections[current][key.strip()] = value.strip()

    return sections


def _ordered_numeric_items(section: dict[str, str]) -> list[tuple[int, str]]:
    items: list[tuple[int, str]] = []
    for key, value in section.items():
        try:
            items.append((int(key), value))
        except ValueError:
            continue
    return sorted(items, key=lambda item: item[0])


def parse_wif_text(text: str):
    sections = _parse_wif_sections(text)
    weaving = sections.get("WEAVING", {})
    shaft_count = int(weaving.get("Shafts", weaving.get("shafts", 4)))
    treadle_count = int(weaving.get("Treadles", weaving.get("treadles", 4)))

    threading_section = sections.get("THREADING", {})
    threading = [int(value.split(",")[0].strip()) for _, value in _ordered_numeric_items(threading_section)]

    treadling_section = sections.get("TREADLING", {})
    treadling = [int(value.split(",")[0].strip()) for _, value in _ordered_numeric_items(treadling_section)]

    tie_up = [[False for _ in range(treadle_count)] for _ in range(shaft_count)]
    tie_up_section = sections.get("TIEUP", {})
    for treadle_number, value in _ordered_numeric_items(tie_up_section):
        entries = [int(token) for token in value.replace(",", " ").split() if token.strip().isdigit()]
        if not entries:
            continue

        if len(entries) == shaft_count and all(entry in (0, 1) for entry in entries):
            for shaft_index, entry in enumerate(entries):
                tie_up[shaft_index][treadle_number - 1] = bool(entry)
            continue

        for shaft in entries:
            if 1 <= shaft <= shaft_count and 1 <= treadle_number <= treadle_count:
                tie_up[shaft - 1][treadle_number - 1] = True

    warnings: list[str] = []
    if not threading:
        warnings.append("No explicit WIF threading section was found, so threading was synthesized.")
    if not treadling:
        warnings.append("No explicit WIF treadling section was found, so treadling was synthesized.")

    return make_document(
        source_type="wif",
        shaft_count=shaft_count,
        treadle_count=treadle_count,
        threading=threading,
        tie_up=tie_up,
        treadling=treadling,
        parse_confidence=0.94,
        warnings=warnings,
        title="WIF Draft",
        source_label="WIF parser",
    )
