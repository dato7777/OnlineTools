import type { CSSProperties } from "react";
import type { PageBlock } from "@/lib/api";
import {
  localPlacementMetrics,
  type PlacementMetrics,
} from "@/lib/exportPlacement";

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
    if (pdf.includes("arial") || pdf.includes("david") || pdf.includes("narkis")) {
      return 'Arial, "Arial Hebrew", "Noto Sans Hebrew", sans-serif';
    }
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
  if (block.deleted) return block.type === "text";
  if (block.type === "image") {
    return block.dirty === true || block.id === selectedId || blockBboxMoved(block);
  }
  if (block.type !== "text") return false;
  if (!hasGlyphMask(block)) return false;
  // Mask glyph ink when editing or after edit — destination-out on glyphs only, not grid lines.
  if (block.tableGroupId) return block.dirty === true || block.id === selectedId;
  return block.dirty === true || block.id === selectedId;
}

export function blockShowsEditedOverlay(
  block: PageBlock,
  selectedId: string | null
): boolean {
  if (block.type !== "text" || block.deleted) return false;
  // Selected block renders in the editor wrapper — skip duplicate overlay.
  if (block.id === selectedId) return false;
  return block.dirty === true;
}

export function editorFontSizePx(block: PageBlock, renderScale: number): number {
  return Math.max(8, (block.fontSize ?? 12) * renderScale);
}

export type ExportPreviewLayout = {
  container: CSSProperties;
  inner: CSSProperties;
  text: CSSProperties;
};

export function exportPreviewLayout(
  block: PageBlock,
  renderScale: number,
  metrics?: PlacementMetrics | null
): ExportPreviewLayout {
  const m = metrics ?? localPlacementMetrics(block);
  const [x0, y0, x1, y1] = block.bbox;
  const [ix0, iy0, ix1, iy1] = m.insertRect;
  const fontPx = Math.max(6, m.exportFontSize * renderScale);

  const container: CSSProperties = {
    position: "absolute",
    left: x0 * renderScale,
    top: y0 * renderScale,
    width: Math.max(8, (x1 - x0) * renderScale),
    height: Math.max(8, (y1 - y0) * renderScale),
    pointerEvents: "none",
    zIndex: 10,
  };

  const flexAlign =
    m.align === "center" ? "center" : m.align === "right" ? "flex-end" : "flex-start";

  const inner: CSSProperties = {
    position: "absolute",
    left: (ix0 - x0) * renderScale,
    top: (iy0 - y0) * renderScale,
    width: Math.max(4, (ix1 - ix0) * renderScale),
    height: Math.max(4, (iy1 - iy0) * renderScale),
    display: "flex",
    alignItems: "center",
    justifyContent: flexAlign,
    overflow: "hidden",
    boxSizing: "border-box",
  };

  const text: CSSProperties = {
    fontSize: fontPx,
    fontFamily: editorFontFamily(block),
    textAlign: m.align,
    direction: textDirection(block),
    lineHeight: 1,
    padding: 0,
    margin: 0,
    whiteSpace: "nowrap",
    color: "#18181b",
    background: "transparent",
  };

  return { container, inner, text };
}

export function blockOverlayStyle(
  block: PageBlock,
  renderScale: number,
  opts?: { border?: boolean; zIndex?: number; fillParent?: boolean }
): CSSProperties {
  const width = Math.max(8, (block.bbox[2] - block.bbox[0]) * renderScale);
  const height = Math.max(8, (block.bbox[3] - block.bbox[1]) * renderScale);
  return {
    position: "absolute",
    ...(opts?.fillParent
      ? { inset: 0, width: "100%", height: "100%" }
      : {
          left: block.bbox[0] * renderScale,
          top: block.bbox[1] * renderScale,
          width,
          height,
        }),
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
    overflow: "visible",
    whiteSpace: "pre-wrap",
    wordBreak: "break-word",
    pointerEvents: "none",
    zIndex: opts?.zIndex ?? 10,
  };
}
