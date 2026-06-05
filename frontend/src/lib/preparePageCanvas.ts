import type { PageBlock } from "@/lib/api";
import { blockBboxMoved, blockMaskBbox, hasGlyphMask } from "@/lib/textLayout";

function clipGlyphToBlock(
  x0: number,
  y0: number,
  x1: number,
  y1: number,
  block: PageBlock
): [number, number, number, number] | null {
  const ref = blockMaskBbox(block);
  if (ref.length < 4) return [x0, y0, x1, y1];
  const cx = (x0 + x1) / 2;
  const cy = (y0 + y1) / 2;
  if (cx < ref[0] || cx > ref[2] || cy < ref[1] || cy > ref[3]) return null;
  return [
    Math.max(x0, ref[0]),
    Math.max(y0, ref[1]),
    Math.min(x1, ref[2]),
    Math.min(y1, ref[3]),
  ];
}

export type MaskedPage = {
  canvas: HTMLCanvasElement;
  textFills: Record<string, string>;
};

/**
 * Hide PDF text under edited glyphs by punching holes in the raster preview.
 * Does not paint white — table lines and borders stay visible.
 */
export function maskTextRegions(
  source: HTMLCanvasElement,
  blocks: PageBlock[],
  renderScale: number,
  maskBlockIds: Set<string>
): MaskedPage {
  const out = document.createElement("canvas");
  out.width = source.width;
  out.height = source.height;
  const ctx = out.getContext("2d");
  if (!ctx) return { canvas: source, textFills: {} };

  ctx.drawImage(source, 0, 0);

  ctx.save();
  ctx.globalCompositeOperation = "destination-out";
  for (const block of blocks) {
    if (!maskBlockIds.has(block.id)) continue;

    if (block.type === "image") {
      const ref = block.originalBbox ?? block.bbox;
      if (ref.length >= 4) {
        const pad = 0.08 * renderScale;
        const x = ref[0] * renderScale - pad;
        const y = ref[1] * renderScale - pad;
        const w = (ref[2] - ref[0]) * renderScale + pad * 2;
        const h = (ref[3] - ref[1]) * renderScale + pad * 2;
        if (w > 0 && h > 0) ctx.fillRect(x, y, w, h);
      }
      continue;
    }

    if (block.type !== "text" || !hasGlyphMask(block)) continue;

    for (const [gx0, gy0, gx1, gy1] of block.glyphRects!) {
      const clipped = clipGlyphToBlock(gx0, gy0, gx1, gy1, block);
      if (!clipped) continue;
      const [x0, y0, x1, y1] = clipped;
      const pad = 0.06 * renderScale;
      const x = x0 * renderScale - pad;
      const y = y0 * renderScale - pad;
      const w = (x1 - x0) * renderScale + pad * 2;
      const h = (y1 - y0) * renderScale + pad * 2;
      if (w > 0 && h > 0) ctx.fillRect(x, y, w, h);
    }

    if (blockBboxMoved(block)) {
      const ref = block.originalBbox ?? block.bbox;
      if (ref.length >= 4) {
        const pad = 0.08 * renderScale;
        const x = ref[0] * renderScale - pad;
        const y = ref[1] * renderScale - pad;
        const w = (ref[2] - ref[0]) * renderScale + pad * 2;
        const h = (ref[3] - ref[1]) * renderScale + pad * 2;
        if (w > 0 && h > 0) ctx.fillRect(x, y, w, h);
      }
    }
  }
  ctx.restore();

  return { canvas: out, textFills: {} };
}
