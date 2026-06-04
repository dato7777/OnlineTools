"""Editor page images — full structure preserved; text cleared only when needed."""

from __future__ import annotations

from typing import Any

import fitz

from app.pipelines.background import (
    link_text_to_backgrounds,
    resolve_background_removal_fill,
    unlink_deleted_backgrounds,
)
from app.pipelines.glyph_quads import collect_glyph_quads_for_block


def render_page_full(pdf_path: str, page_index: int, scale: float = 2.0) -> bytes:
    """Full page raster — no redaction (used for initial editor background)."""
    doc = fitz.open(pdf_path)
    try:
        page = doc[page_index]
        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
        return pix.tobytes("png")
    finally:
        doc.close()


def render_page_without_text(
    pdf_path: str,
    page_index: int,
    blocks: list[dict[str, Any]],
    scale: float = 2.0,
) -> bytes:
    """Clear text only when a colored fill was removed; otherwise return full page."""
    working = list(blocks)
    unlink_deleted_backgrounds(working)
    link_text_to_backgrounds(working)
    deleted_backgrounds = [
        b for b in working if b.get("type") == "background" and b.get("deleted")
    ]
    if not deleted_backgrounds:
        return render_page_full(pdf_path, page_index, scale)

    doc = fitz.open(pdf_path)
    try:
        page = doc[page_index]
        for block in deleted_backgrounds:
            bbox = block.get("originalBbox") or block.get("bbox")
            if not bbox or len(bbox) < 4:
                continue
            fill = rgb_to_fill(resolve_background_removal_fill(page, block, working))
            page.add_redact_annot(fitz.Rect(*bbox), fill=fill, cross_out=False)
        page.apply_redactions(images=0, graphics=2, text=1)

        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
        return pix.tobytes("png")
    finally:
        doc.close()


def render_page_without_text_legacy(
    pdf_path: str,
    page_index: int,
    blocks: list[dict[str, Any]],
    scale: float = 2.0,
) -> bytes:
    """Legacy: redact all text (causes gray shadows on white docs). Kept for tests only."""
    doc = fitz.open(pdf_path)
    try:
        page = doc[page_index]
        working = list(blocks)
        link_text_to_backgrounds(working)
        text_blocks = [
            b
            for b in working
            if b.get("type") == "text"
            and not b.get("deleted")
            and (b.get("originalContent") or b.get("content") or "").strip()
        ]
        for block in text_blocks:
            fill = rgb_to_fill(resolve_block_fill_rgb(page, block, working))
            for quad in collect_glyph_quads_for_block(page, block):
                page.add_redact_annot(quad, fill=fill, cross_out=False)
        if text_blocks:
            page.apply_redactions(images=0, graphics=0, text=0)
        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
        return pix.tobytes("png")
    finally:
        doc.close()
