import type { CSSProperties } from "react";

export type ResizeHandle = "nw" | "n" | "ne" | "e" | "se" | "s" | "sw" | "w";

const HANDLE_SIZE = 10;

export function resizeHandleStyle(
  handle: ResizeHandle,
  width: number,
  height: number
): CSSProperties {
  const half = HANDLE_SIZE / 2;
  const base: CSSProperties = {
    position: "absolute",
    width: HANDLE_SIZE,
    height: HANDLE_SIZE,
    borderRadius: 2,
    background: "#0d9488",
    border: "1px solid #fff",
    zIndex: 35,
    touchAction: "none",
  };
  switch (handle) {
    case "nw":
      return { ...base, left: -half, top: -half, cursor: "nwse-resize" };
    case "n":
      return { ...base, left: width / 2 - half, top: -half, cursor: "ns-resize" };
    case "ne":
      return { ...base, left: width - half, top: -half, cursor: "nesw-resize" };
    case "e":
      return { ...base, left: width - half, top: height / 2 - half, cursor: "ew-resize" };
    case "se":
      return { ...base, left: width - half, top: height - half, cursor: "nwse-resize" };
    case "s":
      return { ...base, left: width / 2 - half, top: height - half, cursor: "ns-resize" };
    case "sw":
      return { ...base, left: -half, top: height - half, cursor: "nesw-resize" };
    case "w":
      return { ...base, left: -half, top: height / 2 - half, cursor: "ew-resize" };
    default:
      return base;
  }
}

export function applyResize(
  handle: ResizeHandle,
  start: [number, number, number, number],
  dx: number,
  dy: number,
  minW = 12,
  minH = 10
): [number, number, number, number] {
  let [x0, y0, x1, y1] = start;

  if (handle.includes("e")) x1 += dx;
  if (handle.includes("w")) x0 += dx;
  if (handle.includes("s")) y1 += dy;
  if (handle.includes("n")) y0 += dy;

  if (x1 - x0 < minW) {
    if (handle.includes("w")) x0 = x1 - minW;
    else x1 = x0 + minW;
  }
  if (y1 - y0 < minH) {
    if (handle.includes("n")) y0 = y1 - minH;
    else y1 = y0 + minH;
  }

  return [x0, y0, x1, y1];
}
