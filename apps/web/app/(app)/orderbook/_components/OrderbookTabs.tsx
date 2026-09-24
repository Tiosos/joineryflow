"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { OrdersClient } from "./OrdersClient";
import { QueueClient } from "./QueueClient";

type Tab = "orders" | "queue";

interface Props {
  initial: {
    tab?: string;
    status?: string;
    supplier?: string;
    project_id?: string;
    order?: string;
  };
}

export function OrderbookTabs({ initial }: Props) {
  const router = useRouter();
  const params = useSearchParams();
  // Arriving with ?order= means "find me this order", so land on Orders even
  // when no tab is named (Q418).
  const raw = params.get("tab") ?? initial.tab ?? "";
  const tab: Tab = raw === "queue" ? "queue" : "orders";

  function setTab(next: Tab) {
    const qs = new URLSearchParams(params.toString());
    if (next === "orders") qs.delete("tab"); else qs.set("tab", next);
    // The two tabs filter different things; carrying one's status value onto
    // the other would silently hide rows.
    qs.delete("status");
    qs.delete("supplier");
    const s = qs.toString();
    router.push(s ? `/orderbook?${s}` : "/orderbook");
  }

  return (
    <div className="grid gap-3">
      <nav className="flex gap-1 border-b border-h-line">
        {(["orders", "queue"] as const).map(t => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            aria-current={tab === t ? "page" : undefined}
            className={`-mb-px border-b-2 px-3 py-1.5 text-xs transition ${
              tab === t
                ? "border-h-accent text-h-ink"
                : "border-transparent text-h-muted hover:text-h-ink"
            }`}
          >
            {t === "orders" ? "Orders" : "Delivery queue"}
          </button>
        ))}
      </nav>
      {tab === "orders" ? <OrdersClient /> : <QueueClient initial={initial} />}
    </div>
  );
}
