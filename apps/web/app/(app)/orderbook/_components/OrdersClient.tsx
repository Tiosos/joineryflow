"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { can, type Me } from "@/lib/permissions";
import type { CostCentre, OrderRow } from "@/lib/orders-types";
import { STATUSES, money } from "./orders/shared";
import { OrderRowView } from "./orders/OrderRowView";
import { OrderDetailPanel } from "./orders/OrderDetailPanel";

/**
 * Orderbook's Orders tab — the commercial layer over `purchase_orders` (Q505).
 *
 * Q504 keeps procurement batches beneath orders as the allocation mechanism,
 * so #4's supplier-grouped queue is not replaced: it moves to the Queue tab
 * beside this one.
 *
 * Q418 is honoured here. Tracking links a related part's issued order number
 * to `/orderbook?order=<po_number>`; that param selects the row, scrolls it
 * into view and opens its detail panel, which is the "locate the order" half
 * the link could not deliver while this page rendered batches.
 *
 * The detail panel is editable (`orderbook:write`) — the PATCH-editing UI
 * `PatchOrderIn` / `field_versions` had carried since §L with nothing to
 * drive them, now that PO generation (a Won Quote) creates real multi-line
 * orders with nothing else to correct or approve them.
 */
export function OrdersClient({ me }: { me: Me | null }) {
  const router = useRouter();
  const params = useSearchParams();
  const [rows, setRows] = useState<OrderRow[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const status = params.get("status") ?? "";
  const supplier = params.get("supplier") ?? "";
  // Q418: the number Tracking sent us here with.
  const selected = params.get("order") ?? "";

  const fetchRows = useCallback(() => {
    const qs = new URLSearchParams();
    if (status) qs.set("status", status);
    if (supplier) qs.set("supplier", supplier);
    setLoading(true);
    return fetch(`/api/orders${qs.toString() ? `?${qs}` : ""}`, { cache: "no-store" })
      .then(r => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then(b => { setRows(b.orders); setErr(null); })
      .catch(e => setErr(String(e)))
      .finally(() => setLoading(false));
  }, [status, supplier]);

  useEffect(() => {
    void fetchRows();
  }, [fetchRows]);

  const suppliers = useMemo(
    () => [...new Set(rows.map(r => r.vendor_name).filter((s): s is string => !!s))].sort(),
    [rows],
  );

  const selectedRow = rows.find(r => r.po_number === selected) ?? null;
  const canEdit = can(me, "orderbook", "write");
  const canApprove = can(me, "orderbook", "approve");
  // The project manager's flag is a manager/admin call; the limit is a purchase officer's (or admin's).
  const canFlag = me?.auth_role === "manager" || me?.auth_role === "admin";
  const canSetLimit = me?.auth_role === "purchase_officer" || me?.auth_role === "admin";
  const [threshold, setThreshold] = useState<string | null>(null);
  const [limitEdit, setLimitEdit] = useState<string | null>(null);
  const [limitErr, setLimitErr] = useState<string | null>(null);

  const [costCentres, setCostCentres] = useState<CostCentre[]>([]);
  const [ccForm, setCcForm] = useState<{ code: string; name: string; budget: string } | null>(null);
  const [ccErr, setCcErr] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/cost-centers", { cache: "no-store" })
      .then(r => (r.ok ? r.json() : null))
      .then((b: { cost_centers: CostCentre[] } | null) => setCostCentres(b?.cost_centers ?? []))
      .catch(() => setCostCentres([]));
  }, []);

  async function addCostCentre() {
    if (!ccForm) return;
    setCcErr(null);
    const res = await fetch("/api/cost-centers", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ code: ccForm.code, name: ccForm.name, budget_amount: ccForm.budget || "0" }),
    }).catch(() => null);
    if (!res || !res.ok) {
      const body = res ? await res.json().catch(() => null) : null;
      setCcErr(body?.detail?.code === "COST_CENTRE_EXISTS" ? "That code is already used" : "Could not add the cost centre");
      return;
    }
    const created = (await res.json()) as CostCentre;
    setCostCentres(list => [...list, created].sort((a, b) => a.code.localeCompare(b.code)));
    setCcForm(null);
  }

  useEffect(() => {
    fetch("/api/order-settings", { cache: "no-store" })
      .then(r => (r.ok ? r.json() : null))
      .then((b: { approval_threshold: string } | null) => setThreshold(b?.approval_threshold ?? null))
      .catch(() => setThreshold(null));
  }, []);

  async function saveLimit() {
    setLimitErr(null);
    const res = await fetch("/api/order-settings", {
      method: "PUT",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ approval_threshold: limitEdit }),
    }).catch(() => null);
    if (!res || !res.ok) { setLimitErr("Could not save the limit"); return; }
    setThreshold(((await res.json()) as { approval_threshold: string }).approval_threshold);
    setLimitEdit(null);
  }

  function setParam(k: string, v: string) {
    const next = new URLSearchParams(params.toString());
    if (v) next.set(k, v); else next.delete(k);
    const qs = next.toString();
    router.push(qs ? `/orderbook?${qs}` : "/orderbook");
  }

  return (
    <div className="grid gap-3" data-testid="orders-panel">
      <div className="flex flex-wrap items-center gap-2">
        <select
          value={status}
          onChange={e => setParam("status", e.target.value)}
          data-testid="orders-status-filter"
          className="rounded border border-h-line bg-h-surface px-2 py-1 text-xs text-h-ink"
        >
          <option value="">All statuses</option>
          {STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
        </select>
        <select
          value={supplier}
          onChange={e => setParam("supplier", e.target.value)}
          data-testid="orders-supplier-filter"
          className="rounded border border-h-line bg-h-surface px-2 py-1 text-xs text-h-ink"
        >
          <option value="">All suppliers</option>
          {suppliers.map(s => <option key={s} value={s}>{s}</option>)}
        </select>
        <span className="text-xs text-h-muted">
          {loading ? "Loading…" : `${rows.length} order${rows.length === 1 ? "" : "s"}`}
        </span>
        {canSetLimit && (
          <span data-testid="cost-centres" className="ml-auto flex items-center gap-1.5 text-xs text-h-muted">
            {costCentres.length} cost centre{costCentres.length === 1 ? "" : "s"}
            {ccForm === null ? (
              <button type="button" data-testid="cost-centre-add"
                onClick={() => setCcForm({ code: "", name: "", budget: "" })}
                className="rounded border border-h-line bg-h-bg px-1.5 py-0.5 hover:text-h-ink">Add</button>
            ) : (
              <>
                <input value={ccForm.code} onChange={e => setCcForm({ ...ccForm, code: e.target.value })}
                  placeholder="Code" data-testid="cost-centre-code"
                  className="h-mono w-20 rounded border border-h-line bg-h-bg px-1.5 py-0.5 text-h-ink" />
                <input value={ccForm.name} onChange={e => setCcForm({ ...ccForm, name: e.target.value })}
                  placeholder="Name" data-testid="cost-centre-name"
                  className="w-32 rounded border border-h-line bg-h-bg px-1.5 py-0.5 text-h-ink" />
                <input value={ccForm.budget} onChange={e => setCcForm({ ...ccForm, budget: e.target.value })}
                  placeholder="Budget" inputMode="decimal"
                  className="h-mono w-24 rounded border border-h-line bg-h-bg px-1.5 py-0.5 text-h-ink" />
                <button type="button" data-testid="cost-centre-save" onClick={() => void addCostCentre()}
                  className="rounded border border-h-line bg-h-bg px-1.5 py-0.5 hover:text-h-ink">Save</button>
                <button type="button" onClick={() => { setCcForm(null); setCcErr(null); }}
                  className="rounded border border-h-line bg-h-bg px-1.5 py-0.5 hover:text-h-ink">Cancel</button>
              </>
            )}
            {ccErr && <span className="text-[#b4443d]">{ccErr}</span>}
          </span>
        )}
        {threshold != null && (
          <span data-testid="approval-limit" className="flex items-center gap-1.5 text-xs text-h-muted">
            Orders over <span className="h-mono text-h-ink">{money(threshold, null)}</span> need approval
            {canSetLimit && limitEdit === null && (
              <button
                type="button"
                data-testid="approval-limit-edit"
                onClick={() => setLimitEdit(threshold)}
                className="rounded border border-h-line bg-h-bg px-1.5 py-0.5 hover:text-h-ink"
              >
                Change
              </button>
            )}
            {canSetLimit && limitEdit !== null && (
              <>
                <input
                  value={limitEdit}
                  onChange={e => setLimitEdit(e.target.value)}
                  inputMode="decimal"
                  data-testid="approval-limit-input"
                  className="h-mono w-24 rounded border border-h-line bg-h-bg px-1.5 py-0.5 text-h-ink"
                />
                <button type="button" data-testid="approval-limit-save" onClick={() => void saveLimit()}
                  className="rounded border border-h-line bg-h-bg px-1.5 py-0.5 hover:text-h-ink">Save</button>
                <button type="button" onClick={() => { setLimitEdit(null); setLimitErr(null); }}
                  className="rounded border border-h-line bg-h-bg px-1.5 py-0.5 hover:text-h-ink">Cancel</button>
              </>
            )}
            {limitErr && <span className="text-[#b4443d]">{limitErr}</span>}
          </span>
        )}
        {selected && (
          <button
            type="button"
            onClick={() => setParam("order", "")}
            className="rounded border border-h-line bg-h-bg px-2 py-1 text-xs text-h-muted hover:text-h-ink"
          >
            Clear selection ({selected})
          </button>
        )}
      </div>

      {err && <p className="text-sm text-[#b4443d]">Could not load orders: {err}</p>}

      {/* Q418: the link may name an order that this filter combination hides.
          Say so rather than showing an empty table under a selection. */}
      {selected && !loading && !selectedRow && !err && (
        <p
          data-testid="orders-not-found"
          className="rounded border border-h-line bg-h-surface px-3 py-2 text-xs text-h-muted"
        >
          Order <span className="h-mono text-h-ink">{selected}</span> is not in this
          list — clear the filters above, or it belongs to another workspace.
        </p>
      )}

      <div className="overflow-x-auto rounded border border-h-line">
        <table className="w-full min-w-[980px] border-collapse text-xs">
          <thead className="bg-h-surface text-left text-[10px] uppercase tracking-wide text-h-muted">
            <tr>
              <th className="px-2 py-1.5">Order #</th>
              <th className="px-2 py-1.5">Supplier</th>
              <th className="px-2 py-1.5">Description</th>
              <th className="px-2 py-1.5">Project</th>
              <th className="px-2 py-1.5">Cutlist no.</th>
              <th className="px-2 py-1.5">Status</th>
              <th className="px-2 py-1.5">Ordered</th>
              <th className="px-2 py-1.5">ETA</th>
              <th className="px-2 py-1.5 text-right">Total</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && !loading ? (
              <tr>
                <td colSpan={9} className="px-4 py-8 text-center text-h-muted">
                  No orders yet.
                </td>
              </tr>
            ) : (
              rows.map(r => (
                <OrderRowView
                  key={r.po_id}
                  row={r}
                  selected={r.po_number === selected}
                  onSelect={() => setParam("order", r.po_number === selected ? "" : r.po_number)}
                />
              ))
            )}
          </tbody>
        </table>
      </div>

      {selectedRow && (
        <OrderDetailPanel
          key={selectedRow.po_id}
          poId={selectedRow.po_id}
          canEdit={canEdit}
          onChanged={fetchRows}
          threshold={threshold}
          meId={me?.id ?? null}
          canApprove={canApprove}
          canFlag={canFlag}
          costCentres={costCentres}
        />
      )}
    </div>
  );
}
