import type { PageBlock } from "@/lib/api";

export function nextStackOrder(blocks: PageBlock[]): number {
  return blocks.reduce((max, b) => Math.max(max, b.stackOrder ?? 0), 0) + 1;
}

export function ensureBlockStackOrders(blocks: PageBlock[]): PageBlock[] {
  return blocks.map((b, i) => ({
    ...b,
    stackOrder: b.stackOrder ?? i,
  }));
}

export function blockStackZIndex(
  block: PageBlock,
  selectedId: string | null,
  base = 10
): number {
  if (block.id === selectedId) return 1000;
  return base + (block.stackOrder ?? 0);
}

export function sortBlocksByStack(blocks: PageBlock[]): PageBlock[] {
  return [...blocks].sort(
    (a, b) => (a.stackOrder ?? 0) - (b.stackOrder ?? 0)
  );
}
