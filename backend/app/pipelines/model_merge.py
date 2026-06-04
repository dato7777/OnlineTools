"""Merge client-edited pages with immutable original* fields from the analyzed model."""

from __future__ import annotations

from typing import Any

from app.pipelines.glyph_quads import resolve_glyph_ownership


def merge_pages_with_originals(
    incoming_pages: list[dict[str, Any]],
    previous_pages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    prev_by_index = {p["pageIndex"]: p for p in previous_pages}
    merged_pages: list[dict[str, Any]] = []

    for page in incoming_pages:
        idx = page["pageIndex"]
        prev_page = prev_by_index.get(idx, {})
        prev_blocks = {b["id"]: b for b in prev_page.get("blocks", [])}
        new_blocks: list[dict[str, Any]] = []

        for block in page.get("blocks", []):
            prev = prev_blocks.get(block.get("id"), {})
            merged = {**block}
            if merged.get("type") == "text":
                merged.setdefault("originalContent", prev.get("originalContent", merged.get("content", "")))
                merged.setdefault("originalBbox", prev.get("originalBbox", merged.get("bbox", [])))
                merged.setdefault("backgroundRgb", prev.get("backgroundRgb"))
                merged.setdefault("backgroundBlockId", prev.get("backgroundBlockId"))
                merged.setdefault("direction", prev.get("direction"))
                merged.setdefault("align", prev.get("align"))
                merged.setdefault("pdfFont", prev.get("pdfFont"))
                merged.setdefault("glyphRects", prev.get("glyphRects"))
                merged.setdefault("textOrigin", prev.get("textOrigin"))
            elif merged.get("type") == "background":
                merged.setdefault("originalBbox", prev.get("originalBbox", merged.get("bbox", [])))
                merged.setdefault("backgroundRgb", prev.get("backgroundRgb"))
            elif merged.get("type") == "image":
                merged.setdefault("originalBbox", prev.get("originalBbox", merged.get("bbox", [])))
            if "dirty" not in merged and prev.get("dirty"):
                merged["dirty"] = prev["dirty"]
            if prev.get("deleted"):
                merged["deleted"] = prev["deleted"]
            new_blocks.append(merged)

        resolve_glyph_ownership(new_blocks)
        merged_pages.append({**page, "blocks": new_blocks})

    return merged_pages
