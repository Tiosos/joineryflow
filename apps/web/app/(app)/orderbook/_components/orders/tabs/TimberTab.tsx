"use client";

import { useEffect, useState } from "react";
import { apiCall, jsonInit } from "@/lib/api";
import type { TimberForm } from "@/lib/order-tabs-types";
import type { OrderDetail } from "@/lib/orders-types";
import { fmtDate } from "../shared";

const INPUT = "w-full rounded border border-h-line bg-h-bg px-1.5 py-1 text-h-ink focus:outline-none focus:ring-1 focus:ring-h-accent disabled:opacity-60";
const LABEL = "text-[10px] font-semibold uppercase tracking-wide text-h-muted";
const BTN = "rounded border border-h-line bg-h-bg px-4 py-2 text-sm font-semibold text-h-ink hover:bg-h-surface disabled:opacity-50";
const FIELDS = ["face", "back", "substrate", "face_by_tg", "back_by_tg", "substrate_by_tg", "finished_description", "deliver_to", "special_instructions"] as const;
type Draft = Pick<TimberForm, (typeof FIELDS)[number]>;
const BLANK: Draft = { face: null, back: null, substrate: null, face_by_tg: false, back_by_tg: false, substrate_by_tg: false, finished_description: null, deliver_to: null, special_instructions: null };
const pick = (f: TimberForm): Draft => Object.fromEntries(FIELDS.map(k => [k, f[k]])) as Draft;

/** The old Timber tab: the Timberwood Panels custom pressing order form. CREATE makes a printable PDF of it; CLEAR empties the fields. */
export function TimberTab({ order, canEdit }: { order: OrderDetail; canEdit: boolean }) {
  const base = `/api/orders/${order.po_id}/timber`;
  const [form, setForm] = useState<TimberForm | null>(null);
  const [d, setD] = useState<Draft>(BLANK);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => { apiCall<TimberForm>(base).then(f => { setForm(f); setD(pick(f)); }).catch(() => setErr("Could not load the form")); }, [base]);

  const norm = (x: Draft) => JSON.stringify(FIELDS.map(k => x[k] || null));
  async function save(x: Draft = d): Promise<boolean> {
    if (!form || !canEdit || norm(x) === norm(pick(form))) return true;
    try { const f = await apiCall<TimberForm>(base, jsonInit("PUT", x)); setForm(f); setErr(null); return true; }
    catch (e) { setErr((e as Error).message === "ORDER_LOCKED" ? "This order is closed: the form is read-only" : "Could not save the form"); return false; }
  }
  const set = (patch: Partial<Draft>, now = false) => { const x = { ...d, ...patch }; setD(x); if (now) void save(x); };

  async function create() {
    if (busy) return;
    setBusy(true);
    try {
      if (!(await save())) return;
      setForm(await apiCall<TimberForm>(`${base}/form`, { method: "POST" })); setErr(null);
    } catch { setErr("Could not create the form"); } finally { setBusy(false); }
  }

  const text = (k: "face" | "back" | "substrate", label: string) => (
    <div className="grid gap-1">
      <span className={LABEL}>{label}</span>
      <input disabled={!canEdit} value={d[k] ?? ""} data-testid={`timber-${k}`} aria-label={label} onChange={e => set({ [k]: e.target.value })} onBlur={() => void save()} className={INPUT} />
      <label className="flex items-center gap-1 text-[10px] uppercase text-h-muted">
        <input type="checkbox" disabled={!canEdit} checked={d[`${k}_by_tg` as const]} data-testid={`timber-${k}-tg`} onChange={e => set({ [`${k}_by_tg`]: e.target.checked }, true)} /> Supplied by TG</label>
    </div>
  );
  const area = (k: "finished_description" | "deliver_to" | "special_instructions", label: string, rows: number) => (
    <label className="grid gap-1"><span className={LABEL}>{label}</span>
      <textarea disabled={!canEdit} rows={rows} value={d[k] ?? ""} data-testid={`timber-${k}`} onChange={e => set({ [k]: e.target.value })} onBlur={() => void save()} className={INPUT} /></label>
  );

  return (
    <div data-testid="tab-timber" className="grid gap-3">
      {err && <p role="alert" data-testid="timber-error" className="text-[#b4443d]">{err}</p>}
      <div className="rounded border border-h-line bg-h-bg px-3 py-2 text-center">
        <div className="text-base font-semibold tracking-wide text-h-ink">TIMBERWOOD PANELS</div>
        <div className="text-h-muted">CUSTOM PRESSING &mdash; ORDER FORM</div>
      </div>
      <div className="grid gap-3 sm:grid-cols-3">{text("face", "Face")}{text("back", "Back")}{text("substrate", "Substrate")}</div>
      {area("finished_description", "Finished product description", 2)}
      {area("deliver_to", "Deliver to", 2)}
      {area("special_instructions", "Special instructions", 5)}
      <div className="flex flex-wrap items-center gap-3">
        {canEdit && <button type="button" data-testid="timber-clear" className={BTN} onClick={() => { setD(BLANK); void save(BLANK); }}>CLEAR</button>}
        {form?.has_form && (
          <a href={`${base}/form`} target="_blank" rel="noreferrer" data-testid="timber-form-link" className="text-h-ink underline">
            Open the form (created {form.form_created_at ? fmtDate(form.form_created_at.slice(0, 10)) : ""})</a>
        )}
        {canEdit && <button type="button" data-testid="timber-create" disabled={busy} className={`${BTN} ml-auto bg-[#d6ecd9]`} onClick={() => void create()}>CREATE</button>}
      </div>
    </div>
  );
}
