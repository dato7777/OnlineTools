"""Shared text placement math — editor preview and PDF export use the same boxes."""

from __future__ import annotations

from typing import Any

import fitz

from app.pipelines.fonts import block_needs_unicode_font, hebrew_font_path

TABLE_INSET_X = 2.2
TABLE_INSET_Y = 1.0

_ALIGN_MAP = {
    "left": fitz.TEXT_ALIGN_LEFT,
    "center": fitz.TEXT_ALIGN_CENTER,
    "right": fitz.TEXT_ALIGN_RIGHT,
}


def placement_bbox(block: dict[str, Any]) -> list[float]:
    cur = block.get("bbox")
    if cur and len(cur) >= 4:
        return list(cur)
    return list(block.get("originalBbox") or [])


def is_table_cell(block: dict[str, Any]) -> bool:
    return bool(block.get("tableGroupId"))


def bbox_moved(block: dict[str, Any]) -> bool:
    orig = block.get("originalBbox")
    cur = block.get("bbox", [])
    if not orig or len(orig) != len(cur):
        return False
    return any(abs(a - b) > 0.5 for a, b in zip(orig, cur))


def export_display_text(block: dict[str, Any]) -> str:
    """Visual-order string for PyMuPDF (RTL Hebrew)."""
    content = (block.get("content") or "").strip()
    if not content:
        return ""
    if block_needs_unicode_font(block):
        try:
            from bidi.algorithm import get_display

            return get_display(content)
        except ImportError:
            pass
    return content


def table_insert_rect(block: dict[str, Any]) -> list[float]:
    bb = placement_bbox(block)
    if len(bb) < 4:
        return bb
    return [
        bb[0] + TABLE_INSET_X,
        bb[1] + TABLE_INSET_Y,
        bb[2] - TABLE_INSET_X,
        bb[3] - TABLE_INSET_Y,
    ]


def placement_origin(block: dict[str, Any], bbox_override: list[float] | None = None) -> list[float]:
    bbox = bbox_override or placement_bbox(block)
    orig = list(block.get("originalBbox") or block.get("bbox") or bbox)
    origin = block.get("textOrigin") or [orig[0], orig[3]]
    align = block.get("align", "left")
    rtl = block.get("direction") == "rtl" or block_needs_unicode_font(block)

    if len(bbox) >= 4 and len(orig) >= 4:
        dx = bbox[0] - orig[0]
        dy = bbox[3] - orig[3]
        if rtl and align == "right":
            return [bbox[2], float(origin[1]) + dy]
        return [float(origin[0]) + dx, float(origin[1]) + dy]
    return [bbox[0], bbox[3]]


def largest_table_font_size(
    content: str,
    rect: fitz.Rect,
    max_fs: float,
    align: int = fitz.TEXT_ALIGN_RIGHT,
) -> float:
    """Largest font size insert_textbox accepts for this rect (scratch document)."""
    if rect.is_empty or not content.strip():
        return max(6.0, max_fs)
    scratch = fitz.open()
    try:
        for fs in range(int(max_fs * 100), 59, -1):
            size = fs / 100.0
            if size * 1.25 > rect.height:
                continue
            page = scratch.new_page(width=rect.x1 + 40, height=rect.y1 + 40)
            try:
                page.insert_font(fontname="Fhebrew", fontfile=hebrew_font_path())
            except Exception:
                pass
            fontname = "Fhebrew" if hebrew_font_path() else "helv"
            try:
                rc = page.insert_textbox(
                    rect,
                    content,
                    fontname=fontname,
                    fontsize=size,
                    color=(0, 0, 0),
                    align=align,
                    fill=None,
                    overlay=True,
                )
            except Exception:
                scratch.delete_page(page.number)
                continue
            if rc >= 0:
                return size
            scratch.delete_page(page.number)
        return max(6.0, max_fs * 0.55)
    finally:
        scratch.close()


def compute_placement_metrics(block: dict[str, Any]) -> dict[str, Any]:
    """Metrics the live editor should mirror for WYSIWYG placement."""
    bbox = placement_bbox(block)
    if len(bbox) < 4 or block.get("type") != "text":
        return {
            "insertRect": bbox,
            "exportFontSize": float(block.get("fontSize") or 12),
            "align": block.get("align", "left"),
            "useTextOrigin": False,
            "textOrigin": block.get("textOrigin"),
            "isTableCell": False,
        }

    align_key = block.get("align", "left")
    if align_key not in ("left", "center", "right"):
        align_key = "right" if block_needs_unicode_font(block) else "left"

    if is_table_cell(block):
        insert = table_insert_rect(block)
        rect = fitz.Rect(*insert)
        display = export_display_text(block)
        max_fs = float(block.get("fontSize") or 12)
        align_int = _ALIGN_MAP.get(align_key, fitz.TEXT_ALIGN_RIGHT)
        export_fs = largest_table_font_size(display, rect, max_fs, align_int)
        moved = bbox_moved(block)
        return {
            "insertRect": insert,
            "exportFontSize": round(export_fs, 2),
            "align": align_key,
            "useTextOrigin": moved,
            "textOrigin": placement_origin(block),
            "isTableCell": True,
        }

    export_fs = float(block.get("fontSize") or 12)
    return {
        "insertRect": bbox,
        "exportFontSize": export_fs,
        "align": align_key,
        "useTextOrigin": bbox_moved(block),
        "textOrigin": placement_origin(block),
        "isTableCell": False,
    }
