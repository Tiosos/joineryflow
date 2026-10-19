"use client";

import { useEffect, useRef, useState } from "react";
import { apiCall, jsonInit } from "@/lib/api";
import type { InvoiceSlot, PaymentMethod, PoDoc, PoInvoice, PoLine } from "@/lib/po-types";
import { fmtDate } from "../orders/shared";
import { PaymentMethodSelect } from "./PaymentMethodSelect";
import { useConfirm } from "@/components/confirm/ConfirmProvider";

const INPUT = "w-full rounded border border-h-line bg-h-bg px-1.5 py-1 text-h-ink focus:outline-none focus:ring-1 focus:ring-h-accent disabled:opacity-60";
const BTN = "rounded border border-h-line bg-h-bg px-3 py-1 text-h-ink hover:bg-h-surface disabled:opacity-50";
const CELL = "border border-h-line px-2 py-1.5";
const LABEL = `${CELL} bg-h-bg text-h-muted`;
const GST_RATE = 0.1;
const SLOTS: { key: InvoiceSlot; label: string; field: "delivery_doc_mime" | "invoice_doc_mime" | "non_delivery_mime" }[] = [
  { key: "delivery", label: "Delivery Doc", field: "delivery_doc_mime" },
  { key: "invoice", label: "Invoice Doc", field: "invoice_doc_mime" },
  { key: "non_delivery", label: "Non Delivery", field: "non_delivery_mime" },
];
const refusal: Record<string, string> = {
  PO_CANCELLED: "This PO is cancelled", PAYMENT_METHOD_NOT_FOUND: "That payment method is not available",
  INVOICE_NOT_FOUND: "That invoice no longer exists",
};

const num = (s: string) => (s.trim() === "" || Number.isNaN(Number(s)) ? null : Number(s));
const two = (n: number) => (Math.round((n + Number.EPSILON) * 100) / 100).toFixed(2);
const today = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; };
const stamp = (iso: string) => { const d = new Date(iso); return `${fmtDate(iso.slice(0, 10))} ${d.toLocaleTimeString()}`; };

type Draft = {
  invoice_number: string; invoiced_date: string; qty: string; payment_method_id: number | null;
  total_ex: string; gst: string; gst_auto: boolean; notes: string;
};

function fromInvoice(i: PoInvoice): Draft {
  return {
    invoice_number: i.invoice_number, invoiced_date: i.invoiced_date ?? "", qty: i.qty != null ? String(Number(i.qty)) : "",
    payment_method_id: i.payment_method_id, total_ex: i.total_ex ?? "", gst: i.gst ?? "", gst_auto: i.gst_auto, notes: i.notes ?? "",
  };
}

/** A new invoice starts from what is still to invoice on the line, priced at the line's unit cost. */
function blank(line: PoLine, others: PoInvoice[]): Draft {
  const ordered = line.quantity != null ? Number(line.quantity) : null;
  const done = others.reduce((t, i) => t + (i.qty != null ? Number(i.qty) : 0), 0);
  const q = ordered != null ? Math.max(ordered - done, 0) || ordered : null;
  const ex = q != null && line.unit_cost != null ? two(q * Number(line.unit_cost)) : "";
  return { invoice_number: "", invoiced_date: today(), qty: q != null ? String(q) : "", payment_method_id: null,
    total_ex: ex, gst: "", gst_auto: true, notes: "" };
}

/** What the server will store for these figures: GST 10% of Ex while auto, else typed; Inc = Ex + GST. */
function figures(d: Draft) {
  const ex = num(d.total_ex);
  if (ex == null) return { gst: d.gst_auto ? null : num(d.gst), inc: null as number | null };
  const gst = d.gst_auto ? Number(two(ex * GST_RATE)) : (num(d.gst) ?? 0);
  return { gst, inc: ex + gst };
}

/**
 * The old Invoice Details window, opened by ticking "Invoiced" on a PO line (or a row of the Invoice
 * Details table). Fields save as they are left (the record is made once the Invoice No is typed), and
 * Close saves what is still being typed, like the PO panel.
 */
export function InvoiceWindow({
  doc, line, invoiceId, editable, methods, canKeep, onListChanged, apply, onSwitch, onClose,
}: {
  doc: PoDoc; line: PoLine; invoiceId: number | null; editable: boolean; methods: PaymentMethod[]; canKeep: boolean;
  onListChanged: () => void; apply: (d: PoDoc) => void; onSwitch: (id: number | null) => void; onClose: () => void;
}) {
  const { confirm } = useConfirm();
  const mine = doc.invoices.filter(i => i.order_id === line.order_id);
  const [recordId, setRecordId] = useState<number | null>(invoiceId);
  const saved = mine.find(i => i.invoice_id === recordId) ?? null;
  const [d, setD] = useState<Draft>(() => (saved ? fromInvoice(saved) : blank(line, mine)));
  const [err, setErr] = useState<string | null>(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<() => void>(() => {});
  const base = `/api/purchase-orders/${doc.po_document_id}`;
  const f = figures(d);
  const canWrite = editable;
  const index = saved ? mine.findIndex(i => i.invoice_id === saved.invoice_id) : -1;

  useEffect(() => {
    // Esc closes this window only: the PO panel under it also listens on window, so stop it there.
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") { e.stopImmediatePropagation(); closeRef.current(); } };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, []);
  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    dialogRef.current?.focus();
    return () => opener?.focus?.();
  }, []);

  const body = (x: Draft) => ({
    invoice_number: x.invoice_number.trim(), invoiced_date: x.invoiced_date || null, qty: num(x.qty),
    payment_method_id: x.payment_method_id, total_ex: num(x.total_ex), gst: x.gst_auto ? undefined : num(x.gst),
    gst_auto: x.gst_auto, notes: x.notes.trim() || null,
  });

  // Saves run one after another: a box losing focus starts one and Close another, and the second must
  // wait for the first (it may be the one that makes the record) instead of being dropped.
  const queue = useRef<Promise<unknown>>(Promise.resolve());
  const docRef = useRef(doc);
  docRef.current = doc;
  const recordRef = useRef<number | null>(invoiceId);
  recordRef.current = recordId;

  /** Save the draft: make the record once it has an Invoice No, otherwise change what differs. True when nothing is left unsaved. */
  function commit(x: Draft = d): Promise<boolean> {
    const run = queue.current.then(() => write(x));
    queue.current = run.catch(() => false);
    return run;
  }

  async function write(x: Draft): Promise<boolean> {
    if (!canWrite) return true;
    const b = body(x);
    const current = docRef.current.invoices.find(i => i.invoice_id === recordRef.current) ?? null;
    if (!b.invoice_number) return current === null;
    try {
      if (current === null) {
        const next = await apiCall<PoDoc>(`${base}/invoices`, jsonInit("POST", { order_id: line.order_id, ...b }));
        const made = next.invoices.filter(i => i.order_id === line.order_id).reduce((a, i) => (i.invoice_id > a ? i.invoice_id : a), 0);
        recordRef.current = made; docRef.current = next;
        setRecordId(made); apply(next);
      } else if (JSON.stringify(body(fromInvoice(current))) !== JSON.stringify(b)) {
        const next = await apiCall<PoDoc>(`${base}/invoices/${current.invoice_id}`, jsonInit("PATCH", b));
        docRef.current = next; apply(next);
      }
      setErr(null);
      return true;
    } catch (e) {
      setErr(refusal[(e as Error).message] ?? "Could not save the invoice");
      return false;
    }
  }

  const closeWithSave = async () => { if (await commit()) onClose(); };
  closeRef.current = () => { void closeWithSave(); };

  /** Change a field; selects and ticks save at once, typed boxes when they lose focus. */
  const set = <K extends keyof Draft>(k: K, v: Draft[K], now = false) => {
    const x = { ...d, [k]: v };
    setD(x);
    if (now) void commit(x);
  };

  async function upload(slot: InvoiceSlot, file: File) {
    if (!saved) return;
    const fd = new FormData(); fd.append("file", file);
    const r = await fetch(`${base}/invoices/${saved.invoice_id}/files/${slot}`, { method: "POST", body: fd }).catch(() => null);
    if (!r || !r.ok) {
      const b = r ? await r.json().catch(() => null) : null;
      setErr(r?.status === 415 ? "Only a PDF, PNG or JPEG can go in this box" : refusal[b?.detail?.code] ?? "Could not attach the file");
      return;
    }
    setErr(null); apply((await r.json()) as PoDoc);
  }

  async function removeFile(slot: InvoiceSlot) {
    if (!saved) return;
    try { apply(await apiCall<PoDoc>(`${base}/invoices/${saved.invoice_id}/files/${slot}`, { method: "DELETE" })); setErr(null); }
    catch { setErr("Could not remove the file"); }
  }

  async function remove() {
    if (!saved || !(await confirm({ title: "Delete this invoice?", confirmLabel: "Delete invoice" }))) return;
    try { apply(await apiCall<PoDoc>(`${base}/invoices/${saved.invoice_id}`, { method: "DELETE" })); onClose(); }
    catch { setErr("Could not delete the invoice"); }
  }

  async function add() {
    if (!(await commit())) return;
    setRecordId(null); onSwitch(null);
  }

  const row = (label: string, child: React.ReactNode, tall = false) => (
    <tr><th scope="row" className={`${LABEL} w-2/5 text-left font-normal ${tall ? "align-top" : ""}`}>{label}</th><td className={CELL}>{child}</td></tr>
  );
  const field = (k: "invoice_number" | "invoiced_date" | "qty", type = "text", extra = "") => (
    <input type={type} disabled={!canWrite} value={d[k]} data-testid={`inv-${k}`} aria-label={k}
      onChange={e => set(k, e.target.value)} onBlur={() => void commit()} className={`${INPUT} ${extra}`} />
  );

  return (
    <div className="fixed inset-0 z-[60] flex items-start justify-center overflow-y-auto bg-black/40 p-4"
      onClick={e => { if (e.target === e.currentTarget) closeRef.current(); }}>
      <div role="dialog" aria-modal="true" aria-labelledby="inv-title" tabIndex={-1} ref={dialogRef} data-testid="invoice-window"
        className="w-full max-w-md rounded-lg border border-h-line bg-h-surface text-xs shadow-xl outline-none">
        <header className="flex items-center gap-2 border-b border-h-line bg-h-bg px-3 py-2">
          <span data-testid="inv-line" className="h-mono rounded border border-h-line bg-h-surface px-2 py-1 text-sm text-h-ink">#{line.line_no}</span>
          <h2 id="inv-title" className="flex-1 text-center text-sm uppercase tracking-wide text-h-ink">Invoice Details</h2>
          {mine.length > 1 && saved && (
            <span className="flex items-center gap-1 text-h-muted">
              <button type="button" aria-label="Previous invoice" disabled={index <= 0}
                onClick={() => void (async () => { if (await commit()) onSwitch(mine[index - 1].invoice_id); })()} className="px-1 disabled:opacity-40">‹</button>
              {index + 1} of {mine.length}
              <button type="button" aria-label="Next invoice" disabled={index >= mine.length - 1}
                onClick={() => void (async () => { if (await commit()) onSwitch(mine[index + 1].invoice_id); })()} className="px-1 disabled:opacity-40">›</button>
            </span>
          )}
          {canWrite && <button type="button" data-testid="inv-add" onClick={() => void add()} disabled={!saved && !d.invoice_number.trim()} className={BTN}>+ Add</button>}
        </header>
        <div className="grid gap-3 p-3">
          {err && <p role="alert" data-testid="inv-error" className="text-[#b4443d]">{err}</p>}
          <div className="rounded border border-h-line px-2 py-2 text-sm text-h-ink">{line.description}</div>
          <table className="w-full border-collapse"><tbody>
            {row("Record ID", <span className="h-mono">{line.order_id}</span>)}
            {row("OrderNumber", <span data-testid="inv-po-no" className="h-mono text-[#b4443d]">{doc.po_no}</span>)}
            {row("Supplier", doc.vendor_name)}
          </tbody></table>
          <table className="w-full border-collapse"><tbody>
            {row("Invoice No", field("invoice_number", "text", "h-mono"))}
            {row("Payment Method", (
              <PaymentMethodSelect label="Payment Method" value={d.payment_method_id} methods={methods} canKeep={canKeep}
                disabled={!canWrite} onChange={id => set("payment_method_id", id, true)} onListChanged={onListChanged} testId="inv-method" />
            ), true)}
            {row("Date Invoiced", field("invoiced_date", "date"))}
          </tbody></table>
          <table className="w-full border-collapse"><tbody>
            {row("Qty Invoiced", field("qty", "number", "text-right font-semibold"))}
            {row("Total Cost (Ex)", (
              <span className="flex items-center gap-1">
                <button type="button" aria-label="Recalculate from quantity and cost" title="Quantity × the line's cost" data-testid="inv-refresh"
                  disabled={!canWrite || num(d.qty) == null || line.unit_cost == null}
                  onClick={() => set("total_ex", two(Number(d.qty) * Number(line.unit_cost)), true)}
                  className="rounded border border-h-line bg-h-bg px-1.5 py-1 text-h-muted hover:text-h-ink disabled:opacity-50">↻</button>
                <input aria-label="Total cost ex GST" disabled={!canWrite} value={d.total_ex} data-testid="inv-total-ex"
                  onChange={e => set("total_ex", e.target.value)} onBlur={() => void commit()} className={`${INPUT} text-right h-mono`} />
              </span>
            ))}
            {row("Total Gst", (
              <span className="flex items-center gap-1">
                <button type="button" role="checkbox" aria-checked={d.gst_auto} aria-label="GST is 10% of Ex" title="Ticked: 10% of Ex. Untick to type your own" data-testid="inv-gst-auto"
                  disabled={!canWrite} onClick={() => {
                    // Unticking starts from the figure that was being worked out, to type over.
                    const x = { ...d, gst_auto: !d.gst_auto, gst: d.gst_auto && f.gst != null ? two(f.gst) : d.gst };
                    setD(x); void commit(x);
                  }}
                  className="rounded border border-h-line bg-h-bg px-1.5 py-1 text-h-muted hover:text-h-ink disabled:opacity-50">{d.gst_auto ? "✓" : "○"}</button>
                {d.gst_auto
                  ? <span data-testid="inv-gst" className="h-mono w-full px-1.5 text-right italic text-h-muted">{f.gst != null ? two(f.gst) : ""}</span>
                  : <input aria-label="Total GST" disabled={!canWrite} value={d.gst} data-testid="inv-gst"
                      onChange={e => set("gst", e.target.value)} onBlur={() => void commit()} className={`${INPUT} text-right h-mono`} />}
              </span>
            ))}
            {row("Total Cost (Inc)", <span data-testid="inv-total-inc" className="h-mono block text-right text-h-ink">{f.inc != null ? two(f.inc) : ""}</span>)}
          </tbody></table>
          <label className="grid gap-0.5 text-h-muted">Notes
            <textarea disabled={!canWrite} rows={2} value={d.notes} data-testid="inv-notes" onChange={e => set("notes", e.target.value)}
              onBlur={() => void commit()} className={INPUT} /></label>
          <div className="grid grid-cols-3 gap-2">
            {SLOTS.map(s => {
              // The stored file is shared by content, so it has no name of its own: show it, not a name.
              const mime = saved?.[s.field] ?? null;
              const url = saved ? `${base}/invoices/${saved.invoice_id}/files/${s.key}` : "";
              const isImage = mime != null && mime.startsWith("image/");
              return (
                <div key={s.key} data-testid={`inv-slot-${s.key}`} className="grid gap-1 text-center">
                  <div className="rounded border border-h-line bg-h-bg px-1 py-1 text-h-muted">{s.label}</div>
                  <div className="grid h-20 place-items-center overflow-hidden rounded border border-h-line">
                    {mime ? (
                      <a href={url} target="_blank" rel="noreferrer" title={`Open ${s.label}`} className="grid h-full w-full place-items-center">
                        {isImage
                          // eslint-disable-next-line @next/next/no-img-element
                          ? <img src={url} alt={s.label} className="max-h-full max-w-full object-contain" />
                          : <span className="px-1 text-h-ink">PDF</span>}
                      </a>
                    ) : canWrite ? (
                      <label className={`cursor-pointer px-1 text-h-muted ${saved ? "hover:text-h-ink" : "opacity-50"}`}
                        title={saved ? "Attach a PDF, PNG or JPEG" : "Type the Invoice No first"}>
                        + file
                        <input type="file" accept="application/pdf,image/png,image/jpeg" disabled={!saved} className="sr-only" data-testid={`inv-file-${s.key}`}
                          onChange={e => { const file = e.target.files?.[0]; e.target.value = ""; if (file) void upload(s.key, file); }} />
                      </label>
                    ) : null}
                  </div>
                  {mime && canWrite && <button data-testid={`inv-file-remove-${s.key}`} type="button" aria-label={`Remove ${s.label}`} onClick={() => void removeFile(s.key)} className="text-[10px] text-h-muted underline hover:text-h-ink">remove</button>}
                </div>
              );
            })}
          </div>
        </div>
        <footer className="flex items-center gap-2 border-t border-h-line bg-h-bg px-3 py-2">
          <button type="button" data-testid="inv-close" onClick={() => closeRef.current()} className={BTN}>Close</button>
          <span data-testid="inv-stamp" className="mx-auto h-mono text-[10px] text-h-muted">{saved ? stamp(saved.updated_at) : ""}</span>
          {canWrite && <button type="button" data-testid="inv-delete" disabled={!saved} onClick={() => void remove()} className={`${BTN} text-[#b4443d]`}>Delete</button>}
        </footer>
      </div>
    </div>
  );
}
