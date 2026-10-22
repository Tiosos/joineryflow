"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import type { CloseOutChecksOut, ProjectOut } from "@/lib/pm-types";
import { PM, ApiError } from "@/lib/pm-fetch";
import { useConfirm } from "@/components/confirm/ConfirmProvider";

interface Props {
  project: ProjectOut;
  canCloseOut: boolean;
}

function openLines(c: CloseOutChecksOut): string[] {
  const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;
  return [
    c.open_defects > 0 && plural(c.open_defects, "open QC defect", "open QC defects"),
    c.open_rework > 0 && plural(c.open_rework, "open rework", "open rework records"),
    c.items_not_installed > 0 && plural(c.items_not_installed, "item not installed", "items not installed"),
    c.open_orders > 0 && plural(c.open_orders, "open order", "open orders"),
  ].filter((l): l is string => l !== false);
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
  const { confirm, askReason } = useConfirm();
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const closed = project.closed_at != null;

  async function closeOut() {
    // Close-out checks are advisory (user decision 2026-10-22): what is still open is listed and a
    // reason is asked for, but nothing stops the close-out. If the list cannot be read, plain confirm.
    const checks = await PM.closeOutChecks(project.id).catch(() => null);
    const open = checks ? openLines(checks) : [];
    const title = `Close out ${project.project_code}?`;
    let reason: string | undefined;
    if (open.length === 0) {
      if (!(await confirm({ title, message: "Closing out is the only way to close a project.", confirmLabel: "Close out" }))) return;
    } else {
      const given = await askReason({
        title,
        message: (
          <div>
            <p>Still open on this project:</p>
            <ul className="mt-1 list-disc pl-5" data-testid="close-out-open">
              {open.map((line) => <li key={line}>{line}</li>)}
            </ul>
            <p className="mt-2">You can close it anyway. The reason is kept in the audit log.</p>
          </div>
        ),
        reasonLabel: "Reason for closing with these open",
        confirmLabel: "Close out anyway",
      });
      if (given === null) return;
      reason = given;
    }
    setBusy(true);
    setError(null);
    try {
      await PM.closeOutProject(project.id, reason);
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
