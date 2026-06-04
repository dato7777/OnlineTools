import { AppShell } from "@/components/layout/AppShell";
import { ToolCard } from "@/components/hub/ToolCard";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  let tools: Awaited<ReturnType<typeof api.listTools>> = [];
  try {
    tools = await api.listTools();
  } catch {
    tools = [
      {
        slug: "pdf-editor",
        title: "PDF Editor",
        description: "Edit text and images. Recover scanned PDFs into editable documents.",
        icon: "file-pen",
        input_mime_types: ["application/pdf"],
        enabled: true,
        coming_soon: false,
      },
    ];
  }

  return (
    <AppShell>
      <section className="mx-auto max-w-6xl px-4 py-12 md:py-20">
        <div className="max-w-2xl">
          <h1 className="text-4xl font-bold tracking-tight md:text-5xl">
            Your documents,
            <span className="text-accent"> simplified.</span>
          </h1>
          <p className="mt-4 text-lg text-[var(--text-muted)]">
            One place for PDF editing, scan recovery, and conversions — starting with PDF Editor.
          </p>
        </div>
        <div className="mt-12 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {tools.map((tool) => (
            <ToolCard key={tool.slug} tool={tool} />
          ))}
        </div>
      </section>
    </AppShell>
  );
}
