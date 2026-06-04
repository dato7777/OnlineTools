"use client";

import { motion } from "framer-motion";
import { Check, Circle, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

const STEPS = ["Upload", "Understand", "Ready"] as const;

export function StepTimeline({
  activeIndex,
  message,
}: {
  activeIndex: number;
  message?: string | null;
}) {
  return (
    <div className="w-full max-w-md mx-auto">
      <div className="flex justify-between gap-2">
        {STEPS.map((step, i) => {
          const done = i < activeIndex;
          const current = i === activeIndex;
          return (
            <div key={step} className="flex flex-1 flex-col items-center gap-2">
              <div
                className={cn(
                  "flex h-10 w-10 items-center justify-center rounded-full border",
                  done && "border-accent bg-accent text-white dark:text-zinc-900",
                  current && "border-accent text-accent",
                  !done && !current && "border-[var(--border)] text-[var(--text-muted)]"
                )}
              >
                {done ? (
                  <Check className="h-5 w-5" />
                ) : current ? (
                  <Loader2 className="h-5 w-5 animate-spin" />
                ) : (
                  <Circle className="h-4 w-4" />
                )}
              </div>
              <span className="text-xs font-medium md:text-sm">{step}</span>
            </div>
          );
        })}
      </div>
      {message && (
        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="mt-6 text-center text-sm text-[var(--text-muted)]"
        >
          {message}
        </motion.p>
      )}
    </div>
  );
}
