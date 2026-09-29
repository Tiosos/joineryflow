"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { can, type Me } from "@/lib/permissions";
import type {
  CreateOrderLineIn,
  OrderDetail as OrderDetailType,
  OrderLine,
  OrderRow,
  PatchOrderLineIn,
} from "@/lib/orders-types";

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
 *
 * The detail panel is editable (`orderbook:write`) — the PATCH-editing UI
 * `PatchOrderIn` / `field_versions` had carried since §L with nothing to
 * drive them, now that PO generation (a Won Quote) creates real multi-line
 * orders with nothing else to correct or approve them.
 */
const STATUSES = [
  "Draft", "Pending", "Approved", "Rejected",
  "Delivered", "Cancelled", "Hold", "Quote", "Next",
] as const;

const PRIORITIES = ["High", "Medium", "Low", "Next", "Hold", "Quote"] as const;

// Mirrors `FROZEN_STATUSES` in apps/api/app/orders/queries.py, which is the
// source of truth and enforces it (409 ORDER_LOCKED). Here it only decides
// which controls to render: a Cancelled or Delivered order is read-only
// except for its status, the deliberate way to reopen it.
const FROZEN_STATUSES: readonly string[] = ["Cancelled", "Delivered"];

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

type ErrorDetail = { code?: string; status?: string };

function orderLocked(body: unknown): ErrorDetail | null {
  const d = (body as { detail?: ErrorDetail } | null)?.detail;
  return d?.code === "ORDER_LOCKED" ? d : null;
}

function lockedMessage(d: ErrorDetail): string {
  return `Order is ${d.status ?? "locked"} — change its status to edit`;
}

function fieldErrorMessage(res: Response, body: unknown, field: string): string {
  const locked = orderLocked(body);
  if (locked) return lockedMessage(locked);
  const code = (body as { detail?: { code?: string; conflicts?: Record<string, { current_value?: unknown }> } } | null)
    ?.detail?.code;
  if (code === "FIELD_CONFLICT") {
    const cur = (body as { detail?: { conflicts?: Record<string, { current_value?: unknown }> } })
      ?.detail?.conflicts?.[field]?.current_value;
    return `Changed to "${cur ?? "…"}" by someone else — reload to see it`;
  }
  // `patch_order_route`'s 404 is a plain string detail ("order not found"),
  // not a {code} object, matching every other 404 in this module — so it's
  // the HTTP status, not a code, that identifies it here.
  if (res.status === 404) return "Order not found";
  return `Save failed (${res.status})`;
}

export function OrdersClient({ me }: { me: Me | null }) {
  const router = useRouter();
  const params = useSearchParams();
  const [rows, setRows] = useState<OrderRow[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const status = params.get("status") ?? "";
  const supplier = params.get("supplier") ?? "";
  // Q418: the number Tracking sent us here with.
  const selected = params.get("order") ?? "";

  const fetchRows = useCallback(() => {
    const qs = new URLSearchParams();
    if (status) qs.set("status", status);
    if (supplier) qs.set("supplier", supplier);
    setLoading(true);
    return fetch(`/api/orders${qs.toString() ? `?${qs}` : ""}`, { cache: "no-store" })
      .then(r => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then(b => { setRows(b.orders); setErr(null); })
      .catch(e => setErr(String(e)))
      .finally(() => setLoading(false));
  }, [status, supplier]);

  useEffect(() => {
    void fetchRows();
  }, [fetchRows]);

  const suppliers = useMemo(
    () => [...new Set(rows.map(r => r.vendor_name).filter((s): s is string => !!s))].sort(),
    [rows],
  );

  const selectedRow = rows.find(r => r.po_number === selected) ?? null;
  const canEdit = can(me, "orderbook", "write");

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

      {selectedRow && (
        <OrderDetailPanel
          key={selectedRow.po_id}
          poId={selectedRow.po_id}
          canEdit={canEdit}
          onChanged={fetchRows}
        />
      )}
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

function OrderDetailPanel({
  poId, canEdit, onChanged,
}: { poId: number; canEdit: boolean; onChanged: () => void }) {
  const [order, setOrder] = useState<OrderDetailType | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadErr, setLoadErr] = useState<string | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});

  const refetch = useCallback(() => {
    setLoading(true);
    return fetch(`/api/orders/${poId}`, { cache: "no-store" })
      .then(r => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((b: OrderDetailType) => { setOrder(b); setLoadErr(null); })
      .catch(e => setLoadErr(String(e)))
      .finally(() => setLoading(false));
  }, [poId]);

  useEffect(() => {
    void refetch();
  }, [refetch]);

  // Every one of the four functions below wraps its fetch in try/catch,
  // matching `ItemMetadataPanel.tsx`'s `patchField` — a thrown network
  // error or invalid-JSON response must surface as a visible error and a
  // `false`/return, the same as a non-2xx response, not an unhandled
  // rejection that leaves the caller believing nothing happened.

  async function patchField(field: string, value: unknown): Promise<boolean> {
    if (!order) return false;
    setErrors(e => ({ ...e, [field]: "" }));
    try {
      const res = await fetch(`/api/orders/${poId}`, {
        method: "PATCH",
        headers: { "content-type": "application/json" },
        // §L Q511/Q512: carry the version this field was at when the page
        // loaded, so a save that raced with someone else's is a named
        // conflict rather than a silent overwrite.
        body: JSON.stringify({
          [field]: value,
          expected_versions: { [field]: order.field_versions?.[field] ?? 0 },
        }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        setErrors(e => ({ ...e, [field]: fieldErrorMessage(res, body, field) }));
        if (orderLocked(body)) { void refetch(); onChanged(); }
        return false;
      }
      const updated = (await res.json()) as OrderDetailType;
      setOrder(updated);
      // A status change can flip the order between frozen and editable, so
      // any per-field message left from before it (notably "Order is
      // Cancelled — change its status to edit") is about a state that no
      // longer holds and would reappear under the now-editable field.
      if (field === "status") setErrors({});
      onChanged();
      return true;
    } catch {
      setErrors(e => ({ ...e, [field]: "Failed to save — check your connection" }));
      return false;
    }
  }

  async function patchLine(lineId: number, payload: PatchOrderLineIn): Promise<boolean> {
    setErrors(e => ({ ...e, [`line-${lineId}`]: "" }));
    try {
      const res = await fetch(`/api/orders/${poId}/lines/${lineId}`, {
        method: "PATCH",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        const locked = orderLocked(body);
        setErrors(e => ({
          ...e,
          [`line-${lineId}`]: locked ? lockedMessage(locked) : `Save failed (${res.status})`,
        }));
        if (locked) { void refetch(); onChanged(); }
        return false;
      }
      const updated = (await res.json()) as OrderDetailType;
      setOrder(updated);
      onChanged();
      return true;
    } catch {
      setErrors(e => ({ ...e, [`line-${lineId}`]: "Failed to save — check your connection" }));
      return false;
    }
  }

  async function removeLine(lineId: number) {
    // A line already gone from the last-known order (removed by this same
    // click's earlier request, e.g. a double-click before the row unmounts,
    // or by someone else) needs no confirm dialog and no request — DELETE
    // is idempotent here, and re-sending it would only 404 and misreport a
    // successful removal as "failed".
    if (!order?.lines.some(l => l.line_id === lineId)) return;
    if (!window.confirm("Remove this line?")) return;
    try {
      const res = await fetch(`/api/orders/${poId}/lines/${lineId}`, { method: "DELETE" });
      if (res.status === 404) return; // already removed elsewhere — goal met
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        const locked = orderLocked(body);
        setErrors(e => ({
          ...e,
          [`line-${lineId}`]: locked ? lockedMessage(locked) : `Remove failed (${res.status})`,
        }));
        if (locked) { void refetch(); onChanged(); }
        return;
      }
      const updated = (await res.json()) as OrderDetailType;
      setOrder(updated);
      onChanged();
    } catch {
      setErrors(e => ({ ...e, [`line-${lineId}`]: "Failed to remove — check your connection" }));
    }
  }

  async function addLine(payload: CreateOrderLineIn): Promise<boolean> {
    setErrors(e => ({ ...e, "new-line": "" }));
    try {
      const res = await fetch(`/api/orders/${poId}/lines`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        const locked = orderLocked(body);
        setErrors(e => ({
          ...e,
          "new-line": locked ? lockedMessage(locked) : `Add failed (${res.status})`,
        }));
        if (locked) { void refetch(); onChanged(); }
        return false;
      }
      const updated = (await res.json()) as OrderDetailType;
      setOrder(updated);
      onChanged();
      return true;
    } catch {
      setErrors(e => ({ ...e, "new-line": "Failed to add — check your connection" }));
      return false;
    }
  }

  if (loading && !order) {
    return (
      <div className="rounded border border-h-line bg-h-surface p-4 text-xs text-h-muted">
        Loading order…
      </div>
    );
  }
  if (loadErr || !order) {
    return (
      <div className="rounded border border-h-line bg-h-surface p-4 text-xs text-[#b4443d]">
        Could not load order: {loadErr}
      </div>
    );
  }

  const frozen = FROZEN_STATUSES.includes(order.status);
  // Status stays editable on a frozen order (canEdit); everything else follows
  // canEditFields.
  const canEditFields = canEdit && !frozen;

  return (
    <div
      data-testid="order-detail"
      className="rounded border border-h-line bg-h-surface p-4 text-xs"
    >
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <h2 className="h-mono text-base text-h-ink">{order.po_number}</h2>
        {canEdit ? (
          <select
            value={order.status}
            onChange={e => void patchField("status", e.target.value)}
            data-testid="order-status-select"
            className={`rounded border-0 px-1.5 py-0.5 text-[10px] ${statusClasses(order.status)}`}
          >
            {STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        ) : (
          <span className={`rounded px-1.5 py-0.5 text-[10px] ${statusClasses(order.status)}`}>
            {order.status}
          </span>
        )}
        {canEditFields ? (
          <select
            value={order.priority}
            onChange={e => void patchField("priority", e.target.value)}
            className="rounded border border-h-line bg-h-bg px-1.5 py-0.5 text-[10px] text-h-ink"
          >
            {PRIORITIES.map(p => <option key={p} value={p}>{p}</option>)}
          </select>
        ) : (
          <span className="text-h-muted">{order.priority}</span>
        )}
        <span className="text-h-muted">{order.category}</span>
      </div>
      {errors.status && <ErrorLine msg={errors.status} />}
      {errors.priority && <ErrorLine msg={errors.priority} />}
      {canEdit && frozen && (
        <p
          data-testid="order-frozen-banner"
          className="mb-3 rounded border border-h-line bg-h-bg px-2 py-1.5 text-h-muted"
        >
          This order is {order.status} and read-only. Change its status above to
          edit it again.
        </p>
      )}

      <dl className="grid grid-cols-2 gap-x-6 gap-y-1.5 sm:grid-cols-3">
        <Field label="Supplier" value={order.vendor_name} />
        <EditableField
          label="Supplier ref"
          value={order.supplier_ref_no}
          canEdit={canEditFields}
          onSave={v => patchField("supplier_ref_no", v || null)}
          error={errors.supplier_ref_no}
        />
        <EditableField
          label="Order no."
          value={order.order_number}
          canEdit={canEditFields}
          onSave={v => patchField("order_number", v || null)}
          error={errors.order_number}
        />
        <Field label="Project" value={order.project_name} />
        <Field label="Location" value={order.location} />
        {/* Q428: the PARENT Joinery Item's number on a related part's order. */}
        <Field label="Cutlist no." value={order.cutlist_no} mono />
        <Field label="Item" value={order.item_number != null ? String(order.item_number) : null} mono />
        <Field label="Product code" value={order.product_code} mono />
        <Field
          label="Quantity"
          value={order.quantity != null ? `${qty(order.quantity)} ${order.unit_of_measure ?? ""}`.trim() : null}
          mono
        />
        <Field label="Unit cost" value={order.unit_cost != null ? money(order.unit_cost, order.currency) : null} mono />
        <Field label="Total" value={order.total_amount != null ? money(order.total_amount, order.currency) : null} mono />
        <EditableDateField
          label="Required by"
          value={order.required_date}
          canEdit={canEditFields}
          onSave={v => patchField("required_date", v || null)}
          error={errors.required_date}
        />
        <EditableDateField
          label="Ordered"
          value={order.date_ordered}
          canEdit={canEditFields}
          onSave={v => patchField("date_ordered", v || null)}
          error={errors.date_ordered}
        />
        <EditableDateField
          label="ETA"
          value={order.due_date}
          canEdit={canEditFields}
          onSave={v => patchField("due_date", v || null)}
          error={errors.due_date}
        />
      </dl>

      {order.product_description && (
        <p className="mt-3 text-h-muted">{order.product_description}</p>
      )}

      <div className="mt-3">
        <p className="mb-1 text-[10px] uppercase tracking-wide text-h-muted">Notes</p>
        {canEditFields ? (
          <BlurTextArea
            defaultValue={order.notes ?? ""}
            onSave={v => patchField("notes", v || null)}
          />
        ) : (
          <p className="text-h-muted">{order.notes || "—"}</p>
        )}
        {errors.notes && <ErrorLine msg={errors.notes} />}
      </div>

      <div className="mt-2">
        <p className="mb-1 text-[10px] uppercase tracking-wide text-h-muted">Internal comments</p>
        {canEditFields ? (
          <BlurTextArea
            defaultValue={order.internal_comments ?? ""}
            onSave={v => patchField("internal_comments", v || null)}
          />
        ) : (
          <p className="text-h-muted">{order.internal_comments || "—"}</p>
        )}
        {errors.internal_comments && <ErrorLine msg={errors.internal_comments} />}
      </div>

      {Object.entries(order.attributes ?? {}).length > 0 && (
        <div className="mt-3">
          {/* Q503: the type-specific fields the one generic form collects. */}
          <p className="mb-1 text-[10px] uppercase tracking-wide text-h-muted">Attributes</p>
          <dl className="grid grid-cols-2 gap-x-6 gap-y-1 sm:grid-cols-3">
            {Object.entries(order.attributes).map(([k, v]) => (
              <Field key={k} label={k} value={v == null ? null : String(v)} />
            ))}
          </dl>
        </div>
      )}

      <LinesSection
        lines={order.lines}
        canEdit={canEditFields}
        currency={order.currency}
        errors={errors}
        onPatchLine={patchLine}
        onRemoveLine={removeLine}
        onAddLine={addLine}
      />
    </div>
  );
}

function ErrorLine({ msg }: { msg: string }) {
  return <p className="mt-0.5 text-[10px] text-[#b4443d]">{msg}</p>;
}

function Field({ label, value, mono = false }: { label: string; value: string | null; mono?: boolean }) {
  return (
    <div>
      <dt className="text-[10px] uppercase tracking-wide text-h-muted">{label}</dt>
      <dd className={`text-h-ink ${mono ? "h-mono" : ""}`}>{value || "—"}</dd>
    </div>
  );
}

function EditableField({
  label, value, canEdit, onSave, error,
}: {
  label: string;
  value: string | null;
  canEdit: boolean;
  onSave: (v: string) => Promise<boolean>;
  error?: string;
}) {
  const [v, setV] = useState(value ?? "");
  // Resync when the order refetches after an unrelated field's save —
  // otherwise a stale local value can be resubmitted with a now-current
  // `expected_versions`, passing the conflict check and silently
  // reverting someone else's concurrent edit.
  useEffect(() => setV(value ?? ""), [value]);
  if (!canEdit) return <Field label={label} value={value} mono />;
  return (
    <div>
      <dt className="text-[10px] uppercase tracking-wide text-h-muted">{label}</dt>
      <input
        value={v}
        onChange={e => setV(e.target.value)}
        onBlur={async () => {
          if (v === (value ?? "")) return;
          if (!(await onSave(v))) setV(value ?? "");
        }}
        className="h-mono w-full rounded border border-h-line bg-h-bg px-1 py-0.5 text-h-ink focus:outline-none focus:ring-1 focus:ring-h-accent"
      />
      {error && <ErrorLine msg={error} />}
    </div>
  );
}

function EditableDateField({
  label, value, canEdit, onSave, error,
}: {
  label: string;
  value: string | null;
  canEdit: boolean;
  onSave: (v: string) => Promise<boolean>;
  error?: string;
}) {
  const [v, setV] = useState(value ?? "");
  useEffect(() => setV(value ?? ""), [value]);
  if (!canEdit) return <Field label={label} value={value} mono />;
  return (
    <div>
      <dt className="text-[10px] uppercase tracking-wide text-h-muted">{label}</dt>
      <input
        type="date"
        value={v}
        onChange={e => setV(e.target.value)}
        onBlur={async () => {
          if (v === (value ?? "")) return;
          if (!(await onSave(v))) setV(value ?? "");
        }}
        className="h-mono w-full rounded border border-h-line bg-h-bg px-1 py-0.5 text-h-ink focus:outline-none focus:ring-1 focus:ring-h-accent"
      />
      {error && <ErrorLine msg={error} />}
    </div>
  );
}

function BlurTextArea({
  defaultValue, onSave,
}: { defaultValue: string; onSave: (v: string) => Promise<boolean> }) {
  const [value, setValue] = useState(defaultValue);
  useEffect(() => setValue(defaultValue), [defaultValue]);
  return (
    <textarea
      rows={2}
      value={value}
      onChange={e => setValue(e.target.value)}
      onBlur={async () => {
        if (value === defaultValue) return;
        if (!(await onSave(value))) setValue(defaultValue);
      }}
      className="w-full resize-none rounded border border-h-line bg-h-bg px-2 py-1 text-h-ink focus:outline-none focus:ring-1 focus:ring-h-accent"
    />
  );
}

function LinesSection({
  lines, canEdit, currency, errors, onPatchLine, onRemoveLine, onAddLine,
}: {
  lines: OrderLine[];
  canEdit: boolean;
  currency: string | null;
  errors: Record<string, string>;
  onPatchLine: (lineId: number, payload: PatchOrderLineIn) => Promise<boolean>;
  onRemoveLine: (lineId: number) => Promise<void>;
  onAddLine: (payload: CreateOrderLineIn) => Promise<boolean>;
}) {
  return (
    <div className="mt-4">
      <p className="mb-1 text-[10px] uppercase tracking-wide text-h-muted">Lines</p>
      <div className="overflow-x-auto rounded border border-h-line">
        <table className="w-full min-w-[720px] border-collapse text-xs">
          <thead className="bg-h-bg text-left text-[10px] uppercase tracking-wide text-h-muted">
            <tr>
              <th className="px-2 py-1">Description</th>
              <th className="px-2 py-1">SKU</th>
              <th className="px-2 py-1 text-right">Qty</th>
              <th className="px-2 py-1">Unit</th>
              <th className="px-2 py-1 text-right">Unit price</th>
              <th className="px-2 py-1 text-right">Total</th>
              {canEdit && <th className="px-2 py-1" />}
            </tr>
          </thead>
          <tbody>
            {lines.length === 0 ? (
              <tr>
                <td colSpan={canEdit ? 7 : 6} className="px-2 py-3 text-center text-h-muted">
                  No lines yet.
                </td>
              </tr>
            ) : (
              lines.map(l => (
                <LineRow
                  key={l.line_id}
                  line={l}
                  canEdit={canEdit}
                  currency={currency}
                  error={errors[`line-${l.line_id}`]}
                  onPatch={payload => onPatchLine(l.line_id, payload)}
                  onRemove={() => onRemoveLine(l.line_id)}
                />
              ))
            )}
          </tbody>
        </table>
      </div>
      {canEdit && (
        <AddLineForm onAdd={onAddLine} error={errors["new-line"]} />
      )}
    </div>
  );
}

function LineRow({
  line, canEdit, currency, error, onPatch, onRemove,
}: {
  line: OrderLine;
  canEdit: boolean;
  currency: string | null;
  error?: string;
  onPatch: (payload: PatchOrderLineIn) => Promise<boolean>;
  onRemove: () => Promise<void>;
}) {
  const [description, setDescription] = useState(line.item_description);
  const [sku, setSku] = useState(line.sku ?? "");
  const [quantity, setQuantity] = useState(line.quantity);
  const [unit, setUnit] = useState(line.unit ?? "");
  const [unitPrice, setUnitPrice] = useState(line.unit_price);

  // Resync to the server's canonical value after a save — e.g. quantity
  // "5" round-trips as "5.000" (numeric(10,3)) — so the next blur's dirty
  // check compares against what the DB actually holds, not what was typed.
  useEffect(() => setDescription(line.item_description), [line.item_description]);
  useEffect(() => setSku(line.sku ?? ""), [line.sku]);
  useEffect(() => setQuantity(line.quantity), [line.quantity]);
  useEffect(() => setUnit(line.unit ?? ""), [line.unit]);
  useEffect(() => setUnitPrice(line.unit_price), [line.unit_price]);

  if (!canEdit) {
    return (
      <tr className="border-t border-h-line">
        <td className="px-2 py-1 text-h-ink">{line.item_description}</td>
        <td className="px-2 py-1 h-mono text-h-muted">{line.sku ?? "—"}</td>
        <td className="px-2 py-1 text-right h-mono">{qty(line.quantity)}</td>
        <td className="px-2 py-1 text-h-muted">{line.unit ?? "—"}</td>
        <td className="px-2 py-1 text-right h-mono">{money(line.unit_price, currency)}</td>
        <td className="px-2 py-1 text-right h-mono">{money(line.line_total, currency)}</td>
      </tr>
    );
  }

  return (
    <tr className="border-t border-h-line align-top">
      <td className="px-2 py-1">
        <input
          value={description}
          onChange={e => setDescription(e.target.value)}
          onBlur={async () => {
            if (description !== line.item_description
              && !(await onPatch({ item_description: description }))) {
              setDescription(line.item_description);
            }
          }}
          className="w-full rounded border border-h-line bg-h-bg px-1 py-0.5 text-h-ink"
        />
      </td>
      <td className="px-2 py-1">
        <input
          value={sku}
          onChange={e => setSku(e.target.value)}
          onBlur={async () => {
            if (sku !== (line.sku ?? "") && !(await onPatch({ sku: sku || null }))) {
              setSku(line.sku ?? "");
            }
          }}
          className="h-mono w-20 rounded border border-h-line bg-h-bg px-1 py-0.5 text-h-ink"
        />
      </td>
      <td className="px-2 py-1">
        <input
          value={quantity}
          onChange={e => setQuantity(e.target.value)}
          onBlur={async () => {
            if (quantity !== line.quantity && !(await onPatch({ quantity }))) {
              setQuantity(line.quantity);
            }
          }}
          className="h-mono w-16 rounded border border-h-line bg-h-bg px-1 py-0.5 text-right text-h-ink"
        />
      </td>
      <td className="px-2 py-1">
        <input
          value={unit}
          onChange={e => setUnit(e.target.value)}
          onBlur={async () => {
            if (unit !== (line.unit ?? "") && !(await onPatch({ unit: unit || null }))) {
              setUnit(line.unit ?? "");
            }
          }}
          className="w-16 rounded border border-h-line bg-h-bg px-1 py-0.5 text-h-ink"
        />
      </td>
      <td className="px-2 py-1">
        <input
          value={unitPrice}
          onChange={e => setUnitPrice(e.target.value)}
          onBlur={async () => {
            if (unitPrice !== line.unit_price && !(await onPatch({ unit_price: unitPrice }))) {
              setUnitPrice(line.unit_price);
            }
          }}
          className="h-mono w-20 rounded border border-h-line bg-h-bg px-1 py-0.5 text-right text-h-ink"
        />
      </td>
      <td className="px-2 py-1 text-right h-mono">{money(line.line_total, currency)}</td>
      <td className="px-2 py-1">
        <button
          type="button"
          onClick={() => void onRemove()}
          className="text-[#b4443d] hover:underline"
          aria-label="Remove line"
        >
          ×
        </button>
        {error && <ErrorLine msg={error} />}
      </td>
    </tr>
  );
}

function AddLineForm({
  onAdd, error,
}: { onAdd: (payload: CreateOrderLineIn) => Promise<boolean>; error?: string }) {
  const [description, setDescription] = useState("");
  const [sku, setSku] = useState("");
  const [quantity, setQuantity] = useState("1");
  const [unit, setUnit] = useState("");
  const [unitPrice, setUnitPrice] = useState("0");
  const [busy, setBusy] = useState(false);

  async function submit() {
    if (!description.trim() || busy) return;
    setBusy(true);
    try {
      const ok = await onAdd({
        item_description: description.trim(),
        quantity,
        unit_price: unitPrice,
        sku: sku || null,
        unit: unit || null,
      });
      if (ok) {
        setDescription(""); setSku(""); setQuantity("1"); setUnit(""); setUnitPrice("0");
      }
    } finally {
      // A thrown network error or invalid-JSON response (onAdd doesn't
      // catch either) must still release the button — otherwise it's
      // stuck on "Adding…" for the rest of the panel's life.
      setBusy(false);
    }
  }

  return (
    <div className="mt-2 flex flex-wrap items-center gap-2">
      <input
        placeholder="Description"
        value={description}
        onChange={e => setDescription(e.target.value)}
        className="min-w-[160px] flex-1 rounded border border-h-line bg-h-bg px-2 py-1 text-h-ink"
      />
      <input
        placeholder="SKU"
        value={sku}
        onChange={e => setSku(e.target.value)}
        className="h-mono w-24 rounded border border-h-line bg-h-bg px-2 py-1 text-h-ink"
      />
      <input
        placeholder="Qty"
        value={quantity}
        onChange={e => setQuantity(e.target.value)}
        className="h-mono w-16 rounded border border-h-line bg-h-bg px-2 py-1 text-h-ink"
      />
      <input
        placeholder="Unit"
        value={unit}
        onChange={e => setUnit(e.target.value)}
        className="w-16 rounded border border-h-line bg-h-bg px-2 py-1 text-h-ink"
      />
      <input
        placeholder="Unit price"
        value={unitPrice}
        onChange={e => setUnitPrice(e.target.value)}
        className="h-mono w-20 rounded border border-h-line bg-h-bg px-2 py-1 text-h-ink"
      />
      <button
        type="button"
        onClick={() => void submit()}
        disabled={busy || !description.trim()}
        className="rounded bg-h-accent px-3 py-1 text-white disabled:opacity-40"
      >
        {busy ? "Adding…" : "+ Add line"}
      </button>
      {error && <ErrorLine msg={error} />}
    </div>
  );
}
