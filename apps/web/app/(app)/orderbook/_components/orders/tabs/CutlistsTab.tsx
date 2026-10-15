"use client";

import { useEffect, useState } from "react";
import { apiCall } from "@/lib/api";
import type { CutlistsTabData } from "@/lib/order-tabs-types";
import type { OrderDetail } from "@/lib/orders-types";

const TH = "border border-h-line bg-h-bg px-2 py-1 text-left text-[10px] font-semibold uppercase tracking-wide text-h-muted";
const TD = "border border-h-line px-2 py-1";
const when = (iso: string) => { const d = new Date(iso); return `${d.toLocaleDateString("en-AU")} ${d.toLocaleTimeString("en-AU", { hour: "numeric", minute: "2-digit" })}`; };

/** The old Cutlists tab: based on the product, the cutlists where this item was used. */
export function CutlistsTab({ order }: { order: OrderDetail }) {
  const [data, setData] = useState<CutlistsTabData | null>(null);
  const [err, setErr] = useState(false);
  useEffect(() => {
    apiCall<CutlistsTabData>(`/api/orders/${order.po_id}/cutlists`).then(setData).catch(() => setErr(true));
  }, [order.po_id]);
  return (
    <div data-testid="tab-cutlists" className="grid gap-2">
      <p className="text-h-muted">Based on the product code, the cutlists where this item was used.</p>
      {err && <p role="alert" className="text-[#b4443d]">Could not load the cutlists</p>}
      {data && !data.product_found && <p data-testid="cutlists-no-product" className="text-h-muted">No catalog product has this order&apos;s product code{order.product_code ? ` (${order.product_code})` : ""}, so there is nothing to look up.</p>}
      {data?.product_found && (
        <table className="w-full border-collapse">
          <thead><tr><th className={TH}>Cutlist</th><th className={TH}>Date</th><th className={TH}>Project</th><th className={TH}>Item</th></tr></thead>
          <tbody>
            {data.cutlists.map(c => (
              <tr key={`${c.cutlist_no}-${c.item_description}`} data-testid="cutlist-row">
                <td className={`${TD} h-mono`}>{c.cutlist_no}</td><td className={`${TD} h-mono`}>{when(c.created_at)}</td>
                <td className={TD}>{c.project_name}</td><td className={TD}>{c.item_description}</td>
              </tr>
            ))}
            {data.cutlists.length === 0 && <tr><td colSpan={4} className={`${TD} text-h-muted`}>This product has not been used on a cutlist yet.</td></tr>}
          </tbody>
        </table>
      )}
    </div>
  );
}
