"use client";

import { useEffect, useMemo, useState } from "react";

import { isOverdue, type DrawingCard } from "@/lib/shop-drawings-types";

import QueueChip from "./QueueChip";

interface Props {
  drawings: DrawingCard[];
  selectedId: number | null;
  onSelect: (id: number) => void;
  onView: (id: number) => void;
}

type SortKey =
  | "drawing_no" | "title" | "latest_rev_no" | "type" | "level"
  | "joinery_id" | "assigned_to_name" | "queue" | "due_date" | "submitted_at";

const PAGE_SIZE = 25;
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** '2026-09-25' -> '25 Sep 2026', without going through Date (no time-zone drift). */
export function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  const [y, m, d] = iso.split("-").map(Number);
  return `${d} ${MONTHS[m - 1]} ${y}`;
}

export function initials(name: string | null): string {
  if (!name) return "?";
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]!.toUpperCase()).join("");
}

const COLUMNS: { key: SortKey; label: string; className?: string }[] = [
  { key: "drawing_no", label: "Item #" },
  { key: "title", label: "Description" },
  { key: "latest_rev_no", label: "Rev" },
  { key: "type", label: "Type" },
  { key: "level", label: "Level" },
  { key: "joinery_id", label: "Joinery ID" },
  { key: "assigned_to_name", label: "Assigned" },
  { key: "queue", label: "Status" },
  { key: "due_date", label: "Due date" },
  { key: "submitted_at", label: "Submitted" },
];

function cmp(a: unknown, b: unknown): number {
  // Empty values sort last in either direction (handled by the caller's flip).
  if (a == null || a === "") return b == null || b === "" ? 0 : 1;
  if (b == null || b === "") return -1;
  if (typeof a === "number" && typeof b === "number") return a - b;
  return String(a).localeCompare(String(b), undefined, { numeric: true, sensitivity: "base" });
}

export default function RegisterTable({ drawings, selectedId, onSelect, onView }: Props) {
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: "drawing_no", dir: 1 });
  const [page, setPage] = useState(0);

  const rows = useMemo(() => {
    const out = [...drawings];
    out.sort((x, y) => {
      const a = x[sort.key], b = y[sort.key];
      const blank = (v: unknown) => v == null || v === "";
      if (blank(a) || blank(b)) return cmp(a, b); // blanks last regardless of direction
      return cmp(a, b) * sort.dir;
    });
    return out;
  }, [drawings, sort]);

  const pages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
  // A filter that shrinks the list must not strand us on a page that no longer exists.
  useEffect(() => { if (page > pages - 1) setPage(pages - 1); }, [page, pages]);
  const shown = rows.slice(page * PAGE_SIZE, page * PAGE_SIZE + PAGE_SIZE);

  const toggle = (key: SortKey) =>
    setSort((s) => (s.key === key ? { key, dir: s.dir === 1 ? -1 : 1 } : { key, dir: 1 }));

  if (drawings.length === 0) {
    return <p className="py-12 text-center text-sm text-h-muted">No drawings here yet.</p>;
  }

  return (
    <div className="min-w-0 flex-1">
      <div className="overflow-x-auto rounded border border-h-line bg-h-surface">
        <table data-testid="register-table" className="w-full min-w-[980px] border-collapse text-sm">
          <thead>
            <tr className="border-b border-h-line bg-h-surface-alt text-left text-[11px] font-semibold uppercase tracking-wide text-h-ink2">
              <Th col={COLUMNS[0]!} sort={sort} onSort={toggle} />
              <th className="px-3 py-2 font-semibold">View</th>
              {COLUMNS.slice(1).map((c) => <Th key={c.key} col={c} sort={sort} onSort={toggle} />)}
            </tr>
          </thead>
          <tbody>
            {shown.map((d) => {
              const overdue = isOverdue(d);
              const selected = d.drawing_id === selectedId;
              return (
                <tr
                  key={d.drawing_id}
                  data-testid="register-row"
                  aria-selected={selected}
                  onClick={() => onSelect(d.drawing_id)}
                  className={`cursor-pointer border-b border-h-line last:border-0 hover:bg-h-surface-alt ${
                    selected ? "bg-h-accent-soft/60" : ""
                  }`}
                >
                  <td className="whitespace-nowrap px-3 py-2">
                    <span className="h-mono text-[13px] text-h-ink">
                      {d.drawing_no ?? `#SD-${String(d.drawing_id).padStart(4, "0")}`}
                    </span>
                    {d.comment_count > 0 && (
                      <span
                        title={`${d.comment_count} comment${d.comment_count === 1 ? "" : "s"}`}
                        className="ml-1.5 inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-h-accent px-1 text-[10px] text-white"
                      >
                        {d.comment_count}
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2">
                    <button
                      type="button"
                      data-testid="view-drawing"
                      onClick={(e) => { e.stopPropagation(); onView(d.drawing_id); }}
                      className="rounded border border-h-accent bg-h-accent px-2.5 py-1 text-xs font-medium text-white hover:opacity-90"
                    >
                      View
                    </button>
                  </td>
                  <td className="max-w-[260px] px-3 py-2 text-h-ink">
                    <span className="block truncate" title={d.title}>{d.title}</span>
                    {d.room && <span className="block truncate text-xs text-h-muted">{d.room}</span>}
                  </td>
                  <td className="h-mono px-3 py-2 text-h-ink2">v{d.latest_rev_no}</td>
                  <td className="px-3 py-2">
                    <span className="rounded border border-h-info/40 bg-h-info/10 px-1.5 py-0.5 text-[11px] font-medium text-h-info">
                      {d.type}
                    </span>
                  </td>
                  <td className="whitespace-nowrap px-3 py-2 text-h-ink2">{d.level ?? "—"}</td>
                  <td className="h-mono whitespace-nowrap px-3 py-2 text-h-ink2">{d.joinery_id ?? "—"}</td>
                  <td className="whitespace-nowrap px-3 py-2">
                    {d.assigned_to_name ? (
                      <span className="inline-flex items-center gap-1.5">
                        <span className="inline-flex h-6 w-6 items-center justify-center rounded-full bg-h-accent-soft text-[10px] font-semibold text-h-accent">
                          {initials(d.assigned_to_name)}
                        </span>
                        <span className="text-h-ink">{d.assigned_to_name}</span>
                      </span>
                    ) : (
                      <span className="text-h-muted">Unassigned</span>
                    )}
                  </td>
                  <td className="px-3 py-2"><QueueChip queue={d.queue} /></td>
                  <td className="whitespace-nowrap px-3 py-2">
                    <span className={overdue ? "font-medium text-h-bad" : "text-h-ink2"}>{fmtDate(d.due_date)}</span>
                    {overdue && (
                      <span data-testid="overdue" className="ml-1.5 rounded bg-h-bad/15 px-1 text-[10px] font-semibold uppercase text-h-bad">
                        Overdue
                      </span>
                    )}
                  </td>
                  <td className="whitespace-nowrap px-3 py-2 text-h-ink2">{fmtDate(d.submitted_at)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between py-2 text-xs text-h-muted">
        <span>{rows.length} drawing{rows.length === 1 ? "" : "s"}</span>
        {pages > 1 && (
          <span className="flex items-center gap-2">
            <button type="button" disabled={page === 0} onClick={() => setPage(page - 1)}
                    className="rounded border border-h-line bg-h-surface px-2 py-0.5 disabled:opacity-40">‹</button>
            <span>Page {page + 1} of {pages}</span>
            <button type="button" disabled={page >= pages - 1} onClick={() => setPage(page + 1)}
                    className="rounded border border-h-line bg-h-surface px-2 py-0.5 disabled:opacity-40">›</button>
          </span>
        )}
      </div>
    </div>
  );
}

function Th({ col, sort, onSort }: {
  col: { key: SortKey; label: string };
  sort: { key: SortKey; dir: 1 | -1 };
  onSort: (k: SortKey) => void;
}) {
  const active = sort.key === col.key;
  return (
    <th
      className="px-3 py-2 font-semibold"
      aria-sort={active ? (sort.dir === 1 ? "ascending" : "descending") : "none"}
    >
      <button type="button" onClick={() => onSort(col.key)} className="inline-flex items-center gap-1 uppercase hover:text-h-ink">
        {col.label}
        <span aria-hidden className={active ? "text-h-ink" : "text-h-ink4"}>{active ? (sort.dir === 1 ? "↑" : "↓") : "↕"}</span>
      </button>
    </th>
  );
}
