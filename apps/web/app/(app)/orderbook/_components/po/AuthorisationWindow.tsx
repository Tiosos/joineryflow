"use client";

import { useEffect, useRef, useState } from "react";
import { apiCall, jsonInit } from "@/lib/api";
import type { PaymentMethod, PoAuthorisation, PoDoc } from "@/lib/po-types";
import { fmtDate, money } from "../orders/shared";
import { PaymentMethodSelect } from "./PaymentMethodSelect";

const INPUT = "w-full rounded border border-h-line bg-h-bg px-1.5 py-1 text-h-ink focus:outline-none focus:ring-1 focus:ring-h-accent disabled:opacity-60";
const BTN = "rounded border border-h-line bg-h-bg px-3 py-1 text-h-ink hover:bg-h-surface disabled:opacity-50";
const LABEL = "border border-h-line bg-h-bg px-2 py-1.5 text-left font-normal text-h-muted";
const refusal: Record<string, string> = {
  DEPOSIT_BOTH: "Enter a deposit % or an amount, not both", PO_CANCELLED: "This PO is cancelled",
  PAYMENT_METHOD_NOT_FOUND: "That payment type is not available", USER_NOT_FOUND: "That person is not available",
};

type Draft = { payment_method_id: number | null; deposit_pct: string; amount_required: string; date_required: string; on_behalf_of_id: number | null };
const fromData = (a: PoAuthorisation): Draft => ({
  payment_method_id: a.payment_method_id, deposit_pct: a.deposit_pct != null ? String(Number(a.deposit_pct)) : "",
  amount_required: a.amount_required ?? "", date_required: a.date_required ?? "", on_behalf_of_id: a.on_behalf_of_id,
});
const num = (s: string) => (s.trim() === "" || Number.isNaN(Number(s)) ? null : Number(s));
const toBody = (d: Draft) => ({
  payment_method_id: d.payment_method_id, deposit_pct: num(d.deposit_pct), amount_required: num(d.amount_required),
  date_required: d.date_required || null, on_behalf_of_id: d.on_behalf_of_id,
});

/**
 * The old Authorisation Form Details window: payment type, the PO amount, a deposit % OR an amount,
 * date required by and who it is on behalf of. Create Form renders the sheet from those details and
 * keeps it in the Pdf Form box; the printed copy, signed by hand, is scanned into Signed Form.
 */
export function AuthorisationWindow({
  doc, editable, methods, canKeep, onListChanged, team, onClose,
}: {
  doc: PoDoc; editable: boolean; methods: PaymentMethod[]; canKeep: boolean; onListChanged: () => void;
  team: { id: number; full_name: string }[]; onClose: () => void;
}) {
  const [data, setData] = useState<PoAuthorisation | null>(null);
  const [d, setD] = useState<Draft | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const dialogRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<() => void>(() => {});
  const base = `/api/purchase-orders/${doc.po_document_id}/authorisation`;

  useEffect(() => {
    apiCall<PoAuthorisation>(base).then(a => { setData(a); setD(fromData(a)); }).catch(() => setErr("Could not load the form details"));
  }, [base]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") { e.stopImmediatePropagation(); closeRef.current(); } };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, []);
  const loaded = data !== null;
  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    if (loaded) dialogRef.current?.focus();
    return () => { if (loaded) opener?.focus?.(); };
  }, [loaded]);

  const fail = (e: unknown) => setErr(refusal[(e as Error).message] ?? "Could not save the form details");

  /** Save the details if they differ from what is stored. True when nothing is left unsaved. */
  async function save(x: Draft | null = d): Promise<boolean> {
    if (!editable || !data || !x) return true;
    if (JSON.stringify(toBody(x)) === JSON.stringify(toBody(fromData(data)))) return true;
    try {
      const a = await apiCall<PoAuthorisation>(base, jsonInit("PUT", toBody(x)));
      setData(a); setErr(null);
      return true;
    } catch (e) { fail(e); return false; }
  }

  const closeWithSave = async () => { if (await save()) onClose(); };
  closeRef.current = () => { void closeWithSave(); };

  const set = (patch: Partial<Draft>, now = false) => {
    if (!d) return;
    const x = { ...d, ...patch };
    setD(x);
    if (now) void save(x);
  };

  async function createForm() {
    if (busy) return;
    setBusy(true);
    try {
      if (!(await save())) return;
      setData(await apiCall<PoAuthorisation>(`${base}/form`, { method: "POST" }));
      setErr(null);
    } catch (e) { fail(e); } finally { setBusy(false); }
  }

  async function uploadSigned(file: File) {
    const fd = new FormData(); fd.append("file", file);
    const r = await fetch(`${base}/signed`, { method: "POST", body: fd }).catch(() => null);
    if (!r || !r.ok) { setErr(r?.status === 415 ? "Only a PDF, PNG or JPEG can go in this box" : "Could not attach the signed form"); return; }
    setData((await r.json()) as PoAuthorisation); setErr(null);
  }

  async function removeSigned() {
    try { setData(await apiCall<PoAuthorisation>(`${base}/signed`, { method: "DELETE" })); setErr(null); }
    catch { setErr("Could not remove the signed form"); }
  }

  const row = (label: string, child: React.ReactNode) => (
    <tr><th scope="row" className={`${LABEL} w-1/2`}>{label}</th><td className="border border-h-line px-2 py-1">{child}</td></tr>
  );
  const signedIsImage = data?.signed_mime != null && data.signed_mime.startsWith("image/");

  return (
    <div className="fixed inset-0 z-[60] flex items-start justify-center overflow-y-auto bg-black/40 p-4"
      onClick={e => { if (e.target === e.currentTarget) closeRef.current(); }}>
      <div role="dialog" aria-modal="true" aria-labelledby="auth-title" tabIndex={-1} ref={dialogRef} data-testid="auth-window"
        className="w-full max-w-sm rounded-lg border border-h-line bg-h-surface text-xs shadow-xl outline-none">
        <header className="border-b border-h-line bg-h-bg px-3 py-2 text-center">
          <h2 id="auth-title" className="text-sm text-h-ink">Authorisation Form Details</h2>
        </header>
        {!data || !d ? (
          <div className="p-4 text-h-muted"><span data-testid="auth-load-state">{err ?? "Loading…"}</span>
            <button type="button" onClick={onClose} className={`${BTN} ml-3`}>Close</button></div>
        ) : (
          <div className="grid gap-3 p-3">
            {err && <p role="alert" data-testid="auth-error" className="text-[#b4443d]">{err}</p>}
            <table className="w-full border-collapse"><tbody>
              {row("Payment Type", (
                <PaymentMethodSelect label="Payment Type" value={d.payment_method_id} methods={methods} canKeep={canKeep}
                  disabled={!editable} onChange={id => set({ payment_method_id: id }, true)} onListChanged={onListChanged} testId="auth-method" />
              ))}
              {row("Purchase Order Amount", <span data-testid="auth-amount" className="h-mono block text-right text-h-ink">{money(data.purchase_order_amount, null)}</span>)}
              {row("Enter Deposit Required %", (
                <input aria-label="Deposit required percent" disabled={!editable} value={d.deposit_pct} data-testid="auth-deposit-pct"
                  onChange={e => set({ deposit_pct: e.target.value, amount_required: e.target.value ? "" : d.amount_required })}
                  onBlur={() => void save()} className={`${INPUT} text-right h-mono`} />
              ))}
              <tr><td colSpan={2} className="py-0.5 text-center text-h-muted">OR</td></tr>
              {row("Enter Amount Required", (
                <input aria-label="Amount required" disabled={!editable} value={d.amount_required} data-testid="auth-amount-required"
                  onChange={e => set({ amount_required: e.target.value, deposit_pct: e.target.value ? "" : d.deposit_pct })}
                  onBlur={() => void save()} className={`${INPUT} text-right h-mono`} />
              ))}
              {row("Date Required by", (
                <input type="date" aria-label="Date required by" disabled={!editable} value={d.date_required} data-testid="auth-date"
                  onChange={e => set({ date_required: e.target.value })} onBlur={() => void save()} className={INPUT} />
              ))}
              {row("On Behalf Of", (
                <select aria-label="On behalf of" disabled={!editable} value={d.on_behalf_of_id ?? ""} data-testid="auth-on-behalf"
                  onChange={e => set({ on_behalf_of_id: e.target.value ? Number(e.target.value) : null }, true)} className={INPUT}>
                  <option value="" />
                  {team.map(m => <option key={m.id} value={m.id}>{m.full_name}</option>)}
                </select>
              ))}
            </tbody></table>
            <div className="grid grid-cols-2 gap-3">
              <div data-testid="auth-form-box" className="grid gap-1 text-center">
                <div className="rounded border border-h-line bg-h-bg px-1 py-1 text-h-muted">Pdf Form</div>
                <div className="grid h-20 place-items-center rounded border border-h-line">
                  {data.form_created_at ? (
                    <a href={`${base}/form`} target="_blank" rel="noreferrer" data-testid="auth-form-link" className="px-1 text-h-ink">
                      PDF<br /><span className="text-[10px] text-h-muted">{data.form_created_at ? fmtDate(data.form_created_at.slice(0, 10)) : ""}</span></a>
                  ) : <span className="text-h-muted">not created</span>}
                </div>
              </div>
              <div data-testid="auth-signed-box" className="grid gap-1 text-center">
                <div className="rounded border border-h-line bg-h-bg px-1 py-1 text-h-muted">Signed Form</div>
                <div className="grid h-20 place-items-center overflow-hidden rounded border border-h-line">
                  {data.signed_mime ? (
                    <a href={`${base}/signed`} target="_blank" rel="noreferrer" title="Open the signed form" data-testid="auth-signed-link" className="grid h-full w-full place-items-center">
                      {signedIsImage
                        // eslint-disable-next-line @next/next/no-img-element
                        ? <img src={`${base}/signed`} alt="Signed form" className="max-h-full max-w-full object-contain" />
                        : <span className="px-1 text-h-ink">PDF</span>}
                    </a>
                  ) : editable ? (
                    <label className="cursor-pointer px-1 text-h-muted hover:text-h-ink">+ file
                      <input type="file" accept="application/pdf,image/png,image/jpeg" className="sr-only" data-testid="auth-signed-file"
                        onChange={e => { const f = e.target.files?.[0]; e.target.value = ""; if (f) void uploadSigned(f); }} />
                    </label>
                  ) : null}
                </div>
                {data.signed_mime && editable && <button data-testid="auth-signed-remove" type="button" onClick={() => void removeSigned()} className="text-[10px] text-h-muted underline hover:text-h-ink">remove</button>}
              </div>
            </div>
            <div className="flex items-center gap-2">
              <button type="button" data-testid="auth-close" onClick={() => closeRef.current()} className={BTN}>Close</button>
              {editable && <button type="button" data-testid="auth-create" disabled={busy} onClick={() => void createForm()} className={`${BTN} ml-auto`}>Create Form</button>}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
