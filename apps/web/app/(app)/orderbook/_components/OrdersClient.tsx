"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import type { OrderRow } from "@/lib/orders-types";

/**
 * Orderbook's Orders tab — the commercial layer over `purchase_orders` (Q505).
 *
 * Q504 keeps procurement batches beneath orders as the allocation mechanism,
 * so #4's supplier-grouped queue is not replaced: it moves to the Queue tab
 * beside this one.
 *
 * Q418 is honoured here. Tracking links a related part's issued order number
 * to `/orderbook?order=<po_number>`; that param selects the row, scrolls it
 * into view and opens its detail panel, which is the "locate the order" half
 * the link could not deliver while this page rendered batches.
 */
const STATUSES = [
  "Draft", "Pending", "Approved", "Rejected",
  "Delivered", "Cancelled", "Hold", "Quote", "Next",
] as const;

function statusClasses(status: string): string {
  switch (status) {
    case "Approved":
    case "Delivered": return "bg-[#e4efe5] text-[#3f7d48]";
    case "Rejected":
    case "Cancelled": return "bg-[#f2dcd9] text-[#b4443d]";
    case "Hold":
    case "Pending":   return "bg-[#f4ebd9] text-[#c48a2e]";
    case "Quote":
    case "Next":      return "bg-[#f3e0d6] text-[#a84f31]";
    default:          return "bg-[#f4f2ed] text-[#8f8b80]";
  }
}

/** Decimal arrives as a string (see `orders-types.ts`), so parse before formatting. */
function money(v: string | null, currency: string | null): string {
  if (v == null) return "—";
  const n = Number(v);
  if (Number.isNaN(n)) return v;
  return `${currency ? `${currency} ` : "$"}${n.toFixed(2)}`;
}

/** Trims Decimal's trailing zeros: "1.000" reads as "1". */
function qty(v: string | null): string | null {
  if (v == null) return null;
  const n = Number(v);
  return Number.isNaN(n) ? v : String(n);
}

export function OrdersClient() {
  const router = useRouter();
  const params = useSearchParams();
  const [rows, setRows] = useState<OrderRow[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const status = params.get("status") ?? "";
  const supplier = params.get("supplier") ?? "";
  // Q418: the number Tracking sent us here with.
  const selected = params.get("order") ?? "";

  useEffect(() => {
    const qs = new URLSearchParams();
    if (status) qs.set("status", status);
    if (supplier) qs.set("supplier", supplier);
    setLoading(true);
    fetch(`/api/orders${qs.toString() ? `?${qs}` : ""}`, { cache: "no-store" })
      .then(r => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then(b => { setRows(b.orders); setErr(null); })
      .catch(e => setErr(String(e)))
      .finally(() => setLoading(false));
  }, [status, supplier]);

  const suppliers = useMemo(
    () => [...new Set(rows.map(r => r.vendor_name).filter((s): s is string => !!s))].sort(),
    [rows],
  );

  const selectedRow = rows.find(r => r.po_number === selected) ?? null;

  function setParam(k: string, v: string) {
    const next = new URLSearchParams(params.toString());
    if (v) next.set(k, v); else next.delete(k);
    const qs = next.toString();
    router.push(qs ? `/orderbook?${qs}` : "/orderbook");
  }

  return (
    <div className="grid gap-3" data-testid="orders-panel">
      <div className="flex flex-wrap items-center gap-2">
        <select
          value={status}
          onChange={e => setParam("status", e.target.value)}
          data-testid="orders-status-filter"
          className="rounded border border-h-line bg-h-surface px-2 py-1 text-xs text-h-ink"
        >
          <option value="">All statuses</option>
          {STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
        </select>
        <select
          value={supplier}
          onChange={e => setParam("supplier", e.target.value)}
          data-testid="orders-supplier-filter"
          className="rounded border border-h-line bg-h-surface px-2 py-1 text-xs text-h-ink"
        >
          <option value="">All suppliers</option>
          {suppliers.map(s => <option key={s} value={s}>{s}</option>)}
        </select>
        <span className="text-xs text-h-muted">
          {loading ? "Loading…" : `${rows.length} order${rows.length === 1 ? "" : "s"}`}
        </span>
        {selected && (
          <button
            type="button"
            onClick={() => setParam("order", "")}
            className="rounded border border-h-line bg-h-bg px-2 py-1 text-xs text-h-muted hover:text-h-ink"
          >
            Clear selection ({selected})
          </button>
        )}
      </div>

      {err && <p className="text-sm text-[#b4443d]">Could not load orders: {err}</p>}

      {/* Q418: the link may name an order that this filter combination hides.
          Say so rather than showing an empty table under a selection. */}
      {selected && !loading && !selectedRow && !err && (
        <p
          data-testid="orders-not-found"
          className="rounded border border-h-line bg-h-surface px-3 py-2 text-xs text-h-muted"
        >
          Order <span className="h-mono text-h-ink">{selected}</span> is not in this
          list — clear the filters above, or it belongs to another workspace.
        </p>
      )}

      <div className="overflow-x-auto rounded border border-h-line">
        <table className="w-full min-w-[980px] border-collapse text-xs">
          <thead className="bg-h-surface text-left text-[10px] uppercase tracking-wide text-h-muted">
            <tr>
              <th className="px-2 py-1.5">Order #</th>
              <th className="px-2 py-1.5">Supplier</th>
              <th className="px-2 py-1.5">Description</th>
              <th className="px-2 py-1.5">Project</th>
              <th className="px-2 py-1.5">Cutlist no.</th>
              <th className="px-2 py-1.5">Status</th>
              <th className="px-2 py-1.5">Ordered</th>
              <th className="px-2 py-1.5">ETA</th>
              <th className="px-2 py-1.5 text-right">Total</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && !loading ? (
              <tr>
                <td colSpan={9} className="px-4 py-8 text-center text-h-muted">
                  No orders yet.
                </td>
              </tr>
            ) : (
              rows.map(r => (
                <OrderRowView
                  key={r.po_id}
                  row={r}
                  selected={r.po_number === selected}
                  onSelect={() => setParam("order", r.po_number === selected ? "" : r.po_number)}
                />
              ))
            )}
          </tbody>
        </table>
      </div>

      {selectedRow && <OrderDetail row={selectedRow} />}
    </div>
  );
}

function OrderRowView({
  row, selected, onSelect,
}: { row: OrderRow; selected: boolean; onSelect: () => void }) {
  const ref = useRef<HTMLTableRowElement>(null);
  // Q418: arriving from Tracking should land on the order, not near it.
  useEffect(() => {
    if (selected) ref.current?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [selected]);

  return (
    <tr
      ref={ref}
      data-testid="order-row"
      data-selected={selected ? "true" : undefined}
      onClick={onSelect}
      className={`cursor-pointer border-t border-h-line hover:bg-h-bg ${
        selected ? "bg-h-accent/10 ring-1 ring-inset ring-h-accent" : ""
      }`}
    >
      <td className="whitespace-nowrap px-2 py-1.5 h-mono text-h-ink">{row.po_number}</td>
      <td className="px-2 py-1.5 text-h-ink">{row.vendor_name ?? "—"}</td>
      <td className="px-2 py-1.5 text-h-muted">{row.description}</td>
      <td className="px-2 py-1.5 text-h-muted">
        {row.project_id ? (
          <Link
            href={`/tracking?project_id=${row.project_id}`}
            onClick={e => e.stopPropagation()}
            className="hover:text-h-accent hover:underline"
          >
            {row.project_name ?? `#${row.project_id}`}
          </Link>
        ) : (
          // Q554: an order with no project keeps its free-text label.
          row.project_name ?? "—"
        )}
      </td>
      <td className="whitespace-nowrap px-2 py-1.5 h-mono text-h-muted">
        {row.cutlist_no ?? "—"}
      </td>
      <td className="px-2 py-1.5">
        <span className={`rounded px-1.5 py-0.5 text-[10px] ${statusClasses(row.status)}`}>
          {row.status}
        </span>
      </td>
      <td className="whitespace-nowrap px-2 py-1.5 h-mono text-h-muted">
        {row.date_ordered ?? "—"}
      </td>
      <td className="whitespace-nowrap px-2 py-1.5 h-mono text-h-muted">
        {row.due_date ?? "—"}
      </td>
      <td className="whitespace-nowrap px-2 py-1.5 text-right h-mono text-h-ink">
        {money(row.total_amount, row.currency)}
      </td>
    </tr>
  );
}

function OrderDetail({ row }: { row: OrderRow }) {
  const attrs = Object.entries(row.attributes ?? {});
  return (
    <div
      data-testid="order-detail"
      className="rounded border border-h-line bg-h-surface p-4 text-xs"
    >
      <div className="mb-3 flex items-baseline gap-3">
        <h2 className="h-mono text-base text-h-ink">{row.po_number}</h2>
        <span className={`rounded px-1.5 py-0.5 text-[10px] ${statusClasses(row.status)}`}>
          {row.status}
        </span>
        <span className="text-h-muted">{row.category} · {row.priority}</span>
      </div>

      <dl className="grid grid-cols-2 gap-x-6 gap-y-1.5 sm:grid-cols-3">
        <Field label="Supplier" value={row.vendor_name} />
        <Field label="Supplier ref" value={row.supplier_ref_no} mono />
        <Field label="Order no." value={row.order_number} mono />
        <Field label="Project" value={row.project_name} />
        <Field label="Location" value={row.location} />
        {/* Q428: the PARENT Joinery Item's number on a related part's order. */}
        <Field label="Cutlist no." value={row.cutlist_no} mono />
        <Field label="Item" value={row.item_number != null ? String(row.item_number) : null} mono />
        <Field label="Product code" value={row.product_code} mono />
        <Field
          label="Quantity"
          value={row.quantity != null ? `${qty(row.quantity)} ${row.unit_of_measure ?? ""}`.trim() : null}
          mono
        />
        <Field label="Unit cost" value={row.unit_cost != null ? money(row.unit_cost, row.currency) : null} mono />
        <Field label="Total" value={row.total_amount != null ? money(row.total_amount, row.currency) : null} mono />
        <Field label="Required by" value={row.required_date} mono />
        <Field label="Ordered" value={row.date_ordered} mono />
        <Field label="ETA" value={row.due_date} mono />
      </dl>

      {row.product_description && (
        <p className="mt-3 text-h-muted">{row.product_description}</p>
      )}
      {row.internal_comments && (
        <p className="mt-2 text-h-muted">
          <span className="text-h-ink">Internal: </span>{row.internal_comments}
        </p>
      )}

      {attrs.length > 0 && (
        <div className="mt-3">
          {/* Q503: the type-specific fields the one generic form collects. */}
          <p className="mb-1 text-[10px] uppercase tracking-wide text-h-muted">Attributes</p>
          <dl className="grid grid-cols-2 gap-x-6 gap-y-1 sm:grid-cols-3">
            {attrs.map(([k, v]) => (
              <Field key={k} label={k} value={v == null ? null : String(v)} />
            ))}
          </dl>
        </div>
      )}
    </div>
  );
}

function Field({ label, value, mono = false }: { label: string; value: string | null; mono?: boolean }) {
  return (
    <div>
      <dt className="text-[10px] uppercase tracking-wide text-h-muted">{label}</dt>
      <dd className={`text-h-ink ${mono ? "h-mono" : ""}`}>{value || "—"}</dd>
    </div>
  );
}
