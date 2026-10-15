"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { SupplierContacts } from "./SupplierContacts";
import { SUPPLIER_STATUSES, type OrderCategory, type SupplierRecord } from "@/lib/orders-types";

type Draft = {
  name: string; category: string; status: string; contact_name: string; contact_email: string;
  contact_phone: string; address: string; payment_terms: string; website: string; notes: string; metadata: string;
};

const EMPTY: Draft = {
  name: "", category: "Other", status: "Active", contact_name: "", contact_email: "",
  contact_phone: "", address: "", payment_terms: "", website: "", notes: "", metadata: "",
};

const toDraft = (s: SupplierRecord): Draft => ({
  name: s.name, category: s.category, status: s.status, contact_name: s.contact_name ?? "",
  contact_email: s.contact_email ?? "", contact_phone: s.contact_phone ?? "",
  address: s.address ?? "", payment_terms: s.payment_terms ?? "",
  website: s.website ?? "", notes: s.notes ?? "", metadata: s.metadata ?? "",
});

const INPUT = "w-full rounded border border-h-line bg-h-bg px-1.5 py-1 text-h-ink focus:outline-none focus:ring-1 focus:ring-h-accent";

/**
 * The Orderbook's Supplier button: every supplier, their contact details, terms and status, with
 * edit and add (`GET/POST/PATCH /suppliers`, `orderbook:write` to change). Tax ID and rating are
 * not shown. A supplier is never deleted: mark it Inactive.
 */
export function SupplierListModal({
  categories, canEdit, onClose, onChanged,
}: {
  categories: OrderCategory[]; canEdit: boolean; onClose: () => void; onChanged: () => void;
}) {
  const [rows, setRows] = useState<SupplierRecord[]>([]);
  const [loadErr, setLoadErr] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  // `null` = nothing open; "new" = the add form; a vendor_id = that row's editor.
  const [open, setOpen] = useState<number | "new" | null>(null);
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [err, setErr] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  // Bumped after a logo change so the browser fetches the new picture.
  const [logoVersion, setLogoVersion] = useState(0);

  const load = useCallback(() => {
    fetch("/api/suppliers", { cache: "no-store" })
      .then(r => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((b: { suppliers: SupplierRecord[] }) => { setRows(b.suppliers); setLoadErr(null); })
      .catch(e => setLoadErr(String(e)));
  }, []);
  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const shown = useMemo(() => {
    const q = search.trim().toLowerCase();
    return q ? rows.filter(r => [r.name, r.contact_name, r.contact_email].some(v => v?.toLowerCase().includes(q))) : rows;
  }, [rows, search]);

  const set = (k: keyof Draft, v: string) => setDraft(d => ({ ...d, [k]: v }));

  function startEdit(s: SupplierRecord) { setErr(null); setDraft(toDraft(s)); setOpen(s.vendor_id); }
  function startAdd() { setErr(null); setDraft(EMPTY); setOpen("new"); }

  async function uploadLogo(id: number, file: File) {
    const fd = new FormData(); fd.append("file", file);
    const r = await fetch(`/api/suppliers/${id}/logo`, { method: "PUT", body: fd }).catch(() => null);
    if (!r || !r.ok) { setErr(r?.status === 415 ? "A logo must be a PNG or JPEG" : "Could not save the logo"); return; }
    setErr(null); setLogoVersion(v => v + 1); load(); onChanged();
  }

  async function removeLogo(id: number) {
    const r = await fetch(`/api/suppliers/${id}/logo`, { method: "DELETE" }).catch(() => null);
    if (!r || !r.ok) { setErr("Could not remove the logo"); return; }
    setErr(null); setLogoVersion(v => v + 1); load(); onChanged();
  }

  async function save() {
    if (open == null) return;
    if (!draft.name.trim()) { setErr("A supplier needs a name"); return; }
    setSaving(true); setErr(null);
    // Empty optional text is "cleared" on an edit and left out on an add.
    const optional = (v: string) => (v.trim() === "" ? null : v.trim());
    const body = open === "new"
      ? {
          name: draft.name.trim(), category: draft.category,
          ...Object.fromEntries((["contact_name", "contact_email", "contact_phone", "address", "payment_terms", "website", "notes", "metadata"] as const)
            .filter(k => draft[k].trim() !== "").map(k => [k, draft[k].trim()])),
        }
      : {
          name: draft.name.trim(), category: draft.category, status: draft.status,
          contact_name: optional(draft.contact_name), contact_email: optional(draft.contact_email),
          contact_phone: optional(draft.contact_phone), address: optional(draft.address),
          payment_terms: optional(draft.payment_terms),
          website: optional(draft.website), notes: optional(draft.notes), metadata: optional(draft.metadata),
        };
    const res = await fetch(open === "new" ? "/api/suppliers" : `/api/suppliers/${open}`, {
      method: open === "new" ? "POST" : "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    }).catch(() => null);
    setSaving(false);
    if (!res || !res.ok) {
      setErr(res?.status === 422 ? "Check the email address and the other fields" : "Could not save the supplier");
      return;
    }
    setOpen(null);
    load();
    onChanged();
  }

  const form = (
    <div data-testid="supplier-form" className="grid gap-2 rounded border border-h-line bg-h-bg p-3 sm:grid-cols-2">
      <label className="grid gap-0.5">Name
        <input value={draft.name} onChange={e => set("name", e.target.value)} data-testid="supplier-name" className={INPUT} /></label>
      <label className="grid gap-0.5">Category
        <select value={draft.category} onChange={e => set("category", e.target.value)} className={INPUT}>
          {categories.map(c => <option key={c.category_key} value={c.category_key}>{c.label}</option>)}
        </select></label>
      {open !== "new" && (
        <label className="grid gap-0.5">Status
          <select value={draft.status} onChange={e => set("status", e.target.value)} data-testid="supplier-status" className={INPUT}>
            {SUPPLIER_STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
          </select></label>
      )}
      <label className="grid gap-0.5">Contact name
        <input value={draft.contact_name} onChange={e => set("contact_name", e.target.value)} className={INPUT} /></label>
      <label className="grid gap-0.5">Email
        <input value={draft.contact_email} onChange={e => set("contact_email", e.target.value)} className={INPUT} /></label>
      <label className="grid gap-0.5">Phone
        <input value={draft.contact_phone} onChange={e => set("contact_phone", e.target.value)} className={INPUT} /></label>
      <label className="grid gap-0.5 sm:col-span-2">Address
        <input value={draft.address} onChange={e => set("address", e.target.value)} className={INPUT} /></label>
      <label className="grid gap-0.5 sm:col-span-2">Payment terms
        <input value={draft.payment_terms} onChange={e => set("payment_terms", e.target.value)} className={INPUT} /></label>
      <label className="grid gap-0.5 sm:col-span-2">Website
        <input value={draft.website} onChange={e => set("website", e.target.value)} data-testid="supplier-website-input" className={INPUT} /></label>
      <label className="grid gap-0.5 sm:col-span-2">Notes
        <textarea rows={2} value={draft.notes} onChange={e => set("notes", e.target.value)} data-testid="supplier-notes-input" className={INPUT} /></label>
      <label className="grid gap-0.5 sm:col-span-2">Metadata
        <textarea rows={2} value={draft.metadata} onChange={e => set("metadata", e.target.value)} className={INPUT} /></label>
      {open !== "new" && open != null && (
        <div className="flex items-center gap-2 sm:col-span-2" data-testid="supplier-logo-box">
          <span>Logo</span>
          {rows.find(r => r.vendor_id === open)?.has_logo
            // eslint-disable-next-line @next/next/no-img-element
            ? <img src={`/api/suppliers/${open}/logo?v=${logoVersion}`} alt="Logo" className="h-10 w-10 rounded object-contain" />
            : <span className="text-h-muted">none</span>}
          <label className="cursor-pointer rounded border border-h-line bg-h-surface px-2 py-0.5 text-h-muted hover:text-h-ink">Upload
            <input type="file" accept="image/png,image/jpeg" className="sr-only" data-testid="supplier-logo-file" aria-label="Logo"
              onChange={e => { const f = e.target.files?.[0]; e.target.value = ""; if (f) void uploadLogo(open, f); }} /></label>
          {rows.find(r => r.vendor_id === open)?.has_logo && (
            <button type="button" className="text-h-muted underline hover:text-h-ink" onClick={() => void removeLogo(open)}>Remove</button>
          )}
        </div>
      )}
      {err && <p className="text-[#b4443d] sm:col-span-2">{err}</p>}
      <div className="flex gap-2 sm:col-span-2">
        <button type="button" disabled={saving} onClick={() => void save()} data-testid="supplier-save"
          className="rounded border border-h-line bg-h-surface px-3 py-1 text-h-ink hover:bg-h-bg disabled:opacity-50">
          {open === "new" ? "Add supplier" : "Save"}
        </button>
        <button type="button" onClick={() => setOpen(null)}
          className="rounded border border-h-line bg-h-surface px-3 py-1 text-h-muted hover:text-h-ink">Cancel</button>
      </div>
    </div>
  );

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/40 p-4"
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div role="dialog" aria-label="Suppliers" data-testid="supplier-modal"
        className="w-full max-w-5xl rounded-lg border border-h-line bg-h-surface text-xs shadow-xl">
        <header className="flex flex-wrap items-center gap-3 border-b border-h-line bg-h-bg px-4 py-3">
          <h2 className="text-sm text-h-ink">Suppliers</h2>
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search name or contact"
            className="w-56 rounded border border-h-line bg-h-surface px-2 py-1 text-h-ink" />
          <span className="text-h-muted">{shown.length} of {rows.length}</span>
          {canEdit && (
            <button type="button" onClick={startAdd} data-testid="supplier-add"
              className="rounded border border-h-line bg-h-surface px-3 py-1 text-h-ink hover:bg-h-bg">Add supplier</button>
          )}
          <button type="button" onClick={onClose}
            className="ml-auto rounded border border-h-line bg-h-surface px-3 py-1 text-sm text-h-ink hover:bg-h-bg">Close</button>
        </header>
        <div className="grid gap-3 p-4">
          {loadErr && <p className="text-[#b4443d]">Could not load suppliers: {loadErr}</p>}
          {open === "new" && form}
          <table className="w-full border-collapse">
            <thead className="text-left text-[10px] uppercase tracking-wide text-h-muted">
              <tr>
                <th className="px-2 py-1.5">Name</th><th className="px-2 py-1.5">Category</th>
                <th className="px-2 py-1.5">Status</th><th className="px-2 py-1.5">Contact</th>
                <th className="px-2 py-1.5">Email</th><th className="px-2 py-1.5">Phone</th>
                <th className="px-2 py-1.5">Payment terms</th><th />
              </tr>
            </thead>
            {shown.map(s => (
              <tbody key={s.vendor_id} data-testid="supplier-row">
                <tr className="border-t border-h-line">
                  <td className="px-2 py-1.5 text-h-ink">{s.name}</td>
                  <td className="px-2 py-1.5 text-h-muted">{categories.find(c => c.category_key === s.category)?.label ?? s.category}</td>
                  <td className="px-2 py-1.5 text-h-muted">{s.status}</td>
                  <td className="px-2 py-1.5 text-h-muted">{s.contact_name ?? ""}</td>
                  <td className="px-2 py-1.5 text-h-muted">{s.contact_email ?? ""}</td>
                  <td className="px-2 py-1.5 h-mono text-h-muted">{s.contact_phone ?? ""}</td>
                  <td className="px-2 py-1.5 text-h-muted">{s.payment_terms ?? ""}</td>
                  <td className="px-2 py-1.5 text-right">
                    {canEdit && (
                      <button type="button" onClick={() => startEdit(s)} data-testid="supplier-edit"
                        className="rounded border border-h-line bg-h-bg px-2 py-0.5 text-h-muted hover:text-h-ink">Edit</button>
                    )}
                  </td>
                </tr>
                {open === s.vendor_id && (
                  <tr><td colSpan={8} className="px-2 pb-3"><div className="grid gap-2">{form}<SupplierContacts vendorId={s.vendor_id} canEdit={canEdit} /></div></td></tr>
                )}
              </tbody>
            ))}
          </table>
        </div>
      </div>
    </div>
  );
}
