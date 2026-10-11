"use client";

import { useEffect, useState } from "react";
import type { CostBreakdown } from "@/lib/orders-types";
import { CostBreakdownTable } from "@/components/procurement/CostBreakdownTable";

/** The Orderbook's Cost centre button: material cost by order type over every order. */
export function CostBreakdownModal({ onClose }: { onClose: () => void }) {
  const [data, setData] = useState<CostBreakdown | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/orders/cost-breakdown", { cache: "no-store" })
      .then(r => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((b: CostBreakdown) => setData(b))
      .catch(e => setErr(String(e)));
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/40 p-4"
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div role="dialog" aria-label="Cost centre" data-testid="cost-breakdown-modal"
        className="w-full max-w-3xl rounded-lg border border-h-line bg-h-surface shadow-xl">
        <header className="flex items-center justify-between gap-4 border-b border-h-line bg-h-bg px-5 py-3">
          <div>
            <div className="text-[10px] font-semibold uppercase tracking-wider text-h-muted">Cost centre</div>
            <div className="text-sm text-h-ink">Material cost by type, every order except cancelled and rejected</div>
          </div>
          <button type="button" onClick={onClose}
            className="rounded border border-h-line bg-h-surface px-3 py-1 text-sm text-h-ink hover:bg-h-bg">
            Close
          </button>
        </header>
        <div className="p-4">
          {err && <p className="text-sm text-[#b4443d]">Could not load the breakdown: {err}</p>}
          {!err && !data && <p className="text-xs text-h-muted">Loading…</p>}
          {data && (data.groups.length === 0
            ? <p className="text-xs text-h-muted">No orders yet.</p>
            : <CostBreakdownTable data={data} />)}
        </div>
      </div>
    </div>
  );
}
