"use client";

import { useEffect, useRef } from "react";
import Link from "next/link";
import type { OrderRow } from "@/lib/orders-types";
import { statusClasses, money, qty, fmtDate } from "./shared";

/** The columns, in the old Orderbook's order. The Orders table's header and group rows read this. */
export const COLUMNS = [
  "Priority", "Order", "Requester", "Qty", "Item", "Location", "Pdf", "Project", "Supplier",
  "Stock", "Cost", "Product code", "Required", "Ordered", "Due", "Arrived", "Status",
] as const;

export function OrderRowView({
  row, selected, onSelect, today,
}: { row: OrderRow; selected: boolean; onSelect: () => void; today: string }) {
  const ref = useRef<HTMLTableRowElement>(null);
  // Q418: arriving from Tracking should land on the order, not near it.
  useEffect(() => {
    if (selected) ref.current?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [selected]);

  const closed = ["Delivered", "Cancelled", "Rejected"].includes(row.status);
  // Like the old screen, a required date that has gone by turns red until the order arrives.
  const lateRequired = !!row.required_date && row.required_date < today && !row.arrived_date && !closed;
  const lateDue = !!row.due_date && row.due_date < today && !row.arrived_date && !closed;
  const date = "whitespace-nowrap px-2 py-1.5 h-mono text-h-muted";

  return (
    <tr
      ref={ref}
      data-testid="order-row"
      data-selected={selected ? "true" : undefined}
      onClick={onSelect}
      className={`cursor-pointer border-t border-h-line hover:bg-h-bg ${
        selected ? "bg-h-accent/10 ring-1 ring-inset ring-h-accent" : ""
      }`}
    >
      <td className="px-2 py-1.5">
        <span className={`inline-block min-w-14 rounded px-1.5 py-0.5 text-center text-[10px] uppercase ${statusClasses(row.priority)}`}>
          {row.priority}
        </span>
      </td>
      <td className="whitespace-nowrap px-2 py-1.5 h-mono text-h-ink">{row.po_number}</td>
      <td className="whitespace-nowrap px-2 py-1.5 text-h-muted">{row.requester_name ?? ""}</td>
      <td className="px-2 py-1.5 text-right h-mono text-h-ink">{qty(row.quantity) ?? ""}</td>
      <td className="min-w-56 px-2 py-1.5 text-h-ink">{row.description}</td>
      <td className="px-2 py-1.5 text-h-muted">{row.location ?? ""}</td>
      <td className="px-2 py-1.5 text-center text-h-muted">{row.has_attachment ? "PDF" : ""}</td>
      <td className="px-2 py-1.5 text-h-muted">
        {row.project_id ? (
          <Link
            href={`/tracking?project_id=${row.project_id}`}
            onClick={e => e.stopPropagation()}
            className="hover:text-h-accent hover:underline"
          >
            {row.project_name ?? `#${row.project_id}`}
          </Link>
        ) : (
          // Q554: an order with no project keeps its free-text label.
          row.project_name ?? "—"
        )}
      </td>
      <td className="px-2 py-1.5 text-h-ink">{row.vendor_name ?? "—"}</td>
      <td className="px-2 py-1.5 text-center text-h-muted">{row.stock_tracked ? "✓" : ""}</td>
      <td className="whitespace-nowrap px-2 py-1.5 text-right h-mono text-h-ink">
        {row.total_amount != null ? money(row.total_amount, row.currency) : ""}
      </td>
      <td className="px-2 py-1.5 h-mono text-h-muted">{row.product_code ?? ""}</td>
      <td className={`${date} ${lateRequired ? "bg-[#f2dcd9] text-[#b4443d]" : ""}`}>{fmtDate(row.required_date)}</td>
      <td className={date}>{fmtDate(row.date_ordered)}</td>
      <td className={`${date} ${lateDue ? "bg-[#f2dcd9] text-[#b4443d]" : ""}`}>{fmtDate(row.due_date)}</td>
      <td className={date}>{fmtDate(row.arrived_date)}</td>
      <td className="px-2 py-1.5">
        <span className={`rounded px-1.5 py-0.5 text-[10px] ${statusClasses(row.status)}`}>
          {row.status}
        </span>
      </td>
    </tr>
  );
}
