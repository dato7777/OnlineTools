"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Stage, Layer, Rect } from "react-konva";
import type { PageBlock, PageModel } from "@/lib/api";
import { api } from "@/lib/api";
import { maskTextRegions } from "@/lib/preparePageCanvas";
import { applyResize, resizeHandleStyle, type ResizeHandle } from "@/lib/blockResize";
import { blockStackZIndex, sortBlocksByStack } from "@/lib/blockStack";
import {
  blockNeedsMask,
  blockOverlayStyle,
  blockShowsEditedOverlay,
  blockShowsImageOverlay,
  editorFontFamily,
  editorFontSizePx,
  konvaAlign,
  textDirection,
} from "@/lib/textLayout";

export function EditorCanvasInner({
  page,
  maskBlocks,
  pdfCanvas,
  fileId,
  renderScale,
  maskText = true,
  editLayer = "text",
  selectedId,
  onSelect,
  onBlockChange,
}: {
  page: PageModel;
  maskBlocks: PageBlock[];
  pdfCanvas?: HTMLCanvasElement | null;
  fileId: string;
  renderScale: number;
  maskText?: boolean;
  editLayer?: "text" | "background";
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  onBlockChange: (
    blockId: string,
    patch: Partial<PageBlock>,
    userEdit?: boolean
  ) => void;
}) {
  const bgRef = useRef<HTMLCanvasElement>(null);
  const [bgReady, setBgReady] = useState(false);
  const [draggingId, setDraggingId] = useState<string | null>(null);
  const dragRef = useRef<{
    blockId: string;
    startX: number;
    startY: number;
    bbox: [number, number, number, number];
  } | null>(null);
  const resizeRef = useRef<{
    blockId: string;
    handle: ResizeHandle;
    startX: number;
    startY: number;
    bbox: [number, number, number, number];
  } | null>(null);
  const [resizingId, setResizingId] = useState<string | null>(null);

  const displayW = page.width * renderScale;
  const displayH = page.height * renderScale;

  const sortedBlocks = useMemo(
    () => sortBlocksByStack(page.blocks),
    [page.blocks]
  );

  const selectedBlock = page.blocks.find(
    (b) => b.id === selectedId && !b.deleted && (b.type === "text" || b.type === "image")
  );
  const selectedTextBlock =
    selectedBlock?.type === "text" ? selectedBlock : null;

  const maskBlockIds = useMemo(() => {
    const ids = new Set<string>();
    for (const block of maskBlocks) {
      if (blockNeedsMask(block, selectedId)) ids.add(block.id);
    }
    return ids;
  }, [maskBlocks, selectedId]);

  const masked = useMemo(() => {
    if (!pdfCanvas || !maskText || maskBlockIds.size === 0) return null;
    return maskTextRegions(pdfCanvas, maskBlocks, renderScale, maskBlockIds);
  }, [pdfCanvas, maskBlocks, renderScale, maskText, maskBlockIds]);

  useEffect(() => {
    const el = bgRef.current;
    if (!el || !pdfCanvas) {
      setBgReady(false);
      return;
    }
    const source = masked?.canvas ?? pdfCanvas;
    el.width = source.width;
    el.height = source.height;
    const ctx = el.getContext("2d");
    if (!ctx) return;
    ctx.drawImage(source, 0, 0);
    setBgReady(true);
  }, [pdfCanvas, masked]);

  useEffect(() => {
    const onMove = (e: PointerEvent) => {
      const d = dragRef.current;
      if (d) {
        const dx = (e.clientX - d.startX) / renderScale;
        const dy = (e.clientY - d.startY) / renderScale;
        const [x0, y0, x1, y1] = d.bbox;
        onBlockChange(d.blockId, { bbox: [x0 + dx, y0 + dy, x1 + dx, y1 + dy] }, false);
        return;
      }
      const r = resizeRef.current;
      if (!r) return;
      const dx = (e.clientX - r.startX) / renderScale;
      const dy = (e.clientY - r.startY) / renderScale;
      onBlockChange(
        r.blockId,
        { bbox: applyResize(r.handle, r.bbox, dx, dy) },
        false
      );
    };
    const onUp = () => {
      const d = dragRef.current;
      if (d) onBlockChange(d.blockId, {}, true);
      const r = resizeRef.current;
      if (r) onBlockChange(r.blockId, {}, true);
      dragRef.current = null;
      resizeRef.current = null;
      setDraggingId(null);
      setResizingId(null);
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };
  }, [onBlockChange, renderScale]);

  const boxW = selectedBlock
    ? Math.max(8, (selectedBlock.bbox[2] - selectedBlock.bbox[0]) * renderScale)
    : 0;
  const boxH = selectedBlock
    ? Math.max(8, (selectedBlock.bbox[3] - selectedBlock.bbox[1]) * renderScale)
    : 0;

  return (
    <div
      className="relative inline-block overflow-hidden rounded-lg bg-white shadow-xl"
      style={{ width: displayW, height: displayH }}
    >
      <canvas
        ref={bgRef}
        className="pointer-events-none absolute inset-0 select-none"
        style={{ width: displayW, height: displayH, imageRendering: "auto" }}
      />
      {!bgReady && <div className="absolute inset-0 bg-white" />}

      {sortedBlocks.map((block) => {
        if (block.type === "text" && !block.deleted && blockShowsEditedOverlay(block, selectedId)) {
          return (
            <div
              key={`preview-${block.id}`}
              style={blockOverlayStyle(block, renderScale, {
                zIndex: blockStackZIndex(block, selectedId),
              })}
            >
              {block.content}
            </div>
          );
        }
        if (
          block.type === "image" &&
          !block.deleted &&
          block.assetId &&
          blockShowsImageOverlay(block, selectedId)
        ) {
          const [x0, y0, x1, y1] = block.bbox;
          return (
            <img
              key={`img-${block.id}`}
              src={api.documentAssetUrl(fileId, block.assetId)}
              alt=""
              draggable={false}
              className="pointer-events-none absolute object-contain"
              style={{
                left: x0 * renderScale,
                top: y0 * renderScale,
                width: Math.max(8, (x1 - x0) * renderScale),
                height: Math.max(8, (y1 - y0) * renderScale),
                zIndex: blockStackZIndex(block, selectedId),
              }}
            />
          );
        }
        return null;
      })}

      <Stage
        width={displayW}
        height={displayH}
        onMouseDown={(e) => {
          if (e.target === e.target.getStage()) onSelect(null);
        }}
      >
        <Layer>
          {sortedBlocks.map((block) => {
            if (block.type === "background") {
              if (editLayer !== "background") return null;
              const [x0, y0, x1, y1] = block.bbox;
              const selected = selectedId === block.id;
              const rgb = block.backgroundRgb;
              const hint = rgb
                ? `rgba(${rgb[0]}, ${rgb[1]}, ${rgb[2]}, 0.15)`
                : "rgba(200,200,200,0.12)";
              return (
                <Rect
                  key={block.id}
                  x={x0 * renderScale}
                  y={y0 * renderScale}
                  width={(x1 - x0) * renderScale}
                  height={(y1 - y0) * renderScale}
                  fill={hint}
                  stroke={selected ? "#0d9488" : "#f59e0b"}
                  strokeWidth={selected ? 2.5 : 1.5}
                  dash={[8, 4]}
                  listening
                  onClick={() => onSelect(block.id)}
                  onTap={() => onSelect(block.id)}
                />
              );
            }

            if (
              (block.type !== "text" && block.type !== "image") ||
              editLayer !== "text" ||
              block.deleted
            ) {
              return null;
            }

            const [x0, y0, x1, y1] = block.bbox;
            const selected = selectedId === block.id;
            const isTableCell = Boolean(block.tableGroupId);

            return (
              <Rect
                key={block.id}
                id={`block-${block.id}`}
                x={x0 * renderScale}
                y={y0 * renderScale}
                width={Math.max(4, (x1 - x0) * renderScale)}
                height={Math.max(4, (y1 - y0) * renderScale)}
                fill="transparent"
                stroke={
                  selected
                    ? "#0d9488"
                    : isTableCell
                      ? "rgba(13,148,136,0.5)"
                      : "rgba(13,148,136,0.4)"
                }
                strokeWidth={selected ? 2 : 1}
                dash={isTableCell && !selected ? [4, 3] : undefined}
                listening
                onClick={() => onSelect(block.id)}
                onTap={() => onSelect(block.id)}
              />
            );
          })}
        </Layer>
      </Stage>

      {selectedBlock && editLayer === "text" && (
        <div
          className="absolute overflow-visible"
          style={{
            left: selectedBlock.bbox[0] * renderScale,
            top: selectedBlock.bbox[1] * renderScale,
            minWidth: boxW,
            minHeight: boxH,
            width: boxW,
            height: boxH,
            zIndex: blockStackZIndex(selectedBlock, selectedId),
          }}
        >
          <div
            role="button"
            tabIndex={0}
            title="Drag to move"
            className="absolute -top-[18px] left-0 right-0 z-30 flex h-[18px] cursor-move items-center justify-center rounded-t bg-teal-600/90 text-[10px] font-medium text-white select-none"
            onPointerDown={(e) => {
              e.preventDefault();
              e.stopPropagation();
              dragRef.current = {
                blockId: selectedBlock.id,
                startX: e.clientX,
                startY: e.clientY,
                bbox: [...selectedBlock.bbox] as [number, number, number, number],
              };
              setDraggingId(selectedBlock.id);
            }}
          >
            ⋮⋮ Move
          </div>
          {(
            ["nw", "n", "ne", "e", "se", "s", "sw", "w"] as ResizeHandle[]
          ).map((handle) => (
            <div
              key={handle}
              role="presentation"
              title="Resize box"
              style={resizeHandleStyle(handle, boxW, boxH)}
              onPointerDown={(e) => {
                e.preventDefault();
                e.stopPropagation();
                resizeRef.current = {
                  blockId: selectedBlock.id,
                  handle,
                  startX: e.clientX,
                  startY: e.clientY,
                  bbox: [...selectedBlock.bbox] as [number, number, number, number],
                };
                setResizingId(selectedBlock.id);
              }}
            />
          ))}
          {selectedTextBlock && (
            <div className="relative min-h-full min-w-full overflow-visible">
              {(draggingId === selectedTextBlock.id ||
                resizingId === selectedTextBlock.id) && (
                <div
                  className="pointer-events-none absolute left-0 top-0 min-w-full border-2 border-teal-600"
                  style={{
                    ...blockOverlayStyle(selectedTextBlock, renderScale, {
                      fillParent: false,
                      zIndex: 1,
                    }),
                    position: "relative",
                    left: 0,
                    top: 0,
                    width: "max-content",
                    minWidth: "100%",
                    height: "auto",
                    minHeight: "100%",
                  }}
                >
                  {selectedTextBlock.content}
                </div>
              )}
              {draggingId !== selectedTextBlock.id &&
                resizingId !== selectedTextBlock.id && (
                  <textarea
                    className="relative z-[2] min-h-full min-w-full resize-none overflow-visible border-2 border-teal-600 bg-transparent text-zinc-900 outline-none"
                    style={{
                      fontSize: editorFontSizePx(selectedTextBlock, renderScale),
                      fontFamily: editorFontFamily(selectedTextBlock),
                      textAlign: konvaAlign(selectedTextBlock),
                      direction: textDirection(selectedTextBlock),
                      lineHeight: 1.15,
                      padding: "1px 2px",
                      margin: 0,
                      boxSizing: "border-box",
                      width: boxW,
                      minWidth: boxW,
                      minHeight: boxH,
                    }}
                    value={selectedTextBlock.content ?? ""}
                    onChange={(e) =>
                      onBlockChange(selectedTextBlock.id, { content: e.target.value })
                    }
                    autoFocus
                  />
                )}
            </div>
          )}
          {selectedBlock.type === "image" && selectedBlock.assetId && (
            <img
              src={api.documentAssetUrl(fileId, selectedBlock.assetId)}
              alt=""
              draggable={false}
              className="pointer-events-none h-full w-full border-2 border-teal-600 object-contain"
            />
          )}
          {selectedBlock.type === "image" && !selectedBlock.assetId && (
            <div className="pointer-events-none h-full w-full border-2 border-dashed border-teal-600 bg-teal-500/10" />
          )}
        </div>
      )}
    </div>
  );
}
