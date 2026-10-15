"use client";

import { useEffect, useState } from "react";
import { apiCall } from "@/lib/api";
import type { StockRow } from "@/lib/order-tabs-types";
import type { OrderDetail } from "@/lib/orders-types";
import { money, qty } from "../shared";

const TH = "border border-h-line bg-h-bg px-2 py-1 text-left text-[10px] font-semibold uppercase tracking-wide text-h-muted";
const TD = "border border-h-line px-2 py-1";

/** The old Stock tab: the stock-tracked orders (not Cancelled / Rejected) for this order's product code. */
export function StockTab({ order }: { order: OrderDetail }) {
  const [rows, setRows] = useState<StockRow[] | null>(null);
  const [err, setErr] = useState(false);
  useEffect(() => {
    apiCall<{ stock: StockRow[] }>(`/api/orders/${order.po_id}/stock`).then(b => setRows(b.stock)).catch(() => setErr(true));
  }, [order.po_id]);
  return (
    <div data-testid="tab-stock" className="grid gap-2">
      <p className="text-h-muted">Stock-tracked orders for product code <span className="h-mono text-h-ink">{order.product_code ?? "—"}</span>.</p>
      {err && <p role="alert" className="text-[#b4443d]">Could not load the stock list</p>}
      <table className="w-full border-collapse">
        <thead><tr><th className={TH}>Qty</th><th className={TH}>Pcode</th><th className={TH}>Project</th><th className={TH}>Item</th><th className={TH}>Cost</th><th className={TH}>Otype</th></tr></thead>
        <tbody>
          {(rows ?? []).map(r => (
            <tr key={r.po_id} data-testid="stock-row">
              <td className={`${TD} h-mono text-right`}>{qty(r.quantity) ?? ""}</td>
              <td className={`${TD} h-mono`}>{r.product_code}</td>
              <td className={TD}>{r.project_name}</td>
              <td className={TD}>{r.description}</td>
              <td className={`${TD} h-mono text-right`}>{money(r.total_amount, null)}</td>
              <td className={TD}>{r.category}</td>
            </tr>
          ))}
          {rows && rows.length === 0 && <tr><td colSpan={6} className={`${TD} text-h-muted`}>No stock-tracked orders for this product.</td></tr>}
        </tbody>
      </table>
    </div>
  );
}
