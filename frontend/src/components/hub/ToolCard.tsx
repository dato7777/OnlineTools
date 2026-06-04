"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { ArrowRight, Lock } from "lucide-react";
import type { ToolInfo } from "@/lib/api";
import { toolIcon } from "@/lib/tools";
import { cn } from "@/lib/utils";

export function ToolCard({ tool }: { tool: ToolInfo }) {
  const Icon = toolIcon(tool.icon);
  const enabled = tool.enabled && !tool.coming_soon;

  const inner = (
    <motion.div
      whileHover={enabled ? { y: -4 } : undefined}
      className={cn(
        "group relative flex h-full flex-col rounded-2xl border border-[var(--border)] p-6 transition-shadow",
        enabled
          ? "bg-[var(--surface-elevated)] hover:shadow-glow cursor-pointer"
          : "bg-[var(--surface-elevated)]/50 opacity-70"
      )}
    >
      <div
        className={cn(
          "mb-4 flex h-12 w-12 items-center justify-center rounded-xl",
          enabled ? "bg-accent-muted text-accent" : "bg-zinc-200 dark:bg-zinc-800 text-zinc-500"
        )}
      >
        <Icon className="h-6 w-6" />
      </div>
      <h3 className="text-lg font-semibold">{tool.title}</h3>
      <p className="mt-2 flex-1 text-sm text-[var(--text-muted)]">{tool.description}</p>
      <div className="mt-4 flex items-center gap-2 text-sm font-medium text-accent">
        {tool.coming_soon ? (
          <>
            <Lock className="h-4 w-4" />
            Coming soon
          </>
        ) : (
          <>
            Open tool
            <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" />
          </>
        )}
      </div>
    </motion.div>
  );

  if (!enabled) return inner;
  return (
    <Link href={`/tools/${tool.slug}`} className="block h-full">
      {inner}
    </Link>
  );
}
