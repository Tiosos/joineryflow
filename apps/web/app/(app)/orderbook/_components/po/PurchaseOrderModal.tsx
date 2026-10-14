"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { OrderRow } from "@/lib/orders-types";
import type { PoDoc, SupplierContact } from "@/lib/po-types";
import { fmtDate, money, qty } from "../orders/shared";
import { PoInvoices } from "./PoInvoices";

const INPUT = "w-full rounded border border-h-line bg-h-bg px-1.5 py-1 text-h-ink focus:outline-none focus:ring-1 focus:ring-h-accent disabled:opacity-60";
const BTN = "rounded border border-h-line bg-h-bg px-3 py-1 text-h-ink hover:bg-h-surface disabled:opacity-50";
type Member = { id: number; full_name: string; email: string };

const initials = (n: string) => n.split(/\s+/).map(w => w[0]).join("").slice(0, 2).toUpperCase();
const refusal: Record<string, string> = {
  ORDER_NOT_OPEN: "That order is closed", ORDER_ALREADY_ON_PO: "That order is already on a PO",
  SUPPLIER_MISMATCH: "That order belongs to another supplier", ORDER_HAS_INVOICES: "Remove its invoices first",
  IS_DELIVERY_ORDER: "Use Delivery to remove the delivery charge", PO_CANCELLED: "This PO is cancelled",
  ORDER_LOCKED: "That order is locked", NO_DELIVERY: "There is no delivery charge",
  PO_HAS_INVOICES: "Remove the invoices first",
};

/**
 * The PO edit panel (the old PurchaseOrder window): header, lines, delivery charge, totals, the
 * supplier's contacts, Email Details (a mailto link: the PDF has to be attached by hand), Add from
 * TBO, Excel / Print / View Pdf / Authorisation Form, and the Invoice Details table.
 */
export function PurchaseOrderModal({
  docId, canEdit, onClose, onChanged,
}: { docId: number; canEdit: boolean; onClose: () => void; onChanged: () => void }) {
  const [doc, setDoc] = useState<PoDoc | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [contacts, setContacts] = useState<SupplierContact[]>([]);
  const [team, setTeam] = useState<Member[]>([]);
  const [ticked, setTicked] = useState<Set<number>>(new Set());
  const [staff, setStaff] = useState<Set<number>>(new Set());
  const [tbo, setTbo] = useState<OrderRow[] | null>(null);
  const [addingId, setAddingId] = useState<number | null>(null);
  const [delivery, setDelivery] = useState("");
  const [newContact, setNewContact] = useState<{ name: string; position: string; mobile: string; email: string } | null>(null);
  const base = `/api/purchase-orders/${docId}`;
  const open = doc?.status === "Open";
  const editable = canEdit && open;

  const load = useCallback(async () => {
    const r = await fetch(base, { cache: "no-store" }).catch(() => null);
    if (!r || !r.ok) { setErr("Could not load the purchase order"); return null; }
    const d = (await r.json()) as PoDoc;
    setDoc(d); setDelivery(d.delivery_charge ?? "");
    return d;
  }, [base]);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    // Names and emails come from the Orderbook-gated staff route; the open team list has no emails.
    fetch("/api/purchase-orders/staff", { cache: "no-store" }).then(r => (r.ok ? r.json() : { staff: [] }))
      .then((b: { staff: Member[] }) => setTeam(b.staff)).catch(() => setTeam([]));
  }, []);
  const vendorId = doc?.vendor_id;
  const loadContacts = useCallback(() => {
    if (vendorId == null) return;
    fetch(`/api/suppliers/${vendorId}/contacts`, { cache: "no-store" }).then(r => (r.ok ? r.json() : { contacts: [] }))
      .then((b: { contacts: SupplierContact[] }) => setContacts(b.contacts)).catch(() => setContacts([]));
  }, [vendorId]);
  useEffect(loadContacts, [loadContacts]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  /** One write against this PO; the reply is the whole PO. True when it worked. */
  const send = useCallback(async (method: string, path: string, body?: unknown) => {
    setErr(null);
    const r = await fetch(`${base}${path}`, {
      method, headers: body === undefined ? undefined : { "content-type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    }).catch(() => null);
    if (!r || !r.ok) {
      const b = r ? await r.json().catch(() => null) : null;
      setErr(refusal[b?.detail?.code] ?? "Could not save that change");
      return false;
    }
    const d = (await r.json()) as PoDoc;
    setDoc(d); setDelivery(d.delivery_charge ?? ""); onChanged();
    return true;
  }, [base, onChanged]);

  const patch = (k: string, v: string) => send("PATCH", "", { [k]: v === "" ? null : v });

  async function showTbo() {
    if (!doc) return;
    if (tbo) { setTbo(null); return; }
    const r = await fetch(`/api/orders?supplier=${encodeURIComponent(doc.vendor_name)}&status=open`, { cache: "no-store" }).catch(() => null);
    const b = r && r.ok ? ((await r.json()) as { orders: OrderRow[] }) : { orders: [] };
    setTbo(b.orders.filter(o => o.vendor_id === doc.vendor_id && o.po_document_id == null));
  }

  async function addContact() {
    if (!newContact || !doc) return;
    const body = Object.fromEntries(Object.entries(newContact).map(([k, v]) => [k, v.trim() || null]));
    const r = await fetch(`/api/suppliers/${doc.vendor_id}/contacts`, {
      method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body),
    }).catch(() => null);
    if (!r || !r.ok) { setErr("Check the contact's name and email address"); return; }
    setNewContact(null); loadContacts();
  }

  const mailto = useMemo(() => {
    if (!doc) return "#";
    // Each address is encoded on its own, so nothing typed into a contact can add a header or a recipient.
    const to = contacts.filter(c => ticked.has(c.contact_id) && c.email).map(c => encodeURIComponent(c.email!)).join(",");
    const cc = team.filter(m => staff.has(m.id)).map(m => encodeURIComponent(m.email)).join(",");
    const subject = `Purchase order ${doc.po_no}${doc.reference_no ? ` (${doc.reference_no})` : ""}`;
    const body = [`Please find purchase order ${doc.po_no} attached.`, "",
      `Total ex GST: $${doc.totals.total_ex}`, `Total inc GST: $${doc.totals.total_inc}`].join("\n");
    return `mailto:${to}?${cc ? `cc=${cc}&` : ""}subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
  }, [doc, contacts, ticked, team, staff]);

  if (!doc) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
        onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
        <div className="flex items-center gap-3 rounded border border-h-line bg-h-surface p-4 text-xs text-h-muted">
          <span data-testid="po-load-state">{err ?? "Loading…"}</span>
          <button type="button" data-testid="po-done" onClick={onClose}
            className="rounded border border-h-line bg-h-bg px-3 py-1 text-h-ink hover:bg-h-surface">Close</button>
        </div>
      </div>
    );
  }
  const toggle = (s: Set<number>, id: number) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; };
  const field = (label: string, k: string, type = "text") => (
    <label className="grid gap-0.5">{label}
      <input key={`${k}-${doc.updated_at}`} type={type} disabled={!editable} defaultValue={(doc as unknown as Record<string, string | null>)[k] ?? ""}
        data-testid={`po-${k}`} onBlur={e => { if (e.target.value !== ((doc as unknown as Record<string, string | null>)[k] ?? "")) void patch(k, e.target.value); }}
        className={INPUT} /></label>
  );

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/40 p-4"
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
      <div role="dialog" aria-label={`Purchase order ${doc.po_no}`} data-testid="po-modal"
        className="w-full max-w-6xl rounded-lg border border-h-line bg-h-surface text-xs shadow-xl">
        <header className="flex flex-wrap items-center gap-3 border-b border-h-line bg-h-bg px-4 py-3">
          <h2 className="text-sm text-h-ink">Purchase order <span data-testid="po-no" className="h-mono">{doc.po_no}</span></h2>
          {!open && <span className="rounded bg-[#f2dcd9] px-1.5 py-0.5 text-[10px] text-[#b4443d]">Cancelled</span>}
          <span className="text-h-muted">{doc.vendor_name}</span>
          <button type="button" onClick={onClose} data-testid="po-done" className="ml-auto rounded border border-h-line bg-h-surface px-4 py-1 text-sm text-h-ink hover:bg-h-bg">Done</button>
        </header>
        <div className="grid gap-4 p-4">
          {err && <p role="alert" data-testid="po-error" className="text-[#b4443d]">{err}</p>}
          <div className="grid gap-3 sm:grid-cols-4">
            {field("Reference no.", "reference_no")}
            <label className="grid gap-0.5">Ordered by
              <select disabled={!editable} value={doc.ordered_by_id ?? ""} data-testid="po-ordered-by"
                onChange={e => void send("PATCH", "", { ordered_by_id: e.target.value ? Number(e.target.value) : null })} className={INPUT}>
                <option value="" />
                {team.map(m => <option key={m.id} value={m.id}>{m.full_name}</option>)}
              </select></label>
            {field("Date ordered", "date_ordered", "date")}
            {field("Date required", "date_required", "date")}
            <div className="sm:col-span-2"><div className="text-h-muted">Supplier</div>
              <div className="text-h-ink">{doc.vendor_name}</div>
              <div className="whitespace-pre-line text-h-muted">{doc.vendor_address}</div></div>
            {field("Date due", "date_due", "date")}
            <div />
            <label className="grid gap-0.5 sm:col-span-2">Memo (to supplier)
              <textarea key={`memo-${doc.updated_at}`} disabled={!editable} defaultValue={doc.memo ?? ""} rows={3} data-testid="po-memo"
                onBlur={e => { if (e.target.value !== (doc.memo ?? "")) void patch("memo", e.target.value); }} className={INPUT} /></label>
            <label className="grid gap-0.5 sm:col-span-2">Deliver to
              <textarea key={`dt-${doc.updated_at}`} disabled={!editable} defaultValue={doc.deliver_to ?? ""} rows={3} data-testid="po-deliver-to"
                onBlur={e => { if (e.target.value !== (doc.deliver_to ?? "")) void patch("deliver_to", e.target.value); }} className={INPUT} /></label>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <span className="text-h-muted">Delivery charge (ex GST)</span>
            <input aria-label="Delivery charge" disabled={!editable} value={delivery} onChange={e => setDelivery(e.target.value)} data-testid="po-delivery" className={`${INPUT} w-24`} />
            {editable && (
              <>
                <button type="button" data-testid="po-add-delivery" disabled={delivery.trim() === "" || Number.isNaN(Number(delivery))}
                  onClick={() => void send("PUT", "/delivery", { amount: delivery })} className={BTN}>{doc.delivery_order_id ? "Update Delivery" : "Add Delivery"}</button>
                {doc.delivery_order_id && <button type="button" onClick={() => void send("DELETE", "/delivery")} className={BTN}>Remove</button>}
              </>
            )}
          </div>

          <div className="overflow-x-auto rounded border border-h-line">
            <table className="w-full border-collapse" data-testid="po-lines">
              <thead className="bg-h-bg text-left text-[10px] uppercase tracking-wide text-h-muted">
                <tr>{["#", "Qty", "Item", "Pcode", "Pdf", "Location", "Project", "Arrived", "Cost", "Um", "Amount $", "Invoiced", ""].map(h => <th key={h} className="px-2 py-1.5">{h}</th>)}</tr>
              </thead>
              <tbody>
                {doc.lines.map(l => (
                  <tr key={l.order_id} data-testid="po-line" className={`border-t border-h-line ${["Cancelled", "Rejected"].includes(l.status) ? "text-h-muted line-through" : ""}`}>
                    <td className="px-2 py-1 h-mono">{l.line_no}</td>
                    <td className="px-2 py-1 text-right h-mono">{qty(l.quantity) ?? ""}</td>
                    <td className="px-2 py-1 text-h-ink">{l.description}</td>
                    <td className="px-2 py-1 h-mono">{l.product_code ?? ""}</td>
                    <td className="px-2 py-1 text-center">{l.has_attachment ? "PDF" : ""}</td>
                    <td className="px-2 py-1">{l.location ?? ""}</td>
                    <td className="px-2 py-1">{l.project_name ?? ""}</td>
                    <td className="px-2 py-1 h-mono">{fmtDate(l.arrived_date)}</td>
                    <td className="px-2 py-1 text-right h-mono">{l.unit_cost != null ? money(l.unit_cost, null) : ""}</td>
                    <td className="px-2 py-1">{l.unit_of_measure ?? ""}</td>
                    <td className="px-2 py-1 text-right h-mono">{l.total_amount != null ? money(l.total_amount, null) : ""}</td>
                    <td className="px-2 py-1 text-center">{l.invoiced ? "✓" : ""}</td>
                    <td className="px-2 py-1 text-right">
                      {editable && !l.is_delivery && (
                        <button type="button" aria-label="Remove line" data-testid="po-line-remove" onClick={() => void send("DELETE", `/orders/${l.order_id}`)}
                          className="rounded border border-h-line bg-h-bg px-1.5 text-h-muted hover:text-h-ink">−</button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {tbo && (
            <div data-testid="po-tbo" className="grid gap-1 rounded border border-h-line bg-h-bg p-2">
              <div className="text-h-muted">Open orders of {doc.vendor_name} not on a PO</div>
              {tbo.length === 0 && <div className="text-h-muted">None.</div>}
              {tbo.map(o => (
                <div key={o.po_id} className="flex items-center gap-2">
                  <span className="h-mono text-h-ink">{o.po_number}</span><span className="text-h-ink">{o.description}</span>
                  <span className="h-mono text-h-muted">{o.total_amount != null ? money(o.total_amount, null) : ""}</span>
                  <button type="button" data-testid="po-tbo-add" className={`${BTN} ml-auto py-0.5`} disabled={addingId !== null}
                    onClick={async () => {
                      setAddingId(o.po_id);
                      if (await send("POST", "/orders", { order_ids: [o.po_id] })) setTbo(t => t && t.filter(x => x.po_id !== o.po_id));
                      setAddingId(null);
                    }}>Add</button>
                </div>
              ))}
            </div>
          )}

          <div className="grid gap-4 sm:grid-cols-[1fr_auto]">
            <div className="grid gap-3">
              <section data-testid="po-contacts" className="grid gap-1">
                <h3 className="text-[10px] font-semibold uppercase tracking-wide text-h-ink">Supplier contacts</h3>
                {contacts.length === 0 && <div className="text-h-muted">No contacts yet.</div>}
                {contacts.map(c => (
                  <label key={c.contact_id} data-testid="po-contact" className="flex items-center gap-2">
                    <input type="checkbox" checked={ticked.has(c.contact_id)} onChange={() => setTicked(s => toggle(s, c.contact_id))} />
                    <span className="text-h-ink">{c.name}</span><span className="text-h-muted">{c.position}</span>
                    <span className="h-mono text-h-muted">{c.mobile}</span><span className="text-h-muted">{c.email}</span>
                    {canEdit && (
                      <button type="button" aria-label={`Delete ${c.name}`} className="ml-auto rounded border border-h-line px-1.5 text-h-muted hover:text-h-ink"
                        onClick={async () => { await fetch(`/api/suppliers/${doc.vendor_id}/contacts/${c.contact_id}`, { method: "DELETE" }); loadContacts(); }}>−</button>
                    )}
                  </label>
                ))}
                {canEdit && (newContact ? (
                  <div className="flex flex-wrap items-end gap-2">
                    {(["name", "position", "mobile", "email"] as const).map(k => (
                      <input key={k} aria-label={`Contact ${k}`} placeholder={k} value={newContact[k]} data-testid={`po-contact-${k}`}
                        onChange={e => setNewContact({ ...newContact, [k]: e.target.value })} className={`${INPUT} w-32`} />
                    ))}
                    <button type="button" data-testid="po-contact-save" disabled={!newContact.name.trim()} onClick={() => void addContact()} className={BTN}>Add contact</button>
                    <button type="button" onClick={() => setNewContact(null)} className={BTN}>Cancel</button>
                  </div>
                ) : (
                  <button type="button" data-testid="po-contact-add" onClick={() => setNewContact({ name: "", position: "", mobile: "", email: "" })}
                    className="w-fit rounded border border-h-line bg-h-bg px-2 py-0.5 text-h-muted hover:text-h-ink">+ Contact</button>
                ))}
              </section>
              <section data-testid="po-staff" className="grid gap-1">
                <h3 className="text-[10px] font-semibold uppercase tracking-wide text-h-ink">Staff (Cc)</h3>
                <div className="flex flex-wrap gap-2">
                  {team.map(m => (
                    <label key={m.id} title={m.full_name} className="flex items-center gap-1">
                      <input type="checkbox" checked={staff.has(m.id)} onChange={() => setStaff(s => toggle(s, m.id))} />
                      <span className="grid h-6 w-6 place-items-center rounded-full bg-h-bg text-[10px] text-h-ink">{initials(m.full_name)}</span>
                    </label>
                  ))}
                </div>
              </section>
            </div>
            <div className="grid content-start gap-1 text-right">
              <div>Total order <span data-testid="po-total-ex" className="h-mono text-h-ink">{money(doc.totals.total_ex, null)}</span></div>
              <div>GST <span className="h-mono text-h-ink">{money(doc.totals.gst, null)}</span></div>
              <div className="font-semibold">Gst inc <span data-testid="po-total-inc" className="h-mono text-h-ink">{money(doc.totals.total_inc, null)}</span></div>
            </div>
          </div>

          <div className="flex flex-wrap gap-2">
            <a href={mailto} data-testid="po-email" title="Opens your mail program; attach the PDF yourself" className={BTN}>Email Details</a>
            {editable && <button type="button" data-testid="po-add-tbo" onClick={() => void showTbo()} className={BTN}>Add from TBO</button>}
            <a href={`${base}/excel`} data-testid="po-excel" className={BTN}>Excel</a>
            <button type="button" data-testid="po-print" className={BTN}
              onClick={() => { const w = window.open(`${base}/pdf`, "_blank"); w?.addEventListener("load", () => w.print()); }}>Print</button>
            <a href={`${base}/pdf`} target="_blank" rel="noreferrer" data-testid="po-pdf" className={BTN}>View Pdf</a>
            <a href={`${base}/authorisation-form`} target="_blank" rel="noreferrer" data-testid="po-auth" className={BTN}>Authorisation Form</a>
            {editable && (
              <button type="button" data-testid="po-cancel" className={`${BTN} ml-auto`}
                onClick={() => { if (window.confirm(`Cancel PO ${doc.po_no}? Its orders go back to unordered.`)) void send("POST", "/cancel"); }}>Cancel PO</button>
            )}
          </div>

          <PoInvoices doc={doc} canEdit={canEdit} send={send} />
        </div>
      </div>
    </div>
  );
}
