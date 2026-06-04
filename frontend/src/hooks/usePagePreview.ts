"use client";

import { useEffect, useState } from "react";

import { PDF_RENDER_SCALE } from "@/hooks/usePdfPage";

/** Server PNG after colored fills are removed (optional). */
export function usePagePreview(
  fileId: string,
  pageIndex: number,
  revision = 0,
  enabled = true
) {
  const [canvas, setCanvas] = useState<HTMLCanvasElement | null>(null);
  const [loading, setLoading] = useState(enabled);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!enabled) {
      setCanvas(null);
      setLoading(false);
      setError(null);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);

    const url = `${
      process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"
    }/api/v1/tools/pdf-editor/documents/${fileId}/pages/${pageIndex}/preview.png?v=${revision}`;

    (async () => {
      try {
        const res = await fetch(url);
        if (!res.ok) throw new Error("Preview not ready");
        const blob = await res.blob();
        const img = await createImageBitmap(blob);
        const c = document.createElement("canvas");
        c.width = img.width;
        c.height = img.height;
        const ctx = c.getContext("2d");
        if (!ctx) throw new Error("Canvas unsupported");
        ctx.drawImage(img, 0, 0);
        if (!cancelled) setCanvas(c);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Preview failed");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [fileId, pageIndex, revision, enabled]);

  return { canvas, loading, error, renderScale: PDF_RENDER_SCALE };
}
