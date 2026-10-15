"use client";

import type { OrderDetail } from "@/lib/orders-types";

const LABEL = "w-40 text-[10px] font-semibold uppercase tracking-wide text-h-muted";
const BOX = "min-h-8 flex-1 rounded border border-h-line bg-h-bg px-2 py-1.5 text-h-ink";
const when = (iso: string) => { const d = new Date(iso); return `${d.toLocaleDateString("en-AU")} ${d.toLocaleTimeString("en-AU", { hour: "numeric", minute: "2-digit" })}`; };

/** The old ADMIN tab: when the order was cancelled, by whom and why, with the product description. */
export function AdminTab({ order }: { order: OrderDetail }) {
  const row = (label: string, value: string | null, testId: string) => (
    <div className="flex items-center gap-2"><span className={LABEL}>{label}</span><div data-testid={testId} className={BOX}>{value ?? ""}</div></div>
  );
  return (
    <div data-testid="tab-admin" className="grid max-w-lg gap-2">
      {row("Date cancelled", order.cancelled_at ? when(order.cancelled_at) : null, "admin-cancelled-at")}
      {row("Cancelled by", order.cancelled_by_name, "admin-cancelled-by")}
      {row("Cancel reason", order.cancel_reason, "admin-cancel-reason")}
      <div className="mt-2 rounded border border-h-line bg-h-bg px-2 py-2 text-h-ink">{order.description}</div>
    </div>
  );
}
