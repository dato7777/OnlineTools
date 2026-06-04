"""Extract filled vector regions (table fills, panels) as separate background blocks."""

from __future__ import annotations

import uuid
from typing import Any

import fitz


def _rgb_from_color(color: tuple | list | None) -> list[int] | None:
    if not color or len(color) < 3:
        return None
    return [int(min(255, max(0, c * 255))) for c in color[:3]]


def _text_overlap_fraction(page: fitz.Page, rect: fitz.Rect) -> float:
    """How much of text ink sits inside this fill (avoid page-wide 'backgrounds')."""
    try:
        words = page.get_text("words")
    except Exception:
        return 0.0
    if not words:
        return 0.0
    hit = 0
    total = 0
    for w in words:
        if len(w) < 5:
            continue
        x0, y0, x1, y1 = w[0], w[1], w[2], w[3]
        total += 1
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        if rect.contains(fitz.Point(cx, cy)):
            hit += 1
    return hit / total if total else 0.0


def extract_background_blocks(page: fitz.Page, page_index: int) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    page_area = page.rect.width * page.rect.height or 1
    min_area = 900
    max_page_fraction = 0.35
    max_text_fraction = 0.55

    try:
        drawings = page.get_drawings()
    except Exception:
        return blocks

    for d in drawings:
        fill = d.get("fill")
        if fill is None:
            continue
        rect = d.get("rect")
        if not rect:
            continue
        w = rect.x1 - rect.x0
        h = rect.y1 - rect.y0
        area = w * h
        if area < min_area:
            continue
        if area / page_area > max_page_fraction:
            continue
        if _text_overlap_fraction(page, rect) > max_text_fraction:
            continue
        rgb = _rgb_from_color(fill)
        if not rgb:
            continue
        blocks.append(
            {
                "id": f"bg-{page_index}-{uuid.uuid4().hex[:8]}",
                "type": "background",
                "layer": "background",
                "bbox": [rect.x0, rect.y0, rect.x1, rect.y1],
                "backgroundRgb": rgb,
                "source": "vector",
            }
        )
    return blocks
