"use client";

import type { PageBlock } from "@/lib/api";

export function MobileBlockSheet({
  block,
  open,
  onClose,
  onChange,
}: {
  block: PageBlock | null;
  open: boolean;
  onClose: () => void;
  onChange: (content: string) => void;
}) {
  if (!open || !block || block.type !== "text") return null;

  return (
    <div className="fixed inset-x-0 bottom-0 z-50 md:hidden">
      <button type="button" className="absolute inset-0 bg-black/40" onClick={onClose} aria-label="Close" />
      <div className="relative glass rounded-t-2xl p-4 pb-8">
        <p className="mb-2 text-xs font-medium text-[var(--text-muted)]">Edit text</p>
        <textarea
          className="w-full min-h-[100px] rounded-xl border border-[var(--border)] bg-[var(--surface)] p-3 text-base"
          value={block.content ?? ""}
          onChange={(e) => onChange(e.target.value)}
        />
        <button
          type="button"
          onClick={onClose}
          className="mt-3 w-full rounded-xl bg-accent py-3 font-medium text-white dark:text-zinc-900"
        >
          Done
        </button>
      </div>
    </div>
  );
}
