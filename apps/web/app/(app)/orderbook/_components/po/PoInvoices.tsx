"use client";

import { useState } from "react";
import type { PoDoc } from "@/lib/po-types";
import { fmtDate, money } from "../orders/shared";

const INPUT = "rounded border border-h-line bg-h-bg px-1.5 py-1 text-h-ink focus:outline-none focus:ring-1 focus:ring-h-accent";

/** The PO screen's Invoice Details table: one row per invoice against a line of this PO. */
export function PoInvoices({
  doc, canEdit, send,
}: {
  doc: PoDoc; canEdit: boolean;
  send: (method: string, path: string, body?: unknown) => Promise<boolean>;
}) {
  const [adding, setAdding] = useState(false);
  const [f, setF] = useState({ order_id: "", invoice_number: "", invoiced_date: "", qty: "", total_inc: "", delivery_doc: "" });
  const set = (k: keyof typeof f, v: string) => setF(x => ({ ...x, [k]: v }));
  const orderLines = doc.lines.filter(l => !l.is_delivery);

  async function add() {
    const body = {
      order_id: Number(f.order_id), invoice_number: f.invoice_number,
      invoiced_date: f.invoiced_date || null, qty: f.qty || null,
      total_inc: f.total_inc || null, delivery_doc: f.delivery_doc || null,
    };
    if (await send("POST", `/invoices`, body)) {
      setAdding(false);
      setF({ order_id: "", invoice_number: "", invoiced_date: "", qty: "", total_inc: "", delivery_doc: "" });
    }
  }

  return (
    <section data-testid="po-invoices" className="grid gap-1">
      <div className="flex items-center gap-2">
        <h3 className="text-[10px] font-semibold uppercase tracking-wide text-h-ink">Invoice details</h3>
        {canEdit && doc.status === "Open" && (
          <button type="button" data-testid="po-invoice-add" onClick={() => setAdding(a => !a)}
            className="rounded border border-h-line bg-h-bg px-2 py-0.5 text-h-muted hover:text-h-ink">{adding ? "−" : "+"}</button>
        )}
      </div>
      {adding && (
        <div className="flex flex-wrap items-end gap-2">
          <select aria-label="Line" value={f.order_id} onChange={e => set("order_id", e.target.value)} data-testid="po-invoice-line" className={INPUT}>
            <option value="">Line…</option>
            {orderLines.map(l => <option key={l.order_id} value={l.order_id}>{l.line_no} · {l.description}</option>)}
          </select>
          <input aria-label="Invoice number" placeholder="Invoice no." value={f.invoice_number} onChange={e => set("invoice_number", e.target.value)} data-testid="po-invoice-number" className={`${INPUT} w-28`} />
          <input aria-label="Invoice date" type="date" value={f.invoiced_date} onChange={e => set("invoiced_date", e.target.value)} className={INPUT} />
          <input aria-label="Quantity" placeholder="Qty" value={f.qty} onChange={e => set("qty", e.target.value)} className={`${INPUT} w-16`} />
          <input aria-label="Total inc GST" placeholder="Total inc" value={f.total_inc} onChange={e => set("total_inc", e.target.value)} className={`${INPUT} w-24`} />
          <input aria-label="Delivery doc" placeholder="Delivery doc" value={f.delivery_doc} onChange={e => set("delivery_doc", e.target.value)} className={`${INPUT} w-28`} />
          <button type="button" data-testid="po-invoice-save" disabled={!f.order_id || !f.invoice_number.trim()} onClick={() => void add()}
            className="rounded border border-h-line bg-h-surface px-3 py-1 text-h-ink hover:bg-h-bg disabled:opacity-50">Add</button>
        </div>
      )}
      <table className="w-full border-collapse">
        <thead className="text-left text-[10px] uppercase tracking-wide text-h-muted">
          <tr><th className="px-2 py-1">Line</th><th className="px-2 py-1">Item</th><th className="px-2 py-1">Invoice</th>
            <th className="px-2 py-1">Date</th><th className="px-2 py-1 text-right">Qty</th><th className="px-2 py-1 text-right">Total inc</th>
            <th className="px-2 py-1">Delivery doc</th><th /></tr>
        </thead>
        <tbody>
          {doc.invoices.length === 0 && <tr><td colSpan={8} className="px-2 py-2 text-h-muted">No invoices yet.</td></tr>}
          {doc.invoices.map(i => (
            <tr key={i.invoice_id} data-testid="po-invoice-row" className="border-t border-h-line">
              <td className="px-2 py-1 h-mono">{i.line_no}</td>
              <td className="px-2 py-1 text-h-ink">{i.description}</td>
              <td className="px-2 py-1 h-mono text-h-ink">{i.invoice_number}</td>
              <td className="px-2 py-1 h-mono text-h-muted">{fmtDate(i.invoiced_date)}</td>
              <td className="px-2 py-1 text-right h-mono">{i.qty != null ? String(Number(i.qty)) : ""}</td>
              <td className="px-2 py-1 text-right h-mono">{i.total_inc != null ? money(i.total_inc, null) : ""}</td>
              <td className="px-2 py-1 h-mono text-h-muted">{i.delivery_doc ?? ""}</td>
              <td className="px-2 py-1 text-right">
                {canEdit && doc.status === "Open" && (
                  <button type="button" aria-label="Remove invoice" data-testid="po-invoice-remove"
                    onClick={() => void send("DELETE", `/invoices/${i.invoice_id}`)}
                    className="rounded border border-h-line bg-h-bg px-1.5 text-h-muted hover:text-h-ink">−</button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
