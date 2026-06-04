"""Adobe-style export: content-stream edits via pdf-edit-engine (no redact fill)."""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any

from pdf_edit_engine import find, replace
from pdf_edit_engine.models import Edit, EditResult
from pdf_edit_engine.structural import delete_block
from pdf_edit_engine.surgeon import batch_replace

from app.pipelines.accuracy import block_is_modified

logger = logging.getLogger(__name__)


def _bbox_iou(a: tuple[float, ...], b: list[float]) -> float:
    if len(a) < 4 or len(b) < 4:
        return 0.0
    ix0, iy0 = max(a[0], b[0]), max(a[1], b[1])
    ix1, iy1 = min(a[2], b[2]), min(a[3], b[3])
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    inter = (ix1 - ix0) * (iy1 - iy0)
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def surgeon_can_edit_pdf(pdf_path: str, page_index: int = 0) -> bool:
    """True when pdf-edit-engine can see text operators (Adobe-like path available)."""
    try:
        from pdf_edit_engine._pathutil import open_pdf
        from pdf_edit_engine.locator import _build_index
    except ImportError:
        return False

    try:
        with open_pdf(Path(pdf_path)) as pdf:
            if page_index >= len(pdf.pages):
                return False
            elements = _build_index(pdf.pages[page_index], page_index)
            return any(
                e.type == "text" and (e.text_content or "").strip() for e in elements
            )
    except Exception:
        return False


def _pick_match(
    matches: list[Any], block: dict[str, Any], page_index: int
) -> Any | None:
    ref = block.get("originalBbox") or block.get("bbox") or []
    if len(ref) < 4:
        return None
    best = None
    best_iou = 0.0
    for match in matches:
        if match.page_number != page_index:
            continue
        iou = _bbox_iou(match.bounding_box, ref)
        if iou > best_iou:
            best_iou = iou
            best = match
    return best if best_iou >= 0.15 else None


def _work_pdf_path() -> str:
    # Use project work dir (not /var tmp symlinks — pdf-edit-engine refuses those).
    root = Path(__file__).resolve().parents[2] / "storage" / "work" / "export"
    root.mkdir(parents=True, exist_ok=True)
    return str((root / f"surgeon_{uuid.uuid4().hex}.pdf").resolve())


def try_surgeon_block_edit(
    pdf_path: str,
    page_index: int,
    block: dict[str, Any],
    *,
    reflow: bool = False,
) -> tuple[str | None, EditResult | None]:
    """Apply one block edit on a copy of the PDF. Returns (output_path, result)."""
    original = (block.get("originalContent") or block.get("content") or "").strip()
    if not original:
        return None, None

    new_text = "" if block.get("deleted") else (block.get("content") or "").strip()
    matches = find(pdf_path, original, page=page_index)
    match = _pick_match(matches, block, page_index)

    out = _work_pdf_path()
    if match is not None:
        result = replace(pdf_path, match, new_text, out, reflow=reflow)
        if result.success:
            return out, result
        logger.info(
            "surgeon replace failed for block %s: %s",
            block.get("id"),
            (result.warnings or ["unknown"])[:2],
        )

    if block.get("deleted") or new_text != original:
        ref = block.get("originalBbox") or block.get("bbox")
        if ref and len(ref) >= 4:
            result = delete_block(
                pdf_path,
                page_index,
                tuple(ref[:4]),
                out,
                close_gap=False,
            )
            if result.success and "No content found" not in " ".join(result.warnings):
                return out, result
    return None, None


def apply_surgeon_export_pass(
    pdf_path: str,
    model: dict[str, Any],
) -> tuple[str, set[str]] | None:
    """Run batch content-stream edits when the PDF is indexer-compatible.

    Returns (output_path, block_ids handled) or None when PyMuPDF fallback is
    required (typical for CID/hex-string invoices like HashDoc).
    """
    if not surgeon_can_edit_pdf(pdf_path):
        logger.debug("surgeon path skipped — no indexed text in %s", pdf_path)
        return None

    edits: list[Edit] = []
    handled_ids: set[str] = set()

    for page_data in model.get("pages", []):
        for block in page_data.get("blocks", []):
            if block.get("type") != "text" or not block_is_modified(block):
                continue
            orig_bbox = block.get("originalBbox") or block.get("bbox") or []
            cur_bbox = block.get("bbox") or []
            if (
                not block.get("deleted")
                and len(orig_bbox) >= 4
                and len(cur_bbox) >= 4
                and any(abs(a - b) > 0.5 for a, b in zip(orig_bbox, cur_bbox))
            ):
                continue
            original = (block.get("originalContent") or block.get("content") or "").strip()
            if not original:
                continue
            new_text = "" if block.get("deleted") else (block.get("content") or "").strip()
            if new_text == original:
                continue
            edits.append(Edit(find=original, replace=new_text))
            if block.get("id"):
                handled_ids.add(block["id"])

    if not edits:
        return None

    out = _work_pdf_path()
    try:
        results = batch_replace(pdf_path, edits, out, reflow=False)
    except Exception as exc:
        logger.warning("batch_replace failed: %s", exc)
        return None

    if not results or not any(r.success for r in results):
        return None
    return out, handled_ids
