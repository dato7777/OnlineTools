import type { CSSProperties } from "react";
import type { PageBlock } from "@/lib/api";

const HEBREW_RE = /[\u0590-\u05FF]/;

export function isHebrewText(text: string): boolean {
  if (!text) return false;
  let n = 0;
  for (const ch of text) {
    if (HEBREW_RE.test(ch)) n += 1;
  }
  return n >= Math.max(1, Math.ceil(text.length * 0.25));
}

export function textDirection(block: PageBlock): "ltr" | "rtl" {
  if (block.direction === "rtl" || block.direction === "ltr") {
    return block.direction;
  }
  return isHebrewText(block.content ?? "") ? "rtl" : "ltr";
}

export function konvaAlign(block: PageBlock): "left" | "center" | "right" {
  if (block.align === "center" || block.align === "right" || block.align === "left") {
    return block.align;
  }
  return textDirection(block) === "rtl" ? "right" : "left";
}

export function editorFontFamily(block: PageBlock): string {
  const pdf = (block.pdfFont || block.fontFamily || "").toLowerCase();
  if (isHebrewText(block.content ?? "")) {
    return '"Noto Sans Hebrew", Arial, "Arial Hebrew", sans-serif';
  }
  if (pdf.includes("times")) return '"Times New Roman", Times, serif';
  if (pdf.includes("courier")) return '"Courier New", monospace';
  return "Helvetica, Arial, sans-serif";
}

export function hasGlyphMask(block: PageBlock): boolean {
  return (block.glyphRects?.length ?? 0) > 0;
}

export function blockBboxMoved(block: PageBlock): boolean {
  const orig = block.originalBbox;
  const cur = block.bbox;
  if (!orig || orig.length < 4 || cur.length < 4) return false;
  return orig.some((v, i) => Math.abs(v - cur[i]) > 0.5);
}

export function blockNeedsMask(block: PageBlock, selectedId: string | null): boolean {
  if (block.type !== "text") return false;
  if (!hasGlyphMask(block)) return false;
  if (block.deleted) return true;
  return block.dirty === true || block.id === selectedId;
}

export function blockShowsEditedOverlay(
  block: PageBlock,
  selectedId: string | null
): boolean {
  if (block.type !== "text" || block.deleted) return false;
  if (block.id === selectedId) return blockBboxMoved(block);
  return block.dirty === true;
}

export function editorFontSizePx(block: PageBlock, renderScale: number): number {
  return Math.max(8, (block.fontSize ?? 12) * renderScale);
}

export function blockOverlayStyle(
  block: PageBlock,
  renderScale: number,
  opts?: { border?: boolean }
): CSSProperties {
  return {
    position: "absolute",
    left: block.bbox[0] * renderScale,
    top: block.bbox[1] * renderScale,
    width: Math.max(8, (block.bbox[2] - block.bbox[0]) * renderScale),
    height: Math.max(8, (block.bbox[3] - block.bbox[1]) * renderScale),
    fontSize: editorFontSizePx(block, renderScale),
    fontFamily: editorFontFamily(block),
    textAlign: konvaAlign(block),
    direction: textDirection(block),
    lineHeight: 1.15,
    padding: "1px 2px",
    margin: 0,
    boxSizing: "border-box",
    background: "transparent",
    color: "#18181b",
    border: opts?.border ? "2px solid #0d9488" : "none",
    overflow: "hidden",
    whiteSpace: "nowrap",
    pointerEvents: "none",
    zIndex: 10,
  };
}
