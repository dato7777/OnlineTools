"""Detect table grids and merge text into one editable block per cell."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import fitz

logger = logging.getLogger(__name__)

_LINE_TOL = 1.5
_MIN_TABLE_CELLS = 2
_CELL_MARGIN = 0.35


@dataclass
class TableCell:
    bbox: list[float]
    row: int
    col: int


@dataclass
class TableRegion:
    id: str
    bbox: list[float]
    cells: list[TableCell]


def _cluster_positions(values: list[float], tol: float = _LINE_TOL) -> list[float]:
    if not values:
        return []
    sorted_vals = sorted(values)
    clusters: list[list[float]] = [[sorted_vals[0]]]
    for v in sorted_vals[1:]:
        if v - clusters[-1][-1] <= tol:
            clusters[-1].append(v)
        else:
            clusters.append([v])
    return [sum(c) / len(c) for c in clusters]


def _cell_from_pdfplumber(cell: tuple[float, float, float, float] | None) -> list[float] | None:
    if cell is None:
        return None
    x0, top, x1, bottom = cell
    if x1 <= x0 or bottom <= top:
        return None
    return [float(x0), float(top), float(x1), float(bottom)]


def _detect_tables_pdfplumber(pdf_path: Path, page_index: int) -> list[TableRegion]:
    try:
        import pdfplumber
    except ImportError:
        return []

    regions: list[TableRegion] = []
    try:
        with pdfplumber.open(pdf_path) as doc:
            if page_index >= len(doc.pages):
                return []
            page = doc.pages[page_index]
            tables = page.find_tables() or []
    except Exception as exc:
        logger.warning("pdfplumber table detection failed page %s: %s", page_index, exc)
        return []

    for table_index, table in enumerate(tables):
        cells: list[TableCell] = []
        for row_idx, row in enumerate(table.rows):
            for col_idx, raw_cell in enumerate(row.cells):
                bbox = _cell_from_pdfplumber(raw_cell)
                if not bbox:
                    continue
                cells.append(TableCell(bbox=bbox, row=row_idx, col=col_idx))
        if len(cells) < _MIN_TABLE_CELLS:
            continue
        tb = table.bbox
        regions.append(
            TableRegion(
                id=f"tbl-{page_index}-{table_index}",
                bbox=[float(tb[0]), float(tb[1]), float(tb[2]), float(tb[3])],
                cells=cells,
            )
        )
    return regions


def _detect_tables_drawings(page: fitz.Page, page_index: int) -> list[TableRegion]:
    """Fallback grid from vector rules when pdfplumber finds nothing."""
    h_ys: list[float] = []
    h_xranges: list[tuple[float, float]] = []
    v_xs: list[float] = []
    v_yranges: list[tuple[float, float]] = []

    try:
        drawings = page.get_drawings()
    except Exception:
        return []

    for drawing in drawings:
        rect = fitz.Rect(drawing.get("rect") or (0, 0, 0, 0))
        if rect.is_empty:
            continue
        if rect.height <= 2.5 and rect.width >= 12:
            h_ys.append((rect.y0 + rect.y1) / 2)
            h_xranges.append((rect.x0, rect.x1))
        elif rect.width <= 2.5 and rect.height >= 12:
            v_xs.append((rect.x0 + rect.x1) / 2)
            v_yranges.append((rect.y0, rect.y1))

    y_lines = _cluster_positions(h_ys)
    x_lines = _cluster_positions(v_xs)
    if len(y_lines) < 2 or len(x_lines) < 2:
        return []

    x0, x1 = min(x_lines), max(x_lines)
    y0, y1 = min(y_lines), max(y_lines)
    if h_xranges:
        x0 = min(min(r[0] for r in h_xranges), x0)
        x1 = max(max(r[1] for r in h_xranges), x1)
    if v_yranges:
        y0 = min(min(r[0] for r in v_yranges), y0)
        y1 = max(max(r[1] for r in v_yranges), y1)

    cells: list[TableCell] = []
    for row_idx in range(len(y_lines) - 1):
        for col_idx in range(len(x_lines) - 1):
            cy0, cy1 = y_lines[row_idx], y_lines[row_idx + 1]
            cx0, cx1 = x_lines[col_idx], x_lines[col_idx + 1]
            if cy1 - cy0 < 4 or cx1 - cx0 < 8:
                continue
            cells.append(
                TableCell(
                    bbox=[cx0, cy0, cx1, cy1],
                    row=row_idx,
                    col=col_idx,
                )
            )

    if len(cells) < _MIN_TABLE_CELLS:
        return []

    return [
        TableRegion(
            id=f"tbl-{page_index}-draw-0",
            bbox=[x0, y0, x1, y1],
            cells=cells,
        )
    ]


def detect_table_regions(
    pdf_path: Path | str,
    page_index: int,
    page: fitz.Page,
) -> list[TableRegion]:
    path = Path(pdf_path)
    regions = _detect_tables_pdfplumber(path, page_index)
    if not regions:
        regions = _detect_tables_drawings(page, page_index)
    return regions


def _point_in_bbox(px: float, py: float, bbox: list[float], margin: float = _CELL_MARGIN) -> bool:
    if len(bbox) < 4:
        return False
    return (
        bbox[0] - margin <= px <= bbox[2] + margin
        and bbox[1] - margin <= py <= bbox[3] + margin
    )


def _words_in_cell(words: list[tuple], cell_bbox: list[float]) -> list[tuple]:
    hits: list[tuple] = []
    for word in words:
        if len(word) < 5:
            continue
        cx = (word[0] + word[2]) / 2
        cy = (word[1] + word[3]) / 2
        if _point_in_bbox(cx, cy, cell_bbox):
            hits.append(word)
    return hits


def _order_words(words: list[tuple], direction: str) -> list[tuple]:
    if direction == "rtl":
        return sorted(words, key=lambda w: (round(w[1], 1), -(w[0] + w[2]) / 2))
    return sorted(words, key=lambda w: (round(w[1], 1), (w[0] + w[2]) / 2))


def _text_direction(text: str) -> str:
    if not text:
        return "ltr"
    hebrew = sum(1 for c in text if "\u0590" <= c <= "\u05FF")
    if hebrew >= max(1, len(text) * 0.25):
        return "rtl"
    return "ltr"


def _span_alignment(cell_bbox: list[float], text: str) -> str:
    if _text_direction(text) == "rtl":
        return "right"
    return "left"


def _blocks_in_cell(blocks: list[dict[str, Any]], cell_bbox: list[float]) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    for block in blocks:
        if block.get("type") != "text":
            continue
        bb = block.get("bbox") or []
        if len(bb) < 4:
            continue
        cx = (bb[0] + bb[2]) / 2
        cy = (bb[1] + bb[3]) / 2
        if _point_in_bbox(cx, cy, cell_bbox):
            hits.append(block)
    return hits


def _pick_font_meta(blocks: list[dict[str, Any]], words: list[tuple]) -> dict[str, Any]:
    if blocks:
        best = max(
            blocks,
            key=lambda b: (b.get("fontSize") or 0)
            * max(1.0, (b["bbox"][2] - b["bbox"][0]) if len(b.get("bbox", [])) >= 4 else 1),
        )
        return {
            "fontSize": best.get("fontSize", 12),
            "fontFamily": best.get("fontFamily", "Helvetica"),
            "pdfFont": best.get("pdfFont", best.get("fontFamily", "Helvetica")),
            "source": best.get("source", "native"),
        }
    if words:
        y0 = min(w[1] for w in words)
        y1 = max(w[3] for w in words)
        return {
            "fontSize": round(max(y1 - y0, 8) * 0.85, 1),
            "fontFamily": "Helvetica",
            "pdfFont": "Helvetica",
            "source": "native",
        }
    return {
        "fontSize": 12,
        "fontFamily": "Helvetica",
        "pdfFont": "Helvetica",
        "source": "native",
    }


def _text_ink_bbox(words: list[tuple], fallback: list[float]) -> list[float]:
    if not words:
        return list(fallback)
    pad_x, pad_y = 1.0, 0.4
    return [
        min(w[0] for w in words) - pad_x,
        min(w[1] for w in words) - pad_y,
        max(w[2] for w in words) + pad_x,
        max(w[3] for w in words) + pad_y,
    ]


def _text_origin(ink_bbox: list[float], direction: str) -> list[float]:
    x0, y0, x1, y1 = ink_bbox
    if direction == "rtl":
        return [x1 - 1.0, y1 - 0.5]
    return [x0 + 1.0, y1 - 0.5]


def _build_cell_block(
    page_index: int,
    table: TableRegion,
    cell: TableCell,
    words: list[tuple],
    source_blocks: list[dict[str, Any]],
) -> dict[str, Any] | None:
    ordered = _order_words(words, "ltr")
    parts = [(w[4] or "").strip() for w in ordered if (w[4] or "").strip()]
    content = " ".join(parts).strip()

    if not content and source_blocks:
        ordered_blocks = sorted(
            source_blocks,
            key=lambda b: (round(b["bbox"][1], 1), b["bbox"][0]),
        )
        content = " ".join((b.get("content") or "").strip() for b in ordered_blocks).strip()

    if not content:
        return None

    direction = _text_direction(content)
    ordered = _order_words(words, direction) if words else []
    if ordered:
        parts = [(w[4] or "").strip() for w in ordered if (w[4] or "").strip()]
        content = " ".join(parts).strip()

    meta = _pick_font_meta(source_blocks, words)
    cell_bbox = list(cell.bbox)
    ink_bbox = _text_ink_bbox(words, cell_bbox)

    return {
        "id": f"cell-{page_index}-{uuid.uuid4().hex[:8]}",
        "type": "text",
        "layer": "text",
        "bbox": cell_bbox,
        "cellBbox": cell_bbox,
        "textInkBbox": ink_bbox,
        "originalTextInkBbox": list(ink_bbox),
        "content": content,
        "fontSize": meta["fontSize"],
        "fontFamily": meta["fontFamily"],
        "pdfFont": meta["pdfFont"],
        "textOrigin": _text_origin(ink_bbox, direction),
        "align": _span_alignment(cell_bbox, content),
        "direction": direction,
        "source": meta["source"],
        "tableGroupId": table.id,
        "tableRow": cell.row,
        "tableCol": cell.col,
        "glyphRects": None,
    }


def _block_claimed_by_cell(block: dict[str, Any], regions: list[TableRegion]) -> bool:
    bb = block.get("bbox") or []
    if len(bb) < 4:
        return False
    cx = (bb[0] + bb[2]) / 2
    cy = (bb[1] + bb[3]) / 2
    for table in regions:
        for cell in table.cells:
            if _point_in_bbox(cx, cy, cell.bbox):
                return True
    return False


def merge_blocks_into_table_cells(
    page: fitz.Page,
    page_index: int,
    blocks: list[dict[str, Any]],
    pdf_path: Path | str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Replace per-word/per-span blocks inside detected tables with one block per cell."""
    regions = detect_table_regions(pdf_path, page_index, page)
    if not regions:
        return blocks, {"tablesDetected": 0, "cellsGrouped": 0}

    try:
        words = page.get_text("words")
    except Exception:
        words = []

    text_blocks = [b for b in blocks if b.get("type") == "text"]
    other_blocks = [b for b in blocks if b.get("type") != "text"]

    cell_blocks: list[dict[str, Any]] = []
    cells_grouped = 0

    for table in regions:
        for cell in table.cells:
            cell_words = _words_in_cell(words, cell.bbox)
            source_blocks = _blocks_in_cell(text_blocks, cell.bbox)
            item = _build_cell_block(page_index, table, cell, cell_words, source_blocks)
            if item:
                cell_blocks.append(item)
                cells_grouped += 1

    kept_text = [b for b in text_blocks if not _block_claimed_by_cell(b, regions)]
    out = kept_text + cell_blocks + other_blocks

    stats = {
        "tablesDetected": len(regions),
        "cellsGrouped": cells_grouped,
        "tableIds": [t.id for t in regions],
    }
    return out, stats
