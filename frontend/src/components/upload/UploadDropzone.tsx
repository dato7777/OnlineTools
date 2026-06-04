"use client";

import { useCallback, useState } from "react";
import { motion } from "framer-motion";
import { FileUp } from "lucide-react";
import { cn } from "@/lib/utils";

export function UploadDropzone({
  accept = "application/pdf",
  onFile,
  label = "Drop your PDF here",
  hint = "or click to browse",
}: {
  accept?: string;
  onFile: (file: File) => void;
  label?: string;
  hint?: string;
}) {
  const [drag, setDrag] = useState(false);

  const handle = useCallback(
    (file: File | undefined) => {
      if (!file) return;
      onFile(file);
    },
    [onFile]
  );

  return (
    <motion.label
      onDragOver={(e) => {
        e.preventDefault();
        setDrag(true);
      }}
      onDragLeave={() => setDrag(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDrag(false);
        handle(e.dataTransfer.files[0]);
      }}
      animate={{ borderColor: drag ? "var(--accent)" : "var(--border)" }}
      className={cn(
        "flex min-h-[220px] cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed px-6 py-12 transition-colors md:min-h-[280px]",
        drag && "bg-accent-muted/30 shadow-glow"
      )}
    >
      <input
        type="file"
        accept={accept}
        className="sr-only"
        onChange={(e) => handle(e.target.files?.[0])}
      />
      <div className="flex h-14 w-14 items-center justify-center rounded-full bg-accent-muted text-accent">
        <FileUp className="h-7 w-7" />
      </div>
      <p className="mt-4 text-lg font-medium">{label}</p>
      <p className="mt-1 text-sm text-[var(--text-muted)]">{hint}</p>
    </motion.label>
  );
}
