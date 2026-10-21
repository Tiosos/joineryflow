"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import type { CostCentreReport } from "@/lib/orders-types";

const money = (v: string) => `$${Number(v).toLocaleString("en-AU", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

/** Every cost centre's budget against what approved orders still hold and what delivered ones cost,
 *  with totals, and the orders that sit outside every budget. Nothing here blocks an order. */
export function BudgetReport() {
  const [data, setData] = useState<CostCentreReport | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/cost-centers/report", { cache: "no-store" })
      .then(r => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((b: CostCentreReport) => setData(b))
      .catch(e => setErr(String(e)));
  }, []);

  if (err) return <p className="text-sm text-[#b4443d]">Could not load the report: {err}</p>;
  if (!data) return <p className="text-xs text-h-muted">Loading…</p>;

  const ordersLink = (id: number | "none", n: number) => (
    n > 0
      ? <Link href={`/orderbook?cost_center=${id}`} className="underline hover:text-h-ink">{n}</Link>
      : <span>0</span>
  );

  return (
    <div className="grid gap-3">
      <table data-testid="budget-report" className="w-full border-collapse text-xs">
        <thead className="bg-h-surface text-left text-[10px] uppercase tracking-wide text-h-muted">
          <tr>
            <th className="px-2 py-1.5">Code</th>
            <th className="px-2 py-1.5">Name</th>
            <th className="px-2 py-1.5 text-right">Year</th>
            <th className="px-2 py-1.5 text-right">Budget</th>
            <th className="px-2 py-1.5 text-right">Committed</th>
            <th className="px-2 py-1.5 text-right">Spent</th>
            <th className="px-2 py-1.5 text-right">Remaining</th>
            <th className="px-2 py-1.5 text-right">Orders</th>
          </tr>
        </thead>
        <tbody>
          {data.rows.length === 0 && (
            <tr><td colSpan={8} className="px-2 py-4 text-h-muted">No cost centres yet.</td></tr>
          )}
          {data.rows.map(r => (
            <tr key={r.cost_center_id} data-testid="budget-row" data-code={r.code}
              className={`border-t border-h-line ${r.is_active ? "text-h-ink" : "text-h-muted"}`}>
              <td className="h-mono px-2 py-1.5">{r.code}{!r.is_active && <span className="ml-1.5 font-sans text-[10px] uppercase">inactive</span>}</td>
              <td className="px-2 py-1.5">{r.name}</td>
              <td className="h-mono px-2 py-1.5 text-right">{r.fiscal_year ?? "—"}</td>
              <td className="h-mono px-2 py-1.5 text-right">{money(r.budget_amount)}</td>
              <td className="h-mono px-2 py-1.5 text-right">{money(r.committed)}</td>
              <td className="h-mono px-2 py-1.5 text-right">{money(r.spent)}</td>
              <td className={`h-mono px-2 py-1.5 text-right ${Number(r.remaining) < 0 ? "font-medium text-[#b4443d]" : ""}`}>{money(r.remaining)}</td>
              <td className="h-mono px-2 py-1.5 text-right">{ordersLink(r.cost_center_id, r.order_count)}</td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr data-testid="budget-total" className="border-t-2 border-h-line bg-h-bg font-medium text-h-ink">
            <td className="px-2 py-1.5" colSpan={3}>Total</td>
            <td className="h-mono px-2 py-1.5 text-right">{money(data.totals.budget_amount)}</td>
            <td className="h-mono px-2 py-1.5 text-right">{money(data.totals.committed)}</td>
            <td className="h-mono px-2 py-1.5 text-right">{money(data.totals.spent)}</td>
            <td className={`h-mono px-2 py-1.5 text-right ${Number(data.totals.remaining) < 0 ? "text-[#b4443d]" : ""}`}>{money(data.totals.remaining)}</td>
            <td className="h-mono px-2 py-1.5 text-right">{data.totals.order_count}</td>
          </tr>
        </tfoot>
      </table>

      <p data-testid="budget-unallocated" className="text-xs text-h-muted">
        Unallocated: {ordersLink("none", data.unallocated.order_count)} order{data.unallocated.order_count === 1 ? "" : "s"}
        {data.unallocated.order_count > 0 && <> worth <span className="h-mono text-h-ink">{money(data.unallocated.total_amount)}</span></>}
        {" "}with no cost centre, so outside every budget above. Orders that are cancelled or rejected are not counted anywhere here.
      </p>
    </div>
  );
}
