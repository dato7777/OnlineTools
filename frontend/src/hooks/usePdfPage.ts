"use client";

import { useEffect, useState } from "react";

/** PDF points → canvas pixels at this scale (use same value for block positioning). */
export const PDF_RENDER_SCALE = 2;

export function usePdfPage(url: string, pageIndex: number, scale = PDF_RENDER_SCALE) {
  const [canvas, setCanvas] = useState<HTMLCanvasElement | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    (async () => {
      try {
        const pdfjs = await import("pdfjs-dist");
        pdfjs.GlobalWorkerOptions.workerSrc = `//cdnjs.cloudflare.com/ajax/libs/pdf.js/${pdfjs.version}/pdf.worker.min.mjs`;

        const doc = await pdfjs.getDocument(url).promise;
        const page = await doc.getPage(pageIndex + 1);
        const viewport = page.getViewport({ scale });
        const c = document.createElement("canvas");
        c.width = viewport.width;
        c.height = viewport.height;
        const ctx = c.getContext("2d", { alpha: false });
        if (!ctx) throw new Error("Canvas unsupported");
        ctx.fillStyle = "#ffffff";
        ctx.fillRect(0, 0, c.width, c.height);
        await page.render({ canvasContext: ctx, viewport }).promise;
        if (!cancelled) setCanvas(c);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "PDF render failed");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [url, pageIndex, scale]);

  return { canvas, loading, error, renderScale: scale };
}
