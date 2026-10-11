"use client";

import { useCallback, useEffect, useState } from "react";
import { can } from "@/lib/permissions";
import type { CostCentre, CreateOrderLineIn, OrderCategory, OrderDetail as OrderDetailType, PatchOrderLineIn } from "@/lib/orders-types";
import { STATUSES, PRIORITIES, statusClasses, money, qty, dec2, orderLocked, lockedMessage, fieldErrorMessage } from "./shared";
import { CostCentreField } from "./CostCentreField";
import { ErrorLine } from "./ErrorLine";
import { AreaRow, CheckRow, Row, SelectRow, TextRow } from "./DetailRows";
import { OrderTypeFields } from "./OrderTypeFields";
import { LinesSection } from "./LinesSection";

/**
 * The order pop-up: the old Orderbook's Details window. Left, the fields every order has and the
 * ones that belong to its type; right, the HOME tab. The other tabs (Delivery, Glass C, Timber...)
 * are shown disabled: nothing in the screens says what they hold.
 */
const OTHER_TABS = ["Delivery", "Glass C", "Timber", "Stock", "Tracking", "Supplier", "TGSolid", "Cutlists", "ADMIN"];

export function OrderDetailPanel({
  poId, canEdit, onChanged, canApprove, costCentres, categories, onClose,
}: {
  poId: number; canEdit: boolean; onChanged: () => void;
  categories: OrderCategory[];
  onClose: () => void;
  /** The purchase officer, manager or admin: may set Approved / Rejected or move an order out of them. */
  canApprove: boolean;
  costCentres: CostCentre[];
}) {
  const [order, setOrder] = useState<OrderDetailType | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadErr, setLoadErr] = useState<string | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  // Choosing Rejected asks for the reason first; the status is not sent until it is given.
  const [rejecting, setRejecting] = useState(false);
  const [rejectNote, setRejectNote] = useState("");

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

  async function patchField(field: string, value: unknown, extra?: Record<string, unknown>): Promise<boolean> {
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
          ...extra,
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
      <Backdrop onClose={onClose}>
        <div className="p-6 text-xs text-h-muted">Loading order…</div>
      </Backdrop>
    );
  }
  if (loadErr || !order) {
    return (
      <Backdrop onClose={onClose}>
        <div className="p-6 text-xs text-[#b4443d]">Could not load order: {loadErr}</div>
      </Backdrop>
    );
  }

  // `locked` is the server's answer (Cancelled / Delivered); the API enforces it
  // with 409 ORDER_LOCKED and this only decides which controls to render.
  const frozen = order.locked;
  // Status stays editable on a frozen order (canEdit); everything else follows
  // canEditFields.
  const canEditFields = canEdit && !frozen;
  const hasLines = order.lines.length > 0;

  /** Writes the whole `attributes` object with one key changed (the API replaces it). */
  const saveAttr = (key: string, value: string | boolean) =>
    patchField("attributes", { ...(order.attributes ?? {}), [key]: value });

  /** A number field: refuse a non-number here; with no lines, the sub total follows qty × cost. */
  async function saveNumber(field: "quantity" | "unit_cost" | "total_amount", v: string) {
    const val = v.trim() === "" ? null : v.trim();
    if (val !== null && Number.isNaN(Number(val))) {
      setErrors(e => ({ ...e, [field]: "Enter a number" }));
      return false;
    }
    const q = field === "quantity" ? val : order!.quantity;
    const c = field === "unit_cost" ? val : order!.unit_cost;
    const extra = field !== "total_amount" && !hasLines && q != null && c != null
      ? { total_amount: (Number(q) * Number(c)).toFixed(2) }
      : undefined;
    return patchField(field, val, extra);
  }

  async function saveDescription(v: string) {
    if (!v.trim()) {
      setErrors(e => ({ ...e, description: "A description is needed" }));
      return false;
    }
    return patchField("description", v.trim());
  }

  const categoryOptions = categories.some(c => c.category_key === order.category)
    ? categories
    : [...categories, { category_key: order.category, label: order.category }];

  return (
    <Backdrop onClose={onClose}>
      <div data-testid="order-detail" className="text-xs">
        <header className="flex flex-wrap items-center gap-3 border-b border-h-line bg-h-bg px-4 py-3">
          <h2 className="h-mono text-base text-h-ink">{order.po_number}</h2>
          {order.status === "Pending" && (
            <span className="rounded bg-[#e4574f] px-2 py-0.5 text-[10px] font-bold tracking-wide text-white">NEW!</span>
          )}
          {canEdit ? (
            <select
              value={order.status}
              onChange={e => {
                if (e.target.value === "Rejected") { setRejecting(true); return; }
                void patchField("status", e.target.value);
              }}
              // Once an order is Approved or Rejected only a decider (purchase officer, manager, admin)
              // may move it on; the API refuses anyone else.
              disabled={!canApprove && (order.status === "Approved" || order.status === "Rejected")}
              data-testid="order-status-select"
              className={`rounded border-0 px-1.5 py-0.5 text-[10px] ${statusClasses(order.status)}`}
            >
              {STATUSES.map(s => (
                <option
                  key={s}
                  value={s}
                  disabled={!canApprove && (s === "Approved" || s === "Rejected") && s !== order.status}
                >
                  {s}
                </option>
              ))}
            </select>
          ) : (
            <span className={`rounded px-1.5 py-0.5 text-[10px] ${statusClasses(order.status)}`}>
              {order.status}
            </span>
          )}
          <button
            type="button"
            onClick={onClose}
            data-testid="order-detail-close"
            className="ml-auto rounded border border-h-line bg-h-surface px-3 py-1 text-sm text-h-ink hover:bg-h-bg"
          >
            Close
          </button>
        </header>

        <div className="px-4 pt-3">
          {errors.status && <ErrorLine msg={errors.status} />}
          {rejecting && (
            <div data-testid="order-reject-form" className="mb-3 rounded border border-h-line bg-h-bg p-2">
              <label className="mb-1 block text-[10px] uppercase tracking-wide text-h-muted" htmlFor="reject-note">
                Why is this order rejected?
              </label>
              <textarea
                id="reject-note"
                value={rejectNote}
                onChange={e => setRejectNote(e.target.value)}
                rows={2}
                data-testid="order-reject-note"
                className="w-full rounded border border-h-line bg-h-surface px-1.5 py-1 text-h-ink"
              />
              <div className="mt-1 flex gap-2">
                <button
                  type="button"
                  data-testid="order-reject-confirm"
                  disabled={!rejectNote.trim()}
                  onClick={async () => {
                    if (await patchField("status", "Rejected", { rejection_note: rejectNote.trim() })) {
                      setRejecting(false);
                      setRejectNote("");
                    }
                  }}
                  className="rounded border border-h-line bg-h-surface px-2 py-0.5 hover:text-h-ink disabled:opacity-50"
                >
                  Reject order
                </button>
                <button
                  type="button"
                  onClick={() => { setRejecting(false); setRejectNote(""); }}
                  className="rounded border border-h-line bg-h-surface px-2 py-0.5 text-h-muted hover:text-h-ink"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
          {order.status === "Rejected" && order.rejection_note && (
            <p data-testid="order-rejection-note" className="mb-3 rounded border border-h-line bg-h-bg px-2 py-1.5 text-h-muted">
              Rejected: <span className="text-h-ink">{order.rejection_note}</span>
            </p>
          )}
          {canEdit && frozen && (
            <p
              data-testid="order-frozen-banner"
              className="mb-3 rounded border border-h-line bg-h-bg px-2 py-1.5 text-h-muted"
            >
              This order is {order.status} and read-only. Change its status above to
              edit it again.
            </p>
          )}
        </div>

        <div className="grid gap-6 px-4 pb-4 lg:grid-cols-2">
          <dl className="self-start rounded border border-h-line">
            <TextRow label="Order number" value={order.order_number} canEdit={canEditFields} mono
              onSave={v => patchField("order_number", v || null)} error={errors.order_number} />
            <SelectRow label="Priority" value={order.priority} canEdit={canEditFields}
              options={PRIORITIES.map(p => ({ value: p, label: p }))}
              onSave={v => patchField("priority", v)} error={errors.priority} />
            <TextRow label="Date required" type="date" value={order.required_date} canEdit={canEditFields} mono
              onSave={v => patchField("required_date", v || null)} error={errors.required_date} />
            <Row label="Project">{order.project_name ?? "—"}</Row>
            <TextRow label="Location" value={order.location} canEdit={canEditFields}
              onSave={v => patchField("location", v || null)} error={errors.location} />
            <Row label="Supplier">{order.vendor_name ?? "—"}</Row>
            <SelectRow label="Order type" value={order.category} canEdit={canEditFields} testId="order-category"
              options={categoryOptions.map(c => ({ value: c.category_key, label: c.label }))}
              onSave={v => patchField("category", v)} error={errors.category} />
            {/* Q428: the PARENT Joinery Item's number on a related part's order. */}
            <Row label="Cutlist no."><span className="h-mono">{order.cutlist_no ?? "—"}</span></Row>
            <TextRow label="Supplier ref no." value={order.supplier_ref_no} canEdit={canEditFields} mono
              onSave={v => patchField("supplier_ref_no", v || null)} error={errors.supplier_ref_no} />
            <Row label="Item"><span className="h-mono">{order.item_number ?? "—"}</span></Row>
            <Row label="Requested by">{order.requester_name ?? "—"}</Row>
            <Row label="Requested date"><span className="h-mono">{order.requested_date ?? "—"}</span></Row>
            <TextRow label="Product code" value={order.product_code} canEdit={canEditFields} mono
              onSave={v => patchField("product_code", v || null)} error={errors.product_code} />
            <CheckRow label="Stock tracked" value={order.stock_tracked} canEdit={canEditFields}
              onSave={v => patchField("stock_tracked", v)} error={errors.stock_tracked} />
            <TextRow label="Qty" value={qty(order.quantity)} canEdit={canEditFields} mono
              onSave={v => saveNumber("quantity", v)} error={errors.quantity} />
            <OrderTypeFields category={order.category} attributes={order.attributes ?? {}}
              canEdit={canEditFields} onSave={saveAttr} />
            {errors.attributes && <div className="px-2 pb-1"><ErrorLine msg={errors.attributes} /></div>}
            {order.category !== "Acoustic" && order.category !== "Benchtop" && (
              <AreaRow label="Description" rows={4} value={order.description} canEdit={canEditFields}
                onSave={saveDescription}
                error={errors.description} />
            )}
            <CheckRow label="GST applicable" value={order.gst_applicable} canEdit={canEditFields}
              onSave={v => patchField("gst_applicable", v)} error={errors.gst_applicable} />
            <CheckRow label="GST included in price?" value={order.gst_included_in_price} canEdit={canEditFields}
              onSave={v => patchField("gst_included_in_price", v)} error={errors.gst_included_in_price} />
            <TextRow label="Cost" value={dec2(order.unit_cost)} canEdit={canEditFields} mono
              onSave={v => saveNumber("unit_cost", v)} error={errors.unit_cost} />
            <TextRow label="UM" value={order.unit_of_measure} canEdit={canEditFields}
              onSave={v => patchField("unit_of_measure", v || null)} error={errors.unit_of_measure} />
            {/* With lines, the sub total is their sum and not editable; the database makes GST and
                the grand total from it. */}
            <TextRow label="Sub total" value={dec2(order.total_amount)} canEdit={canEditFields && !hasLines} mono
              onSave={v => saveNumber("total_amount", v)} error={errors.total_amount} />
            <Row label="GST"><span className="h-mono">{money(order.gst_amount, order.currency)}</span></Row>
            <Row label="Grand total"><span className="h-mono font-semibold">{money(order.grand_total, order.currency)}</span></Row>
            <div className="border-t border-h-line p-2">
              <CostCentreField
                value={order.cost_center_id}
                label={order.cost_center_code ? `${order.cost_center_code} ${order.cost_center_name ?? ""}`.trim() : null}
                costCentres={costCentres}
                canEdit={canEditFields}
                onSave={id => patchField("cost_center_id", id)}
                error={errors.cost_center_id}
              />
            </div>
          </dl>

          <div className="grid content-start gap-3">
            <div className="flex flex-wrap items-center gap-1 border-b border-h-line pb-2">
              <span className="rounded bg-h-accent px-2.5 py-1 text-[11px] font-medium text-white">HOME</span>
              {OTHER_TABS.map(t => (
                <button key={t} type="button" disabled
                  title="Not built: nothing in the customer's screens says what this tab holds"
                  className="rounded px-2 py-1 text-[11px] text-h-muted opacity-40">{t}</button>
              ))}
            </div>
            <div>
              <button type="button" disabled data-testid="order-create-po"
                title="Not built yet: what Create PO! should do is not decided"
                className="rounded border border-h-line bg-h-bg px-4 py-2 text-sm font-semibold text-h-ink opacity-50">
                Create PO!
              </button>
            </div>
            <div className="grid grid-cols-2 gap-3">
              {["FILE", "PDF"].map(t => (
                <div key={t} className="rounded border border-dashed border-h-line p-2 text-h-muted opacity-60">
                  <div className="text-[10px] font-semibold uppercase tracking-wide text-h-ink">{t}</div>
                  <div>{order.has_attachment ? "Attached" : "Attachments are not built yet"}</div>
                </div>
              ))}
            </div>
            <div className="grid grid-cols-[8rem_1fr] gap-3">
              <div className="flex h-28 items-center justify-center rounded border border-h-line bg-h-bg text-h-muted">
                Product image
              </div>
              <dl className="rounded border border-h-line">
                <TextRow label="Website" value={order.product_website} canEdit={canEditFields}
                  onSave={v => patchField("product_website", v || null)} error={errors.product_website} />
                <AreaRow label="Description" rows={3} value={order.product_description} canEdit={canEditFields}
                  onSave={v => patchField("product_description", v || null)} error={errors.product_description} />
              </dl>
            </div>
            <div>
              <p className="mb-1 text-[10px] uppercase tracking-wide text-h-muted">Change log</p>
              <p className="min-h-10 whitespace-pre-wrap rounded border border-h-line bg-h-bg px-2 py-1 text-h-muted">
                {order.changelog || "—"}
              </p>
            </div>
            <dl className="rounded border border-h-line">
              <AreaRow label="Line item comments" rows={2} value={order.line_item_comments} canEdit={canEditFields}
                onSave={v => patchField("line_item_comments", v || null)} error={errors.line_item_comments} />
              <AreaRow label="Internal comments" rows={4} value={order.internal_comments} canEdit={canEditFields}
                onSave={v => patchField("internal_comments", v || null)} error={errors.internal_comments} />
            </dl>
            <p className="-mt-2 text-[10px] text-h-muted">
              Line item comments are seen on the purchase order; internal comments are not.
            </p>
            <dl className="grid grid-cols-4 rounded border border-h-line text-center">
              {[
                ["Requested", order.requested_date, null],
                ["Ordered", order.date_ordered, "date_ordered"],
                ["Due", order.due_date, "due_date"],
                ["Arrived", order.arrived_date, "arrived_date"],
              ].map(([label, value, field]) => (
                <div key={label as string} className="border-r border-h-line p-1.5 last:border-r-0">
                  <dt className="text-[10px] font-semibold uppercase tracking-wide text-h-muted">{label}</dt>
                  <dd className="mt-0.5">
                    {field && canEditFields ? (
                      <input type="date" defaultValue={(value as string | null) ?? ""} key={(value as string | null) ?? ""}
                        data-testid={`order-${field}`}
                        onBlur={async e => {
                          const el = e.target;
                          if (el.value !== ((value as string | null) ?? "")
                            && !(await patchField(field as string, el.value || null))) el.value = (value as string | null) ?? "";
                        }}
                        className="h-mono w-full rounded border border-h-line bg-h-bg px-1 py-0.5 text-h-ink" />
                    ) : (
                      <span className="h-mono">{(value as string | null) ?? "—"}</span>
                    )}
                    {field && errors[field as string] && <ErrorLine msg={errors[field as string]} />}
                  </dd>
                </div>
              ))}
            </dl>
          </div>
        </div>

        <div className="px-4 pb-4">
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
      </div>
    </Backdrop>
  );
}

/** The pop-up shell: a click on the dim background or Escape closes it. */
function Backdrop({ onClose, children }: { onClose: () => void; children: React.ReactNode }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/40 p-4"
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div role="dialog" aria-label="Order details"
        className="w-full max-w-5xl rounded-lg border border-h-line bg-h-surface shadow-xl">
        {children}
      </div>
    </div>
  );
}
