"""Fonts for PDF export — pick a font that actually renders the block's characters."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import fitz

_ASSETS = Path(__file__).resolve().parents[2] / "assets" / "fonts"


@lru_cache(maxsize=1)
def hebrew_font_path() -> str | None:
    bundled = _ASSETS / "NotoSansHebrew-Regular.ttf"
    if bundled.is_file():
        return str(bundled)
    for path in (
        Path("/System/Library/Fonts/Supplemental/Arial Hebrew.ttf"),
        Path("/Library/Fonts/Arial Hebrew.ttf"),
        Path("/usr/share/fonts/truetype/noto/NotoSansHebrew-Regular.ttf"),
    ):
        if path.is_file():
            return str(path)
    return None


def block_needs_unicode_font(block: dict) -> bool:
    for key in ("content", "originalContent"):
        text = (block.get(key) or "").strip()
        for ch in text:
            o = ord(ch)
            if 0x0590 <= o <= 0x05FF or 0x0600 <= o <= 0x06FF:
                return True
    return block.get("direction") == "rtl"


def block_is_mostly_latin(block: dict) -> bool:
    text = (block.get("content") or block.get("originalContent") or "").strip()
    if not text:
        return True
    latin = sum(
        1
        for ch in text
        if ord(ch) < 0x0590 or (0x05FF < ord(ch) < 0x0600) or ord(ch) > 0x06FF
    )
    return latin / len(text) >= 0.85


def _font_matches(pdf_font: str, entry: tuple) -> bool:
    if len(entry) < 4:
        return False
    basefont = str(entry[3] or "")
    name = str(entry[4] if len(entry) > 4 else "")
    key = pdf_font.split("+")[-1]
    return pdf_font in (basefont, name) or key in (basefont, name)


def _cache_key(page: fitz.Page, block: dict[str, Any]) -> str:
    pdf_font = (block.get("pdfFont") or block.get("fontFamily") or "").strip()
    if block_needs_unicode_font(block):
        return f"{id(page)}:unicode"
    if block_is_mostly_latin(block):
        return f"{id(page)}:latin"
    return f"{id(page)}:embed:{pdf_font}"


def _register_hebrew(page: fitz.Page, cache: dict[str, str], key: str) -> str | None:
    path = hebrew_font_path()
    if not path:
        return None
    label = "Fhebrew"
    if key not in cache:
        page.insert_font(fontname=label, fontfile=path)
        cache[key] = label
    return cache[key]


def register_document_font(page: fitz.Page, doc: fitz.Document, block: dict[str, Any]) -> str:
    """Return a font name that can render this block's content in the exported PDF."""
    cache: dict[str, str] = getattr(register_document_font, "_cache", {})
    key = _cache_key(page, block)
    if key in cache:
        return cache[key]

    # Hebrew / mixed invoices: embedded fon* subsets often omit Latin digits.
    if block_needs_unicode_font(block):
        label = _register_hebrew(page, cache, key)
        if label:
            register_document_font._cache = cache
            return label

    if block_is_mostly_latin(block):
        cache[key] = "helv"
        register_document_font._cache = cache
        return "helv"

    pdf_font = (block.get("pdfFont") or block.get("fontFamily") or "").strip()
    if pdf_font:
        try:
            for entry in page.get_fonts():
                xref = entry[0]
                if not _font_matches(pdf_font, entry):
                    continue
                font_data = doc.extract_font(xref)
                if font_data and len(font_data) >= 4 and font_data[3]:
                    label = f"F{xref}"
                    page.insert_font(fontname=label, fontbuffer=font_data[3])
                    cache[key] = label
                    register_document_font._cache = cache
                    return label
        except Exception:
            pass

        for candidate in (pdf_font, pdf_font.split("+")[-1]):
            try:
                fitz.Font(candidate)
                cache[key] = candidate
                register_document_font._cache = cache
                return candidate
            except Exception:
                continue

    label = _register_hebrew(page, cache, f"{id(page)}:unicode-fallback")
    if label:
        register_document_font._cache = cache
        return label

    cache[key] = "helv"
    register_document_font._cache = cache
    return "helv"


def clear_font_cache() -> None:
    register_document_font._cache = {}


register_document_font._cache = {}
