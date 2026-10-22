"use client";

import Link from "next/link";
import { Fragment, useCallback, useEffect, useState } from "react";

import { ApiError, errorText, summaryApi } from "@/lib/material-take-fetch";
import { UNIT_LABEL, type CurrentSummary, type SummaryLine } from "@/lib/material-take-types";

// Project Material Summary (sub-project #12, Plan V1 §20). Confirmation is
// advisory (Q499): Procurement may act on an unconfirmed summary.
// The Catalog tab a material type lives on (its rows are found there by description).
const CATALOG_TAB: Record<string, string> = {
  BOARD: "board", HARDWARE: "hardware", CUSTOM: "custom_made", BENCHTOP: "benchtop", APPLIANCE: "appliance",
  HIRE: "hire", EDGING: "edging", GLASS: "glass", TIMBER: "timber",
};

const WHY_NOT: Record<string, string> = {
  NO_SKU: "No SKU on this material.",
  NO_SUPPLIER: "No default supplier.",
  NOTHING_TO_ORDER: "Already on an order.",
  NO_CATALOG_MATERIAL: "Not a catalog material.",
};

const ORDER_REFUSED: Record<string, string> = {
  NO_SUPPLIER: "This material has no default supplier. Set one in the Catalog first.",
  NO_SKU: "This material has no SKU, so orders cannot be matched to it. Add one in the Catalog first.",
  NOTHING_TO_ORDER: "Everything this line needs is already on an order.",
  NO_CATALOG_MATERIAL: "This line is not a catalog material, so it cannot be ordered from here.",
  SUMMARY_SUPERSEDED: "A newer summary has been built. Reload to order from it.",
};

export function MaterialSummaryPanel({ projectId, canEdit, canConfirm, canOrder }: {
  projectId: number;
  canEdit: boolean;
  canConfirm: boolean;
  canOrder: boolean;
}) {
  const [data, setData] = useState<CurrentSummary | null>(null);
  const [open, setOpen] = useState<Set<number>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [raised, setRaised] = useState<{ po_id: number; po_number: string } | null>(null);

  const load = useCallback(async () => {
    try {
      setData(await summaryApi.current(projectId));
      setError(null);
    } catch (e) {
      setError(errorText(e));
    }
  }, [projectId]);

  useEffect(() => {
    load();
  }, [load]);

  async function act(fn: () => Promise<unknown>) {
    setBusy(true);
    try {
      await fn();
      await load();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  async function orderLine(summaryId: number, lineId: number) {
    setBusy(true);
    setRaised(null);
    try {
      setRaised(await summaryApi.orderLine(summaryId, lineId));
      await load();
    } catch (e) {
      const code = e instanceof ApiError ? (e.detail as { code?: string } | undefined)?.code : undefined;
      setError((code && ORDER_REFUSED[code]) || errorText(e));
    } finally {
      setBusy(false);
    }
  }

  if (!data) return <p className="text-sm text-h-muted">{error ?? "Loading…"}</p>;
  const s = data.summary;
  const draft = s?.status === "draft";
  const staleCount = s?.lines.filter((l) => l.stale).length ?? 0;
  const noSku = s?.lines.filter((l) => l.order_block === "NO_SKU").length ?? 0;
  const noSupplier = s?.lines.filter((l) => l.order_block === "NO_SUPPLIER").length ?? 0;

  return (
    <div className="grid gap-4">
      {error && <div className="rounded bg-red-50 px-3 py-2 text-sm text-red-800">{error}</div>}
      {raised && (
        <p data-testid="summary-order-raised" className="rounded border border-h-line bg-h-surface px-3 py-2 text-sm text-h-ink">
          {`Order ${raised.po_number} raised (Pending). `}
          <Link href={`/orderbook?order=${raised.po_id}`} className="text-h-accent">Open it</Link>
        </p>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-lg font-semibold text-h-ink">Material Summary</h2>
        {s && (
          <span className="rounded border border-h-line px-2 py-0.5 text-xs text-h-muted">
            #{s.summary_id} · {s.status === "confirmed" ? "Confirmed" : "Unconfirmed"}
          </span>
        )}
        <div className="ml-auto flex gap-2">
          {canEdit && (
            <button type="button" disabled={busy} onClick={() => act(() => summaryApi.build(projectId))}
              className="rounded border border-h-line px-3 py-1.5 text-sm text-h-ink disabled:opacity-50">
              {s ? "Rebuild from approved takes" : "Build summary"}
            </button>
          )}
          {s && draft && canConfirm && (
            <button type="button" disabled={busy} onClick={() => act(() => summaryApi.confirm(s.summary_id))}
              className="rounded bg-h-accent px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50">
              Confirm
            </button>
          )}
        </div>
      </div>

      {staleCount > 0 && (
        <p className="rounded border border-h-line bg-h-surface px-3 py-2 text-sm text-h-ink">
          {`${staleCount} ${staleCount === 1 ? "line" : "lines"} may be outdated — an item's take has changed since this summary was built. Rebuild to refresh.`}
        </p>
      )}

      {(noSku > 0 || noSupplier > 0) && (
        <p data-testid="summary-blocked" className="rounded border border-h-line bg-h-surface px-3 py-2 text-sm text-h-ink">
          {`${noSku + noSupplier} ${noSku + noSupplier === 1 ? "line" : "lines"} can't be ordered yet (${
            [noSupplier > 0 && `${noSupplier} no supplier`, noSku > 0 && `${noSku} no SKU`].filter(Boolean).join(", ")
          }). Fix them in the Catalog.`}
        </p>
      )}

      {data.missing_takes.length > 0 && (
        <details className="rounded border border-h-line bg-h-surface px-3 py-2 text-sm">
          <summary className="cursor-pointer text-h-ink">
            {data.missing_takes.length} item{data.missing_takes.length === 1 ? "" : "s"} without an approved take
          </summary>
          <ul className="mt-2 grid gap-1">
            {data.missing_takes.map((m) => (
              <li key={m.item_id}>
                <Link href={`/items/${m.item_id}?tab=take`} className="text-h-accent">
                  <span className="h-mono">{m.num}</span> {m.description}
                </Link>
              </li>
            ))}
          </ul>
        </details>
      )}

      {!s && <p className="text-sm text-h-muted">No summary yet.</p>}

      {s && (
        <table className="w-full rounded border border-h-line bg-h-surface text-sm">
          <thead className="text-left text-xs uppercase tracking-wide text-h-muted">
            <tr>
              <th className="px-3 py-1.5">Material</th>
              <th className="px-3 py-1.5 text-right">Consolidated</th>
              <th className="px-3 py-1.5 text-right">Nest</th>
              <th className="px-3 py-1.5 text-right">Confirmed</th>
              <th className="px-3 py-1.5 text-right">Required</th>
              <th className="px-3 py-1.5 text-right">Ordered</th>
              <th className="px-3 py-1.5 text-right">Received</th>
              <th className="px-3 py-1.5 text-right">Outstanding</th>
              <th className="px-3 py-1.5"><span className="sr-only">Order</span></th>
              <th className="px-3 py-1.5">Note</th>
            </tr>
          </thead>
          <tbody>
            {s.lines.map((l) => (
              <Fragment key={l.line_id}>
                <SummaryRow projectId={projectId} line={l} editable={draft && canEdit} expanded={open.has(l.line_id)}
                  canOrder={canOrder && !busy} order={() => orderLine(s.summary_id, l.line_id)}
                  toggle={() => setOpen((o) => {
                    const n = new Set(o);
                    if (n.has(l.line_id)) n.delete(l.line_id);
                    else n.add(l.line_id);
                    return n;
                  })}
                  save={(changes) => act(() => summaryApi.patchLine(s.summary_id, l.line_id, changes))} />
                {open.has(l.line_id) && l.sources.map((src) => (
                  <tr key={`${l.line_id}-${src.item_id}`} className="text-xs text-h-muted">
                    <td className="py-1 pl-8 pr-3">
                      <Link href={`/items/${src.item_id}?tab=take`} className="hover:text-h-ink">
                        <span className="h-mono">{src.num}</span> {src.description}
                      </Link>{" "}
                      · take v{src.take_version}
                    </td>
                    <td className="h-mono px-3 py-1 text-right">{src.qty}</td>
                    <td colSpan={8} />
                  </tr>
                ))}
              </Fragment>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function SummaryRow({ projectId, line, editable, canOrder, order, expanded, toggle, save }: {
  projectId: number;
  line: SummaryLine;
  editable: boolean;
  canOrder: boolean;
  order: () => void;
  expanded: boolean;
  toggle: () => void;
  save: (changes: { qty_confirmed?: string | null; note?: string | null }) => void;
}) {
  const [qty, setQty] = useState(line.qty_confirmed ?? "");
  const [note, setNote] = useState(line.note ?? "");
  useEffect(() => {
    setQty(line.qty_confirmed ?? "");
    setNote(line.note ?? "");
  }, [line]);
  const unit = UNIT_LABEL[line.unit];

  return (
    <tr className="border-t border-h-line align-top">
      <td className="px-3 py-1.5">
        <button type="button" onClick={toggle} aria-expanded={expanded} className="text-left text-h-ink">
          {expanded ? "▾" : "▸"} {line.description}
        </button>
        {line.stale && <span className="ml-2 rounded bg-h-bg px-1.5 text-xs text-h-muted">outdated</span>}
      </td>
      <td className="h-mono px-3 py-1.5 text-right text-h-ink">{line.qty_consolidated} {unit}</td>
      <td className="h-mono px-3 py-1.5 text-right text-h-muted">
        {line.nest_sheets != null ? `${line.nest_sheets} sheets` : "—"}
      </td>
      <td className="px-3 py-1.5 text-right">
        {editable ? (
          <input aria-label={`Confirmed qty for ${line.description}`} inputMode="decimal"
            placeholder={line.qty_consolidated} value={qty} onChange={(e) => setQty(e.target.value)}
            onBlur={() => qty !== (line.qty_confirmed ?? "") && save({ qty_confirmed: qty || null })}
            className="h-mono w-24 rounded border border-h-line bg-white px-2 py-0.5 text-right text-sm" />
        ) : (
          <span className="h-mono text-h-ink">{line.qty_confirmed ?? "—"}</span>
        )}
      </td>
      <td className="h-mono px-3 py-1.5 text-right text-h-ink" data-testid="summary-required">{line.qty_required}</td>
      <td className="h-mono px-3 py-1.5 text-right text-h-muted" data-testid="summary-ordered">
        {line.sku && line.qty_on_order !== null && Number(line.qty_on_order) > 0 ? (
          <Link data-testid="summary-ordered-link" className="text-h-accent hover:underline"
            href={`/orderbook?${new URLSearchParams({ project_id: String(projectId), product_code: line.sku, ordered: "1" })}`}>
            {line.qty_on_order}
          </Link>
        ) : (line.qty_on_order ?? "—")}
      </td>
      <td className="h-mono px-3 py-1.5 text-right text-h-muted" data-testid="summary-received">{line.qty_received ?? "—"}</td>
      <td className="h-mono px-3 py-1.5 text-right text-h-ink" data-testid="summary-outstanding">{line.qty_outstanding ?? "—"}</td>
      <td className="px-3 py-1.5 text-right">
        {line.order_block && (
          <span data-testid="summary-order-block" className="text-xs text-h-muted">
            {WHY_NOT[line.order_block]}
            {(line.order_block === "NO_SKU" || line.order_block === "NO_SUPPLIER") && CATALOG_TAB[line.material_type] && (
              <>{" "}
                <Link data-testid="summary-order-block-link" className="text-h-accent hover:underline"
                  href={`/catalog?${new URLSearchParams({ tab: CATALOG_TAB[line.material_type], q: line.description })}`}>
                  Fix in the Catalog
                </Link>
              </>
            )}
          </span>
        )}
        {canOrder && Number(line.qty_to_order ?? 0) > 0 && (
          <button type="button" onClick={order} data-testid="summary-order"
            aria-label={`Create order for ${line.description}`}
            className="rounded border border-h-line px-2 py-0.5 text-xs text-h-ink">
            Order {line.qty_to_order}
          </button>
        )}
        {line.qty_confirmed === null && (
          <span className="ml-1 rounded bg-h-bg px-1.5 text-xs text-h-muted">unconfirmed</span>
        )}
      </td>
      <td className="px-3 py-1.5">
        {editable ? (
          <input aria-label={`Note for ${line.description}`} value={note}
            onChange={(e) => setNote(e.target.value)}
            onBlur={() => note !== (line.note ?? "") && save({ note: note || null })}
            className="w-full rounded border border-h-line bg-white px-2 py-0.5 text-sm" />
        ) : (
          <span className="text-h-muted">{line.note}</span>
        )}
      </td>
    </tr>
  );
}
