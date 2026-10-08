"use client";

import Link from "next/link";
import type { TrackingItemRow } from "@/lib/pm-types";

/**
 * Q417: the leftmost reference depends on the row type — a Joinery Item shows
 * its cutlist number, a related part shows the supplier-order number, because
 * a related part never receives a cutlist number at all.
 *
 * Q567 fixes what "issued" means: the API returns `issued_order_no` only once
 * that order carries a `date_ordered`, so a draft order leaves the cell blank.
 *
 * Q418: clicking the order number opens Orderbook **on that order**.
 * `/orderbook` reads `purchase_orders` since the E2 rework and honours the
 * `order` param by selecting the row and opening its detail panel; #4's
 * procurement-batch queue moved to the Delivery queue tab beside it (Q504).
 */
export function ReferenceCell({
  row,
  projectId,
  readOnly = false,
}: {
  row: TrackingItemRow;
  projectId: number;
  readOnly?: boolean;
}) {
  if (row.row_type !== "related_part") {
    // Q438/Q568: the cutlist's number, which several items share — not this
    // item's own. Blank while the item has no cutlist, which Q440 allows
    // indefinitely; its Item ID still identifies the row.
    //
    // `plan_v1.md` §1218: "Clicking that number opens a separate window
    // containing the cutlist details" — Q545 defines "separate window" as a
    // target="_blank" tab, and Q474 puts those details on /list.
    if (row.cutlist_no == null) {
      return <span className="text-h-muted" title="No cutlist assigned yet">—</span>;
    }
    if (readOnly) return <span>{row.cutlist_no}</span>;      // a deleted item's cutlist is hidden too
    return (
      <Link
        href={`/list?project_id=${projectId}&cutlist=${row.cutlist_id}`}
        target="_blank"
        className="hover:text-h-accent hover:underline"
        title="Open this cutlist in a new tab"
      >
        {row.cutlist_no}
      </Link>
    );
  }
  if (!row.issued_order_no) {
    return (
      <span className="text-h-muted" title="No supplier order issued yet">
        —
      </span>
    );
  }
  return (
    <Link
      href={`/orderbook?order=${encodeURIComponent(row.issued_order_no)}`}
      className="text-h-accent hover:underline"
      title="Open this order in Orderbook"
    >
      {row.issued_order_no}
    </Link>
  );
}
