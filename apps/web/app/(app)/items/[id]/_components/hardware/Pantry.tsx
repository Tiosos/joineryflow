"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { PM } from "@/lib/pm-fetch";
import type { HardwareCatalogOut, HardwareCatalogRow, ItemOut } from "@/lib/pm-types";

interface PantryProps {
  item: ItemOut;
  catalog: HardwareCatalogOut | null;
  onOpenModal: () => void;
  onRefresh: () => void;
}

function groupBySourceTable(
  rows: HardwareCatalogRow[],
): Record<string, HardwareCatalogRow[]> {
  return rows.reduce<Record<string, HardwareCatalogRow[]>>((acc, row) => {
    const key = row.source_table ?? "other";
    return { ...acc, [key]: [...(acc[key] ?? []), row] };
  }, {});
}

export function Pantry({ item, catalog, onOpenModal, onRefresh }: PantryProps) {
  const router = useRouter();
  const [search, setSearch] = useState("");
  const [adding, setAdding] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const catalogRows = catalog?.rows ?? [];
  const filtered = search.trim()
    ? catalogRows.filter(
        (r) =>
          r.name.toLowerCase().includes(search.toLowerCase()) ||
          (r.supplier ?? "").toLowerCase().includes(search.toLowerCase()),
      )
    : catalogRows;

  const grouped = groupBySourceTable(filtered);

  async function addToCart(catalogId: number) {
    setAdding(catalogId);
    setError(null);
    try {
      await PM.createHardwareLine(item.id, { catalog_id: catalogId, qty: 1 });
      router.refresh();
      onRefresh();
    } catch {
      setError("Failed to add hardware line");
    } finally {
      setAdding(null);
    }
  }

  return (
    <aside className="w-[360px] shrink-0 flex flex-col gap-3 rounded-lg border border-h-line bg-h-surface p-3">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-h-muted">
        Project Hardware
      </h3>
      <input
        type="search"
        placeholder="Search catalog…"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        className="rounded border border-h-line bg-h-bg px-2 py-1 text-sm text-h-ink focus:outline-none focus:ring-1 focus:ring-h-accent"
      />
      {error && <p className="text-xs text-h-bad">{error}</p>}

      <div className="flex-1 space-y-4 overflow-y-auto max-h-[480px]">
        {Object.entries(grouped).map(([table, rows]) => (
          <div key={table}>
            <p className="mb-1 text-xs font-medium uppercase tracking-wide text-h-muted">
              {table.replace(/_/g, " ")}
            </p>
            {rows.map((r) => (
              <div
                key={r.catalog_id}
                data-testid="pantry-row"
                className="flex items-center justify-between gap-2 rounded px-2 py-1.5 hover:bg-h-bg"
              >
                <div className="min-w-0">
                  <p className="truncate text-sm text-h-ink">{r.name || "—"}</p>
                  {r.supplier && (
                    <p className="truncate text-xs text-h-muted">{r.supplier}</p>
                  )}
                </div>
                <button
                  type="button"
                  aria-label="Add"
                  onClick={() => addToCart(r.catalog_id)}
                  disabled={adding === r.catalog_id}
                  className="shrink-0 rounded border border-h-line px-2 py-0.5 text-sm text-h-muted hover:border-h-accent hover:text-h-ink disabled:opacity-50 transition-colors"
                >
                  +
                </button>
              </div>
            ))}
          </div>
        ))}
        {filtered.length === 0 && (
          <p className="text-sm text-h-muted">No catalog items.</p>
        )}
      </div>

      <button
        type="button"
        onClick={onOpenModal}
        className="rounded border border-dashed border-h-line px-3 py-2 text-sm text-h-muted hover:border-h-accent hover:text-h-ink transition-colors"
      >
        + Add from global
      </button>
    </aside>
  );
}
