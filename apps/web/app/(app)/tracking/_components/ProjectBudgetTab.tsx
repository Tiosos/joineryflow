"use client";

import { useEffect, useState } from "react";
import type { CostBreakdown } from "@/lib/orders-types";
import { CostBreakdownTable } from "@/components/procurement/CostBreakdownTable";

/**
 * Tracking > Info > Budget: the project's material cost by order type (every order on the project
 * except cancelled and rejected). Managers and admins only; the API refuses anyone else, this tab
 * is just not offered to them. Labour hours sit below it, blank until payroll is connected (Q571).
 */
export function ProjectBudgetTab({ projectId, hours }: { projectId: number; hours: React.ReactNode }) {
  const [data, setData] = useState<CostBreakdown | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    setData(null);
    setErr(null);
    fetch(`/api/projects/${projectId}/budget`, { cache: "no-store" })
      .then(r => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((b: CostBreakdown) => setData(b))
      .catch(e => setErr(String(e)));
  }, [projectId]);

  return (
    <div data-testid="project-budget" className="grid gap-4 p-5">
      <section>
        <h3 className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-h-muted">Material cost</h3>
        {err && <p className="text-sm text-[#b4443d]">Could not load the budget: {err}</p>}
        {!err && !data && <p className="text-xs text-h-muted">Loading…</p>}
        {data && (data.groups.length === 0
          ? <p className="text-xs text-h-muted">No orders on this project yet.</p>
          : <div className="overflow-hidden rounded border border-h-line"><CostBreakdownTable data={data} /></div>)}
      </section>
      <section>
        <h3 className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-h-muted">Labour hours</h3>
        {hours}
      </section>
    </div>
  );
}
