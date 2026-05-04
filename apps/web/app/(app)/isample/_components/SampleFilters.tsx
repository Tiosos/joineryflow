"use client";

import { useState } from "react";

import type { SampleStatus } from "@/lib/samples-types";

interface Project {
  id: number;
  project_code: string;
  name: string;
}

interface Props {
  projects: Project[];
  selectedProjectId: number | null;
  selectedStatus: SampleStatus | null;
  selectedSupplier: string | null;
  searchValue: string;
  suppliers: string[];
  counts: { pending: number; approved: number; rejected: number };
  onProjectChange: (id: number) => void;
  onStatusChange: (status: SampleStatus | null) => void;
  onSupplierChange: (supplier: string | null) => void;
  onSearchChange: (q: string) => void;
}

export default function SampleFilters(p: Props) {
  const [search, setSearch] = useState(p.searchValue);

  const chip = (label: string, status: SampleStatus | null, count: number) => {
    const active = p.selectedStatus === status;
    return (
      <button
        type="button"
        key={label}
        onClick={() => p.onStatusChange(status)}
        className={`rounded border px-2.5 py-1 text-xs transition ${
          active
            ? "border-h-accent bg-h-accent/10 text-h-ink"
            : "border-h-line bg-h-surface text-h-muted hover:text-h-ink"
        }`}
      >
        {label} <span className="h-mono ml-1">{count}</span>
      </button>
    );
  };

  return (
    <div className="space-y-3 py-3">
      <div className="flex flex-wrap items-center gap-3">
        <input
          type="search"
          placeholder="Find sample…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          onBlur={() => p.onSearchChange(search)}
          onKeyDown={(e) => { if (e.key === "Enter") p.onSearchChange(search); }}
          className="rounded-md border border-h-line bg-h-surface px-2.5 py-1.5 text-sm text-h-ink placeholder:text-h-muted"
        />
        <select
          value={p.selectedProjectId ?? ""}
          onChange={(e) => p.onProjectChange(Number(e.target.value))}
          className="rounded-md border border-h-line bg-h-surface px-2.5 py-1.5 text-sm text-h-ink"
        >
          {p.projects.map((proj) => (
            <option key={proj.id} value={proj.id}>{proj.project_code} · {proj.name}</option>
          ))}
        </select>
        <select
          value={p.selectedSupplier ?? ""}
          onChange={(e) => p.onSupplierChange(e.target.value || null)}
          className="rounded-md border border-h-line bg-h-surface px-2.5 py-1.5 text-sm text-h-ink"
        >
          <option value="">All suppliers</option>
          {p.suppliers.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {chip("All", null, p.counts.pending + p.counts.approved + p.counts.rejected)}
        {chip("Awaiting client", "pending", p.counts.pending)}
        {chip("Approved", "approved", p.counts.approved)}
        {chip("Rejected", "rejected", p.counts.rejected)}
      </div>
    </div>
  );
}
