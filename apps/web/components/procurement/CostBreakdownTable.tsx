"use client";

import { useState } from "react";
import type { CostBreakdown } from "@/lib/orders-types";

const money = (v: string) => `$${Number(v).toLocaleString("en-AU", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

/**
 * Material cost by order type, as a collapsible table: one row per type (order count and total),
 * each opening onto its orders. Open by default. Shared by the Orderbook's Cost centre pop-up and
 * Tracking > Info > Budget.
 */
export function CostBreakdownTable({ data }: { data: CostBreakdown }) {
  const [closed, setClosed] = useState<Set<string>>(new Set());
  const toggle = (k: string) =>
    setClosed(s => { const n = new Set(s); if (!n.delete(k)) n.add(k); return n; });

  return (
    <table data-testid="cost-breakdown" className="w-full border-collapse text-xs">
      <thead className="bg-h-surface text-left text-[10px] uppercase tracking-wide text-h-muted">
        <tr>
          <th className="px-2 py-1.5">Material type</th>
          <th className="px-2 py-1.5 text-right">Orders</th>
          <th className="px-2 py-1.5 text-right">Cost</th>
        </tr>
      </thead>
      {data.groups.map(g => {
        const open = !closed.has(g.category);
        return (
          <tbody key={g.category} data-testid="cost-breakdown-group">
            <tr
              onClick={() => toggle(g.category)}
              aria-expanded={open}
              className="cursor-pointer border-t border-h-line bg-h-bg font-medium text-h-ink hover:bg-h-surface"
            >
              <td className="px-2 py-1.5">
                <span className="mr-1.5 inline-block w-3 text-h-muted">{open ? "▾" : "▸"}</span>
                {g.label}
              </td>
              <td className="px-2 py-1.5 text-right h-mono">{g.order_count}</td>
              <td className="px-2 py-1.5 text-right h-mono">{money(g.total)}</td>
            </tr>
            {open && g.orders.map(o => (
              <tr key={o.po_id} className="border-t border-h-line text-h-muted">
                <td className="py-1 pl-7 pr-2">
                  <span className="h-mono text-h-ink">{o.po_number}</span>
                  {" "}{o.vendor_name ?? "—"} · {o.description}
                  {o.product_code ? <span className="h-mono"> · {o.product_code}</span> : null}
                </td>
                <td className="px-2 py-1 text-right">{o.status}</td>
                <td className="px-2 py-1 text-right h-mono">{money(o.total_amount)}</td>
              </tr>
            ))}
          </tbody>
        );
      })}
      <tfoot>
        <tr className="border-t-2 border-h-line font-semibold text-h-ink">
          <td className="px-2 py-1.5" colSpan={2}>Total material cost</td>
          <td className="px-2 py-1.5 text-right h-mono" data-testid="cost-breakdown-total">{money(data.total)}</td>
        </tr>
      </tfoot>
    </table>
  );
}
