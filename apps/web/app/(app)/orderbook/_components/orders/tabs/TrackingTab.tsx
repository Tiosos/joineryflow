"use client";

import { useEffect, useState } from "react";
import { apiCall } from "@/lib/api";
import type { TrackingTabData } from "@/lib/order-tabs-types";
import type { OrderDetail } from "@/lib/orders-types";
import { fmtDate, qty } from "../shared";

const TH = "border border-h-line bg-h-bg px-2 py-1 text-left text-[10px] font-semibold uppercase tracking-wide text-h-muted";
const TD = "border border-h-line px-2 py-1";

/** The old Tracking tab: the Tracking item this order is for (item, date made, item number) and the order's own number. */
export function TrackingTab({ order }: { order: OrderDetail }) {
  const [data, setData] = useState<TrackingTabData | null>(null);
  const [err, setErr] = useState(false);
  useEffect(() => {
    apiCall<TrackingTabData>(`/api/orders/${order.po_id}/tracking`).then(setData).catch(() => setErr(true));
  }, [order.po_id]);
  return (
    <div data-testid="tab-tracking" className="grid gap-2">
      {err && <p role="alert" className="text-[#b4443d]">Could not load the tracking details</p>}
      {data && !data.item && <p data-testid="tracking-none" className="text-h-muted">This order is not linked to a Tracking item.</p>}
      {data?.item && (
        <>
          <div className="flex items-center gap-2"><span className="text-[10px] font-semibold uppercase tracking-wide text-h-muted">Item ID</span>
            <a href={`/items/${data.item.item_id}`} data-testid="tracking-item-link" className="h-mono rounded border border-h-line bg-h-bg px-2 py-1 text-h-ink hover:bg-h-surface">{data.item.item_number}</a></div>
          <table className="w-full border-collapse">
            <thead><tr><th className={TH}>Item</th><th className={TH}>Date made</th><th className={TH}>Item no.</th><th className={TH}>Order no.</th></tr></thead>
            <tbody><tr data-testid="tracking-row">
              <td className={TD}>{data.item.description}</td>
              <td className={`${TD} h-mono`}>{fmtDate(data.item.date_made) || "—"}</td>
              <td className={`${TD} h-mono`}>{data.item.item_number}</td>
              <td className={`${TD} h-mono`}>{data.order_number}</td>
            </tr></tbody>
          </table>
        </>
      )}
      {data && (
        <div className="grid grid-cols-[1fr_6rem] gap-2">
          <div className="rounded border border-h-line px-2 py-2 text-h-ink">{data.description}</div>
          <div className="h-mono rounded border border-h-line px-2 py-2 text-right text-h-ink">{qty(data.quantity) ?? ""}</div>
        </div>
      )}
    </div>
  );
}
