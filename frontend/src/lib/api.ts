const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type ToolInfo = {
  slug: string;
  title: string;
  description: string;
  icon: string;
  input_mime_types: string[];
  enabled: boolean;
  coming_soon: boolean;
};

export type FileAsset = {
  id: string;
  filename: string;
  mime_type: string;
  size_bytes: number;
  created_at: string;
};

export type Job = {
  id: string;
  tool_slug: string;
  status: string;
  progress: number;
  progress_message: string | null;
  error: string | null;
  input_file_id: string;
  output_file_id: string | null;
  created_at: string;
  updated_at: string;
};

export type PageBlock = {
  id: string;
  type: "text" | "image" | "background";
  layer?: "text" | "background";
  align?: "left" | "center" | "right";
  direction?: "ltr" | "rtl";
  bbox: number[];
  content?: string;
  fontSize?: number;
  fontFamily?: string;
  assetId?: string;
  source?: string;
  dirty?: boolean;
  originalContent?: string;
  originalBbox?: number[];
  backgroundRgb?: [number, number, number];
  backgroundBlockId?: string;
  pdfFont?: string;
  textOrigin?: [number, number];
  glyphRects?: number[][];
  deleted?: boolean;
  tableGroupId?: string;
  tableRow?: number;
  tableCol?: number;
  cellBbox?: number[];
  /** Tight bounds of actual text ink inside a table cell (not the full grid cell). */
  textInkBbox?: number[];
  /** Ink bounds at analyze time — used to erase original glyphs after drag. */
  originalTextInkBbox?: number[];
};

export type PageModel = {
  pageIndex: number;
  pageType: string;
  width: number;
  height: number;
  blocks: PageBlock[];
  tierUsed?: string;
};

export type BlockDocument = {
  fileId: string;
  pages: PageModel[];
  nativePageRatio?: number;
  diagnostics?: Record<string, unknown>;
};

export type PlacementMetrics = {
  insertRect: number[];
  exportFontSize: number;
  align: "left" | "center" | "right";
  useTextOrigin: boolean;
  textOrigin: [number, number] | null;
  isTableCell: boolean;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}/api/v1${path}`, {
    ...init,
    headers: {
      ...(init?.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...init?.headers,
    },
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  listTools: () => request<ToolInfo[]>("/tools"),

  uploadFile: async (file: File) => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`${API_BASE}/api/v1/files`, { method: "POST", body: form });
    if (!res.ok) throw new Error(await res.text());
    return res.json() as Promise<FileAsset>;
  },

  runTool: (slug: string, fileId: string, options: Record<string, unknown> = {}) =>
    request<Job>(`/tools/${slug}/run`, {
      method: "POST",
      body: JSON.stringify({ file_id: fileId, options }),
    }),

  getJob: (jobId: string) => request<Job>(`/jobs/${jobId}`),

  getModel: (fileId: string) => request<BlockDocument>(`/tools/pdf-editor/documents/${fileId}/model`),

  saveModel: (fileId: string, pages: PageModel[]) =>
    request<BlockDocument>(`/tools/pdf-editor/documents/${fileId}/model`, {
      method: "PATCH",
      body: JSON.stringify({ pages }),
    }),

  placementMetrics: (block: PageBlock) =>
    request<PlacementMetrics>("/tools/pdf-editor/placement-metrics", {
      method: "POST",
      body: JSON.stringify({ block }),
    }),

  exportPdf: (fileId: string, model?: BlockDocument) =>
    request<{ jobId: string; status: string; outputFileId: string | null; unchanged?: boolean }>(
      `/tools/pdf-editor/documents/${fileId}/export`,
      {
        method: "POST",
        body: JSON.stringify({ model: model ?? null }),
      }
    ),

  fileDownloadUrl: (fileId: string) => `${API_BASE}/api/v1/files/${fileId}/download`,
};

export function pollJob(jobId: string, onUpdate: (job: Job) => void, intervalMs = 800): () => void {
  let active = true;
  const tick = async () => {
    if (!active) return;
    try {
      const job = await api.getJob(jobId);
      onUpdate(job);
      if (job.status === "completed" || job.status === "failed") return;
    } catch {
      /* retry */
    }
    setTimeout(tick, intervalMs);
  };
  tick();
  return () => {
    active = false;
  };
}
