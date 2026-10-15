"use client";

import { useCallback, useEffect, useState } from "react";
import { apiCall, jsonInit } from "@/lib/api";
import type { TgRun } from "@/lib/order-tabs-types";
import type { OrderDetail } from "@/lib/orders-types";

const INPUT = "w-full rounded border border-h-line bg-h-bg px-1.5 py-1 text-h-ink focus:outline-none focus:ring-1 focus:ring-h-accent disabled:opacity-60";
const TH = "border border-h-line bg-h-bg px-2 py-1 text-left text-[10px] font-semibold uppercase tracking-wide text-h-muted";
const TD = "border border-h-line px-1 py-1";
const MINI = "rounded border border-h-line bg-h-bg px-1.5 py-0.5 text-h-muted hover:text-h-ink disabled:opacity-40";
type Key = "production_start" | "date_made" | "made_by" | "date_ex_factory" | "location" | "notes";
const COLS: { k: Key; label: string; date?: boolean }[] = [
  { k: "production_start", label: "Production start", date: true }, { k: "date_made", label: "Date made", date: true }, { k: "made_by", label: "Made by" },
  { k: "date_ex_factory", label: "Date ex factory", date: true }, { k: "location", label: "Location" }, { k: "notes", label: "Notes" },
];
const EMPTY: Record<Key, string> = { production_start: "", date_made: "", made_by: "", date_ex_factory: "", location: "", notes: "" };

/** The old TGSolid tab: the TG Solid production rows of the order. A record only; it does not move the Tracking item's stages. */
export function TgSolidTab({ order, canEdit }: { order: OrderDetail; canEdit: boolean }) {
  const base = `/api/orders/${order.po_id}/tg-runs`;
  const [runs, setRuns] = useState<TgRun[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [add, setAdd] = useState(EMPTY);
  const load = useCallback(() => apiCall<{ runs: TgRun[] }>(base).then(b => setRuns(b.runs)).catch(() => setErr("Could not load the production rows")), [base]);
  useEffect(() => { void load(); }, [load]);
  const run = async (fn: () => Promise<{ runs: TgRun[] }>) => {
    try { setRuns((await fn()).runs); setErr(null); return true; }
    catch (e) { setErr((e as Error).message === "ORDER_LOCKED" ? "This order is closed: its production rows are read-only" : "Could not save that change"); return false; }
  };
  const body = (v: Record<Key, string>) => Object.fromEntries(COLS.map(c => [c.k, v[c.k].trim() || null]));

  return (
    <div data-testid="tab-tgsolid" className="grid gap-2">
      {err && <p role="alert" data-testid="tg-error" className="text-[#b4443d]">{err}</p>}
      <div className="overflow-x-auto">
        <table className="w-full border-collapse">
          <thead><tr>{COLS.map(c => <th key={c.k} className={TH}>{c.label}</th>)}<th className={TH} /></tr></thead>
          <tbody>
            {(runs ?? []).map(r => (
              <tr key={r.run_id} data-testid="tg-row">
                {COLS.map(c => (
                  <td key={c.k} className={TD}>
                    <input type={c.date ? "date" : "text"} aria-label={c.label} disabled={!canEdit} defaultValue={r[c.k] ?? ""} key={`${c.k}${r[c.k] ?? ""}`}
                      onBlur={e => { if (e.target.value !== (r[c.k] ?? "")) void run(() => apiCall(`${base}/${r.run_id}`, jsonInit("PATCH", { [c.k]: e.target.value.trim() || null }))); }} className={INPUT} />
                  </td>
                ))}
                <td className={`${TD} text-right`}>{canEdit && <button type="button" aria-label="Remove row" data-testid="tg-remove" className={MINI}
                  onClick={() => void run(() => apiCall(`${base}/${r.run_id}`, { method: "DELETE" }))}>−</button>}</td>
              </tr>
            ))}
            {runs && runs.length === 0 && <tr><td colSpan={7} className={`${TD} px-2 text-h-muted`}>No production rows yet.</td></tr>}
            {canEdit && (
              <tr className="bg-h-bg" data-testid="tg-add-row">
                {COLS.map(c => (
                  <td key={c.k} className={TD}><input type={c.date ? "date" : "text"} aria-label={`New ${c.label}`} data-testid={`tg-new-${c.k}`} value={add[c.k]}
                    onChange={e => setAdd({ ...add, [c.k]: e.target.value })} className={INPUT} /></td>
                ))}
                <td className={`${TD} text-right`}><button type="button" data-testid="tg-add" className={MINI} disabled={COLS.every(c => !add[c.k].trim())}
                  onClick={() => void run(() => apiCall(base, jsonInit("POST", body(add)))).then(ok => { if (ok) setAdd(EMPTY); })}>+ Add</button></td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
