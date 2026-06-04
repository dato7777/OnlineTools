"use client";

import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { UploadDropzone } from "@/components/upload/UploadDropzone";
import { StepTimeline } from "@/components/processing/StepTimeline";
import { api, pollJob, type FileAsset, type Job } from "@/lib/api";

export default function ToolPage() {
  const { slug } = useParams<{ slug: string }>();
  const router = useRouter();
  const [phase, setPhase] = useState<"upload" | "processing">("upload");
  const [file, setFile] = useState<FileAsset | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);

  const stepIndex =
    phase === "upload" ? 0 : job?.status === "completed" ? 2 : 1;

  async function handleUpload(f: File) {
    setError(null);
    try {
      const uploaded = await api.uploadFile(f);
      setFile(uploaded);
      setPhase("processing");
      const j = await api.runTool(slug, uploaded.id, { action: "analyze" });
      setJob(j);
      pollJob(j.id, (updated) => {
        setJob(updated);
        if (updated.status === "completed") {
          router.push(`/tools/pdf-editor/${uploaded.id}?job=${updated.id}`);
        }
        if (updated.status === "failed") {
          setError(updated.error ?? "Processing failed");
          setPhase("upload");
        }
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
      setPhase("upload");
    }
  }

  const title = slug === "pdf-editor" ? "PDF Editor" : slug;

  return (
    <AppShell>
      <section className="mx-auto max-w-2xl px-4 py-10 md:py-16">
        <h1 className="text-3xl font-bold tracking-tight">{title}</h1>
        <p className="mt-2 text-[var(--text-muted)]">
          Drop a PDF to analyze layout and open the editor.
        </p>

        <div className="mt-10">
          {phase === "upload" && (
            <UploadDropzone
              accept="application/pdf"
              onFile={handleUpload}
              label="Drop your PDF here"
            />
          )}
          {phase === "processing" && (
            <div className="py-8">
              <StepTimeline
                activeIndex={stepIndex}
                message={job?.progress_message ?? "Processing…"}
              />
              {file && (
                <p className="mt-6 text-center text-sm text-[var(--text-muted)]">
                  {file.filename}
                </p>
              )}
            </div>
          )}
          {error && (
            <p className="mt-4 text-center text-sm text-red-600">{error}</p>
          )}
        </div>
      </section>
    </AppShell>
  );
}
