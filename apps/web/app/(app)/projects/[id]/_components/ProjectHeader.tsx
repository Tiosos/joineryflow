"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import type { ProjectOut } from "@/lib/pm-types";
import { PM, ApiError } from "@/lib/pm-fetch";

interface Props {
  project: ProjectOut;
  canCloseOut: boolean;
}

function money(v: number | null): string {
  if (v == null) return "—";
  return v.toLocaleString(undefined, {
    style: "currency",
    currency: "AUD",
    maximumFractionDigits: 0,
  });
}

export function ProjectHeader({ project, canCloseOut }: Props) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const closed = project.closed_at != null;

  async function closeOut() {
    if (!confirm(`Close out ${project.project_code}?`)) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await PM.closeOutProject(project.id);
      router.refresh();
    } catch (e) {
      setError(
        e instanceof ApiError && e.status === 409
          ? "Already closed."
          : "Failed to close out project.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <header className="rounded-lg border border-h-line bg-h-surface p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-h-ink">
            {project.name}
            <span className="ml-2 font-mono text-sm text-h-muted">
              {project.project_code}
            </span>
          </h1>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-h-muted">
            <span className="rounded-full border border-h-line px-2 py-0.5 text-xs">
              {project.status ?? "—"}
            </span>
            {project.builder && <span>Builder: {project.builder}</span>}
            {project.classification && <span>· {project.classification}</span>}
          </div>
        </div>

        {canCloseOut && (
          <div className="flex flex-col items-end gap-1">
            <button
              type="button"
              disabled={busy || closed}
              onClick={closeOut}
              className="rounded border border-h-line bg-h-surface px-3 py-1.5 text-sm text-h-ink hover:bg-h-line/40 disabled:cursor-not-allowed disabled:opacity-50"
              title={closed ? `Closed ${project.closed_at?.slice(0, 10)} by ${project.closed_by_name ?? "—"}` : undefined}
            >
              {closed ? "Closed" : busy ? "Closing…" : "Close out"}
            </button>
            {error && <span className="text-xs text-rose-700">{error}</span>}
          </div>
        )}
      </div>

      <div className="mt-3 grid grid-cols-2 gap-3 border-t border-h-line pt-3 text-sm sm:grid-cols-4">
        <Field label="Install start">{project.install_start ?? "—"}</Field>
        <Field label="Total value">{money(project.total_value)}</Field>
        <Field label="Item count">{project.item_count}</Field>
        <Field label="PM">{project.pm_name ?? "—"}</Field>
      </div>
    </header>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="text-[10px] font-semibold uppercase tracking-wider text-h-muted">
        {label}
      </div>
      <div className="mt-0.5 font-mono text-h-ink">{children}</div>
    </div>
  );
}
