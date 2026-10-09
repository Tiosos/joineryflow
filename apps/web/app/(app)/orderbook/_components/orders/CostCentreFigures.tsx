"use client";

import type { CostCentre } from "@/lib/orders-types";
import { money } from "./shared";

/** Budget against what the ledger holds. Information only: nothing is blocked by it. */
export function CostCentreFigures({ cc }: { cc: CostCentre }) {
  const over = Number(cc.remaining) < 0;
  return (
    <p data-testid="cost-centre-figures" className="h-mono mt-0.5 text-[10px] text-h-muted">
      Budget {money(cc.budget_amount, null)} · committed {money(cc.committed, null)} · spent {money(cc.spent, null)} ·{" "}
      <span className={over ? "text-[#b4443d]" : "text-h-ink"}>
        {over ? "over by" : "remaining"} {money(over ? String(-Number(cc.remaining)) : cc.remaining, null)}
      </span>
    </p>
  );
}
