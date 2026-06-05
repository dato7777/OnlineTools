"use client";

import type { PageModel, PageBlock } from "@/lib/api";
import { EditorCanvasInner } from "./EditorCanvasInner";

export function EditorCanvas(props: {
  page: PageModel;
  maskBlocks: PageBlock[];
  pdfCanvas?: HTMLCanvasElement | null;
  fileId: string;
  renderScale: number;
  maskText?: boolean;
  editLayer?: "text" | "background";
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  onBlockChange: (blockId: string, patch: Partial<PageBlock>) => void;
}) {
  return <EditorCanvasInner {...props} />;
}
