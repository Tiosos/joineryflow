"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { listCatalog } from "@/lib/catalog-fetch";
import {
  deleteBoardInventory,
  listBoardInventory,
  patchBoardInventory,
  upsertBoardInventory,
} from "@/lib/cut-floor-fetch";
import type { BoardInventoryRow } from "@/lib/cut-floor-types";

interface Props {
  canWrite: boolean;
}

/** Sheet stock on hand, per board material and sheet size (migration 0025).
 *
 * Stock is what the CutPlan optimiser sizes its nests against, so this is the
 * screen that decides whether an optimise run can pick a sheet automatically.
 */
export default function StockPanel({ canWrite }: Props) {
  const [rows, setRows] = useState<BoardInventoryRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [inStockOnly, setInStockOnly] = useState(false);
  const [tick, setTick] = useState(0);

  const reload = useCallback(() => setTick((n) => n + 1), []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    listBoardInventory({ inStockOnly })
      .then((r) => {
        if (!cancelled) setRows(r);
      })
      .catch((e) => {
        if (!cancelled) setError(String(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [inStockOnly, tick]);

  const totalSheets = useMemo(
    () => rows.reduce((n, r) => n + r.qty_on_hand, 0),
    [rows],
  );

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3">
        <label className="flex items-center gap-2 text-sm text-h-ink">
          <input
            type="checkbox"
            checked={inStockOnly}
            onChange={(e) => setInStockOnly(e.target.checked)}
          />
          In stock only
        </label>
        <span className="text-sm text-h-muted">
          {rows.length} size{rows.length === 1 ? "" : "s"} ·{" "}
          <span className="font-mono">{totalSheets}</span> sheet
          {totalSheets === 1 ? "" : "s"} on hand
        </span>
      </div>

      {canWrite && <AddStockForm onAdded={reload} />}

      {loading && <p className="text-sm text-h-muted">Loading…</p>}
      {error && <p className="text-sm text-rose-700">{error}</p>}

      {!loading && rows.length === 0 && (
        <p className="rounded border border-h-line bg-h-surface px-3 py-6 text-center text-sm text-h-muted">
          No sheet stock recorded. Add a size above so the optimiser can size
          nests automatically.
        </p>
      )}

      {rows.length > 0 && (
        <div className="overflow-x-auto rounded border border-h-line">
          <table className="min-w-full text-sm">
            <thead className="bg-h-surface text-h-muted">
              <tr className="text-left">
                <th className="px-3 py-2">SKU</th>
                <th className="px-3 py-2">Material</th>
                <th className="px-3 py-2">Sheet size (mm)</th>
                <th className="px-3 py-2">On hand</th>
                <th className="px-3 py-2">Location</th>
                <th className="px-3 py-2" />
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <StockRow
                  key={r.inventory_id}
                  row={r}
                  canWrite={canWrite}
                  onChanged={reload}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function StockRow({
  row,
  canWrite,
  onChanged,
}: {
  row: BoardInventoryRow;
  canWrite: boolean;
  onChanged: () => void;
}) {
  const [qty, setQty] = useState(String(row.qty_on_hand));
  const [location, setLocation] = useState(row.location ?? "");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setQty(String(row.qty_on_hand));
    setLocation(row.location ?? "");
  }, [row.qty_on_hand, row.location]);

  async function save(patch: { qty_on_hand?: number; location?: string | null }) {
    setBusy(true);
    try {
      await patchBoardInventory(row.inventory_id, patch);
      onChanged();
    } catch (e) {
      window.alert(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (
      !window.confirm(
        `Remove ${row.material_sku} ${row.len_mm}×${row.wid_mm} from stock?`,
      )
    ) {
      return;
    }
    setBusy(true);
    try {
      await deleteBoardInventory(row.inventory_id);
      onChanged();
    } catch (e) {
      window.alert(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <tr className="border-t border-h-line">
      <td className="px-3 py-1 font-mono">{row.material_sku ?? "—"}</td>
      <td className="px-3 py-1">
        {row.material_description ?? "—"}
        {row.grain_locked && (
          <span
            className="ml-2 rounded bg-h-surface-alt px-1.5 py-0.5 text-xs text-h-muted"
            title="Grain-locked: the optimiser never rotates parts on this board"
          >
            grain
          </span>
        )}
      </td>
      <td className="px-3 py-1 font-mono">
        {row.len_mm}×{row.wid_mm}
      </td>
      <td className="px-3 py-1 w-24">
        {canWrite ? (
          <input
            type="number"
            min={0}
            value={qty}
            disabled={busy}
            onChange={(e) => setQty(e.target.value)}
            onBlur={() => {
              const n = Number(qty);
              if (Number.isFinite(n) && n >= 0 && n !== row.qty_on_hand) {
                void save({ qty_on_hand: n });
              } else {
                setQty(String(row.qty_on_hand));
              }
            }}
            className="w-full bg-transparent px-1 py-0.5 font-mono text-sm focus:bg-h-surface focus:outline focus:outline-1 focus:outline-h-line"
          />
        ) : (
          <span className="font-mono">{row.qty_on_hand}</span>
        )}
      </td>
      <td className="px-3 py-1">
        {canWrite ? (
          <input
            value={location}
            disabled={busy}
            onChange={(e) => setLocation(e.target.value)}
            onBlur={() => {
              if (location !== (row.location ?? "")) {
                void save({ location: location || null });
              }
            }}
            className="w-full bg-transparent px-1 py-0.5 text-sm focus:bg-h-surface focus:outline focus:outline-1 focus:outline-h-line"
          />
        ) : (
          <span>{row.location || "—"}</span>
        )}
      </td>
      <td className="px-3 py-1">
        {canWrite && (
          <button
            onClick={remove}
            disabled={busy}
            className="text-xs text-rose-700 hover:underline disabled:opacity-50"
          >
            Remove
          </button>
        )}
      </td>
    </tr>
  );
}

function AddStockForm({ onAdded }: { onAdded: () => void }) {
  const [sku, setSku] = useState("");
  const [lenMm, setLenMm] = useState(2440);
  const [widMm, setWidMm] = useState(1220);
  const [qty, setQty] = useState(0);
  const [location, setLocation] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Board SKUs for the typeahead — stock is only ever held against a board.
  const [skus, setSkus] = useState<string[]>([]);
  useEffect(() => {
    listCatalog({ slug: "board-materials" })
      .then((r) => setSkus(r.rows.map((row) => row.sku).filter(Boolean)))
      .catch(() => {
        /* typeahead is a convenience; the field stays free-text */
      });
  }, []);

  async function submit() {
    if (!sku.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await upsertBoardInventory({
        material_sku: sku.trim(),
        len_mm: lenMm,
        wid_mm: widMm,
        qty_on_hand: qty,
        location: location || null,
      });
      setSku("");
      setQty(0);
      setLocation("");
      onAdded();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded border border-h-line bg-h-surface p-3">
      <div className="flex flex-wrap items-end gap-3">
        <div className="min-w-40 flex-1">
          <label className="block text-xs text-h-muted">Board SKU</label>
          <input
            value={sku}
            onChange={(e) => setSku(e.target.value)}
            list="stock-sku-options"
            autoComplete="off"
            placeholder="e.g. MEL-19-WH"
            className="w-full rounded border border-h-line bg-h-bg px-2 py-1 font-mono text-sm text-h-ink"
          />
          <datalist id="stock-sku-options">
            {skus.map((s) => (
              <option key={s} value={s} />
            ))}
          </datalist>
        </div>
        <div className="w-28">
          <label className="block text-xs text-h-muted">Length (mm)</label>
          <input
            type="number"
            min={1}
            value={lenMm}
            onChange={(e) => setLenMm(Number(e.target.value))}
            className="w-full rounded border border-h-line bg-h-bg px-2 py-1 text-sm text-h-ink"
          />
        </div>
        <div className="w-28">
          <label className="block text-xs text-h-muted">Width (mm)</label>
          <input
            type="number"
            min={1}
            value={widMm}
            onChange={(e) => setWidMm(Number(e.target.value))}
            className="w-full rounded border border-h-line bg-h-bg px-2 py-1 text-sm text-h-ink"
          />
        </div>
        <div className="w-24">
          <label className="block text-xs text-h-muted">Sheets</label>
          <input
            type="number"
            min={0}
            value={qty}
            onChange={(e) => setQty(Number(e.target.value))}
            className="w-full rounded border border-h-line bg-h-bg px-2 py-1 font-mono text-sm text-h-ink"
          />
        </div>
        <div className="w-32">
          <label className="block text-xs text-h-muted">Location</label>
          <input
            value={location}
            onChange={(e) => setLocation(e.target.value)}
            placeholder="Rack A1"
            className="w-full rounded border border-h-line bg-h-bg px-2 py-1 text-sm text-h-ink"
          />
        </div>
        <button
          type="button"
          onClick={submit}
          disabled={busy || !sku.trim()}
          className="rounded bg-h-accent px-3 py-1.5 text-sm text-white disabled:opacity-50"
        >
          {busy ? "Saving…" : "Set stock"}
        </button>
      </div>
      <p className="mt-2 text-xs text-h-muted">
        Recording the same SKU and sheet size again updates its quantity rather
        than adding a duplicate row.
      </p>
      {error && <p className="mt-2 text-sm text-rose-700">{error}</p>}
    </div>
  );
}
