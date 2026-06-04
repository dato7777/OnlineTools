"""Text-only export: erase exact glyphs (like delete), re-type with a font that renders."""

from __future__ import annotations

import logging
import uuid
from typing import Any

import fitz

from app.pipelines.accuracy import block_is_modified, model_has_changes
from app.pipelines.background import (
    resolve_background_removal_fill,
    rgb_to_fill,
)
from app.pipelines.fonts import (
    block_is_mostly_latin,
    block_needs_unicode_font,
    clear_font_cache,
    hebrew_font_path,
    register_document_font,
)
from app.pipelines.export_surgeon import apply_surgeon_export_pass
from app.pipelines.glyph_quads import (
    _owner_block_id,
    glyph_rects_for_block,
    harvest_search_glyph_rects,
    resolve_glyph_ownership,
    stamp_glyph_rects,
)
from app.storage import file_path, read_file, save_bytes

logger = logging.getLogger(__name__)

_ALIGN = {
    "left": fitz.TEXT_ALIGN_LEFT,
    "center": fitz.TEXT_ALIGN_CENTER,
    "right": fitz.TEXT_ALIGN_RIGHT,
}


def _placement_bbox(block: dict[str, Any]) -> list[float]:
    """Match the editor box exactly (where the user placed/resized the block)."""
    cur = block.get("bbox")
    if cur and len(cur) >= 4:
        return list(cur)
    return list(block.get("originalBbox") or [])


def _digit_only_placement_bbox(
    page: fitz.Page, block: dict[str, Any], page_blocks: list[dict[str, Any]]
) -> list[float] | None:
    """Narrow insert target to digit glyphs when the block model merged '100מחסן'."""
    if not _numeric_only_edit(block):
        return None
    ref_bbox = list(block.get("originalBbox") or block.get("bbox") or [])
    if len(ref_bbox) < 4:
        return None
    probe = _erase_search_content(block, page_blocks)
    rects = harvest_search_glyph_rects(page, ref_bbox, probe) if probe else []
    hebrew_zones = _hebrew_label_blocks(page_blocks, block.get("id"))
    rects = [
        r
        for r in rects
        if _rect_covers_only_digits(page, r) and not _rect_hits_hebrew_zone(r, hebrew_zones)
    ]
    if not rects:
        return None
    return [
        min(r.x0 for r in rects),
        min(r.y0 for r in rects),
        max(r.x1 for r in rects),
        max(r.y1 for r in rects),
    ]


def _vertical_stack(a: fitz.Rect, b: fitz.Rect) -> bool:
    overlap = min(a.y1, b.y1) - max(a.y0, b.y0)
    if overlap <= 0:
        return False
    return overlap >= min(a.height, b.height) * 0.2


def _clip_insert_rect(
    rect: fitz.Rect, block: dict[str, Any], page_blocks: list[dict[str, Any]]
) -> fitz.Rect:
    """Only nudge insert away from unmodified blocks stacked above/below — not table columns."""
    for other in page_blocks:
        if other.get("type") != "text":
            continue
        if other.get("id") == block.get("id"):
            continue
        if block_is_modified(other) or other.get("deleted"):
            continue
        ob = fitz.Rect(*(other.get("originalBbox") or other.get("bbox") or []))
        if ob.is_empty or not rect.intersects(ob) or not _vertical_stack(rect, ob):
            continue
        o_cy = (ob.y0 + ob.y1) / 2
        r_cy = (rect.y0 + rect.y1) / 2
        if o_cy <= r_cy and ob.y1 > rect.y0:
            rect.y0 = max(rect.y0, ob.y1 + 0.5)
        elif o_cy > r_cy and ob.y0 < rect.y1:
            rect.y1 = min(rect.y1, ob.y0 - 0.5)
    return rect


def _reference_bbox(block: dict[str, Any]) -> list[float]:
    ref = block.get("originalBbox")
    if ref and len(ref) >= 4:
        return list(ref)
    return _placement_bbox(block)


def _bbox_moved(block: dict[str, Any]) -> bool:
    orig = block.get("originalBbox")
    cur = block.get("bbox", [])
    if not orig or len(orig) != len(cur):
        return False
    return any(abs(a - b) > 0.5 for a, b in zip(orig, cur))


def _placement_origin(
    block: dict[str, Any], bbox_override: list[float] | None = None
) -> fitz.Point:
    bbox = bbox_override or _placement_bbox(block)
    orig = list(block.get("originalBbox") or block.get("bbox") or bbox)
    origin = block.get("textOrigin") or [orig[0], orig[3]]
    align = block.get("align", "left")
    rtl = block.get("direction") == "rtl" or block_needs_unicode_font(block)

    if len(bbox) >= 4 and len(orig) >= 4:
        dx = bbox[0] - orig[0]
        dy = bbox[3] - orig[3]
        if rtl and align == "right":
            return fitz.Point(bbox[2], float(origin[1]) + dy)
        return fitz.Point(float(origin[0]) + dx, float(origin[1]) + dy)
    return fitz.Point(bbox[0], bbox[3])


def _tighten_erase_rect(
    rect: fitz.Rect, block: dict[str, Any] | None = None, max_height: float = 11.0
) -> fitz.Rect:
    """Narrow tall erase boxes so redaction does not drop whole PDF text runs."""
    if block:
        bb = block.get("originalBbox") or block.get("bbox") or []
        if len(bb) >= 4 and (bb[2] - bb[0]) < 130 and (bb[3] - bb[1]) < 24:
            max_height = 8.5
    if rect.height <= max_height + 1:
        return rect
    cy = (rect.y0 + rect.y1) / 2
    half = min(rect.height, max_height) / 2
    pad_x = min(0.4, rect.width * 0.05)
    return fitz.Rect(rect.x0 + pad_x, cy - half, rect.x1 - pad_x, cy + half)


def _hebrew_label_blocks(page_blocks: list[dict[str, Any]], skip_id: str) -> list[fitz.Rect]:
    import re

    zones: list[fitz.Rect] = []
    for other in page_blocks:
        if other.get("type") != "text" or other.get("id") == skip_id:
            continue
        text = (other.get("content") or "").strip()
        if not text or not re.search(r"[\u0590-\u05FF]{2,}", text):
            continue
        # Mixed digit+Hebrew rows (e.g. '100מחסן :') are quantity cells, not label shields.
        if re.search(r"\d", text) and re.search(r"[\u0590-\u05FF]{2,}", text):
            continue
        bb = other.get("originalBbox") or other.get("bbox") or []
        if len(bb) >= 4:
            zones.append(fitz.Rect(*bb))
    return zones


def _rect_hits_hebrew_zone(rect: fitz.Rect, zones: list[fitz.Rect]) -> bool:
    for zone in zones:
        if rect.intersects(zone):
            return True
    return False


def _intersects_unmodified_neighbor(
    rect: fitz.Rect, block_id: str, page_blocks: list[dict[str, Any]]
) -> bool:
    """Skip erase only when an unmodified neighbor owns the center of this rect."""
    texts = [
        b
        for b in page_blocks
        if b.get("type") == "text" and not b.get("deleted")
    ]
    cx = (rect.x0 + rect.x1) / 2
    cy = (rect.y0 + rect.y1) / 2
    if _owner_block_id(cx, cy, texts) == block_id:
        return False
    for other in page_blocks:
        if other.get("type") != "text" or other.get("id") == block_id:
            continue
        if block_is_modified(other) or other.get("deleted"):
            continue
        ob = fitz.Rect(*(other.get("originalBbox") or other.get("bbox") or []))
        if ob.is_empty or not rect.intersects(ob):
            continue
        overlap = rect & ob
        if _rect_area(overlap) > 0.2 * _rect_area(rect):
            return True
    return False


def _line_erase_rect(block: dict[str, Any]) -> fitz.Rect | None:
    """One tight band across the original line — clears residue when per-glyph erase misses."""
    ref = block.get("originalBbox") or block.get("bbox")
    if not ref or len(ref) < 4:
        return None
    fs = float(block.get("fontSize") or 11)
    cy = (ref[1] + ref[3]) / 2
    half = min(max(fs * 0.52, 4.0), (ref[3] - ref[1]) * 0.42)
    pad_x = min(1.0, (ref[2] - ref[0]) * 0.03)
    return fitz.Rect(ref[0] + pad_x, cy - half, ref[2] - pad_x, cy + half)


def _original_text_still_visible(page: fitz.Page, block: dict[str, Any]) -> bool:
    old = (block.get("originalContent") or block.get("content") or "").strip()
    ref = block.get("originalBbox") or block.get("bbox")
    if not ref or len(ref) < 4:
        return False
    box = (page.get_textbox(fitz.Rect(*ref) + (-2, -2, 2, 2)) or "").strip()
    if not box:
        return False
    # Moved box: any leftover paint at the old coordinates is ghost text.
    if _bbox_moved(block):
        return True
    if not old:
        return False
    for token in old.split():
        if len(token) >= 2 and token in box:
            return True
    if len(old) >= 2 and old in box:
        return True
    return False


def _shrink_erase_from_drawings(page: fitz.Page, rect: fitz.Rect) -> fitz.Rect | None:
    """Trim erase boxes so redact fill does not paint over table rules."""
    shrunk = fitz.Rect(rect)
    for drawing in page.get_drawings():
        dr = fitz.Rect(drawing.get("rect") or (0, 0, 0, 0))
        if dr.is_empty or not shrunk.intersects(dr):
            continue
        if dr.height <= 2.5 and dr.width >= 6:
            line_y = (dr.y0 + dr.y1) / 2
            if shrunk.y0 < line_y < shrunk.y1:
                if line_y - shrunk.y0 <= shrunk.y1 - line_y:
                    shrunk.y0 = min(shrunk.y1 - 1.2, line_y + 0.6)
                else:
                    shrunk.y1 = max(shrunk.y0 + 1.2, line_y - 0.6)
        if dr.width <= 2.5 and dr.height >= 6:
            line_x = (dr.x0 + dr.x1) / 2
            if shrunk.x0 < line_x < shrunk.x1:
                if line_x - shrunk.x0 <= shrunk.x1 - line_x:
                    shrunk.x0 = min(shrunk.x1 - 1.2, line_x + 0.6)
                else:
                    shrunk.x1 = max(shrunk.x0 + 1.2, line_x - 0.6)
    if shrunk.width < 0.8 or shrunk.height < 0.8:
        return None
    return shrunk


def _numeric_only_edit(block: dict[str, Any]) -> bool:
    import re

    old = (block.get("originalContent") or "").strip()
    new = (block.get("content") or "").strip()
    if not old or not new:
        return False
    return (
        bool(re.search(r"\d", new))
        and not re.search(r"[\u0590-\u05FF]{2,}", new)
        and bool(re.search(r"[\u0590-\u05FF]{2,}", old))
    )


def _rect_covers_only_digits(page: fitz.Page, rect: fitz.Rect) -> bool:
    import re

    box = (page.get_textbox(rect + (-1, -1, 1, 1)) or "").strip()
    if not box:
        return True
    if re.search(r"[\u0590-\u05FF]{2,}", box):
        return False
    return bool(re.search(r"\d", box))


def _erase_search_content(block: dict[str, Any], page_blocks: list[dict[str, Any]]) -> str:
    """Limit search-based erase so a merged '100מחסן' block does not wipe מחסן."""
    import re

    old = (block.get("originalContent") or block.get("content") or "").strip()
    new = (block.get("content") or "").strip()
    if not old:
        return ""
    neighbor_parts: set[str] = set()
    ref = block.get("originalBbox") or block.get("bbox") or []
    if len(ref) >= 4:
        region = fitz.Rect(*ref)
        for other in page_blocks:
            if other.get("type") != "text" or other.get("id") == block.get("id"):
                continue
            if block_is_modified(other) or other.get("deleted"):
                continue
            ob = fitz.Rect(*(other.get("originalBbox") or other.get("bbox") or []))
            if ob.is_empty or not region.intersects(ob):
                continue
            for part in re.split(r"\s+", (other.get("content") or "").strip()):
                if len(part) >= 2:
                    neighbor_parts.add(part)

    parts = re.findall(r"\d+\.?\d*|[\u0590-\u05FF]{2,}|[^\d\s\u0590-\u05FF]+", old)
    if re.search(r"\d", new) and not re.search(r"[\u0590-\u05FF]{2,}", new):
        parts = [p for p in parts if re.search(r"\d", p)]
    elif re.search(r"[\u0590-\u05FF]", new):
        parts = [p for p in parts if re.search(r"[\u0590-\u05FF]", p)]

    keep = [p for p in parts if p and p not in neighbor_parts]
    return " ".join(keep) if keep else old


def _erase_rects_for_block(
    page: fitz.Page, block: dict[str, Any], page_blocks: list[dict[str, Any]]
) -> list[fitz.Rect]:
    rects: list[fitz.Rect] = []
    block_id = block.get("id")
    erase_content = _erase_search_content(block, page_blocks)
    ref_bbox = list(block.get("originalBbox") or block.get("bbox") or [])

    sources: list[fitz.Rect] = list(glyph_rects_for_block(page, block, page_blocks))
    if erase_content and len(ref_bbox) >= 4:
        sources.extend(harvest_search_glyph_rects(page, ref_bbox, erase_content))

    seen: set[tuple[float, float, float, float]] = set()
    numeric_only = _numeric_only_edit(block)
    hebrew_zones = _hebrew_label_blocks(page_blocks, block_id) if numeric_only else []
    for rect in sources:
        if numeric_only and not _rect_covers_only_digits(page, rect):
            continue
        if numeric_only and _rect_hits_hebrew_zone(rect, hebrew_zones):
            continue
        tight = _tighten_erase_rect(rect, block)
        key = (round(tight.x0, 1), round(tight.y0, 1), round(tight.x1, 1), round(tight.y1, 1))
        if key in seen:
            continue
        seen.add(key)
        if _intersects_unmodified_neighbor(tight, block_id, page_blocks):
            continue
        tight = _shrink_erase_from_drawings(page, tight)
        if tight is None:
            continue
        if tight.width > 0.2 and tight.height > 0.2:
            rects.append(tight)

    if not numeric_only:
        band = _line_erase_rect(block)
        if band and band.width > 1 and band.height > 1:
            if not _intersects_unmodified_neighbor(band, block_id, page_blocks):
                rects.append(band)
    return rects


def _overlap_foreign_ratio(
    rect: fitz.Rect, block_id: str, page_blocks: list[dict[str, Any]]
) -> float:
    area = _rect_area(rect)
    if area <= 0:
        return 0.0
    foreign = 0.0
    for other in page_blocks:
        if other.get("type") != "text" or other.get("id") == block_id:
            continue
        if block_is_modified(other) or other.get("deleted"):
            continue
        ob = fitz.Rect(*(other.get("originalBbox") or other.get("bbox") or []))
        if not ob.is_empty:
            foreign = max(foreign, _rect_area(rect & ob))
    return foreign / area


def _rect_area(rect: fitz.Rect) -> float:
    return max(0.0, rect.width) * max(0.0, rect.height)


def _export_text(block: dict[str, Any]) -> str:
    """Return text in visual order for PyMuPDF's LTR text engine."""
    content = (block.get("content") or "").strip()
    if block_needs_unicode_font(block):
        try:
            from bidi.algorithm import get_display

            return get_display(content)
        except ImportError:
            pass
    return content


def _search_probes(text: str) -> list[str]:
    t = (text or "").strip()
    if not t:
        return []
    probes: list[str] = []
    for part in t.split():
        part = part.strip()
        if len(part) >= 2:
            probes.append(part)
    if len(t) >= 2 and t not in probes:
        probes.insert(0, t)
    if not probes:
        return []
    return probes


def _hit_near_bbox(hit: fitz.Rect, bbox: list[float], pad: float = 6.0) -> bool:
    if len(bbox) < 4:
        return True
    region = fitz.Rect(*bbox) + (-pad, -pad, pad, pad)
    return bool(region.intersects(hit))


def _residual_old_text_in_bbox(
    page: fitz.Page, bbox: list[float], old_text: str, new_text: str
) -> bool:
    """True when pre-edit tokens still show in the box (would cause stacked/double text)."""
    old = (old_text or "").strip()
    new = (new_text or "").strip()
    if not old or len(bbox) < 4:
        return False
    box = (page.get_textbox(fitz.Rect(*bbox) + (-3, -3, 3, 3)) or "").strip()
    if not box:
        return False
    for token in old.split():
        if len(token) < 2 or token in new:
            continue
        if token in box:
            return True
    if len(old) >= 3 and old not in new and old in box:
        return True
    return False


def _new_text_placed(
    page: fitz.Page, bbox: list[float], text: str, *, also_try: str = "", old_text: str = ""
) -> bool:
    """True only when the new string is present and old content is not left behind."""
    if len(bbox) < 4:
        return False
    if _residual_old_text_in_bbox(page, bbox, old_text, also_try or text):
        return False
    region = fitz.Rect(*bbox)
    expanded = region + (-4, -4, 4, 4)
    box_text = (page.get_textbox(expanded) or "").strip()
    hebrew_in_box = sum(1 for ch in box_text if 0x0590 <= ord(ch) <= 0x05FF)
    for candidate in (text, also_try):
        c = (candidate or "").strip()
        if not c:
            continue
        if c in box_text:
            return True
        for part in c.split():
            if len(part) >= 2 and part in box_text:
                return True
        hebrew_needed = sum(1 for ch in c if 0x0590 <= ord(ch) <= 0x05FF)
        if hebrew_needed >= 2 and hebrew_in_box >= hebrew_needed * 0.65:
            return True

    for candidate in (text, also_try):
        for probe in _search_probes(candidate):
            for hit in page.search_for(probe):
                if _hit_near_bbox(hit, bbox):
                    return True
    return False


def _ensure_hebrew_font(page: fitz.Page) -> str:
    label = "Fhebrew"
    path = hebrew_font_path()
    if not path:
        return "helv"
    try:
        page.insert_font(fontname=label, fontfile=path)
    except Exception:
        pass
    return label


def _insert_with_textwriter(
    page: fitz.Page,
    block: dict[str, Any],
    content: str,
    fontname: str,
    bbox_override: list[float] | None = None,
) -> bool:
    path = hebrew_font_path()
    if not path:
        return False
    try:
        font = fitz.Font(fontfile=path)
        tw = fitz.TextWriter(page.rect)
        tw.append(
            _placement_origin(block, bbox_override),
            content,
            font=font,
            fontsize=float(block.get("fontSize") or 12),
        )
        tw.write_text(page, color=(0, 0, 0))
        return True
    except Exception:
        return False


def _try_insert_textbox(
    page: fitz.Page,
    rect: fitz.Rect,
    content: str,
    fontname: str,
    fontsize: float,
    align: int,
) -> bool:
    for scale in (1.0, 0.92, 0.85, 0.78, 0.72):
        fs = max(6.0, fontsize * scale)
        try:
            rc = page.insert_textbox(
                rect,
                content,
                fontname=fontname,
                fontsize=fs,
                color=(0, 0, 0),
                align=align,
                fill=None,
                overlay=True,
            )
        except Exception:
            continue
        if rc >= 0:
            return True
    return False


def _insert_text_in_bbox(
    page: fitz.Page,
    doc: fitz.Document,
    block: dict[str, Any],
    page_blocks: list[dict[str, Any]],
) -> None:
    content = _export_text(block)
    if not content:
        return

    bbox = _digit_only_placement_bbox(page, block, page_blocks) or _placement_bbox(block)
    if len(bbox) < 4:
        return

    raw = (block.get("content") or "").strip()
    original = (block.get("originalContent") or "").strip()
    fontsize = float(block.get("fontSize") or 12)
    text_rect = _clip_insert_rect(fitz.Rect(*bbox), block, page_blocks)
    if text_rect.width < 2 or text_rect.height < 2:
        text_rect = fitz.Rect(*bbox)
    # Never draw outside the editor box the user sees.
    editor = fitz.Rect(*bbox)
    text_rect = text_rect & editor
    align = _ALIGN.get(block.get("align", "left"), fitz.TEXT_ALIGN_LEFT)
    hebrew = block_needs_unicode_font(block)

    if hebrew:
        fontname = _ensure_hebrew_font(page)
        if not _numeric_only_edit(block) and _try_insert_textbox(
            page, text_rect, content, fontname, fontsize, align
        ):
            if _new_text_placed(page, bbox, content, also_try=raw, old_text=original):
                return
        try:
            page.insert_text(
                _placement_origin(block, bbox),
                content,
                fontname=fontname,
                fontsize=fontsize,
                color=(0, 0, 0),
            )
            if _new_text_placed(page, bbox, content, also_try=raw, old_text=original):
                return
        except Exception:
            pass
        if _insert_with_textwriter(page, block, content, fontname, bbox):
            if _new_text_placed(page, bbox, content, also_try=raw, old_text=original):
                return
        logger.warning(
            "Hebrew text not visible after insert for block %s (%r)",
            block.get("id"),
            content[:40],
        )
        return

    fontname = register_document_font(page, doc, block)
    if not _numeric_only_edit(block) and _try_insert_textbox(
        page, text_rect, content, fontname, fontsize, align
    ):
        if _new_text_placed(page, bbox, content, also_try=raw, old_text=original):
            return
    try:
        page.insert_text(
            _placement_origin(block, bbox),
            content,
            fontname=fontname,
            fontsize=fontsize,
            color=(0, 0, 0),
        )
        if _new_text_placed(page, bbox, content, also_try=raw, old_text=original):
            return
    except Exception:
        pass
    if not block_is_mostly_latin(block):
        return
    if fontname != "helv" and _try_insert_textbox(
        page, text_rect, content, "helv", fontsize, align
    ):
        if _new_text_placed(page, bbox, content, also_try=raw, old_text=original):
            return
    logger.warning(
        "Could not place visible text for block %s (%r)",
        block.get("id"),
        content[:40],
    )


def _erase_glyphs_only(
    page: fitz.Page, block: dict[str, Any], page_blocks: list[dict[str, Any]]
) -> bool:
    return bool(_erase_rects_for_block(page, block, page_blocks))


def _redact_fill_for_block(block: dict[str, Any]) -> tuple[float, float, float]:
    rgb = block.get("backgroundRgb") or [255, 255, 255]
    if len(rgb) >= 3:
        return (rgb[0] / 255.0, rgb[1] / 255.0, rgb[2] / 255.0)
    return (1.0, 1.0, 1.0)


def _refresh_page_glyphs(page: fitz.Page, page_blocks: list[dict[str, Any]]) -> None:
    """Re-harvest glyph rects from the PDF so export matches current file (Adobe-like precision)."""
    for block in page_blocks:
        if block.get("type") == "text":
            stamp_glyph_rects(page, block)
    resolve_glyph_ownership(page_blocks)


def _redact_background_rect(
    page: fitz.Page, block: dict[str, Any], page_blocks: list[dict[str, Any]]
) -> None:
    bbox = block.get("originalBbox") or block.get("bbox")
    if not bbox or len(bbox) < 4:
        return
    fill = rgb_to_fill(resolve_background_removal_fill(page, block, page_blocks))
    page.add_redact_annot(fitz.Rect(*bbox), fill=fill)


def _flush_text_redactions(page: fitz.Page) -> None:
    page.apply_redactions(images=0, graphics=0, text=0)


def _flush_background_redactions(page: fitz.Page) -> None:
    page.apply_redactions(images=0, graphics=2, text=1)


def export_pdf_from_model(
    source_storage_key: str,
    model: dict[str, Any],
    output_suffix: str = ".pdf",
) -> str:
    if not model_has_changes(model):
        return save_bytes(read_file(source_storage_key), "exports", output_suffix)

    clear_font_cache()
    source_path = str(file_path(source_storage_key))
    surgeon_result = apply_surgeon_export_pass(source_path, model)
    surgeon_handled: set[str] = set()
    open_path = source_path
    if surgeon_result:
        open_path, surgeon_handled = surgeon_result

    doc = fitz.open(open_path)

    try:
        for page_data in model.get("pages", []):
            page_idx = page_data["pageIndex"]
            if page_idx >= len(doc):
                continue
            page = doc[page_idx]
            page_blocks = page_data.get("blocks", [])
            _refresh_page_glyphs(page, page_blocks)

            for block in page_blocks:
                if block.get("type") == "background" and block.get("deleted"):
                    _redact_background_rect(page, block, page_blocks)
            if any(
                b.get("type") == "background" and b.get("deleted") for b in page_blocks
            ):
                _flush_background_redactions(page)

            text_touched = False
            claimed: set[tuple[float, float, float, float]] = set()
            for block in page_blocks:
                if block.get("type") == "text" and block_is_modified(block):
                    if block.get("id") in surgeon_handled:
                        continue
                    rects = _erase_rects_for_block(page, block, page_blocks)
                    added = False
                    for rect in rects:
                        key = (
                            round(rect.x0, 1),
                            round(rect.y0, 1),
                            round(rect.x1, 1),
                            round(rect.y1, 1),
                        )
                        if key in claimed:
                            continue
                        claimed.add(key)
                        page.add_redact_annot(
                            rect,
                            fill=_redact_fill_for_block(block),
                            cross_out=False,
                        )
                        added = True
                    if added:
                        text_touched = True
            if text_touched:
                _flush_text_redactions(page)

            # Second pass: clear ghost text left at the pre-move / pre-edit coordinates.
            touch2 = False
            for block in page_blocks:
                if block.get("type") != "text" or not block_is_modified(block):
                    continue
                if block.get("id") in surgeon_handled:
                    continue
                if not _original_text_still_visible(page, block):
                    continue
                if _numeric_only_edit(block):
                    continue
                ref = block.get("originalBbox") or block.get("bbox")
                if not ref or len(ref) < 4:
                    continue
                erase_rect = _line_erase_rect(block)
                if _bbox_moved(block) and erase_rect and not _intersects_unmodified_neighbor(
                    erase_rect, block.get("id"), page_blocks
                ):
                    pass
                elif _bbox_moved(block):
                    full = fitz.Rect(*ref)
                    if _overlap_foreign_ratio(full, block.get("id"), page_blocks) < 0.12:
                        erase_rect = full
                    else:
                        erase_rect = _line_erase_rect(block)
                if not erase_rect or erase_rect.is_empty:
                    continue
                if _intersects_unmodified_neighbor(erase_rect, block.get("id"), page_blocks):
                    erase_rect = _line_erase_rect(block)
                    if not erase_rect or _intersects_unmodified_neighbor(
                        erase_rect, block.get("id"), page_blocks
                    ):
                        continue
                page.add_redact_annot(
                    erase_rect,
                    fill=_redact_fill_for_block(block),
                    cross_out=False,
                )
                touch2 = True
            if touch2:
                _flush_text_redactions(page)

            for block in page_blocks:
                if block.get("type") != "text" or not block_is_modified(block):
                    continue
                if block.get("id") in surgeon_handled:
                    continue
                if block.get("deleted"):
                    continue
                original = (block.get("originalContent") or "").strip()
                new_text = (block.get("content") or "").strip()
                if original == new_text and not _bbox_moved(block):
                    continue
                if new_text:
                    _insert_text_in_bbox(page, doc, block, page_blocks)

        out = file_path(f"work/export/{uuid.uuid4().hex}.pdf")
        out.parent.mkdir(parents=True, exist_ok=True)
        doc.save(str(out), garbage=4, deflate=True)
        return save_bytes(out.read_bytes(), "exports", output_suffix)
    finally:
        doc.close()
