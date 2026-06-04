"""Optional PaddleOCR integration — install paddleocr separately to enable."""

from __future__ import annotations

from typing import Any


def paddle_available() -> bool:
    try:
        import paddleocr  # noqa: F401

        return True
    except ImportError:
        return False


def ocr_page_image(image_bytes: bytes) -> list[dict[str, Any]]:
    """Return text blocks from PaddleOCR when installed."""
    if not paddle_available():
        return []
    from paddleocr import PaddleOCR

    ocr = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
    import tempfile
    from pathlib import Path

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp.write(image_bytes)
        path = tmp.name
    result = ocr.ocr(path, cls=True)
    Path(path).unlink(missing_ok=True)
    blocks: list[dict[str, Any]] = []
    if not result or not result[0]:
        return blocks
    for i, line in enumerate(result[0]):
        box, (text, conf) = line
        if conf < 0.5 or not text.strip():
            continue
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        blocks.append(
            {
                "id": f"paddle-{i}",
                "type": "text",
                "bbox": [min(xs), min(ys), max(xs), max(ys)],
                "content": text.strip(),
                "fontSize": max(8, (max(ys) - min(ys)) * 0.75),
                "fontFamily": "Helvetica",
                "source": "paddleocr",
            }
        )
    return blocks
