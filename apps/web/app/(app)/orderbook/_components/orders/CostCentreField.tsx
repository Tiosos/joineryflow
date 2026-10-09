"use client";

import type { CostCentre } from "@/lib/orders-types";
import { ErrorLine } from "./ErrorLine";
import { Field } from "./Field";

/** The order's optional cost centre: the budget an approval's Commitment is posted against. */
export function CostCentreField({
  value, label, costCentres, canEdit, onSave, error,
}: {
  value: number | null;
  /** "CODE Name" of the current one, from the order. */
  label: string | null;
  costCentres: CostCentre[];
  canEdit: boolean;
  onSave: (id: number | null) => Promise<boolean>;
  error?: string;
}) {
  if (!canEdit) return <Field label="Cost centre" value={label} mono />;
  return (
    <div>
      <dt className="text-[10px] uppercase tracking-wide text-h-muted">Cost centre</dt>
      <select
        value={value ?? ""}
        data-testid="order-cost-centre"
        onChange={e => void onSave(e.target.value ? Number(e.target.value) : null)}
        className="h-mono w-full rounded border border-h-line bg-h-bg px-1 py-0.5 text-h-ink"
      >
        <option value="">None</option>
        {costCentres.map(c => <option key={c.cost_center_id} value={c.cost_center_id}>{c.code} {c.name}</option>)}
      </select>
      {error && <ErrorLine msg={error} />}
    </div>
  );
}
