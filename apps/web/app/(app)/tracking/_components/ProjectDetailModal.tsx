"use client";

import type { ProjectOut } from "@/lib/pm-types";

interface Props {
  project: ProjectOut | null;
  onClose: () => void;
}

/**
 * Q408's Project Details window has four tabs — PROJECT STATS · CARS · OH&S ·
 * SCOPE (`legacy/tracking_dashboard.html:850`). Only **Project Stats** is built
 * (Q476 keeps this modal rather than a separate window; `/projects/[id]` stays
 * as the full page, since Q409 makes them two views of one record).
 *
 * The other three are shown disabled rather than hidden, so the window's real
 * shape stays visible: **Cars and OH&S** wait on Q550 and **Scope** on Q572 —
 * nothing in this repo or the reference mock says what any of the three holds.
 */
const TABS = [
  { key: "stats", label: "Project stats", blocked: null },
  { key: "cars", label: "Cars", blocked: "Q550" },
  { key: "ohs", label: "OH&S", blocked: "Q550" },
  { key: "scope", label: "Scope", blocked: "Q572" },
] as const;

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

        <div className="flex gap-1 border-b border-h-line px-5 py-2">
          {TABS.map((t) => (
            <button
              key={t.key}
              type="button"
              disabled={t.blocked != null}
              title={
                t.blocked
                  ? `Awaiting the customer's definition of this tab (${t.blocked})`
                  : undefined
              }
              className={`rounded px-2.5 py-1 text-[11px] font-medium ${
                t.blocked == null
                  ? "bg-h-accent text-white"
                  : "text-h-muted opacity-40"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

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
          {/* The rest of the mock's meta tiles — all real columns. */}
          <Field label="Created by">{project.created_by ?? "—"}</Field>
          <Field label="TG Solid">
            {project.tg_solid == null ? "—" : project.tg_solid ? "✓" : "—"}
          </Field>
          <Field label="Total line items">
            <span className="font-mono tabular-nums">
              {project.total_line_items ?? "—"}
            </span>
          </Field>
        </div>

        {/* Q571: the mock's two hours tables come from TGPAY, an external
            payroll system. Nothing in this schema records hours — there is no
            time_record table, which #8 put explicitly out of scope — so the
            rows are shown with their labels and no values. Blank because the
            integration does not exist, not because the data is missing. */}
        <div className="grid gap-4 border-t border-h-line p-5 sm:grid-cols-2">
          <HoursTable
            title="Admin stats"
            rows={[
              "Project manage",
              "Shop drawing",
              "Procuring",
              "Meetings",
              "Listing",
              "Document control",
              "Listing reworks",
            ]}
          />
          <HoursTable
            title="Production / install"
            rows={["Assembly hours", "Site install hours"]}
          />
        </div>

        <footer className="border-t border-h-line bg-h-bg px-5 py-3 text-[11px] text-h-muted">
          Read-only view. Edit project metadata from the admin tools. Hours come
          from TGPAY, which is not integrated — see Q571.
        </footer>
      </div>
    </div>
  );
}

function HoursTable({ title, rows }: { title: string; rows: string[] }) {
  return (
    <div className="rounded border border-h-line">
      <div className="border-b border-h-line bg-h-bg px-2 py-1 text-center text-[10px] font-semibold uppercase tracking-wider text-h-muted">
        {title}
      </div>
      <table className="w-full text-[11px]">
        <tbody>
          {rows.map((r) => (
            <tr key={r} className="border-b border-h-line last:border-b-0">
              <td className="px-2 py-1 text-h-muted">{r}</td>
              <td className="px-2 py-1 text-right font-mono tabular-nums text-h-line">
                —
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="px-2 py-1 text-[9px] italic text-h-muted">
        Data from TGPAY — not integrated
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
