"""Background colors for text cells and vector fills."""

from __future__ import annotations

from typing import Any

import fitz


def rgb_to_fill(rgb: list[int] | None) -> tuple[float, float, float]:
    if not rgb or len(rgb) < 3:
        return (1.0, 1.0, 1.0)
    return (rgb[0] / 255.0, rgb[1] / 255.0, rgb[2] / 255.0)


def _intersection_area(a: list[float], b: list[float]) -> float:
    ix0 = max(a[0], b[0])
    iy0 = max(a[1], b[1])
    ix1 = min(a[2], b[2])
    iy1 = min(a[3], b[3])
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    return (ix1 - ix0) * (iy1 - iy0)


def find_overlapping_background(
    text_bbox: list[float], blocks: list[dict[str, Any]]
) -> dict[str, Any] | None:
    best: dict[str, Any] | None = None
    best_overlap = 0.0
    for block in blocks:
        if block.get("type") != "background" or block.get("deleted"):
            continue
        bg_bbox = block.get("bbox") or []
        if len(bg_bbox) < 4:
            continue
        overlap = _intersection_area(text_bbox, bg_bbox)
        if overlap > best_overlap:
            best_overlap = overlap
            best = block
    return best


def _text_area(bbox: list[float]) -> float:
    return max(0.0, (bbox[2] - bbox[0]) * (bbox[3] - bbox[1]))


def link_text_to_backgrounds(blocks: list[dict[str, Any]]) -> None:
    """Link text to a fill only when the color panel is clearly beneath that text."""
    for block in blocks:
        if block.get("type") != "text":
            continue
        tb = block.get("bbox") or []
        if len(tb) < 4:
            continue
        ta = _text_area(tb)
        best: dict[str, Any] | None = None
        best_ratio = 0.0
        for bg in blocks:
            if bg.get("type") != "background" or bg.get("deleted"):
                continue
            bb = bg.get("bbox") or []
            if len(bb) < 4:
                continue
            overlap = _intersection_area(tb, bb)
            if overlap <= 0 or ta <= 0:
                continue
            ratio = overlap / ta
            bg_area = _text_area(bb)
            if bg_area > 0 and overlap / bg_area < 0.08:
                continue
            if ratio > best_ratio:
                best_ratio = ratio
                best = bg
        if not best or best_ratio < 0.35:
            continue
        block["backgroundBlockId"] = best["id"]
        if best.get("backgroundRgb"):
            block["backgroundRgb"] = list(best["backgroundRgb"])


def unlink_deleted_backgrounds(blocks: list[dict[str, Any]]) -> None:
    deleted_ids = {
        b["id"] for b in blocks if b.get("type") == "background" and b.get("deleted")
    }
    if not deleted_ids:
        return
    for block in blocks:
        if block.get("type") != "text":
            continue
        if block.get("backgroundBlockId") in deleted_ids:
            block.pop("backgroundBlockId", None)
            if not block.get("dirty"):
                block["backgroundRgb"] = [255, 255, 255]


def sample_border_rgb(page: fitz.Page, bbox: list[float]) -> list[int]:
    """Sample color from the cell border (avoids dark glyph pixels in the center)."""
    rect = fitz.Rect(*bbox)
    if rect.is_empty or rect.width < 2 or rect.height < 2:
        return [255, 255, 255]

    clips: list[fitz.Rect] = []
    t = max(2.0, min(4.0, rect.height * 0.2))
    l = max(2.0, min(4.0, rect.width * 0.15))
    clips.append(fitz.Rect(rect.x0, rect.y0, rect.x1, min(rect.y1, rect.y0 + t)))
    clips.append(fitz.Rect(rect.x0, max(rect.y0, rect.y1 - t), rect.x1, rect.y1))
    clips.append(fitz.Rect(rect.x0, rect.y0, min(rect.x1, rect.x0 + l), rect.y1))
    clips.append(fitz.Rect(max(rect.x0, rect.x1 - l), rect.y0, rect.x1, rect.y1))

    r = g = b = 0
    n = 0
    for clip in clips:
        if clip.is_empty:
            continue
        try:
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), clip=clip, alpha=False)
        except Exception:
            continue
        data = pix.samples
        for i in range(0, len(data) - 2, 12):
            pr, pg, pb = data[i], data[i + 1], data[i + 2]
            lum = 0.299 * pr + 0.587 * pg + 0.114 * pb
            if lum < 40 or lum > 250:
                continue
            r += pr
            g += pg
            b += pb
            n += 1

    if n == 0:
        return sample_surround_rgb(page, bbox)
    return [int(r / n), int(g / n), int(b / n)]


def sample_surround_rgb(page: fitz.Page, bbox: list[float], ring: float = 6.0) -> list[int]:
    """Sample page color just outside a region (for removing a colored fill box)."""
    rect = fitz.Rect(*bbox)
    outer = fitz.Rect(
        rect.x0 - ring,
        rect.y0 - ring,
        rect.x1 + ring,
        rect.y1 + ring,
    )
    frame = outer & page.rect
    if frame.is_empty:
        return [255, 255, 255]

    clips = [
        fitz.Rect(frame.x0, frame.y0, frame.x1, min(frame.y1, rect.y0)),
        fitz.Rect(frame.x0, max(frame.y0, rect.y1), frame.x1, frame.y1),
        fitz.Rect(frame.x0, frame.y0, min(frame.x1, rect.x0), frame.y1),
        fitz.Rect(max(frame.x0, rect.x1), frame.y0, frame.x1, frame.y1),
    ]

    r = g = b = 0
    n = 0
    for clip in clips:
        if clip.is_empty or clip.width < 1 or clip.height < 1:
            continue
        try:
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), clip=clip, alpha=False)
        except Exception:
            continue
        data = pix.samples
        for i in range(0, len(data) - 2, 12):
            pr, pg, pb = data[i], data[i + 1], data[i + 2]
            r += pr
            g += pg
            b += pb
            n += 1

    if n == 0:
        return [255, 255, 255]
    return [int(r / n), int(g / n), int(b / n)]


def sample_background_rgb(page: fitz.Page, bbox: list[float]) -> list[int]:
    return sample_border_rgb(page, bbox)


def resolve_block_fill_rgb(
    page: fitz.Page, block: dict[str, Any], page_blocks: list[dict[str, Any]]
) -> list[int]:
    """Fill color for redacting glyphs — matches the cell fill, not 'where text was'."""
    if block.get("backgroundRgb") and len(block["backgroundRgb"]) >= 3:
        return list(block["backgroundRgb"])

    bg_id = block.get("backgroundBlockId")
    if bg_id:
        for other in page_blocks:
            if other.get("id") == bg_id and other.get("backgroundRgb"):
                return list(other["backgroundRgb"])

    bg = find_overlapping_background(block.get("originalBbox") or block.get("bbox") or [], page_blocks)
    if bg and bg.get("backgroundRgb"):
        return list(bg["backgroundRgb"])

    bbox = block.get("originalBbox") or block.get("bbox") or []
    if len(bbox) >= 4:
        rgb = sample_border_rgb(page, bbox)
        if sum(rgb) / 3 < 200:
            return [255, 255, 255]
        return rgb
    return [255, 255, 255]


def resolve_background_removal_fill(
    page: fitz.Page, block: dict[str, Any], page_blocks: list[dict[str, Any]]
) -> list[int]:
    """Fill when erasing a colored vector panel — use page color outside the panel."""
    bbox = block.get("originalBbox") or block.get("bbox") or []
    if len(bbox) >= 4:
        return sample_surround_rgb(page, bbox)
    return [255, 255, 255]
