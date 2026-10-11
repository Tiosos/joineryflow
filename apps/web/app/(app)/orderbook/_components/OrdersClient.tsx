"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { can, type Me } from "@/lib/permissions";
import type { CostCentre, OrderCategory, OrderRow } from "@/lib/orders-types";
import { STATUSES } from "./orders/shared";
import { COLUMNS, OrderRowView } from "./orders/OrderRowView";
import { OrderDetailPanel } from "./orders/OrderDetailPanel";
import { CostCentreManager } from "./orders/CostCentreManager";
import { CostBreakdownModal } from "./CostBreakdownModal";

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
 * The detail is a pop-up (the old Orderbook's Details window) and is editable
 * (`orderbook:write`) — the PATCH-editing UI `PatchOrderIn` / `field_versions` had
 * carried since §L with nothing to drive them, now that PO generation (a Won
 * Quote) creates real multi-line orders with nothing else to correct or approve them.
 *
 * The list follows the old screen: orders grouped under their type, its columns, and a
 * row of filter buttons. Of those buttons, Due / Over Due / Arrived / My Orders are
 * built; RTO, TBO, New, Supplier and Po are shown disabled until what they filter is
 * confirmed.
 */

/** The old screen's filter buttons; `view` in the URL holds the one that is on. */
const VIEWS = [
  { key: "due", label: "Due", hint: "Due in the next 7 days, not yet arrived" },
  { key: "overdue", label: "Over Due", hint: "Due date has passed, not yet arrived" },
  { key: "arrived", label: "Arrived", hint: "Has an arrived date" },
  { key: "mine", label: "My Orders", hint: "Orders you requested" },
] as const;
const UNCONFIRMED = ["RTO", "TBO", "New", "Supplier", "Po"] as const;

function ymd(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
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
  const view = params.get("view") ?? "";
  const [categories, setCategories] = useState<OrderCategory[]>([]);
  const [costOpen, setCostOpen] = useState(false);
  const today = useMemo(() => ymd(new Date()), []);
  const weekAhead = useMemo(() => ymd(new Date(Date.now() + 7 * 86_400_000)), []);

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

  useEffect(() => {
    fetch("/api/order-categories", { cache: "no-store" })
      .then(r => (r.ok ? r.json() : []))
      .then((b: OrderCategory[]) => setCategories(b))
      .catch(() => setCategories([]));
  }, []);

  const shown = useMemo(() => rows.filter(r => {
    const open = !["Delivered", "Cancelled", "Rejected"].includes(r.status);
    if (view === "due") return open && !r.arrived_date && !!r.due_date && r.due_date >= today && r.due_date <= weekAhead;
    if (view === "overdue") return open && !r.arrived_date && !!r.due_date && r.due_date < today;
    if (view === "arrived") return !!r.arrived_date;
    if (view === "mine") return r.requester_id === me?.id;
    return true;
  }), [rows, view, today, weekAhead, me]);

  // Grouped under the order type, in the lookup's order; a type the lookup no longer lists goes last.
  const groups = useMemo(() => {
    const order = new Map(categories.map((c, i) => [c.category_key, i]));
    const by = new Map<string, { label: string; rows: OrderRow[] }>();
    for (const r of shown) {
      const g = by.get(r.category) ?? { label: categories.find(c => c.category_key === r.category)?.label ?? r.category, rows: [] };
      g.rows.push(r);
      by.set(r.category, g);
    }
    return [...by.entries()].sort(([a], [b]) => (order.get(a) ?? 1e6) - (order.get(b) ?? 1e6)).map(([key, g]) => ({ key, ...g }));
  }, [shown, categories]);

  const selectedRow = rows.find(r => r.po_number === selected) ?? null;
  const canEdit = can(me, "orderbook", "write");
  const canApprove = can(me, "orderbook", "approve");
  // Cost centres are a purchase officer's (or admin's) to add and edit.
  const canManageCostCentres = me?.auth_role === "purchase_officer" || me?.auth_role === "admin";

  const [costCentres, setCostCentres] = useState<CostCentre[]>([]);
  const [ccForm, setCcForm] = useState<{ code: string; name: string } | null>(null);
  const [ccErr, setCcErr] = useState<string | null>(null);
  const [ccManage, setCcManage] = useState(false);

  // Also reloaded after every order change: approving, cancelling or delivering moves the figures.
  const loadCostCentres = useCallback(() => {
    fetch("/api/cost-centers", { cache: "no-store" })
      .then(r => (r.ok ? r.json() : null))
      .then((b: { cost_centers: CostCentre[] } | null) => setCostCentres(b?.cost_centers ?? []))
      .catch(() => setCostCentres([]));
  }, []);

  useEffect(() => { loadCostCentres(); }, [loadCostCentres]);

  async function addCostCentre() {
    if (!ccForm) return;
    setCcErr(null);
    const res = await fetch("/api/cost-centers", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ code: ccForm.code, name: ccForm.name }),
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
          {/* The dashboard's Open POs tile links here. */}
          <option value="open">Open (not delivered, cancelled or rejected)</option>
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
          {loading ? "Loading…" : `${shown.length} order${shown.length === 1 ? "" : "s"}`}
        </span>
        <button type="button" data-testid="cost-centre-breakdown-open" onClick={() => setCostOpen(true)}
          className="ml-auto rounded border border-h-line bg-h-bg px-2 py-1 text-xs text-h-ink hover:bg-h-surface">
          Cost centre
        </button>
        {canManageCostCentres && (
          <span data-testid="cost-centres" className="flex items-center gap-1.5 text-xs text-h-muted">
            {costCentres.filter(c => c.is_active).length} cost centre{costCentres.filter(c => c.is_active).length === 1 ? "" : "s"}
            <button type="button" data-testid="cost-centre-manage" onClick={() => setCcManage(m => !m)}
              className="rounded border border-h-line bg-h-bg px-1.5 py-0.5 hover:text-h-ink">
              {ccManage ? "Done" : "Edit"}
            </button>
            {ccForm === null ? (
              <button type="button" data-testid="cost-centre-add"
                onClick={() => setCcForm({ code: "", name: "" })}
                className="rounded border border-h-line bg-h-bg px-1.5 py-0.5 hover:text-h-ink">Add</button>
            ) : (
              <>
                <input value={ccForm.code} onChange={e => setCcForm({ ...ccForm, code: e.target.value })}
                  placeholder="Code" data-testid="cost-centre-code"
                  className="h-mono w-20 rounded border border-h-line bg-h-bg px-1.5 py-0.5 text-h-ink" />
                <input value={ccForm.name} onChange={e => setCcForm({ ...ccForm, name: e.target.value })}
                  placeholder="Name" data-testid="cost-centre-name"
                  className="w-32 rounded border border-h-line bg-h-bg px-1.5 py-0.5 text-h-ink" />
                <button type="button" data-testid="cost-centre-save" onClick={() => void addCostCentre()}
                  className="rounded border border-h-line bg-h-bg px-1.5 py-0.5 hover:text-h-ink">Save</button>
                <button type="button" onClick={() => { setCcForm(null); setCcErr(null); }}
                  className="rounded border border-h-line bg-h-bg px-1.5 py-0.5 hover:text-h-ink">Cancel</button>
              </>
            )}
            {ccErr && <span className="text-[#b4443d]">{ccErr}</span>}
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

      <div data-testid="orders-view-filters" className="flex flex-wrap items-center gap-1.5 text-xs">
        {UNCONFIRMED.map(label => (
          <button key={label} type="button" disabled
            title="Not built: what this filter shows is not confirmed yet"
            className="rounded border border-h-line bg-h-bg px-2.5 py-1 text-h-muted opacity-40">
            {label}
          </button>
        ))}
        <span className="mx-1 h-4 border-l border-h-line" />
        {VIEWS.map(v => (
          <button key={v.key} type="button" title={v.hint} data-testid={`orders-view-${v.key}`}
            aria-pressed={view === v.key}
            onClick={() => setParam("view", view === v.key ? "" : v.key)}
            className={`rounded border px-2.5 py-1 ${
              view === v.key
                ? "border-h-accent bg-h-accent text-white"
                : "border-h-line bg-h-bg text-h-ink hover:bg-h-surface"
            }`}>
            {v.label}
          </button>
        ))}
        <button type="button" data-testid="orders-view-clear"
          onClick={() => router.push(selected ? `/orderbook?order=${encodeURIComponent(selected)}` : "/orderbook")}
          className="ml-1 rounded border border-h-line bg-h-bg px-2.5 py-1 text-h-muted hover:text-h-ink">
          Clear
        </button>
      </div>

      {canManageCostCentres && ccManage && (
        <CostCentreManager
          costCentres={costCentres}
          onChanged={u => setCostCentres(list =>
            list.map(c => (c.cost_center_id === u.cost_center_id ? u : c)).sort((a, b) => a.code.localeCompare(b.code)))}
        />
      )}

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
        <table className="w-full min-w-[1500px] border-collapse text-xs">
          <thead className="bg-h-surface text-left text-[10px] uppercase tracking-wide text-h-muted">
            <tr>
              {COLUMNS.map(c => <th key={c} className="px-2 py-1.5">{c}</th>)}
            </tr>
          </thead>
          {shown.length === 0 && !loading ? (
            <tbody>
              <tr>
                <td colSpan={COLUMNS.length} className="px-4 py-8 text-center text-h-muted">
                  No orders yet.
                </td>
              </tr>
            </tbody>
          ) : (
            groups.map(g => (
              <tbody key={g.key} data-testid="order-group">
                <tr>
                  <th colSpan={COLUMNS.length}
                    className="border-t border-h-line bg-h-bg px-2 py-1.5 text-left text-[11px] font-semibold uppercase tracking-wide text-h-ink">
                    {g.label}
                  </th>
                </tr>
                {g.rows.map(r => (
                  <OrderRowView
                    key={r.po_id}
                    row={r}
                    today={today}
                    selected={r.po_number === selected}
                    onSelect={() => setParam("order", r.po_number === selected ? "" : r.po_number)}
                  />
                ))}
              </tbody>
            ))
          )}
        </table>
      </div>

      {selectedRow && (
        <OrderDetailPanel
          key={selectedRow.po_id}
          poId={selectedRow.po_id}
          canEdit={canEdit}
          onChanged={() => { fetchRows(); loadCostCentres(); }}
          onClose={() => setParam("order", "")}
          canApprove={canApprove}
          costCentres={costCentres}
          categories={categories}
        />
      )}

      {costOpen && <CostBreakdownModal onClose={() => setCostOpen(false)} />}
    </div>
  );
}
