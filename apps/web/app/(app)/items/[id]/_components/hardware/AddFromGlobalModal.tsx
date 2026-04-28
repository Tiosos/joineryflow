"use client";
import { useState, useEffect } from "react";
import { PM } from "@/lib/pm-fetch";
import type { SourceTable } from "@/lib/pm-types";

interface AddFromGlobalModalProps {
  projectId: number;
  onClose: () => void;
  onAdded: () => void;
}

const SOURCE_TABLES: SourceTable[] = [
  "board_materials",
  "hardware_materials",
  "custom_made",
  "benchtop_materials",
  "appliances",
  "equipment_hire",
];

interface SourceRow {
  source_id: number;
  sku: string | null;
  description: string;
  supplier: string | null;
  unit_cost: number | null;
}

export function AddFromGlobalModal({
  projectId,
  onClose,
  onAdded,
}: AddFromGlobalModalProps) {
  const [activeTable, setActiveTable] = useState<SourceTable>("board_materials");
  const [rows, setRows] = useState<SourceRow[]>([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setRows([]);
    setError(null);
    PM.sourceCatalog("", activeTable)
      .then((data) => {
        if (!cancelled) {
          setRows(data.rows);
          setLoading(false);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setError("Failed to load catalog");
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [activeTable]);

  const filtered = search.trim()
    ? rows.filter(
        (r) =>
          r.description.toLowerCase().includes(search.toLowerCase()) ||
          (r.sku ?? "").toLowerCase().includes(search.toLowerCase()),
      )
    : rows;

  async function addRow(row: SourceRow) {
    setAdding(row.source_id);
    setError(null);
    try {
      await PM.addCatalog(projectId, {
        source_table: activeTable,
        source_id: row.source_id,
        qty: 1,
      });
      onAdded();
    } catch {
      setError("Failed to add to project catalog");
      setAdding(null);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="flex max-h-[80vh] w-[600px] flex-col rounded-xl border border-h-line bg-h-surface shadow-xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-h-line px-4 py-3">
          <h2 className="text-sm font-semibold text-h-ink">
            Add from global catalog
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="text-h-muted hover:text-h-ink"
          >
            ✕
          </button>
        </div>

        {/* Source table tabs */}
        <div className="flex overflow-x-auto border-b border-h-line">
          {SOURCE_TABLES.map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => {
                setActiveTable(t);
                setSearch("");
              }}
              className={[
                "shrink-0 whitespace-nowrap px-3 py-2 text-xs capitalize",
                activeTable === t
                  ? "border-b-2 border-h-accent font-medium text-h-ink"
                  : "text-h-muted hover:text-h-ink",
              ].join(" ")}
            >
              {t.replace(/_/g, " ")}
            </button>
          ))}
        </div>

        {/* Search */}
        <div className="border-b border-h-line px-4 py-2">
          <input
            type="search"
            placeholder="Search…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full rounded border border-h-line bg-h-bg px-2 py-1 text-sm text-h-ink focus:outline-none focus:ring-1 focus:ring-h-accent"
          />
        </div>

        {/* Rows */}
        <div className="flex-1 overflow-y-auto px-4 py-2">
          {error && <p className="mb-2 text-xs text-h-bad">{error}</p>}
          {loading && <p className="text-sm text-h-muted">Loading…</p>}
          {!loading &&
            filtered.map((row) => (
              <div
                key={row.source_id}
                className="flex items-center justify-between gap-2 rounded px-2 py-1.5 hover:bg-h-bg"
              >
                <div className="min-w-0">
                  <p className="truncate text-sm text-h-ink">
                    {row.description || "—"}
                  </p>
                  {row.sku && (
                    <p className="font-mono text-xs text-h-muted">{row.sku}</p>
                  )}
                  {row.unit_cost !== null && (
                    <p className="text-xs text-h-muted">
                      ${row.unit_cost.toFixed(2)}
                    </p>
                  )}
                </div>
                <button
                  type="button"
                  onClick={() => addRow(row)}
                  disabled={adding === row.source_id}
                  className="shrink-0 rounded border border-h-line px-3 py-1 text-sm text-h-muted hover:border-h-accent hover:text-h-ink disabled:opacity-50 transition-colors"
                >
                  Add
                </button>
              </div>
            ))}
          {!loading && filtered.length === 0 && (
            <p className="text-sm text-h-muted">No items found.</p>
          )}
        </div>
      </div>
    </div>
  );
}
