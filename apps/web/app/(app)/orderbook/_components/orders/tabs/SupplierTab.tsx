"use client";

import { useEffect, useState } from "react";
import { apiCall } from "@/lib/api";
import type { SupplierCard } from "@/lib/order-tabs-types";
import type { OrderDetail } from "@/lib/orders-types";

const BOX = "min-h-9 whitespace-pre-wrap rounded border border-h-line bg-h-bg px-2 py-1.5 text-h-ink";
const LABEL = "text-[10px] font-semibold uppercase tracking-wide text-h-muted";

/** The old Supplier tab: the order's supplier as a company card (logo, name, website, notes, metadata). Read-only here; edited in the Supplier list. */
export function SupplierTab({ order }: { order: OrderDetail }) {
  const [s, setS] = useState<SupplierCard | null>(null);
  const [err, setErr] = useState(false);
  useEffect(() => {
    if (order.vendor_id == null) return;
    apiCall<SupplierCard>(`/api/suppliers/${order.vendor_id}`).then(setS).catch(() => setErr(true));
  }, [order.vendor_id]);
  return (
    <div data-testid="tab-supplier" className="grid gap-3">
      {err && <p role="alert" className="text-[#b4443d]">Could not load the supplier</p>}
      {s && (
        <>
          <div className="flex items-start gap-3">
            <div className="grid gap-1 flex-1">
              <span className={LABEL}>Company</span>
              <div data-testid="supplier-name" className={`${BOX} text-sm`}>{s.name}</div>
            </div>
            <div className="grid h-24 w-24 place-items-center overflow-hidden rounded border border-h-line bg-h-bg text-h-muted">
              {s.has_logo
                // eslint-disable-next-line @next/next/no-img-element
                ? <img src={`/api/suppliers/${s.vendor_id}/logo`} alt={`${s.name} logo`} data-testid="supplier-logo" className="max-h-full max-w-full object-contain" />
                : <span>Logo</span>}
            </div>
          </div>
          <div className="grid gap-1"><span className={LABEL}>Website</span>
            <div data-testid="supplier-website" className={BOX}>
              {s.website ? <a href={s.website} target="_blank" rel="noreferrer" className="underline">{s.website}</a> : ""}
            </div></div>
          <div className="grid gap-1"><span className={LABEL}>Notes</span><div data-testid="supplier-notes" className={`${BOX} min-h-20`}>{s.notes ?? ""}</div></div>
          <div className="grid gap-1"><span className={LABEL}>Metadata</span><div data-testid="supplier-metadata" className={`${BOX} min-h-16`}>{s.metadata ?? ""}</div></div>
        </>
      )}
    </div>
  );
}
