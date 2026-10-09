"use client";

import { useState } from "react";
import type { CostCentre } from "@/lib/orders-types";
import { ErrorLine } from "./ErrorLine";

/**
 * Rename or switch off a cost centre (purchase officer / admin). Orders that already use one are
 * left as they are; an inactive one just cannot be chosen on an order again.
 */
export function CostCentreManager({
  costCentres, onChanged,
}: {
  costCentres: CostCentre[];
  onChanged: (updated: CostCentre) => void;
}) {
  const [edit, setEdit] = useState<Record<number, { code: string; name: string }>>({});
  const [errors, setErrors] = useState<Record<number, string>>({});

  async function patch(id: number, body: { code?: string; name?: string; is_active?: boolean }) {
    setErrors(e => ({ ...e, [id]: "" }));
    const res = await fetch(`/api/cost-centers/${id}`, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    }).catch(() => null);
    if (!res || !res.ok) {
      const b = res ? await res.json().catch(() => null) : null;
      setErrors(e => ({
        ...e,
        [id]: b?.detail?.code === "COST_CENTRE_EXISTS" ? "That code is already used" : "Could not save",
      }));
      return;
    }
    onChanged((await res.json()) as CostCentre);
    setEdit(({ [id]: _done, ...rest }) => rest);
  }

  return (
    <ul data-testid="cost-centre-manager" className="mb-2 space-y-1 text-xs">
      {costCentres.map(c => {
        const draft = edit[c.cost_center_id] ?? { code: c.code, name: c.name };
        const dirty = draft.code !== c.code || draft.name !== c.name;
        return (
          <li key={c.cost_center_id}>
            <div className="flex items-center gap-1.5">
              <input value={draft.code} data-testid="cost-centre-edit-code"
                onChange={e => setEdit(m => ({ ...m, [c.cost_center_id]: { ...draft, code: e.target.value } }))}
                className="h-mono w-20 rounded border border-h-line bg-h-bg px-1.5 py-0.5 text-h-ink" />
              <input value={draft.name} data-testid="cost-centre-edit-name"
                onChange={e => setEdit(m => ({ ...m, [c.cost_center_id]: { ...draft, name: e.target.value } }))}
                className="w-40 rounded border border-h-line bg-h-bg px-1.5 py-0.5 text-h-ink" />
              {dirty && (
                <button type="button" data-testid="cost-centre-edit-save"
                  disabled={!draft.code.trim() || !draft.name.trim()}
                  onClick={() => void patch(c.cost_center_id, { code: draft.code, name: draft.name })}
                  className="rounded border border-h-line bg-h-bg px-1.5 py-0.5 hover:text-h-ink disabled:opacity-50">Save</button>
              )}
              <button type="button" data-testid="cost-centre-toggle"
                onClick={() => void patch(c.cost_center_id, { is_active: !c.is_active })}
                className="rounded border border-h-line bg-h-bg px-1.5 py-0.5 text-h-muted hover:text-h-ink">
                {c.is_active ? "Deactivate" : "Reactivate"}
              </button>
              {!c.is_active && <span className="text-h-muted">inactive</span>}
            </div>
            {errors[c.cost_center_id] && <ErrorLine msg={errors[c.cost_center_id]} />}
          </li>
        );
      })}
    </ul>
  );
}
