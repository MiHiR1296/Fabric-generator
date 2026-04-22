from __future__ import annotations

from pathlib import Path

from .image_parser import parse_image_bytes
from .text_parser import parse_text_payload
from .wif_parser import parse_wif_text


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}


def parse_file_bytes(data: bytes, filename: str):
    suffix = Path(filename or "upload").suffix.lower()

    if suffix in IMAGE_SUFFIXES:
        return parse_image_bytes(data, filename=filename or "image upload")

    text = data.decode("utf-8", errors="ignore")
    if suffix == ".wif":
        return parse_wif_text(text)
    if suffix in {".json", ".txt", ".draft"}:
        return parse_text_payload(text)

    try:
        return parse_wif_text(text)
    except Exception:
        return parse_text_payload(text)
