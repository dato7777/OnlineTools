"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { Download, ChevronLeft, ChevronRight } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { EditorCanvas } from "@/components/editor/EditorCanvas";
import { FloatingToolbar } from "@/components/editor/FloatingToolbar";
import { MobileBlockSheet } from "@/components/editor/MobileBlockSheet";
import {
  api,
  pollJob,
  type BlockDocument,
  type PageBlock,
  type PageModel,
} from "@/lib/api";
import { usePagePreview } from "@/hooks/usePagePreview";
import { PDF_RENDER_SCALE, usePdfPage } from "@/hooks/usePdfPage";
import { ensureBlockStackOrders, nextStackOrder } from "@/lib/blockStack";
import { cn } from "@/lib/utils";

export default function PdfEditorPage() {
  const { fileId } = useParams<{ fileId: string }>();
  const [model, setModel] = useState<BlockDocument | null>(null);
  const [pageIndex, setPageIndex] = useState(0);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [saved, setSaved] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [editLayer, setEditLayer] = useState<"text" | "background">("text");
  const [previewRevision, setPreviewRevision] = useState(0);

  const page = model?.pages[pageIndex];
  const hasDeletedFills =
    page?.blocks.some((b) => b.type === "background" && b.deleted) ?? false;

  const pdfUrl = api.fileDownloadUrl(fileId);
  const { canvas: pdfCanvas, loading: pdfJsLoading } = usePdfPage(pdfUrl, pageIndex);
  const { canvas: previewCanvas, loading: previewLoading } = usePagePreview(
    fileId,
    pageIndex,
    previewRevision,
    hasDeletedFills
  );

  const canvas = hasDeletedFills ? previewCanvas : pdfCanvas;
  const pdfLoading = hasDeletedFills ? previewLoading : pdfJsLoading;

  useEffect(() => {
    api
      .getModel(fileId)
      .then((doc) =>
        setModel({
          ...doc,
          pages: doc.pages.map((p) => ({
            ...p,
            blocks: ensureBlockStackOrders(p.blocks),
          })),
        })
      )
      .catch((e) => setLoadError(e instanceof Error ? e.message : "Failed to load model"));
  }, [fileId]);

  const activeBlocks = page?.blocks.filter((b) => !b.deleted) ?? [];
  const maskBlocks =
    page?.blocks.filter((b) => b.type === "text" || b.type === "image") ?? [];
  const pageForEditor = page ? { ...page, blocks: activeBlocks } : undefined;
  const selectedBlock = activeBlocks.find((b) => b.id === selectedId) ?? null;

  const bumpPreview = useCallback(() => {
    setPreviewRevision((r) => r + 1);
  }, []);

  const handleSelect = useCallback(
    (id: string | null) => {
      if (id && model) {
        const pages = model.pages.map((p) => {
          if (p.pageIndex !== pageIndex) return p;
          const stackOrder = nextStackOrder(p.blocks);
          return {
            ...p,
            blocks: p.blocks.map((b) =>
              b.id === id ? { ...b, stackOrder } : b
            ),
          };
        });
        setModel({ ...model, pages });
      }
      setSelectedId(id);
    },
    [model, pageIndex]
  );

  const updateBlock = useCallback(
    (blockId: string, patch: Partial<PageBlock>, userEdit = true) => {
      if (!model) return;
      const prev = model.pages[pageIndex]?.blocks.find((b) => b.id === blockId);
      let merged = patch;
      if (patch.bbox && prev?.textOrigin && prev.originalBbox?.length === 4) {
        const [x0, y0, , y1] = patch.bbox;
        const [ox0, , , oy1] = prev.originalBbox;
        merged = {
          ...patch,
          textOrigin: [
            prev.textOrigin[0] + (x0 - ox0),
            prev.textOrigin[1] + (y1 - oy1),
          ],
        };
      }
      const pages = model.pages.map((p) => {
        if (p.pageIndex !== pageIndex) return p;
        const stackOrder = userEdit ? nextStackOrder(p.blocks) : undefined;
        return {
          ...p,
          blocks: p.blocks.map((b) =>
            b.id === blockId
              ? {
                  ...b,
                  ...merged,
                  ...(userEdit ? { dirty: true, stackOrder } : {}),
                }
              : b
          ),
        };
      });
      setModel({ ...model, pages });
      setSaved(false);
      if (
        patch.deleted !== undefined ||
        prev?.type === "background" ||
        patch.content === ""
      ) {
        bumpPreview();
      }
    },
    [model, pageIndex, bumpPreview]
  );

  const save = useCallback(async () => {
    if (!model) return;
    await api.saveModel(fileId, model.pages);
    setSaved(true);
  }, [model, fileId]);

  useEffect(() => {
    if (!model || saved) return;
    const t = setTimeout(() => {
      save().catch(() => {});
    }, 2000);
    return () => clearTimeout(t);
  }, [model, saved, save]);

  async function handleExport() {
    if (!model) return;
    setExporting(true);
    try {
      await save();
      const res = await api.exportPdf(fileId, model);
      if (res.outputFileId) {
        window.open(api.fileDownloadUrl(res.outputFileId), "_blank");
        setExporting(false);
        return;
      }
      pollJob(res.jobId, (job) => {
        if (job.status === "completed" && job.output_file_id) {
          window.open(api.fileDownloadUrl(job.output_file_id), "_blank");
          setExporting(false);
        }
        if (job.status === "failed") setExporting(false);
      });
    } catch {
      setExporting(false);
    }
  }

  function deleteSelected() {
    if (!selectedId || !model) return;
    const target = model.pages[pageIndex]?.blocks.find((b) => b.id === selectedId);
    const pages = model.pages.map((p) => {
      if (p.pageIndex !== pageIndex) return p;
      return {
        ...p,
        blocks: p.blocks.map((b) => {
          if (b.id === selectedId) {
            return { ...b, deleted: true, dirty: true };
          }
          if (
            target?.type === "background" &&
            b.type === "text" &&
            b.backgroundBlockId === selectedId
          ) {
            const next = { ...b };
            delete next.backgroundBlockId;
            next.backgroundRgb = [255, 255, 255];
            return next;
          }
          return b;
        }),
      };
    });
    setModel({ ...model, pages });
    setSelectedId(null);
    setSaved(false);
    bumpPreview();
  }

  if (loadError) {
    return (
      <AppShell>
        <p className="p-8 text-center text-red-600">{loadError}</p>
      </AppShell>
    );
  }

  if (!model || !pageForEditor) {
    return (
      <AppShell>
        <p className="p-8 text-center text-[var(--text-muted)]">Loading editor…</p>
      </AppShell>
    );
  }

  return (
    <AppShell hideNav>
      <div className="flex min-h-dvh flex-col bg-zinc-950">
        <header className="glass flex items-center justify-between px-4 py-3 md:px-6">
          <div className="flex items-center gap-3">
            <span className="text-sm font-medium text-zinc-100">PDF Editor</span>
            {model.nativePageRatio !== undefined && model.nativePageRatio < 0.5 && (
              <span className="rounded-full bg-amber-500/20 px-2 py-0.5 text-xs text-amber-200">
                Scan detected
              </span>
            )}
            <span className="hidden text-xs text-zinc-500 md:inline">
              Download without edits keeps your original PDF
            </span>
            {saved && (
              <span className="text-xs text-zinc-400">Saved</span>
            )}
          </div>
          <button
            type="button"
            onClick={handleExport}
            disabled={exporting}
            className="flex items-center gap-2 rounded-full bg-accent px-4 py-2 text-sm font-medium text-white dark:text-zinc-900 disabled:opacity-50"
          >
            <Download className="h-4 w-4" />
            {exporting ? "Exporting…" : "Download"}
          </button>
        </header>

        <div className="flex flex-1 flex-col items-center justify-center overflow-auto p-4 md:p-8">
          {pdfLoading && (
            <div className="h-[400px] w-[300px] animate-pulse rounded-lg bg-zinc-800" />
          )}
          {!pdfLoading && (
            <EditorCanvas
              page={pageForEditor}
              maskBlocks={maskBlocks}
              pdfCanvas={canvas}
              fileId={fileId}
              maskText
              editLayer={editLayer}
              renderScale={PDF_RENDER_SCALE}
              selectedId={selectedId}
              onSelect={handleSelect}
              onBlockChange={updateBlock}
            />
          )}
        </div>

        <footer className="glass flex flex-col items-center gap-3 px-4 py-3 md:flex-row md:justify-center">
          <div className="flex rounded-full bg-zinc-800/80 p-1 text-xs">
            <button
              type="button"
              onClick={() => {
                setEditLayer("text");
                setSelectedId(null);
              }}
              className={cn(
                "rounded-full px-4 py-1.5 font-medium transition-colors",
                editLayer === "text"
                  ? "bg-accent text-white dark:text-zinc-900"
                  : "text-zinc-400 hover:text-zinc-200"
              )}
            >
              Text
            </button>
            <button
              type="button"
              onClick={() => {
                setEditLayer("background");
                setSelectedId(null);
              }}
              className={cn(
                "rounded-full px-4 py-1.5 font-medium transition-colors",
                editLayer === "background"
                  ? "bg-amber-500 text-zinc-900"
                  : "text-zinc-400 hover:text-zinc-200"
              )}
            >
              Color fills
            </button>
          </div>
          <div className="flex items-center gap-4">
          <button
            type="button"
            disabled={pageIndex <= 0}
            onClick={() => {
              setPageIndex((i) => i - 1);
              setSelectedId(null);
              bumpPreview();
            }}
            className="rounded-full p-2 hover:bg-zinc-800 disabled:opacity-30"
          >
            <ChevronLeft className="h-5 w-5 text-zinc-200" />
          </button>
          <span className="text-sm text-zinc-300">
            Page {pageIndex + 1} of {model.pages.length}
          </span>
          <button
            type="button"
            disabled={pageIndex >= model.pages.length - 1}
            onClick={() => {
              setPageIndex((i) => i + 1);
              setSelectedId(null);
              bumpPreview();
            }}
            className="rounded-full p-2 hover:bg-zinc-800 disabled:opacity-30"
          >
            <ChevronRight className="h-5 w-5 text-zinc-200" />
          </button>
          </div>
        </footer>

        <FloatingToolbar
          visible={!!selectedBlock}
          deleteLabel={
            selectedBlock?.type === "background" ? "Remove fill" : "Delete text"
          }
          onEdit={() => setSheetOpen(true)}
          onDelete={deleteSelected}
          showEdit={selectedBlock?.type === "text" || selectedBlock?.type === "image"}
        />

        <MobileBlockSheet
          block={selectedBlock}
          open={sheetOpen}
          onClose={() => setSheetOpen(false)}
          onChange={(content) => {
            if (selectedId) updateBlock(selectedId, { content });
          }}
        />


        {selectedBlock?.type === "background" && (
          <div className="hidden md:block fixed right-4 top-20 w-72 glass rounded-2xl p-4">
            <p className="text-xs font-medium text-zinc-400 mb-2">Color fill</p>
            <p className="text-sm text-zinc-300 mb-3">
              Removes this colored panel from the page and restores the document background
              underneath.
            </p>
            <button
              type="button"
              onClick={deleteSelected}
              className="w-full rounded-lg bg-red-600/90 px-3 py-2 text-sm font-medium text-white hover:bg-red-600"
            >
              Remove fill
            </button>
          </div>
        )}
      </div>
    </AppShell>
  );
}
