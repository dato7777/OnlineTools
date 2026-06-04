"use client";

import Link from "next/link";
import { Layers } from "lucide-react";
import { cn } from "@/lib/utils";

export function AppShell({
  children,
  className,
  hideNav,
}: {
  children: React.ReactNode;
  className?: string;
  hideNav?: boolean;
}) {
  return (
    <div className={cn("min-h-dvh flex flex-col", className)}>
      {!hideNav && (
        <header className="glass sticky top-0 z-50 px-4 py-3 md:px-8">
          <div className="mx-auto flex max-w-6xl items-center justify-between">
            <Link href="/" className="flex items-center gap-2 font-semibold tracking-tight">
              <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-accent text-white dark:text-zinc-900">
                <Layers className="h-5 w-5" />
              </span>
              OnlineTools
            </Link>
          </div>
        </header>
      )}
      <main className="flex-1">{children}</main>
    </div>
  );
}
