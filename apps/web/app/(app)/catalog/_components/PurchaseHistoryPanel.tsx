"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { getPurchaseHistory } from "@/lib/catalog-fetch";
import type { CatalogSlug, PurchaseHistory } from "@/lib/catalog-types";

/** What this workspace has paid for a catalog row's SKU, from the Orderbook (placed or Delivered
 * orders, matched on product code). Read-only: the row's Unit cost is never changed from here. */
export default function PurchaseHistoryPanel({ slug, mid }: { slug: CatalogSlug; mid: number }) {
  const [data, setData] = useState<PurchaseHistory | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getPurchaseHistory(slug, mid)
      .then((d) => { if (!cancelled) setData(d); })
      .catch((e: Error) => {
        if (!cancelled) setError(e.message === "forbidden" ? "You do not have access to order prices." : "Could not load the purchase history.");
      });
    return () => { cancelled = true; };
  }, [slug, mid]);

  if (error) return <p className="px-3 py-2 text-xs text-rose-700">{error}</p>;
  if (!data) return <p className="px-3 py-2 text-xs text-h-muted">Loading…</p>;
  if (data.orders.length === 0) {
    return <p data-testid="purchase-history-empty" className="px-3 py-2 text-xs text-h-muted">No placed or delivered orders for this SKU yet.</p>;
  }
  const money = (v: string | null) => (v == null ? "—" : Number(v).toFixed(2));
  return (
    <div data-testid="purchase-history" className="px-3 py-2">
      <p className="mb-1 text-xs text-h-muted">
        Latest paid <span className="h-mono text-h-ink">{money(data.latest_price)}</span>
        {" · "}average <span className="h-mono text-h-ink">{money(data.average_price)}</span>
        {` over the last ${data.orders.length} order${data.orders.length === 1 ? "" : "s"}, as entered on the orders.`}
      </p>
      <table className="text-xs">
        <thead className="text-left text-h-muted">
          <tr>
            <th className="pr-4 font-normal">Date</th>
            <th className="pr-4 font-normal">Order</th>
            <th className="pr-4 font-normal">Supplier</th>
            <th className="pr-4 font-normal">Project</th>
            <th className="pr-4 text-right font-normal">Qty</th>
            <th className="pr-4 text-right font-normal">Unit price</th>
            <th className="font-normal">Status</th>
          </tr>
        </thead>
        <tbody>
          {data.orders.map((o) => (
            <tr key={o.po_id} data-testid="purchase-history-row">
              <td className="h-mono pr-4">{o.ordered_on ?? "—"}</td>
              <td className="pr-4"><Link href={`/orderbook?order=${o.po_id}`} className="h-mono text-h-accent">{o.po_number}</Link></td>
              <td className="pr-4">{o.vendor_name ?? "—"}</td>
              <td className="pr-4">{o.project_name ?? "—"}</td>
              <td className="h-mono pr-4 text-right">{o.quantity ?? "—"}</td>
              <td className="h-mono pr-4 text-right">{money(o.unit_price)}</td>
              <td>{o.status}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
