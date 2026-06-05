"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Stage, Layer, Rect } from "react-konva";
import type { PageBlock, PageModel } from "@/lib/api";
import { maskTextRegions } from "@/lib/preparePageCanvas";
import { applyResize, resizeHandleStyle, type ResizeHandle } from "@/lib/blockResize";
import {
  blockNeedsMask,
  blockOverlayStyle,
  blockShowsEditedOverlay,
  editorFontFamily,
  editorFontSizePx,
  konvaAlign,
  textDirection,
} from "@/lib/textLayout";

export function EditorCanvasInner({
  page,
  maskBlocks,
  pdfCanvas,
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

  const selectedBlock = page.blocks.find(
    (b) => b.id === selectedId && b.type === "text" && !b.deleted
  );

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

      {page.blocks.map((block) => {
        if (
          block.type !== "text" ||
          block.deleted ||
          !blockShowsEditedOverlay(block, selectedId)
        ) {
          return null;
        }
        return (
          <div key={`preview-${block.id}`} style={blockOverlayStyle(block, renderScale)}>
            {block.content}
          </div>
        );
      })}

      <Stage
        width={displayW}
        height={displayH}
        onMouseDown={(e) => {
          if (e.target === e.target.getStage()) onSelect(null);
        }}
      >
        <Layer>
          {page.blocks.map((block) => {
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

            if (block.type !== "text" || editLayer !== "text" || block.deleted) {
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
                stroke={selected ? "#0d9488" : isTableCell ? "rgba(13,148,136,0.35)" : "rgba(13,148,136,0.2)"}
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
          className="absolute z-20"
          style={{
            left: selectedBlock.bbox[0] * renderScale,
            top: selectedBlock.bbox[1] * renderScale,
            width: Math.max(8, (selectedBlock.bbox[2] - selectedBlock.bbox[0]) * renderScale),
            height: Math.max(8, (selectedBlock.bbox[3] - selectedBlock.bbox[1]) * renderScale),
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
              style={resizeHandleStyle(
                handle,
                Math.max(8, (selectedBlock.bbox[2] - selectedBlock.bbox[0]) * renderScale),
                Math.max(8, (selectedBlock.bbox[3] - selectedBlock.bbox[1]) * renderScale)
              )}
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
          {draggingId !== selectedBlock.id && resizingId !== selectedBlock.id && (
            <textarea
              className="h-full w-full resize-none overflow-hidden border-2 border-teal-600 bg-transparent text-black outline-none"
              style={{
                fontSize: editorFontSizePx(selectedBlock, renderScale),
                fontFamily: editorFontFamily(selectedBlock),
                textAlign: konvaAlign(selectedBlock),
                direction: textDirection(selectedBlock),
                lineHeight: 1.15,
                padding: "1px 2px",
                margin: 0,
                boxSizing: "border-box",
              }}
              value={selectedBlock.content ?? ""}
              onChange={(e) =>
                onBlockChange(selectedBlock.id, { content: e.target.value })
              }
              autoFocus
            />
          )}
        </div>
      )}
    </div>
  );
}
