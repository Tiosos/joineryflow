"use client";

import { useCallback, useEffect, useState } from "react";
import { can } from "@/lib/permissions";
import type { CostCentre, CreateOrderLineIn, OrderDetail as OrderDetailType, PatchOrderLineIn } from "@/lib/orders-types";
import { STATUSES, PRIORITIES, statusClasses, money, qty, orderLocked, lockedMessage, fieldErrorMessage } from "./shared";
import { CostCentreField } from "./CostCentreField";
import { ErrorLine } from "./ErrorLine";
import { Field } from "./Field";
import { EditableField } from "./EditableField";
import { EditableDateField } from "./EditableDateField";
import { BlurTextArea } from "./BlurTextArea";
import { LinesSection } from "./LinesSection";

export function OrderDetailPanel({
  poId, canEdit, onChanged, canApprove, costCentres,
}: {
  poId: number; canEdit: boolean; onChanged: () => void;
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

  // `locked` is the server's answer (Cancelled / Delivered); the API enforces it
  // with 409 ORDER_LOCKED and this only decides which controls to render.
  const frozen = order.locked;
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
        <CostCentreField
          value={order.cost_center_id}
          label={order.cost_center_code ? `${order.cost_center_code} ${order.cost_center_name ?? ""}`.trim() : null}
          costCentres={costCentres}
          canEdit={canEditFields}
          onSave={id => patchField("cost_center_id", id)}
          error={errors.cost_center_id}
        />
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
