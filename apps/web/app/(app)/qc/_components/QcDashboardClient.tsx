"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { qcApi } from "@/lib/qc-fetch";
import type { QcDashboard, QcDashboardFilters } from "@/lib/qc-types";

interface Project {
  id: number;
  project_code: string;
  name: string;
}

const DAY_MS = 86_400_000;

function ageDays(iso: string): number {
  return Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / DAY_MS));
}

function ageLabel(iso: string): string {
  const d = ageDays(iso);
  return d === 0 ? "today" : d === 1 ? "1 day" : `${d} days`;
}

// Money arrives as a string (a Pydantic Decimal); never assume a number.
function money(v: string): string {
  return `$${Number(v).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

// "$0.00" would read as a real total when nothing has been priced yet.
function cost(total: string, unpriced: number, open: number): string {
  return open > 0 && unpriced === open ? "—" : money(total);
}

function Tile({ label, value, note, testId }: {
  label: string; value: string | number; note?: string; testId: string;
}) {
  return (
    <div className="rounded-lg border border-h-line bg-h-surface px-4 py-3" data-testid={testId}>
      <div className="font-mono text-xs uppercase text-h-muted">{label}</div>
      <div className="mt-1 text-2xl font-medium text-h-ink">{value}</div>
      {note && <div className="mt-1 text-xs text-h-muted">{note}</div>}
    </div>
  );
}

function Panel({ title, children, testId }: {
  title: string; children: React.ReactNode; testId?: string;
}) {
  return (
    <section className="rounded-lg border border-h-line bg-h-surface" data-testid={testId}>
      <h2 className="border-b border-h-line px-4 py-2 text-sm font-medium text-h-ink">{title}</h2>
      <div className="overflow-x-auto">{children}</div>
    </section>
  );
}

const TH = "px-4 py-2 text-left font-mono text-xs font-normal uppercase text-h-muted";
const TD = "px-4 py-2 text-sm text-h-ink";

function Empty({ children }: { children: React.ReactNode }) {
  return <p className="px-4 py-6 text-center text-sm text-h-muted">{children}</p>;
}

export function QcDashboardClient({
  projects,
  initial,
}: {
  projects: Project[];
  initial: QcDashboardFilters;
}) {
  const [filters, setFilters] = useState<QcDashboardFilters>(initial);
  const [data, setData] = useState<QcDashboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  // Only the newest request may write: a slow response for an earlier filter
  // must not overwrite the numbers for the one on screen now.
  const seq = useRef(0);

  useEffect(() => {
    const mine = ++seq.current;
    setLoading(true);
    qcApi
      .dashboard(filters)
      .then((d) => {
        if (mine !== seq.current) return;
        setData(d);
        setError(null);
      })
      .catch((e: unknown) => {
        if (mine !== seq.current) return;
        // Not the previous filter's numbers under the new filter's header.
        setData(null);
        setError(e instanceof Error ? e.message : "Could not load the QC dashboard");
      })
      .finally(() => {
        if (mine === seq.current) setLoading(false);
      });
  }, [filters]);

  function update(next: Partial<QcDashboardFilters>) {
    const f = { ...filters, ...next };
    setFilters(f);
    // Keep the URL linkable without a server round trip.
    const q = new URLSearchParams();
    if (f.projectId != null) q.set("project", String(f.projectId));
    if (f.dateFrom) q.set("from", f.dateFrom);
    if (f.dateTo) q.set("to", f.dateTo);
    const qs = q.toString();
    window.history.replaceState(null, "", `/qc${qs ? `?${qs}` : ""}`);
  }

  const outside = data
    ? data.scope.open_defects_out_of_scope + data.scope.open_rework_out_of_scope
    : 0;
  const maxStage = data ? Math.max(1, ...data.defects_by_stage.map((s) => s.open)) : 1;

  return (
    <div className="grid gap-4" data-testid="qc-dashboard">
      <header className="flex flex-wrap items-baseline gap-3">
        <h1 className="text-xl font-medium text-h-ink">QC</h1>
        <span className="text-sm text-h-muted">
          Open defects and rework on cutlists that have started but not finished
        </span>
      </header>

      <div className="flex flex-wrap items-center gap-2 rounded-lg border border-h-line bg-h-surface px-3 py-2">
        <label className="flex items-center gap-2 text-sm text-h-muted">
          Project
          <select
            aria-label="Project"
            value={filters.projectId ?? ""}
            onChange={(e) => update({ projectId: e.target.value ? Number(e.target.value) : null })}
            className="rounded border border-h-line bg-h-bg px-2 py-1 text-sm text-h-ink"
          >
            <option value="">All projects</option>
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.project_code} — {p.name}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2 text-sm text-h-muted">
          Raised from
          <input
            type="date"
            aria-label="Raised from"
            value={filters.dateFrom}
            max={filters.dateTo || undefined}
            onChange={(e) => update({ dateFrom: e.target.value })}
            className="rounded border border-h-line bg-h-bg px-2 py-1 text-sm text-h-ink"
          />
        </label>
        <label className="flex items-center gap-2 text-sm text-h-muted">
          to
          <input
            type="date"
            aria-label="Raised to"
            value={filters.dateTo}
            min={filters.dateFrom || undefined}
            onChange={(e) => update({ dateTo: e.target.value })}
            className="rounded border border-h-line bg-h-bg px-2 py-1 text-sm text-h-ink"
          />
        </label>
        {(filters.projectId != null || filters.dateFrom || filters.dateTo) && (
          <button
            type="button"
            onClick={() => update({ projectId: null, dateFrom: "", dateTo: "" })}
            className="rounded border border-h-line px-2 py-1 text-sm text-h-muted hover:text-h-ink"
          >
            Clear
          </button>
        )}
        {loading && <span className="ml-auto text-xs text-h-muted">Loading…</span>}
      </div>

      {error && (
        <div role="alert" data-testid="qc-error" className="rounded-lg border border-red-500 bg-red-50 p-3 text-sm text-red-900">
          {error}
        </div>
      )}

      {data && (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Tile testId="tile-defects" label="Open defects" value={data.defects_open} />
            <Tile testId="tile-rework" label="Open rework" value={data.rework_open} />
            <Tile
              testId="tile-cost"
              label="Rework cost"
              value={cost(data.rework_cost_total, data.rework_cost_missing, data.rework_open)}
              note={
                data.rework_cost_missing > 0
                  ? `Excludes ${data.rework_cost_missing} open rework with no cost recorded`
                  : undefined
              }
            />
            <Tile testId="tile-items" label="Items in production" value={data.scope.items_in_scope} />
          </div>

          {outside > 0 && (
            <p
              data-testid="qc-outside-scope"
              className="rounded-lg border border-amber-500 bg-amber-50 px-3 py-2 text-sm text-amber-900"
            >
              Not counted above:{" "}
              {[
                [data.scope.open_defects_out_of_scope, "open defect"],
                [data.scope.open_rework_out_of_scope, "open rework"],
              ]
                .filter(([n]) => (n as number) > 0)
                .map(([n, what]) => `${n} ${what}${what === "open defect" && n !== 1 ? "s" : ""}`)
                .join(" and ")}{" "}
              on items whose cutlist has not started, has finished, or does not exist.
            </p>
          )}

          <div className="grid gap-4 lg:grid-cols-2">
            <Panel title="Open defects by stage" testId="panel-by-stage">
              {data.defects_by_stage.length === 0 ? (
                <Empty>No open defects.</Empty>
              ) : (
                <ul className="grid gap-2 px-4 py-3">
                  {data.defects_by_stage.map((s) => (
                    <li key={s.stage_key ?? "untagged"} className="grid grid-cols-[8rem_1fr_2rem] items-center gap-2 text-sm">
                      <span className="text-h-ink">{s.label}</span>
                      <span className="h-2 rounded bg-h-bg">
                        <span
                          className="block h-2 rounded bg-h-accent"
                          style={{ width: `${(s.open / maxStage) * 100}%` }}
                        />
                      </span>
                      <span className="text-right font-mono text-h-ink">{s.open}</span>
                    </li>
                  ))}
                </ul>
              )}
            </Panel>

            <Panel title="Open rework by project" testId="panel-rework">
              {data.rework_by_project.length === 0 ? (
                <Empty>No open rework.</Empty>
              ) : (
                <table className="w-full">
                  <thead>
                    <tr>
                      <th className={TH}>Project</th>
                      <th className={TH}>Internal</th>
                      <th className={TH}>Full</th>
                      <th className={TH}>Cost</th>
                      <th className={TH}>Oldest</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.rework_by_project.map((r) => (
                      <tr key={r.project_id} className="border-t border-h-line">
                        <td className={TD}>
                          <span className="font-mono">{r.project_code}</span>{" "}
                          <span className="text-h-muted">{r.project_name}</span>
                        </td>
                        <td className={TD}>{r.internal}</td>
                        <td className={TD}>{r.full}</td>
                        <td className={`${TD} font-mono`}>
                          {cost(r.cost_total, r.cost_missing, r.internal + r.full)}
                          {r.cost_missing > 0 && (
                            <span className="ml-1 text-xs text-h-muted">(+{r.cost_missing} unpriced)</span>
                          )}
                        </td>
                        <td className={TD}>{ageLabel(r.oldest_open_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </Panel>
          </div>

          <Panel title="Open defects by project" testId="panel-by-project">
            {data.defects_by_project.length === 0 ? (
              <Empty>No open defects.</Empty>
            ) : (
              <table className="w-full">
                <thead>
                  <tr>
                    <th className={TH}>Project</th>
                    <th className={TH}>Open</th>
                    <th className={TH}>By stage</th>
                    <th className={TH}>Oldest</th>
                  </tr>
                </thead>
                <tbody>
                  {data.defects_by_project.map((p) => (
                    <tr key={p.project_id} className="border-t border-h-line">
                      <td className={TD}>
                        <span className="font-mono">{p.project_code}</span>{" "}
                        <span className="text-h-muted">{p.project_name}</span>
                      </td>
                      <td className={TD}>{p.open}</td>
                      <td className={TD}>
                        <span className="flex flex-wrap gap-1">
                          {p.by_stage.map((s) => (
                            <span
                              key={s.stage_key ?? "untagged"}
                              className="rounded bg-h-bg px-2 py-0.5 text-xs text-h-ink"
                            >
                              {s.label} {s.open}
                            </span>
                          ))}
                        </span>
                      </td>
                      <td className={TD}>{ageLabel(p.oldest_open_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Panel>

          <Panel title="Items with open records (oldest first)" testId="panel-items">
            {data.items.length === 0 ? (
              <Empty>Nothing open on items in production.</Empty>
            ) : (
              <table className="w-full">
                <thead>
                  <tr>
                    <th className={TH}>Item</th>
                    <th className={TH}>Project</th>
                    <th className={TH}>Description</th>
                    <th className={TH}>Defects</th>
                    <th className={TH}>Rework</th>
                    <th className={TH}>Oldest</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((i) => (
                    <tr key={i.item_id} className="border-t border-h-line" data-testid={`item-row-${i.item_id}`}>
                      <td className={`${TD} font-mono`}>
                        <Link
                          href={`/items/${i.item_id}?tab=qc`}
                          className="text-h-accent hover:underline"
                        >
                          {i.num}
                        </Link>
                      </td>
                      <td className={`${TD} font-mono`}>{i.project_code}</td>
                      <td className={TD}>{i.description ?? "—"}</td>
                      <td className={TD}>{i.open_defects}</td>
                      <td className={TD}>{i.open_rework}</td>
                      <td className={TD}>{ageLabel(i.oldest_open_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Panel>
        </>
      )}
    </div>
  );
}
