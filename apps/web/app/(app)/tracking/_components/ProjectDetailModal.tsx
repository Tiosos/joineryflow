"use client";

import type { ProjectOut } from "@/lib/pm-types";

interface Props {
  project: ProjectOut | null;
  onClose: () => void;
}

export function ProjectDetailModal({ project, onClose }: Props) {
  if (!project) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="w-full max-w-2xl rounded-lg border border-h-line bg-h-surface shadow-xl">
        <header className="flex items-center justify-between gap-4 border-b border-h-line bg-h-bg px-5 py-3">
          <div>
            <div className="text-[10px] font-semibold uppercase tracking-wider text-h-muted">
              Project details
            </div>
            <div className="text-sm text-h-ink">
              {project.name}
              <span className="ml-2 font-mono text-xs text-h-muted">
                {project.project_code}
              </span>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded border border-h-line bg-h-surface px-3 py-1 text-sm text-h-ink hover:bg-h-bg"
          >
            Close
          </button>
        </header>

        <div className="grid grid-cols-2 gap-4 p-5">
          <Field label="Project code">
            <span className="font-mono text-sm">{project.project_code}</span>
          </Field>
          <Field label="Status">{project.status ?? "—"}</Field>
          <Field label="Project manager">{project.pm_name ?? "—"}</Field>
          <Field label="Install start">
            <span className="font-mono tabular-nums">
              {project.install_start ?? "—"}
            </span>
          </Field>
          <Field label="Item count">
            <span className="font-mono tabular-nums">{project.item_count}</span>
          </Field>
          <Field label="Total value">
            <span className="font-mono tabular-nums">
              {project.total_value == null
                ? "—"
                : project.total_value.toLocaleString(undefined, {
                    style: "currency",
                    currency: "AUD",
                    maximumFractionDigits: 0,
                  })}
            </span>
          </Field>
          <Field label="Favourite">{project.is_favourite ? "Yes ★" : "No"}</Field>
          <Field label="Created">
            <span className="font-mono tabular-nums">
              {project.created_at?.slice(0, 10) ?? "—"}
            </span>
          </Field>
        </div>

        <footer className="border-t border-h-line bg-h-bg px-5 py-3 text-[11px] text-h-muted">
          Read-only view. Edit project metadata from the admin tools.
        </footer>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="text-[10px] font-semibold uppercase tracking-wider text-h-muted">
        {label}
      </div>
      <div className="mt-0.5 text-sm text-h-ink">{children}</div>
    </div>
  );
}
