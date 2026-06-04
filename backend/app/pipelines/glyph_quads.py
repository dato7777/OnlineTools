"""Glyph-level regions — each rect belongs to exactly one text block."""

from __future__ import annotations

from typing import Any

import fitz

from app.pipelines.text_match import bbox_iou


def _rect_area(r: fitz.Rect) -> float:
    return max(0.0, r.width) * max(0.0, r.height)


def _intersection_area(a: fitz.Rect, b: fitz.Rect) -> float:
    r = a & b
    return _rect_area(r)


def _bbox_area(bbox: list[float]) -> float:
    if len(bbox) < 4:
        return 0.0
    return max(0.0, bbox[2] - bbox[0]) * max(0.0, bbox[3] - bbox[1])


def _point_in_bbox(px: float, py: float, bbox: list[float], margin: float = 0.0) -> bool:
    if len(bbox) < 4:
        return False
    return (
        bbox[0] - margin <= px <= bbox[2] + margin
        and bbox[1] - margin <= py <= bbox[3] + margin
    )


def _char_center_inside(cb: list[float], ref_bbox: list[float]) -> bool:
    if len(cb) < 4 or len(ref_bbox) < 4:
        return False
    r = fitz.Rect(*cb)
    cx = (r.x0 + r.x1) / 2
    cy = (r.y0 + r.y1) / 2
    return _point_in_bbox(cx, cy, ref_bbox, 0.25)


def filter_hits_by_bbox(
    hits: list[fitz.Rect | fitz.Quad],
    ref_bbox: list[float],
    min_iou: float = 0.12,
) -> list[fitz.Rect | fitz.Quad]:
    if not hits or not ref_bbox or len(ref_bbox) < 4:
        return []
    scored = [(bbox_iou(ref_bbox, _hit_bbox(h)), h) for h in hits]
    scored.sort(key=lambda x: x[0], reverse=True)
    best_iou = scored[0][0]
    if best_iou < min_iou:
        return []
    return [h for iou, h in scored if iou >= max(min_iou, best_iou * 0.45)]


def _hit_bbox(hit: fitz.Rect | fitz.Quad) -> list[float]:
    r = hit.rect if isinstance(hit, fitz.Quad) else hit
    return [r.x0, r.y0, r.x1, r.y1]


def _iter_page_chars(page: fitz.Page):
    for mode in ("rawdict", "dict"):
        try:
            data = page.get_text(mode)
        except Exception:
            continue
        blocks = data if isinstance(data, list) else data.get("blocks", [])
        for block in blocks:
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    for ch in span.get("chars") or []:
                        yield ch


def harvest_glyph_rects(
    page: fitz.Page, ref_bbox: list[float], content: str = ""
) -> list[fitz.Rect]:
    """Collect per-character boxes whose centers lie inside this block only."""
    if len(ref_bbox) < 4:
        return []
    rects: list[fitz.Rect] = []
    for ch in _iter_page_chars(page):
        cb = ch.get("bbox")
        if cb and len(cb) >= 4 and _char_center_inside(cb, ref_bbox):
            rects.append(fitz.Rect(*cb))

    if rects:
        return rects

    text = (content or "").strip()
    if not text:
        return []
    seen: set[str] = set()
    for token in text.split():
        if len(token) < 2 or token in seen:
            continue
        seen.add(token)
        for hit in page.search_for(token):
            r = hit if isinstance(hit, fitz.Rect) else hit.rect
            cx = (r.x0 + r.x1) / 2
            cy = (r.y0 + r.y1) / 2
            if _point_in_bbox(cx, cy, ref_bbox, 0.25):
                rects.append(r)
    return rects


def _rect_to_list(rects: list[fitz.Rect]) -> list[list[float]]:
    out: list[list[float]] = []
    for r in rects:
        box = [round(r.x0, 2), round(r.y0, 2), round(r.x1, 2), round(r.y1, 2)]
        if box not in out:
            out.append(box)
    return out


def _owner_block_id(
    cx: float, cy: float, text_blocks: list[dict[str, Any]]
) -> str | None:
    """Smallest block bbox containing the point wins (most specific cell)."""
    best_id: str | None = None
    best_area = float("inf")
    for block in text_blocks:
        bb = block.get("originalBbox") or block.get("bbox") or []
        if len(bb) < 4 or not _point_in_bbox(cx, cy, bb, 0.5):
            continue
        area = _bbox_area(bb)
        if area < best_area:
            best_area = area
            best_id = block.get("id")
    return best_id


def resolve_glyph_ownership(blocks: list[dict[str, Any]]) -> None:
    """Assign each glyph rect to a single block so erase never crosses boundaries."""
    text_blocks = [
        b
        for b in blocks
        if b.get("type") == "text" and not b.get("deleted") and b.get("glyphRects")
    ]
    for block in text_blocks:
        owned: list[list[float]] = []
        for raw in block.get("glyphRects") or []:
            if not raw or len(raw) < 4:
                continue
            cx = (raw[0] + raw[2]) / 2
            cy = (raw[1] + raw[3]) / 2
            if _owner_block_id(cx, cy, text_blocks) == block.get("id"):
                owned.append(raw)
        block["glyphRects"] = owned


def stamp_glyph_rects(page: fitz.Page, block: dict[str, Any]) -> None:
    bbox = block.get("originalBbox") or block.get("bbox") or []
    if len(bbox) < 4:
        return
    content = block.get("content") or block.get("originalContent") or ""
    rects = harvest_glyph_rects(page, bbox, content)
    rects = _sanitize_glyph_rects(_filter_rects_for_block(rects, bbox), bbox)
    if rects:
        block["glyphRects"] = _rect_to_list(rects)


def _normalize_char_rect(rect: fitz.Rect, max_height: float = 13.5) -> fitz.Rect:
    """PDF char boxes often span the full table cell — shrink to the glyph band."""
    if rect.height <= max_height:
        return rect
    cy = (rect.y0 + rect.y1) / 2
    half = max_height / 2
    pad_x = min(0.35, rect.width * 0.08)
    return fitz.Rect(rect.x0 + pad_x, cy - half, rect.x1 - pad_x, cy + half)


def _sanitize_glyph_rects(
    rects: list[fitz.Rect], ref_bbox: list[float]
) -> list[fitz.Rect]:
    """Drop merged/search hit boxes — they white-out table rules on redact."""
    if len(ref_bbox) < 4:
        return rects
    bw = ref_bbox[2] - ref_bbox[0]
    bh = ref_bbox[3] - ref_bbox[1]
    max_w = max(14.0, bw * 0.38)
    max_area = max(320.0, bw * bh * 0.14)
    out: list[fitz.Rect] = []
    for rect in rects:
        tight = _normalize_char_rect(rect)
        if tight.width > max_w or _rect_area(tight) > max_area:
            continue
        out.append(tight)
    return out


def _filter_rects_for_block(
    rects: list[fitz.Rect], ref_bbox: list[float]
) -> list[fitz.Rect]:
    if len(ref_bbox) < 4:
        return rects
    outer = fitz.Rect(*ref_bbox)
    out: list[fitz.Rect] = []
    for rect in rects:
        clipped = rect & outer
        if clipped.width <= 0.15 or clipped.height <= 0.15:
            continue
        cx = (clipped.x0 + clipped.x1) / 2
        cy = (clipped.y0 + clipped.y1) / 2
        if _point_in_bbox(cx, cy, ref_bbox, 0.25):
            out.append(clipped)
    return out


def harvest_search_glyph_rects(
    page: fitz.Page, ref_bbox: list[float], content: str
) -> list[fitz.Rect]:
    """Locate glyphs via search_for when char harvest misses CID/hex PDFs."""
    if len(ref_bbox) < 4:
        return []
    region = fitz.Rect(*ref_bbox)
    rects: list[fitz.Rect] = []
    seen: set[str] = set()
    text = (content or "").strip()
    probes: list[str] = []
    for part in text.split():
        if len(part) >= 2:
            probes.append(part)
    if len(text) >= 2 and text not in probes:
        probes.insert(0, text)
    for probe in probes:
        if probe in seen:
            continue
        seen.add(probe)
        for hit in page.search_for(probe):
            r = hit if isinstance(hit, fitz.Rect) else hit.rect
            cx = (r.x0 + r.x1) / 2
            cy = (r.y0 + r.y1) / 2
            if region.contains(fitz.Point(cx, cy)):
                rects.append(r)
    return rects


def harvest_owned_glyph_rects(
    page: fitz.Page,
    block: dict[str, Any],
    page_blocks: list[dict[str, Any]],
) -> list[fitz.Rect]:
    """Per-character boxes owned by this block only (safe for redaction)."""
    ref_bbox = list(block.get("originalBbox") or block.get("bbox") or [])
    if len(ref_bbox) < 4:
        return []
    block_id = block.get("id")
    texts = [
        b
        for b in page_blocks
        if b.get("type") == "text" and not b.get("deleted")
    ]
    rects: list[fitz.Rect] = []
    for ch in _iter_page_chars(page):
        cb = ch.get("bbox")
        if not cb or len(cb) < 4:
            continue
        if not _char_center_inside(cb, ref_bbox):
            continue
        r = fitz.Rect(*cb)
        cx = (r.x0 + r.x1) / 2
        cy = (r.y0 + r.y1) / 2
        if _owner_block_id(cx, cy, texts) != block_id:
            continue
        rects.append(r)
    content = (block.get("originalContent") or block.get("content") or "").strip()
    if not rects and content:
        rects = harvest_glyph_rects(page, ref_bbox, content)
        rects = _filter_rects_for_block(rects, ref_bbox)
    if content:
        for r in harvest_search_glyph_rects(page, ref_bbox, content):
            rects.append(r)
    return _sanitize_glyph_rects(rects, ref_bbox)


def glyph_rects_for_block(
    page: fitz.Page,
    block: dict[str, Any],
    page_blocks: list[dict[str, Any]] | None = None,
) -> list[fitz.Rect]:
    if page_blocks:
        owned = harvest_owned_glyph_rects(page, block, page_blocks)
        if owned:
            return owned

    ref_bbox = list(block.get("originalBbox") or block.get("bbox") or [])
    stored = block.get("glyphRects")

    if stored and ref_bbox:
        rects = _sanitize_glyph_rects(
            _filter_rects_for_block(
                [fitz.Rect(*r) for r in stored if r and len(r) >= 4], ref_bbox
            ),
            ref_bbox,
        )
        if rects:
            return rects

    if len(ref_bbox) >= 4:
        content = block.get("originalContent") or block.get("content") or ""
        rects = harvest_glyph_rects(page, ref_bbox, content)
        if rects:
            return _sanitize_glyph_rects(_filter_rects_for_block(rects, ref_bbox), ref_bbox)

    return []


def collect_glyph_quads_for_block(
    page: fitz.Page, block: dict[str, Any]
) -> list[fitz.Rect | fitz.Quad]:
    return glyph_rects_for_block(page, block)
