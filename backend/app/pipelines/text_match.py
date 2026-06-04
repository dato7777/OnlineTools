"""Pick the correct OCR/PDF text match when the same string appears multiple times (e.g. tables)."""

from __future__ import annotations

from typing import Any


def bbox_iou(a: list[float], b: tuple[float, float, float, float] | list[float]) -> float:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    inter = (ix1 - ix0) * (iy1 - iy0)
    union = (ax1 - ax0) * (ay1 - ay0) + (bx1 - bx0) * (by1 - by0) - inter
    return inter / union if union > 0 else 0.0


def pick_best_text_match(matches: list[Any], block_bbox: list[float]) -> Any | None:
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0]
    best = None
    best_score = -1.0
    for m in matches:
        box = getattr(m, "bounding_box", None)
        if not box:
            continue
        score = bbox_iou(block_bbox, box)
        if score > best_score:
            best_score = score
            best = m
    return best if best_score > 0.05 else matches[0]
