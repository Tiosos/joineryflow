"use client";

import { useEffect, useState } from "react";

interface Props {
  searchValue: string;
  selectedSupplier: string | null;
  archived: boolean;
  suppliers: string[];
  onSearchChange: (s: string) => void;
  onSupplierChange: (s: string | null) => void;
  onArchivedChange: (a: boolean) => void;
}

export default function CatalogFilters(p: Props) {
  const [search, setSearch] = useState(p.searchValue);

  useEffect(() => {
    setSearch(p.searchValue);
  }, [p.searchValue]);

  useEffect(() => {
    if (search === p.searchValue) return;
    const t = setTimeout(() => p.onSearchChange(search), 200);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

  return (
    <div className="flex flex-wrap items-center gap-3">
      <input
        type="search"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder="Search description or SKU…"
        className="rounded border border-h-line px-2 py-1 text-sm"
      />
      <select
        value={p.selectedSupplier ?? ""}
        onChange={(e) => p.onSupplierChange(e.target.value || null)}
        className="rounded border border-h-line px-2 py-1 text-sm"
      >
        <option value="">All suppliers</option>
        {p.suppliers.map((s) => <option key={s} value={s}>{s}</option>)}
      </select>
      <label className="flex items-center gap-1 text-sm text-h-muted">
        <input
          type="checkbox"
          checked={p.archived}
          onChange={(e) => p.onArchivedChange(e.target.checked)}
        />
        Show archived
      </label>
    </div>
  );
}
