"""Tiered PDF analysis: PyMuPDF native extract, optional OCR escalation."""

from __future__ import annotations

import json
import logging
import shutil
import uuid
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF

from app.config import settings
from app.pipelines.background import link_text_to_backgrounds, sample_border_rgb
from app.pipelines.glyph_quads import resolve_glyph_ownership, stamp_glyph_rects
from app.pipelines.background_layers import extract_background_blocks
from app.pipelines.table_cells import merge_blocks_into_table_cells
from app.storage import file_path, read_file, save_bytes

logger = logging.getLogger(__name__)

_TESSERACT_RESOLVED: str | None | bool = False  # False = not checked yet


def resolve_tesseract_cmd() -> str | None:
    """Find tesseract binary; cache result. Returns None if unavailable."""
    global _TESSERACT_RESOLVED
    if _TESSERACT_RESOLVED is not False:
        return _TESSERACT_RESOLVED  # type: ignore[return-value]

    candidates: list[str] = []
    if settings.tesseract_cmd:
        candidates.append(settings.tesseract_cmd)
    found = shutil.which("tesseract")
    if found:
        candidates.append(found)
    for path in (
        "/opt/homebrew/bin/tesseract",
        "/usr/local/bin/tesseract",
    ):
        if Path(path).is_file():
            candidates.append(path)

    for cmd in candidates:
        if Path(cmd).is_file() or shutil.which(cmd):
            _TESSERACT_RESOLVED = cmd
            return cmd

    _TESSERACT_RESOLVED = None
    return None

NATIVE_TEXT_THRESHOLD = 0.15


def _page_has_native_glyphs(page: fitz.Page) -> bool:
    """True when PDF has real vector text spans (tables, forms, labels)."""
    for block in page.get_text("dict").get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                if (span.get("text") or "").strip():
                    return True
    return False


def _classify_page(page: fitz.Page) -> tuple[str, str]:
    if _page_has_native_glyphs(page):
        return "native", "pymupdf"
    text = page.get_text().strip()
    blocks = page.get_text("blocks")
    text_area = sum((b[2] - b[0]) * (b[3] - b[1]) for b in blocks if len(b) >= 5)
    page_area = page.rect.width * page.rect.height or 1
    ratio = text_area / page_area if text_area else (len(text) / 500.0)
    if ratio >= NATIVE_TEXT_THRESHOLD or len(text) > 80:
        return "native", "pymupdf"
    return "scanned", "pymupdf_ocr_fallback"


def _iou(a: list[float], b: list[float]) -> float:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    inter = (ix1 - ix0) * (iy1 - iy0)
    area_a = (ax1 - ax0) * (ay1 - ay0)
    area_b = (bx1 - bx0) * (by1 - by0)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def _merge_adjacent_spans(blocks: list[dict[str, Any]], page_index: int) -> list[dict[str, Any]]:
    """Merge only spans on the same line with a small horizontal gap (not table columns)."""
    if not blocks:
        return blocks
    sorted_blocks = sorted(blocks, key=lambda b: (round(b["bbox"][1], 1), b["bbox"][0]))
    merged: list[dict[str, Any]] = []
    max_gap = 2.5  # word space only — never merge separate table columns

    for block in sorted_blocks:
        placed = False
        for m in merged:
            my0, my1 = m["bbox"][1], m["bbox"][3]
            by0, by1 = block["bbox"][1], block["bbox"][3]
            y_overlap = min(my1, by1) - max(my0, by0)
            line_h = max(my1 - my0, by1 - by0, 1)
            if y_overlap / line_h < 0.6:
                continue
            if block["bbox"][0] >= m["bbox"][2]:
                gap = block["bbox"][0] - m["bbox"][2]
            elif m["bbox"][0] >= block["bbox"][2]:
                gap = m["bbox"][0] - block["bbox"][2]
            else:
                gap = 0.0
            if gap > max_gap:
                continue
            m["bbox"] = [
                min(m["bbox"][0], block["bbox"][0]),
                min(m["bbox"][1], block["bbox"][1]),
                max(m["bbox"][2], block["bbox"][2]),
                max(m["bbox"][3], block["bbox"][3]),
            ]
            m["content"] = f"{m['content']} {block['content']}".strip()
            m["fontSize"] = max(m.get("fontSize", 12), block.get("fontSize", 12))
            placed = True
            break
        if not placed:
            merged.append({**block, "id": f"t-{page_index}-{uuid.uuid4().hex[:8]}"})
    return merged


def _text_direction(text: str) -> str:
    if not text:
        return "ltr"
    hebrew = sum(1 for c in text if "\u0590" <= c <= "\u05FF")
    if hebrew >= max(1, len(text) * 0.25):
        return "rtl"
    return "ltr"


def _span_alignment(span_bbox: list[float], line_bbox: list[float], text: str = "") -> str:
    if _text_direction(text) == "rtl":
        return "right"
    sw = span_bbox[2] - span_bbox[0]
    lw = line_bbox[2] - line_bbox[0]
    if lw <= 0:
        return "left"
    cx = (span_bbox[0] + span_bbox[2]) / 2
    lx0, lx1 = line_bbox[0], line_bbox[2]
    if cx < lx0 + lw * 0.35:
        return "left"
    if cx > lx0 + lw * 0.65:
        return "right"
    return "center"


def _dedupe_overlapping_text(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop only true duplicates (same glyphs), keep nearby separate cells."""
    texts = [b for b in blocks if b.get("type") == "text"]
    others = [b for b in blocks if b.get("type") != "text"]
    kept: list[dict[str, Any]] = []
    for block in sorted(texts, key=lambda b: -len(b.get("content", ""))):
        dup = False
        for k in kept:
            if _iou(block["bbox"], k["bbox"]) < 0.92:
                continue
            a = (block.get("content") or "").strip()
            b = (k.get("content") or "").strip()
            if a == b or (a and b and (a in b or b in a)):
                dup = True
                break
        if dup:
            continue
        kept.append(block)
    return kept + others


def _word_touches_block(word: tuple, block: dict[str, Any]) -> bool:
    wb = [word[0], word[1], word[2], word[3]]
    if _iou(wb, block["bbox"]) > 0.08:
        return True
    cx, cy = (word[0] + word[2]) / 2, (word[1] + word[3]) / 2
    bx0, by0, bx1, by1 = block["bbox"]
    return bx0 <= cx <= bx1 and by0 <= cy <= by1


def _split_multiword_blocks(
    page: fitz.Page, page_index: int, blocks: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Split wide cells into one block per PDF word (e.g. '100' vs 'מחסן')."""
    out: list[dict[str, Any]] = []
    for block in blocks:
        if block.get("type") != "text":
            out.append(block)
            continue
        if block.get("tableGroupId"):
            out.append(block)
            continue
        bb = block.get("bbox") or []
        if len(bb) < 4 or (bb[2] - bb[0]) < 28:
            out.append(block)
            continue
        try:
            words = page.get_text("words")
        except Exception:
            out.append(block)
            continue
        hits = [w for w in words if len(w) >= 5 and _word_touches_block(w, block)]
        if len(hits) < 2:
            out.append(block)
            continue
        for word in hits:
            text = (word[4] or "").strip()
            if not text:
                continue
            bbox = [word[0], word[1], word[2], word[3]]
            out.append(
                {
                    **block,
                    "id": f"t-{page_index}-{uuid.uuid4().hex[:8]}",
                    "bbox": bbox,
                    "content": text,
                    "textOrigin": [bbox[0], bbox[3] - 1],
                    "align": _span_alignment(bbox, bbox, text),
                    "direction": _text_direction(text),
                    "glyphRects": None,
                }
            )
    return out


def _split_oversized_line_blocks(
    page: fitz.Page, page_index: int, blocks: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Split one PDF span that covers a whole table row into per-word editable cells."""
    out: list[dict[str, Any]] = []
    for block in blocks:
        if block.get("type") != "text":
            out.append(block)
            continue
        if block.get("tableGroupId"):
            out.append(block)
            continue
        bb = block.get("bbox") or []
        if len(bb) < 4 or (bb[2] - bb[0]) < 100:
            out.append(block)
            continue
        try:
            words = page.get_text("words")
        except Exception:
            out.append(block)
            continue
        hits = [w for w in words if len(w) >= 5 and _word_touches_block(w, block)]
        if len(hits) < 2:
            out.append(block)
            continue
        for word in hits:
            text = (word[4] or "").strip()
            if not text:
                continue
            bbox = [word[0], word[1], word[2], word[3]]
            out.append(
                {
                    **block,
                    "id": f"t-{page_index}-{uuid.uuid4().hex[:8]}",
                    "bbox": bbox,
                    "content": text,
                    "textOrigin": [bbox[0], bbox[3] - 1],
                    "align": _span_alignment(bbox, bbox, text),
                    "direction": _text_direction(text),
                    "glyphRects": None,
                }
            )
    return out


def _append_missing_word_blocks(
    page: fitz.Page, page_index: int, blocks: list[dict[str, Any]]
) -> None:
    """Add editable blocks for native text missed by line extraction."""
    texts = [b for b in blocks if b.get("type") == "text"]
    try:
        words = page.get_text("words")
    except Exception:
        return
    for word in words:
        if len(word) < 5:
            continue
        text = (word[4] or "").strip()
        if not text or len(text) > 120:
            continue
        if any(_word_touches_block(word, t) for t in texts):
            continue
        x0, y0, x1, y1 = word[0], word[1], word[2], word[3]
        bbox = [x0, y0, x1, y1]
        blocks.append(
            {
                "id": f"t-{page_index}-{uuid.uuid4().hex[:8]}",
                "type": "text",
                "layer": "text",
                "bbox": bbox,
                "content": text,
                "fontSize": round(max(y1 - y0, 8) * 0.85, 1),
                "fontFamily": "Helvetica",
                "pdfFont": "Helvetica",
                "align": _span_alignment(bbox, bbox, text),
                "direction": _text_direction(text),
                "source": "native",
            }
        )
        texts.append(blocks[-1])


def _span_origin(span: dict[str, Any], bbox: list[float]) -> list[float]:
    origin = span.get("origin")
    if isinstance(origin, (list, tuple)) and len(origin) >= 2:
        return [float(origin[0]), float(origin[1])]
    chars = span.get("chars") or []
    if chars and chars[0].get("origin"):
        o = chars[0]["origin"]
        if isinstance(o, (list, tuple)) and len(o) >= 2:
            return [float(o[0]), float(o[1])]
    return [bbox[0], bbox[3] - 1]


def _block_from_span(page_index: int, span: dict[str, Any], line_bbox: list[float]) -> dict[str, Any] | None:
    text = (span.get("text") or "").strip()
    if not text:
        return None
    x0, y0, x1, y1 = span["bbox"]
    bbox = [x0, y0, x1, y1]
    return {
        "id": f"t-{page_index}-{uuid.uuid4().hex[:8]}",
        "type": "text",
        "layer": "text",
        "bbox": bbox,
        "content": text,
        "fontSize": round(float(span.get("size", 12)), 2),
        "fontFamily": span.get("font", "Helvetica"),
        "pdfFont": span.get("font", "Helvetica"),
        "textOrigin": _span_origin(span, bbox),
        "align": _span_alignment(bbox, line_bbox, text),
        "direction": _text_direction(text),
        "source": "native",
    }


def _extract_text_blocks(page: fitz.Page, page_index: int) -> list[dict[str, Any]]:
    """One block per PDF span — preserves per-cell fonts, sizes, and Hebrew order."""
    raw: list[dict[str, Any]] = []
    data = page.get_text("dict")
    for block in data.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            spans = [s for s in line.get("spans", []) if (s.get("text") or "").strip()]
            if not spans:
                continue
            line_bbox = list(spans[0]["bbox"])
            for span in spans[1:]:
                x0, y0, x1, y1 = span["bbox"]
                line_bbox = [
                    min(line_bbox[0], x0),
                    min(line_bbox[1], y0),
                    max(line_bbox[2], x1),
                    max(line_bbox[3], y1),
                ]
            for span in spans:
                item = _block_from_span(page_index, span, line_bbox)
                if item:
                    raw.append(item)
    return _dedupe_overlapping_text(_merge_adjacent_spans(raw, page_index))


def _extract_image_blocks(page: fitz.Page, page_index: int, assets_prefix: str) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for img_index, img in enumerate(page.get_images(full=True)):
        xref = img[0]
        try:
            info = page.parent.extract_image(xref)
            ext = info.get("ext", "png")
            asset_id = f"img-{page_index}-{img_index}"
            key = save_bytes(info["image"], f"{assets_prefix}/images", f".{ext}")
            rects = page.get_image_rects(xref)
            for rect_index, rect in enumerate(rects):
                blocks.append(
                    {
                        "id": f"{asset_id}-{rect_index}",
                        "type": "image",
                        "bbox": [rect.x0, rect.y0, rect.x1, rect.y1],
                        "assetId": key,
                        "source": "extracted",
                    }
                )
        except Exception:
            continue
    return blocks


def _ocr_fallback_blocks(page: fitz.Page, page_index: int) -> list[dict[str, Any]]:
    try:
        import pytesseract
        from PIL import Image
        from pytesseract import TesseractNotFoundError
    except ImportError:
        return []

    tesseract_cmd = resolve_tesseract_cmd()
    if not tesseract_cmd:
        return []

    pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

    try:
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
    except TesseractNotFoundError:
        logger.warning("Tesseract not found at %s", tesseract_cmd)
        return []
    except Exception as exc:
        logger.warning("OCR failed for page %s: %s", page_index, exc)
        return []
    blocks: list[dict[str, Any]] = []
    n = len(data["text"])
    for i in range(n):
        text = (data["text"][i] or "").strip()
        conf = int(data["conf"][i]) if data["conf"][i] != "-1" else 0
        if not text or conf < 40:
            continue
        scale = 0.5
        x = data["left"][i] * scale
        y = data["top"][i] * scale
        w = data["width"][i] * scale
        h = data["height"][i] * scale
        blocks.append(
            {
                "id": f"ocr-{page_index}-{i}",
                "type": "text",
                "bbox": [x, y, x + w, y + h],
                "content": text,
                "fontSize": max(8, round(h * 0.75, 1)),
                "fontFamily": "Helvetica",
                "source": "ocr",
            }
        )
    return blocks


def _stamp_originals(page: fitz.Page, blocks: list[dict[str, Any]]) -> None:
    for block in blocks:
        if block.get("type") == "text":
            block["originalContent"] = block.get("content", "")
            block["originalBbox"] = list(block.get("bbox", []))
            if not block.get("backgroundRgb"):
                rgb = sample_border_rgb(page, block["bbox"])
                if sum(rgb) / 3 < 200:
                    rgb = [255, 255, 255]
                block["backgroundRgb"] = rgb
            stamp_glyph_rects(page, block)
        elif block.get("type") == "background":
            block["originalBbox"] = list(block.get("bbox", []))
            block.setdefault("backgroundRgb", block.get("backgroundRgb"))
        elif block.get("type") == "image":
            block["originalBbox"] = list(block.get("bbox", []))
    resolve_glyph_ownership(blocks)


def _bbox_changed(block: dict[str, Any]) -> bool:
    orig = block.get("originalBbox")
    if not orig:
        return False
    cur = block.get("bbox", [])
    if len(orig) != len(cur):
        return True
    return any(abs(a - b) > 0.5 for a, b in zip(orig, cur))


def _norm_text(value: str) -> str:
    return " ".join((value or "").split())


def block_is_modified(block: dict[str, Any]) -> bool:
    if block.get("deleted") is True:
        return True
    if block.get("dirty") is True:
        return True
    if block.get("type") == "text":
        if _norm_text(block.get("content", "")) != _norm_text(
            block.get("originalContent", block.get("content", ""))
        ):
            return True
        return _bbox_changed(block)
    if block.get("type") == "background":
        return block.get("deleted") is True
    if block.get("type") == "image":
        return _bbox_changed(block)
    return False


def model_has_changes(model: dict[str, Any]) -> bool:
    for page in model.get("pages", []):
        for block in page.get("blocks", []):
            if block_is_modified(block):
                return True
    return False


def analyze_pdf(storage_key: str, file_id: str) -> dict[str, Any]:
    path = file_path(storage_key)
    doc = fitz.open(path)
    assets_prefix = f"artifacts/{file_id}"
    pages_out: list[dict[str, Any]] = []
    native_count = 0
    scanned_without_ocr = 0
    ocr_available = resolve_tesseract_cmd() is not None
    table_stats_total = {"tablesDetected": 0, "cellsGrouped": 0}

    for i in range(len(doc)):
        page = doc[i]
        page_type, tier = _classify_page(page)
        native_blocks = _extract_text_blocks(page, i)
        if page_type == "native":
            native_count += 1
            blocks = native_blocks
        else:
            blocks = _ocr_fallback_blocks(page, i)
            if not blocks:
                blocks = native_blocks
                tier = "pymupdf_partial" if native_blocks else tier
                if not blocks:
                    scanned_without_ocr += 1
            else:
                tier = "tesseract"

        blocks.extend(_extract_image_blocks(page, i, assets_prefix))
        blocks.extend(extract_background_blocks(page, i))
        _append_missing_word_blocks(page, i, blocks)
        blocks, table_stats = merge_blocks_into_table_cells(page, i, blocks, path)
        table_stats_total["tablesDetected"] += table_stats.get("tablesDetected", 0)
        table_stats_total["cellsGrouped"] += table_stats.get("cellsGrouped", 0)
        blocks = _split_multiword_blocks(page, i, blocks)
        blocks = _split_oversized_line_blocks(page, i, blocks)
        blocks = _dedupe_overlapping_text(blocks)
        link_text_to_backgrounds(blocks)
        _stamp_originals(page, blocks)
        pages_out.append(
            {
                "pageIndex": i,
                "pageType": page_type,
                "width": page.rect.width,
                "height": page.rect.height,
                "blocks": blocks,
                "tierUsed": tier,
            }
        )

    doc.close()
    total = len(pages_out) or 1
    return {
        "fileId": file_id,
        "pages": pages_out,
        "nativePageRatio": round(native_count / total, 3),
        "diagnostics": {
            "pageCount": total,
            "engine": "pymupdf",
            "tesseractAvailable": ocr_available,
            "scannedPagesWithoutOcr": scanned_without_ocr,
            "tablesDetected": table_stats_total["tablesDetected"],
            "tableCellsGrouped": table_stats_total["cellsGrouped"],
            **(
                {
                    "warning": (
                        "Tesseract is not installed. Scanned pages may have few editable text blocks. "
                        "Install with: brew install tesseract (macOS) or apt install tesseract-ocr (Linux)."
                    )
                }
                if not ocr_available
                else {}
            ),
        },
    }


def export_pdf_from_model(
    source_storage_key: str,
    model: dict[str, Any],
    output_suffix: str = ".pdf",
) -> str:
    from app.pipelines.export_apply import export_pdf_from_model as _export

    return _export(source_storage_key, model, output_suffix)


def save_block_document(model: dict[str, Any], prefix: str) -> str:
    return save_bytes(json.dumps(model, indent=2).encode(), prefix, ".json")
