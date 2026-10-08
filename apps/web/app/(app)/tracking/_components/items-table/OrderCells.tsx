"use client";

import Link from "next/link";
import type { TrackingItemRow } from "@/lib/pm-types";

/**
 * Q425's O/BOOK columns: this row's latest order, whatever its state — a Draft
 * raised moments ago is precisely what the sub-tab is for. Related parts get
 * these columns too: an order against a related part is the normal case (Q424).
 */
export function OrderCells({ row }: { row: TrackingItemRow }) {
  if (row.order_no == null) {
    return (
      <>
        <td className="px-2 py-1 text-h-muted">—</td>
        <td className="px-2 py-1 text-h-muted">—</td>
        <td className="px-2 py-1 text-h-muted">—</td>
        <td className="px-2 py-1 text-h-muted">—</td>
      </>
    );
  }
  return (
    <>
      <td className="whitespace-nowrap px-2 py-1 font-mono text-h-ink">
        <Link
          href={`/orderbook?order=${encodeURIComponent(row.order_no)}`}
          target="_blank"
          className="hover:text-h-accent hover:underline"
          title="Open this order in Orderbook"
        >
          {row.order_no}
        </Link>
      </td>
      <td className="px-2 py-1 text-h-ink">{row.order_supplier ?? "—"}</td>
      <td className="px-2 py-1">
        <span className="rounded-full bg-h-line/50 px-2 py-0.5 text-[10px] font-semibold text-h-ink">
          {row.order_status ?? "—"}
        </span>
      </td>
      <td className="px-2 py-1 font-mono text-[10px] tabular-nums text-h-muted">
        {row.order_due_date ? row.order_due_date.slice(5) : "—"}
      </td>
    </>
  );
}
