import type { PageBlock } from "@/lib/api";

const HEBREW_RE = /[\u0590-\u05FF]/;

function isHebrewText(text: string): boolean {
  if (!text) return false;
  let n = 0;
  for (const ch of text) {
    if (HEBREW_RE.test(ch)) n += 1;
  }
  return n >= Math.max(1, Math.ceil(text.length * 0.25));
}

function konvaAlign(block: PageBlock): "left" | "center" | "right" {
  if (block.align === "center" || block.align === "right" || block.align === "left") {
    return block.align;
  }
  const dir =
    block.direction === "rtl" || block.direction === "ltr"
      ? block.direction
      : isHebrewText(block.content ?? "")
        ? "rtl"
        : "ltr";
  return dir === "rtl" ? "right" : "left";
}

function blockBboxMoved(block: PageBlock): boolean {
  const orig = block.originalBbox;
  const cur = block.bbox;
  if (!orig || orig.length < 4 || cur.length < 4) return false;
  return orig.some((v, i) => Math.abs(v - cur[i]) > 0.5);
}

export const TABLE_INSET_X = 2.2;
export const TABLE_INSET_Y = 1.0;

export type PlacementMetrics = {
  insertRect: number[];
  exportFontSize: number;
  align: "left" | "center" | "right";
  useTextOrigin: boolean;
  textOrigin: [number, number] | null;
  isTableCell: boolean;
};

export function localTableInsertRect(bbox: number[]): number[] {
  if (bbox.length < 4) return bbox;
  return [
    bbox[0] + TABLE_INSET_X,
    bbox[1] + TABLE_INSET_Y,
    bbox[2] - TABLE_INSET_X,
    bbox[3] - TABLE_INSET_Y,
  ];
}

/** Fallback when the placement-metrics API is unavailable. */
export function localPlacementMetrics(block: PageBlock): PlacementMetrics {
  const align = konvaAlign(block);
  const isTableCell = Boolean(block.tableGroupId);
  return {
    insertRect: isTableCell ? localTableInsertRect(block.bbox) : block.bbox,
    exportFontSize: block.fontSize ?? 12,
    align,
    useTextOrigin: blockBboxMoved(block),
    textOrigin: block.textOrigin ?? null,
    isTableCell,
  };
}
