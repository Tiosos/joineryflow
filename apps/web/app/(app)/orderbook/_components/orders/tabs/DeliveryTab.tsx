"use client";

import { useCallback, useEffect, useState } from "react";
import { apiCall, jsonInit } from "@/lib/api";
import type { DeliveryLog } from "@/lib/order-tabs-types";
import type { OrderDetail } from "@/lib/orders-types";

const INPUT = "w-full rounded border border-h-line bg-h-bg px-1.5 py-1 text-h-ink focus:outline-none focus:ring-1 focus:ring-h-accent disabled:opacity-60";
const TH = "border border-h-line bg-h-bg px-2 py-1 text-left text-[10px] font-semibold uppercase tracking-wide text-h-muted";
const TD = "border border-h-line px-1 py-1";
const MINI = "rounded border border-h-line bg-h-bg px-1.5 py-0.5 text-h-muted hover:text-h-ink disabled:opacity-40";
const today = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; };
const num = (v: string | null) => (v == null ? "" : String(Number(v)));

/**
 * The old Delivery Log tab: one row per delivery received (qty, date, signed by, noted, and the docket
 * as a file), then Stock tracked, Sum received, Tot remaining, Received by and Date delivered. The log
 * is a record only: it does not change the order's status.
 */
export function DeliveryTab({
  order, canEdit, patchField, onChanged,
}: {
  order: OrderDetail; canEdit: boolean; onChanged: () => void;
  patchField: (field: string, value: unknown) => Promise<boolean>;
}) {
  const base = `/api/orders/${order.po_id}/deliveries`;
  const [log, setLog] = useState<DeliveryLog | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [add, setAdd] = useState({ qty: "", date_received: today(), signed_by: "", notes: "" });

  const load = useCallback(() => apiCall<DeliveryLog>(base).then(setLog).catch(() => setErr("Could not load the delivery log")), [base]);
  useEffect(() => { void load(); }, [load]);

  const run = async (fn: () => Promise<DeliveryLog>) => {
    try { setLog(await fn()); setErr(null); onChanged(); return true; }
    catch (e) { setErr((e as Error).message === "ORDER_LOCKED" ? "This order is closed: its delivery log is read-only" : "Could not save that change"); return false; }
  };
  const patchRow = (id: number, body: Record<string, unknown>) => run(() => apiCall<DeliveryLog>(`${base}/${id}`, jsonInit("PATCH", body)));

  async function upload(id: number, file: File) {
    const fd = new FormData(); fd.append("file", file);
    const r = await fetch(`${base}/${id}/docket`, { method: "POST", body: fd }).catch(() => null);
    if (!r || !r.ok) { setErr(r?.status === 415 ? "A docket must be a PDF, PNG or JPEG" : "Could not attach the docket"); return; }
    setLog((await r.json()) as DeliveryLog); setErr(null);
  }

  return (
    <div data-testid="tab-delivery" className="grid gap-3">
      {err && <p role="alert" data-testid="delivery-error" className="text-[#b4443d]">{err}</p>}
      <div className="overflow-x-auto">
        <table className="w-full border-collapse">
          <thead><tr><th className={TH}>Qty rec&apos;d</th><th className={TH}>Date rec&apos;d</th><th className={TH}>Signed by</th><th className={TH}>Noted</th><th className={TH} /></tr></thead>
          <tbody>
            {(log?.deliveries ?? []).map(d => (
              <tr key={d.delivery_id} data-testid="delivery-row">
                <td className={TD}><input aria-label="Quantity received" disabled={!canEdit} defaultValue={num(d.qty)} key={`q${d.qty}`}
                  onBlur={e => { if (e.target.value !== num(d.qty)) void patchRow(d.delivery_id, { qty: e.target.value }).then(ok => { if (!ok) e.target.value = num(d.qty); }); }} className={`${INPUT} h-mono text-right`} /></td>
                <td className={TD}><input type="date" aria-label="Date received" disabled={!canEdit} defaultValue={d.date_received} key={`d${d.date_received}`}
                  onBlur={e => { if (e.target.value && e.target.value !== d.date_received) void patchRow(d.delivery_id, { date_received: e.target.value }); }} className={INPUT} /></td>
                <td className={TD}><input aria-label="Signed by" disabled={!canEdit} defaultValue={d.signed_by ?? ""} key={`s${d.signed_by}`}
                  onBlur={e => { if (e.target.value !== (d.signed_by ?? "")) void patchRow(d.delivery_id, { signed_by: e.target.value || null }); }} className={INPUT} /></td>
                <td className={TD}><input aria-label="Notes" disabled={!canEdit} defaultValue={d.notes ?? ""} key={`n${d.notes}`}
                  onBlur={e => { if (e.target.value !== (d.notes ?? "")) void patchRow(d.delivery_id, { notes: e.target.value || null }); }} className={INPUT} /></td>
                <td className={`${TD} whitespace-nowrap text-right`}>
                  {d.has_docket ? (
                    <>
                      <a href={`${base}/${d.delivery_id}/docket`} target="_blank" rel="noreferrer" data-testid="delivery-docket-link" className={MINI}>Docket</a>
                      {canEdit && <button type="button" aria-label="Remove docket" className={`${MINI} ml-1`}
                        onClick={() => void run(() => apiCall<DeliveryLog>(`${base}/${d.delivery_id}/docket`, { method: "DELETE" }))}>×</button>}
                    </>
                  ) : canEdit ? (
                    <label className={`${MINI} cursor-pointer`} title="Attach the delivery docket (PDF, PNG or JPEG)">↑ Docket
                      <input type="file" accept="application/pdf,image/png,image/jpeg" className="sr-only" data-testid="delivery-docket-file"
                        onChange={e => { const f = e.target.files?.[0]; e.target.value = ""; if (f) void upload(d.delivery_id, f); }} />
                    </label>
                  ) : null}
                  {canEdit && <button type="button" aria-label="Remove delivery" data-testid="delivery-remove" className={`${MINI} ml-1`}
                    onClick={() => void run(() => apiCall<DeliveryLog>(`${base}/${d.delivery_id}`, { method: "DELETE" }))}>−</button>}
                </td>
              </tr>
            ))}
            {log && log.deliveries.length === 0 && <tr><td colSpan={5} className={`${TD} px-2 text-h-muted`}>No deliveries logged yet.</td></tr>}
            {canEdit && (
              <tr data-testid="delivery-add-row" className="bg-h-bg">
                <td className={TD}><input aria-label="New quantity" placeholder="Qty" value={add.qty} data-testid="delivery-new-qty"
                  onChange={e => setAdd({ ...add, qty: e.target.value })} className={`${INPUT} h-mono text-right`} /></td>
                <td className={TD}><input type="date" aria-label="New date" value={add.date_received} onChange={e => setAdd({ ...add, date_received: e.target.value })} className={INPUT} /></td>
                <td className={TD}><input aria-label="New signed by" placeholder="Signed by" value={add.signed_by} onChange={e => setAdd({ ...add, signed_by: e.target.value })} className={INPUT} /></td>
                <td className={TD}><input aria-label="New notes" placeholder="Noted…" value={add.notes} onChange={e => setAdd({ ...add, notes: e.target.value })} className={INPUT} /></td>
                <td className={`${TD} text-right`}>
                  <button type="button" data-testid="delivery-add" className={MINI} disabled={!(Number(add.qty) > 0) || !add.date_received}
                    onClick={() => void run(() => apiCall<DeliveryLog>(base, jsonInit("POST", {
                      qty: add.qty, date_received: add.date_received, signed_by: add.signed_by.trim() || null, notes: add.notes.trim() || null,
                    }))).then(ok => { if (ok) setAdd({ qty: "", date_received: today(), signed_by: "", notes: "" }); })}>+ Add</button>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <div className="grid max-w-md gap-1">
        <label className="flex items-center gap-2"><span className="w-32 text-[10px] font-semibold uppercase tracking-wide text-h-muted">Stock tracked</span>
          <input type="checkbox" disabled={!canEdit} checked={!!order.stock_tracked} data-testid="delivery-stock-tracked"
            onChange={e => void patchField("stock_tracked", e.target.checked)} /></label>
        <div className="flex items-center gap-2"><span className="w-32 text-[10px] font-semibold uppercase tracking-wide text-h-muted">Sum received</span>
          <span data-testid="delivery-sum" className="h-mono text-h-ink">{log ? num(log.sum_received) : ""}</span></div>
        <div className="flex items-center gap-2"><span className="w-32 text-[10px] font-semibold uppercase tracking-wide text-h-muted">Tot remaining</span>
          <span data-testid="delivery-remaining" className="h-mono text-h-ink">{log?.remaining != null ? num(log.remaining) : "—"}</span></div>
        <label className="flex items-center gap-2"><span className="w-32 text-[10px] font-semibold uppercase tracking-wide text-h-muted">Received by</span>
          <input disabled={!canEdit} defaultValue={order.received_by ?? ""} key={order.received_by ?? ""} data-testid="delivery-received-by" className={INPUT}
            onBlur={e => { if (e.target.value !== (order.received_by ?? "")) void patchField("received_by", e.target.value || null); }} /></label>
        <label className="flex items-center gap-2"><span className="w-32 text-[10px] font-semibold uppercase tracking-wide text-h-muted">Date delivered</span>
          <input type="date" disabled={!canEdit} defaultValue={order.arrived_date ?? ""} key={order.arrived_date ?? ""} data-testid="delivery-date-delivered" className={INPUT}
            onBlur={e => { if (e.target.value !== (order.arrived_date ?? "")) void patchField("arrived_date", e.target.value || null); }} />
        </label>
      </div>
    </div>
  );
}
