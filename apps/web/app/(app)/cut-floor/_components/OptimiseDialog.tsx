"use client";

import { useEffect, useMemo, useState } from "react";

import { listCatalog } from "@/lib/catalog-fetch";
import {
  createCutPlan,
  listBoardInventory,
  optimiseProject,
} from "@/lib/cut-floor-fetch";
import type {
  BoardInventoryRow,
  OptimiseOut,
  OptimiseStrategy,
} from "@/lib/cut-floor-types";
import { PM } from "@/lib/pm-fetch";
import { SheetCanvas } from "./SheetCanvas";

interface Project {
  id: number;
  project_code: string;
  name: string;
}

/** Board material the SKU field can suggest, from the catalog. */
interface SkuOption {
  sku: string;
  description: string;
}

/** One selectable item in the project. */
interface ItemOption {
  id: number;
  label: string;
}

interface OptimiseDialogProps {
  projects: Project[];
  defaultProjectId: number | null;
  onClose: () => void;
  onSaved: () => void | Promise<void>;
}

export function OptimiseDialog({
  projects,
  defaultProjectId,
  onClose,
  onSaved,
}: OptimiseDialogProps) {
  const [projectId, setProjectId] = useState<number | null>(
    defaultProjectId ?? projects[0]?.id ?? null,
  );
  const [name, setName] = useState("Optimised nest");
  const [materialSku, setMaterialSku] = useState("18-PB");
  const [sheetLen, setSheetLen] = useState(2440);
  const [sheetWid, setSheetWid] = useState(1220);
  const [kerf, setKerf] = useState(3);
  const [strategy, setStrategy] = useState<OptimiseStrategy>("maxrects");
  // Default to stock-driven sizing; the manual fields are the escape hatch for
  // ad-hoc sheets the catalog doesn't know about.
  const [useStockSize, setUseStockSize] = useState(true);

  // Stock rows for the SKU currently typed, so the dialog can show what's on
  // hand before the user commits to a run.
  const [stock, setStock] = useState<BoardInventoryRow[]>([]);
  useEffect(() => {
    const sku = materialSku.trim();
    if (!sku) {
      setStock([]);
      return;
    }
    let cancelled = false;
    // Small debounce — the SKU field is free-text and fires per keystroke.
    const t = setTimeout(() => {
      listBoardInventory({ materialSku: sku })
        .then((rows) => {
          if (!cancelled) setStock(rows);
        })
        .catch(() => {
          if (!cancelled) setStock([]);
        });
    }, 250);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [materialSku]);

  const inStock = useMemo(
    () => stock.filter((r) => r.qty_on_hand > 0),
    [stock],
  );
  // Mirrors the server's choice: largest in-stock sheet by area.
  const bestStock = useMemo(
    () =>
      inStock
        .slice()
        .sort(
          (a, b) =>
            b.len_mm * b.wid_mm - a.len_mm * a.wid_mm ||
            b.qty_on_hand - a.qty_on_hand,
        )[0] ?? null,
    [inStock],
  );

  const [result, setResult] = useState<OptimiseOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Board-material SKUs for the datalist. Catalog-wide (not project-scoped),
  // fetched once — the field stays free-text so an unlisted SKU still works.
  const [skus, setSkus] = useState<SkuOption[]>([]);
  useEffect(() => {
    let cancelled = false;
    listCatalog({ slug: "board-materials" })
      .then((r) => {
        if (cancelled) return;
        setSkus(
          r.rows
            .filter((row) => row.sku)
            .map((row) => ({ sku: row.sku, description: row.description })),
        );
      })
      .catch(() => {
        /* typeahead is a convenience — a failure must not block optimising */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Items in the selected project. All are included by default; unchecking
  // narrows the run via include_only_item_ids.
  const [items, setItems] = useState<ItemOption[]>([]);
  const [excludedIds, setExcludedIds] = useState<Set<number>>(new Set());
  const [itemsLoading, setItemsLoading] = useState(false);

  useEffect(() => {
    if (projectId === null) {
      setItems([]);
      setExcludedIds(new Set());
      return;
    }
    let cancelled = false;
    setItemsLoading(true);
    PM.trackingGrid("", projectId)
      .then((grid) => {
        if (cancelled) return;
        setItems(
          grid.items.map((it) => ({
            id: it.id,
            label:
              [it.code, it.description].filter(Boolean).join(" · ") ||
              `Item ${it.item_number ?? it.id}`,
          })),
        );
        setExcludedIds(new Set()); // switching project resets the selection
      })
      .catch(() => {
        if (!cancelled) setItems([]);
      })
      .finally(() => {
        if (!cancelled) setItemsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  const includedIds = useMemo(
    () => items.filter((it) => !excludedIds.has(it.id)).map((it) => it.id),
    [items, excludedIds],
  );
  const allIncluded = excludedIds.size === 0;
  const noneSelected = items.length > 0 && includedIds.length === 0;

  function toggleItem(id: number) {
    setExcludedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function runOptimise() {
    if (projectId === null) return;
    setBusy(true);
    setError(null);
    try {
      const out = await optimiseProject(projectId, {
        name,
        material_sku: materialSku,
        // Omitting the dims tells the server to size from stock.
        sheet_len_mm: useStockSize ? null : sheetLen,
        sheet_wid_mm: useStockSize ? null : sheetWid,
        kerf_mm: kerf,
        strategy,
        // Omit when everything is selected so the API keeps its "all parts"
        // default rather than receiving a redundant list.
        include_only_item_ids: allIncluded ? null : includedIds,
      });
      setResult(out);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function saveAsPlan() {
    if (projectId === null || result === null) return;
    setBusy(true);
    setError(null);
    try {
      await createCutPlan(projectId, result.proposal);
      await onSaved();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-label="Optimise cut plan"
        className="max-h-[90vh] w-full max-w-3xl overflow-y-auto rounded-lg border border-h-line bg-h-bg p-4"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="mb-3 text-lg font-medium text-h-ink">
          Optimise nest
          <span className="ml-2 font-mono text-xs uppercase text-h-muted">
            stub
          </span>
        </h2>

        {result === null ? (
          <div className="grid gap-3">
            <div>
              <label className="block text-sm text-h-muted">Project</label>
              <select
                value={projectId ?? ""}
                onChange={(e) =>
                  setProjectId(e.target.value ? Number(e.target.value) : null)
                }
                className="w-full rounded border border-h-line bg-h-surface px-2 py-1 text-sm text-h-ink"
              >
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.project_code} — {p.name}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-sm text-h-muted">Plan name</label>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="w-full rounded border border-h-line bg-h-surface px-2 py-1 text-sm text-h-ink"
              />
            </div>

            <div>
              <label className="block text-sm text-h-muted">
                Material SKU
              </label>
              <input
                value={materialSku}
                onChange={(e) => setMaterialSku(e.target.value)}
                list="optimise-sku-options"
                autoComplete="off"
                className="w-full rounded border border-h-line bg-h-surface px-2 py-1 font-mono text-sm text-h-ink"
              />
              <datalist id="optimise-sku-options">
                {skus.map((s) => (
                  <option key={s.sku} value={s.sku}>
                    {s.description}
                  </option>
                ))}
              </datalist>
              <p className="mt-1 text-xs text-h-muted">
                {bestStock ? (
                  <>
                    In stock:{" "}
                    {inStock.map((r, i) => (
                      <span key={r.inventory_id}>
                        {i > 0 && " · "}
                        <span className="font-mono">
                          {r.qty_on_hand}× {r.len_mm}×{r.wid_mm}
                        </span>
                        {r.location ? ` (${r.location})` : ""}
                      </span>
                    ))}
                  </>
                ) : stock.length > 0 ? (
                  "Recorded, but none on hand at any size."
                ) : (
                  "No sheet stock recorded for this SKU."
                )}
              </p>
            </div>

            <label className="flex items-center gap-2 text-sm text-h-ink">
              <input
                type="checkbox"
                checked={useStockSize}
                onChange={(e) => setUseStockSize(e.target.checked)}
              />
              Use sheet size from stock
              {bestStock && useStockSize && (
                <span className="font-mono text-xs text-h-muted">
                  ({bestStock.len_mm}×{bestStock.wid_mm})
                </span>
              )}
            </label>

            <div className="grid grid-cols-3 gap-3">
              <div className={useStockSize ? "opacity-50" : ""}>
                <label className="block text-sm text-h-muted">
                  Sheet length (mm)
                </label>
                <input
                  type="number"
                  min={1}
                  value={sheetLen}
                  disabled={useStockSize}
                  onChange={(e) => setSheetLen(Number(e.target.value))}
                  className="w-full rounded border border-h-line bg-h-surface px-2 py-1 text-sm text-h-ink disabled:cursor-not-allowed"
                />
              </div>
              <div className={useStockSize ? "opacity-50" : ""}>
                <label className="block text-sm text-h-muted">
                  Sheet width (mm)
                </label>
                <input
                  type="number"
                  min={1}
                  value={sheetWid}
                  disabled={useStockSize}
                  onChange={(e) => setSheetWid(Number(e.target.value))}
                  className="w-full rounded border border-h-line bg-h-surface px-2 py-1 text-sm text-h-ink disabled:cursor-not-allowed"
                />
              </div>
              <div>
                {/* Kerf is a saw property, not a stock property — always editable. */}
                <label className="block text-sm text-h-muted">Kerf (mm)</label>
                <input
                  type="number"
                  min={0}
                  value={kerf}
                  onChange={(e) => setKerf(Number(e.target.value))}
                  className="w-full rounded border border-h-line bg-h-surface px-2 py-1 text-sm text-h-ink"
                />
              </div>
            </div>

            <div>
              <label className="block text-sm text-h-muted">Algorithm</label>
              <select
                value={strategy}
                onChange={(e) => setStrategy(e.target.value as OptimiseStrategy)}
                className="w-full rounded border border-h-line bg-h-surface px-2 py-1 text-sm text-h-ink"
              >
                <option value="maxrects">MaxRects (best yield)</option>
                <option value="naive">Naive shelf (baseline)</option>
              </select>
            </div>

            <div>
              <div className="flex items-baseline justify-between">
                <label className="block text-sm text-h-muted">
                  Items to include
                </label>
                {items.length > 0 && (
                  <button
                    type="button"
                    onClick={() =>
                      setExcludedIds(
                        allIncluded ? new Set(items.map((it) => it.id)) : new Set(),
                      )
                    }
                    className="text-xs text-h-accent hover:underline"
                  >
                    {allIncluded ? "Clear all" : "Select all"}
                  </button>
                )}
              </div>
              {itemsLoading ? (
                <div className="rounded border border-h-line bg-h-surface px-2 py-2 text-xs text-h-muted">
                  Loading items…
                </div>
              ) : items.length === 0 ? (
                <div className="rounded border border-h-line bg-h-surface px-2 py-2 text-xs text-h-muted">
                  No items in this project.
                </div>
              ) : (
                <div className="max-h-40 overflow-y-auto rounded border border-h-line bg-h-surface">
                  {items.map((it) => (
                    <label
                      key={it.id}
                      className="flex cursor-pointer items-center gap-2 px-2 py-1 text-sm text-h-ink hover:bg-h-bg"
                    >
                      <input
                        type="checkbox"
                        checked={!excludedIds.has(it.id)}
                        onChange={() => toggleItem(it.id)}
                      />
                      <span className="truncate">{it.label}</span>
                    </label>
                  ))}
                </div>
              )}
              <p className="mt-1 text-xs text-h-muted">
                {allIncluded
                  ? "All items included."
                  : `${includedIds.length} of ${items.length} items included.`}
              </p>
            </div>

            <p className="text-xs text-h-muted">
              Nests the selected items&apos; parts across as many sheets as
              needed; parts larger than the sheet are skipped. Preview the
              result before saving it as a cut plan.
            </p>

            {error && (
              <div className="rounded border border-red-500 bg-red-50 p-2 text-xs text-red-900">
                {error}
              </div>
            )}

            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={onClose}
                className="rounded border border-h-line px-3 py-1 text-sm text-h-ink hover:bg-h-surface"
              >
                Cancel
              </button>
              <button
                type="button"
                // Block the empty selection: an empty include_only_item_ids is
                // treated as "no filter" server-side, which would silently pack
                // everything — the opposite of what unchecking all means.
                disabled={busy || projectId === null || noneSelected}
                onClick={runOptimise}
                title={noneSelected ? "Select at least one item" : undefined}
                className="rounded border border-h-accent bg-h-accent px-3 py-1 text-sm text-h-bg disabled:opacity-50"
              >
                {busy ? "Optimising…" : "Optimise"}
              </button>
            </div>
          </div>
        ) : (
          <div className="grid gap-3">
            <div className="flex flex-wrap gap-4 rounded-lg border border-h-line bg-h-surface px-3 py-2 text-sm">
              <span className="text-h-ink">
                <span className="font-medium">{result.summary.placed}</span>
                <span className="text-h-muted"> placed</span>
              </span>
              <span className="text-h-ink">
                <span className="font-medium">{result.summary.skipped}</span>
                <span className="text-h-muted"> skipped</span>
              </span>
              <span className="text-h-ink">
                <span className="font-medium">
                  {Math.round(result.summary.utilization_pct * 100)}%
                </span>
                <span className="text-h-muted"> utilisation</span>
              </span>
              <span className="text-h-muted">
                {result.summary.total_parts} parts ·{" "}
                {result.summary.sheets_used} sheet
                {result.summary.sheets_used === 1 ? "" : "s"}
                {result.summary.sheet_len_mm != null && (
                  <>
                    {" · "}
                    <span className="font-mono">
                      {Math.round(result.summary.sheet_len_mm)}×
                      {Math.round(result.summary.sheet_wid_mm ?? 0)}
                    </span>
                    {result.summary.sheet_dims_from_stock && " from stock"}
                  </>
                )}
              </span>
            </div>

            {result.summary.sheet_shortfall > 0 && (
              <div className="rounded-lg border border-h-warn bg-h-surface px-3 py-2 text-sm text-h-ink">
                <span className="font-medium">
                  Short {result.summary.sheet_shortfall} sheet
                  {result.summary.sheet_shortfall === 1 ? "" : "s"}.
                </span>{" "}
                <span className="text-h-muted">
                  This nest needs {result.summary.sheets_used} but only{" "}
                  {result.summary.sheets_available} on hand. You can still save
                  the plan — order or re-stock before cutting.
                </span>
              </div>
            )}

            {result.summary.skipped > 0 && (
              <details className="rounded-lg border border-h-line bg-h-surface px-3 py-2 text-sm">
                <summary className="cursor-pointer text-h-muted">
                  {result.summary.skipped} part
                  {result.summary.skipped === 1 ? "" : "s"} skipped
                </summary>
                <ul className="mt-2 flex flex-col gap-1 text-xs text-h-ink">
                  {result.summary.skipped_reasons.map((s, i) => (
                    <li key={i}>
                      <span className="font-mono">{s.label}</span>
                      <span className="text-h-muted"> — {s.reason}</span>
                    </li>
                  ))}
                </ul>
              </details>
            )}

            <div className="flex flex-col gap-3">
              {result.proposal.sheets.map((sheet) => (
                <SheetCanvas
                  key={sheet.sheet_no}
                  sheetNo={sheet.sheet_no}
                  materialSku={sheet.material_sku}
                  slots={sheet.slots.map((s) => ({
                    x: s.x,
                    y: s.y,
                    w: s.w,
                    h: s.h,
                    label: s.label ?? null,
                  }))}
                  extent={{ width: sheetLen, height: sheetWid }}
                />
              ))}
            </div>

            {error && (
              <div className="rounded border border-red-500 bg-red-50 p-2 text-xs text-red-900">
                {error}
              </div>
            )}

            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setResult(null)}
                className="rounded border border-h-line px-3 py-1 text-sm text-h-ink hover:bg-h-surface"
              >
                ← Back
              </button>
              <button
                type="button"
                onClick={onClose}
                className="rounded border border-h-line px-3 py-1 text-sm text-h-muted hover:text-h-ink"
              >
                Discard
              </button>
              <button
                type="button"
                disabled={busy || result.summary.placed === 0}
                onClick={saveAsPlan}
                className="rounded border border-h-accent bg-h-accent px-3 py-1 text-sm text-h-bg disabled:opacity-50"
              >
                {busy ? "Saving…" : "Save as plan"}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
