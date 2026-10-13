"use client";

import { useCallback, useEffect, useState } from "react";
import type { SupplierContact } from "@/lib/po-types";

const INPUT = "w-full rounded border border-h-line bg-h-bg px-1.5 py-1 text-h-ink focus:outline-none focus:ring-1 focus:ring-h-accent";
type Draft = { name: string; position: string; mobile: string; email: string };
const EMPTY: Draft = { name: "", position: "", mobile: "", email: "" };
const FIELDS = ["name", "position", "mobile", "email"] as const;

/**
 * A supplier's contacts (the list the PO screen ticks for Email Details): `GET/POST/PATCH/DELETE
 * /suppliers/{id}/contacts`, `orderbook:write` to change. Edited here from the Supplier list and
 * from the PO panel.
 */
export function SupplierContacts({ vendorId, canEdit }: { vendorId: number; canEdit: boolean }) {
  const [rows, setRows] = useState<SupplierContact[]>([]);
  const [loadErr, setLoadErr] = useState<string | null>(null);
  // `null` = nothing open; "new" = the add row; a contact_id = that row's editor.
  const [open, setOpen] = useState<number | "new" | null>(null);
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(() => {
    fetch(`/api/suppliers/${vendorId}/contacts`, { cache: "no-store" })
      .then(r => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((b: { contacts: SupplierContact[] }) => { setRows(b.contacts); setLoadErr(null); })
      .catch(e => setLoadErr(String(e)));
  }, [vendorId]);
  useEffect(() => { load(); }, [load]);

  function startEdit(c: SupplierContact) {
    setErr(null);
    setDraft({ name: c.name, position: c.position ?? "", mobile: c.mobile ?? "", email: c.email ?? "" });
    setOpen(c.contact_id);
  }

  async function save() {
    if (open == null) return;
    if (!draft.name.trim()) { setErr("A contact needs a name"); return; }
    setErr(null);
    const body = Object.fromEntries(FIELDS.map(k => [k, draft[k].trim() || null]));
    const res = await fetch(open === "new" ? `/api/suppliers/${vendorId}/contacts` : `/api/suppliers/${vendorId}/contacts/${open}`, {
      method: open === "new" ? "POST" : "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    }).catch(() => null);
    if (!res || !res.ok) {
      setErr(res?.status === 422 ? "Check the name and the email address" : "Could not save the contact");
      return;
    }
    setOpen(null);
    load();
  }

  async function remove(c: SupplierContact) {
    setErr(null);
    const res = await fetch(`/api/suppliers/${vendorId}/contacts/${c.contact_id}`, { method: "DELETE" }).catch(() => null);
    if (!res || !res.ok) { setErr("Could not delete the contact"); return; }
    if (open === c.contact_id) setOpen(null);
    load();
  }

  const form = (
    <div data-testid="supplier-contact-form" className="flex flex-wrap items-end gap-2">
      {FIELDS.map(k => (
        <input key={k} aria-label={`Contact ${k}`} placeholder={k[0].toUpperCase() + k.slice(1)} value={draft[k]}
          data-testid={`supplier-contact-${k}`} onChange={e => setDraft(d => ({ ...d, [k]: e.target.value }))}
          className={`${INPUT} w-36`} />
      ))}
      <button type="button" data-testid="supplier-contact-save" onClick={() => void save()}
        className="rounded border border-h-line bg-h-surface px-3 py-1 text-h-ink hover:bg-h-bg">
        {open === "new" ? "Add contact" : "Save contact"}
      </button>
      <button type="button" onClick={() => setOpen(null)}
        className="rounded border border-h-line bg-h-surface px-3 py-1 text-h-muted hover:text-h-ink">Cancel</button>
    </div>
  );

  return (
    <div data-testid="supplier-contacts" className="grid gap-1.5 rounded border border-h-line bg-h-surface p-3">
      <div className="flex items-center gap-2">
        <h3 className="text-[10px] font-semibold uppercase tracking-wide text-h-ink">Contacts</h3>
        {canEdit && open !== "new" && (
          <button type="button" data-testid="supplier-contact-add" onClick={() => { setErr(null); setDraft(EMPTY); setOpen("new"); }}
            className="rounded border border-h-line bg-h-bg px-2 py-0.5 text-h-muted hover:text-h-ink">+ Contact</button>
        )}
      </div>
      {loadErr && <p className="text-[#b4443d]">Could not load contacts: {loadErr}</p>}
      {rows.length === 0 && !loadErr && open !== "new" && <p className="text-h-muted">No contacts yet.</p>}
      {rows.map(c => (
        open === c.contact_id ? <div key={c.contact_id}>{form}</div> : (
          <div key={c.contact_id} data-testid="supplier-contact" className="flex flex-wrap items-center gap-3">
            <span className="text-h-ink">{c.name}</span>
            <span className="text-h-muted">{c.position}</span>
            <span className="h-mono text-h-muted">{c.mobile}</span>
            <span className="text-h-muted">{c.email}</span>
            {canEdit && (
              <span className="ml-auto flex gap-1">
                <button type="button" data-testid="supplier-contact-edit" onClick={() => startEdit(c)}
                  className="rounded border border-h-line bg-h-bg px-2 py-0.5 text-h-muted hover:text-h-ink">Edit</button>
                <button type="button" data-testid="supplier-contact-delete" aria-label={`Delete ${c.name}`} onClick={() => void remove(c)}
                  className="rounded border border-h-line bg-h-bg px-2 py-0.5 text-h-muted hover:text-h-ink">−</button>
              </span>
            )}
          </div>
        )
      ))}
      {open === "new" && form}
      {err && <p role="alert" className="text-[#b4443d]">{err}</p>}
    </div>
  );
}
