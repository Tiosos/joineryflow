"use client";

import { useEffect, useRef } from "react";
import Link from "next/link";
import type { OrderRow } from "@/lib/orders-types";
import { statusClasses, money } from "./shared";

export function OrderRowView({
  row, selected, onSelect,
}: { row: OrderRow; selected: boolean; onSelect: () => void }) {
  const ref = useRef<HTMLTableRowElement>(null);
  // Q418: arriving from Tracking should land on the order, not near it.
  useEffect(() => {
    if (selected) ref.current?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [selected]);

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
      <td className="whitespace-nowrap px-2 py-1.5 h-mono text-h-ink">{row.po_number}</td>
      <td className="px-2 py-1.5 text-h-ink">{row.vendor_name ?? "—"}</td>
      <td className="px-2 py-1.5 text-h-muted">{row.description}</td>
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
      <td className="whitespace-nowrap px-2 py-1.5 h-mono text-h-muted">
        {row.cutlist_no ?? "—"}
      </td>
      <td className="px-2 py-1.5">
        <span className={`rounded px-1.5 py-0.5 text-[10px] ${statusClasses(row.status)}`}>
          {row.status}
        </span>
      </td>
      <td className="whitespace-nowrap px-2 py-1.5 h-mono text-h-muted">
        {row.date_ordered ?? "—"}
      </td>
      <td className="whitespace-nowrap px-2 py-1.5 h-mono text-h-muted">
        {row.due_date ?? "—"}
      </td>
      <td className="whitespace-nowrap px-2 py-1.5 text-right h-mono text-h-ink">
        {money(row.total_amount, row.currency)}
      </td>
    </tr>
  );
}
