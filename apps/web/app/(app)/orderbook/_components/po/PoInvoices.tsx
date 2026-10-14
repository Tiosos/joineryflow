"use client";

import type { PoDoc, PoInvoice } from "@/lib/po-types";
import { fmtDate, money } from "../orders/shared";

/**
 * The PO screen's Invoice Details table: one row per invoice against a line of this PO. A row opens
 * the Invoice Details window; invoices are added from the "Invoiced" tick of a line.
 */
export function PoInvoices({ doc, onOpen }: { doc: PoDoc; onOpen: (i: PoInvoice) => void }) {
  return (
    <section data-testid="po-invoices" className="grid gap-1">
      <h3 className="text-[10px] font-semibold uppercase tracking-wide text-h-ink">Invoice details</h3>
      <div className="overflow-x-auto rounded border border-h-line">
        <table className="w-full border-collapse">
          <thead className="bg-h-bg text-left text-[10px] uppercase tracking-wide text-h-muted">
            <tr><th className="px-2 py-1">Line</th><th className="px-2 py-1">Invoice number</th><th className="px-2 py-1">Invoiced</th>
              <th className="px-2 py-1 text-right">Qty</th><th className="px-2 py-1">Item</th><th className="px-2 py-1">PCode</th>
              <th className="px-2 py-1">Notes</th><th className="px-2 py-1">Delv doc</th><th className="px-2 py-1 text-right">Total (inc $)</th><th /></tr>
          </thead>
          <tbody>
            {doc.invoices.length === 0 && <tr><td colSpan={10} className="px-2 py-2 text-h-muted">No invoices yet. Tick Invoiced on a line to add one.</td></tr>}
            {doc.invoices.map(i => (
              <tr key={i.invoice_id} data-testid="po-invoice-row" className="border-t border-h-line">
                <td className="px-2 py-1 h-mono">{i.line_no}</td>
                <td className="px-2 py-1 h-mono text-h-ink">{i.invoice_number}</td>
                <td className="px-2 py-1 h-mono text-h-muted">{fmtDate(i.invoiced_date)}</td>
                <td className="px-2 py-1 text-right h-mono">{i.qty != null ? String(Number(i.qty)) : ""}</td>
                <td className="px-2 py-1 text-h-ink">{i.description}</td>
                <td className="px-2 py-1 h-mono">{i.product_code ?? ""}</td>
                <td className="px-2 py-1 text-h-muted">{i.notes ?? ""}</td>
                <td className="px-2 py-1 text-h-muted">{i.delivery_doc_mime ? "✓" : "—"}</td>
                <td className="px-2 py-1 text-right h-mono">{i.total_inc != null ? money(i.total_inc, null) : ""}</td>
                <td className="px-2 py-1 text-right">
                  <button type="button" data-testid="po-invoice-open" aria-label={`Open invoice ${i.invoice_number}`} onClick={() => onOpen(i)}
                    className="rounded border border-h-line bg-h-bg px-1.5 text-h-muted hover:text-h-ink">Open</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
