"use client";

import { useCallback, useEffect, useState } from "react";
import { apiCall, jsonInit } from "@/lib/api";
import type { GlassCalc, GlassCalcLine, GlassRate } from "@/lib/order-tabs-types";
import type { OrderDetail } from "@/lib/orders-types";

const INPUT = "w-full rounded border border-h-line bg-h-bg px-1.5 py-1 text-h-ink focus:outline-none focus:ring-1 focus:ring-h-accent disabled:opacity-60";
const TH = "border border-h-line bg-h-bg px-2 py-1 text-left text-[10px] font-semibold uppercase tracking-wide text-h-muted";
const TD = "border border-h-line px-2 py-1";
const MINI = "rounded border border-h-line bg-h-bg px-1.5 py-0.5 text-h-muted hover:text-h-ink disabled:opacity-40";
const money = (v: string) => `$${Number(v).toFixed(2)}`;
const intOrNull = (s: string) => (s.trim() === "" || !Number.isFinite(Number(s)) || Number(s) <= 0 ? null : Math.round(Number(s)));

/**
 * The old Glass Calc tab, a price calculator: tick glass and processing rates for the size in Copy Size;
 * glass is costed per m2, `Lm` rates per metre of perimeter, `ea` rates per item. The total is shown
 * for the buyer to use: nothing is written to the order but the ticks. The price list is kept here by
 * a purchase officer or admin.
 */
export function GlassTab({ order, canEdit, canKeep }: { order: OrderDetail; canEdit: boolean; canKeep: boolean }) {
  const base = `/api/orders/${order.po_id}/glass-calc`;
  const [calc, setCalc] = useState<GlassCalc | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [size, setSize] = useState({ length: "", width: "", thick: "" });
  const [listOpen, setListOpen] = useState(false);

  const adopt = (c: GlassCalc) => { setCalc(c); setSize({ length: c.length_mm?.toString() ?? "", width: c.width_mm?.toString() ?? "", thick: c.thick_mm?.toString() ?? "" }); };
  const load = useCallback(() => apiCall<GlassCalc>(base).then(adopt).catch(() => setErr("Could not load the calculator")), [base]);
  useEffect(() => { void load(); }, [load]);

  /** Save the size and the rows' qty / ticks; the reply carries the costs. */
  async function save(next: { size?: typeof size; lines?: GlassCalcLine[] }) {
    if (!calc) return;
    const sz = next.size ?? size;
    const lines = next.lines ?? calc.lines;
    try {
      adopt(await apiCall<GlassCalc>(base, jsonInit("PUT", {
        length_mm: intOrNull(sz.length), width_mm: intOrNull(sz.width), thick_mm: intOrNull(sz.thick),
        selection: Object.fromEntries(lines.filter(l => l.ticked || Number(l.qty) !== 1).map(l => [l.glass_rate_id, { qty: l.qty, ticked: l.ticked }])),
      })));
      setErr(null);
    } catch (e) { setErr((e as Error).message === "ORDER_LOCKED" ? "This order is closed: the calculator is read-only" : "Could not save"); }
  }

  const setLine = (id: number, patch: Partial<GlassCalcLine>) => {
    if (!calc) return;
    const lines = calc.lines.map(l => (l.glass_rate_id === id ? { ...l, ...patch } : l));
    setCalc({ ...calc, lines });          // the tick shows at once; the costs follow the reply
    void save({ lines });
  };

  const table = (kind: "glass" | "process") => (
    <table className="w-full border-collapse" data-testid={`glass-table-${kind}`}>
      <thead><tr><th className={TH}>Item</th><th className={TH}>Qty</th><th className={TH}>Rate</th><th className={TH}>Um</th><th className={TH}>Supplier</th><th className={TH}>Cost</th>
        <th className={TH}>{kind === "glass" && canEdit && (
          <button type="button" data-testid="glass-clear" className={MINI} onClick={() => calc && void save({ lines: calc.lines.map(l => ({ ...l, ticked: false, qty: "1" })) })}>Clear All</button>)}</th></tr></thead>
      <tbody>
        {calc?.lines.filter(l => l.kind === kind).map(l => (
          <tr key={l.glass_rate_id} data-testid="glass-line">
            <td className={TD}>{l.name}</td>
            <td className={TD}><input aria-label={`Quantity of ${l.name}`} disabled={!canEdit} defaultValue={String(Number(l.qty))} key={l.qty}
              onBlur={e => { if (Number(e.target.value) > 0 && Number(e.target.value) !== Number(l.qty)) setLine(l.glass_rate_id, { qty: e.target.value }); else e.target.value = String(Number(l.qty)); }}
              className={`${INPUT} h-mono w-14 text-right`} /></td>
            <td className={`${TD} h-mono text-right`}>{money(l.rate)}</td><td className={TD}>{l.um}</td><td className={TD}>{l.supplier_no}</td>
            <td className={`${TD} h-mono text-right`} data-testid="glass-cost">{money(l.cost)}</td>
            <td className={`${TD} text-center`}><input type="checkbox" aria-label={`Tick ${l.name}`} disabled={!canEdit} checked={l.ticked}
              onChange={e => setLine(l.glass_rate_id, { ticked: e.target.checked })} /></td>
          </tr>
        ))}
        {calc && calc.lines.every(l => l.kind !== kind) && <tr><td colSpan={7} className={`${TD} text-h-muted`}>No rates on the price list.</td></tr>}
      </tbody>
    </table>
  );

  return (
    <div data-testid="tab-glass" className="grid gap-3">
      {err && <p role="alert" data-testid="glass-error" className="text-[#b4443d]">{err}</p>}
      {table("glass")}
      {table("process")}
      <div className="flex flex-wrap items-end gap-2">
        <button type="button" data-testid="glass-copy-size" disabled={!canEdit || !calc?.suggested_size} className={`${MINI} px-3 py-2`}
          title="Take the size from the start of the order's description, e.g. 1471 x 1000 x 6"
          onClick={() => { const s = calc?.suggested_size; if (s) void save({ size: { length: String(s.length_mm), width: String(s.width_mm), thick: s.thick_mm ? String(s.thick_mm) : "" } }); }}>▸ Copy Size</button>
        {([["length", "Length"], ["width", "Width"], ["thick", "Thick"]] as const).map(([k, label]) => (
          <label key={k} className="grid w-24 gap-0.5"><span className="text-[10px] font-semibold uppercase tracking-wide text-h-muted">{label}</span>
            <input disabled={!canEdit} value={size[k]} data-testid={`glass-${k}`} onChange={e => setSize({ ...size, [k]: e.target.value })}
              onBlur={() => void save({})} className={`${INPUT} h-mono text-right`} /></label>
        ))}
        <div className="grid gap-0.5"><span className="text-[10px] font-semibold uppercase tracking-wide text-h-muted">Total</span>
          <span data-testid="glass-total" className="h-mono rounded border border-h-line bg-h-bg px-3 py-1.5 text-sm text-h-ink">{calc ? money(calc.total) : ""}</span></div>
      </div>
      {canKeep && (
        <div>
          <button type="button" data-testid="glass-edit-list" className={MINI} onClick={() => setListOpen(o => !o)}>{listOpen ? "Done" : "Edit price list"}</button>
          {listOpen && <PriceList onChanged={() => void load()} />}
        </div>
      )}
    </div>
  );
}

/** The price list editor: rename, re-rate, switch off, add (purchase officer / admin). */
function PriceList({ onChanged }: { onChanged: () => void }) {
  const [rates, setRates] = useState<GlassRate[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [n, setN] = useState({ kind: "glass", name: "", rate: "", um: "m2", supplier_no: "" });
  const reload = useCallback(() => apiCall<{ rates: GlassRate[] }>("/api/glass-rates").then(b => setRates(b.rates)).catch(() => setErr("Could not load the price list")), []);
  useEffect(() => { void reload(); }, [reload]);
  const run = async (fn: () => Promise<unknown>) => {
    try { await fn(); setErr(null); await reload(); onChanged(); }
    catch (e) { setErr((e as Error).message === "GLASS_RATE_EXISTS" ? "That name is already on the list" : "Could not save the price list"); }
  };
  const patch = (id: number, body: Record<string, unknown>) => run(() => apiCall(`/api/glass-rates/${id}`, jsonInit("PATCH", body)));
  return (
    <div data-testid="glass-price-list" className="mt-2 grid gap-1 rounded border border-h-line bg-h-bg p-2">
      {rates.map(r => (
        <div key={r.glass_rate_id} className="flex flex-wrap items-center gap-2">
          <span className="w-14 text-[10px] uppercase text-h-muted">{r.kind}</span>
          <input aria-label={`Name of ${r.name}`} defaultValue={r.name} key={r.name} className={`${INPUT} w-48`}
            onBlur={e => { const v = e.target.value.trim(); if (v && v !== r.name) void patch(r.glass_rate_id, { name: v }); }} />
          <input aria-label={`Rate of ${r.name}`} defaultValue={String(Number(r.rate))} key={r.rate} className={`${INPUT} h-mono w-20 text-right`}
            onBlur={e => { if (Number(e.target.value) >= 0 && Number(e.target.value) !== Number(r.rate)) void patch(r.glass_rate_id, { rate: e.target.value }); }} />
          <input aria-label={`Unit of ${r.name}`} defaultValue={r.um} key={r.um} className={`${INPUT} w-14`}
            onBlur={e => { const v = e.target.value.trim(); if (v && v !== r.um) void patch(r.glass_rate_id, { um: v }); }} />
          <input aria-label={`Supplier of ${r.name}`} defaultValue={r.supplier_no ?? ""} key={r.supplier_no ?? ""} className={`${INPUT} w-20`}
            onBlur={e => { if (e.target.value !== (r.supplier_no ?? "")) void patch(r.glass_rate_id, { supplier_no: e.target.value || null }); }} />
          <button type="button" className={MINI} onClick={() => void patch(r.glass_rate_id, { is_active: !r.is_active })}>{r.is_active ? "Switch off" : "Switch on"}</button>
        </div>
      ))}
      <div className="flex flex-wrap items-center gap-2">
        <select aria-label="Kind" value={n.kind} onChange={e => setN({ ...n, kind: e.target.value, um: e.target.value === "glass" ? "m2" : "Lm" })} className={`${INPUT} w-24`}>
          <option value="glass">glass</option><option value="process">process</option></select>
        <input aria-label="New rate name" placeholder="Name" value={n.name} data-testid="glass-new-name" onChange={e => setN({ ...n, name: e.target.value })} className={`${INPUT} w-48`} />
        <input aria-label="New rate" placeholder="Rate" value={n.rate} data-testid="glass-new-rate" onChange={e => setN({ ...n, rate: e.target.value })} className={`${INPUT} h-mono w-20 text-right`} />
        <input aria-label="New unit" value={n.um} onChange={e => setN({ ...n, um: e.target.value })} className={`${INPUT} w-14`} />
        <input aria-label="New supplier" placeholder="Supplier" value={n.supplier_no} onChange={e => setN({ ...n, supplier_no: e.target.value })} className={`${INPUT} w-20`} />
        <button type="button" data-testid="glass-new-add" className={MINI} disabled={!n.name.trim() || !(Number(n.rate) >= 0) || n.rate === ""}
          onClick={() => void run(async () => {
            await apiCall("/api/glass-rates", jsonInit("POST", { kind: n.kind, name: n.name.trim(), rate: n.rate, um: n.um.trim(), supplier_no: n.supplier_no.trim() || null }));
            setN({ ...n, name: "", rate: "", supplier_no: "" });
          })}>Add</button>
      </div>
      {err && <p role="alert" className="text-[#b4443d]">{err}</p>}
    </div>
  );
}
