"use client";

import type { CreateOrderLineIn, OrderLine, PatchOrderLineIn } from "@/lib/orders-types";
import { LineRow } from "./LineRow";
import { AddLineForm } from "./AddLineForm";

export function LinesSection({
  lines, canEdit, currency, errors, onPatchLine, onRemoveLine, onAddLine,
}: {
  lines: OrderLine[];
  canEdit: boolean;
  currency: string | null;
  errors: Record<string, string>;
  onPatchLine: (lineId: number, payload: PatchOrderLineIn) => Promise<boolean>;
  onRemoveLine: (lineId: number) => Promise<void>;
  onAddLine: (payload: CreateOrderLineIn) => Promise<boolean>;
}) {
  return (
    <div className="mt-4">
      <p className="mb-1 text-[10px] uppercase tracking-wide text-h-muted">Lines</p>
      <div className="overflow-x-auto rounded border border-h-line">
        <table className="w-full min-w-[720px] border-collapse text-xs">
          <thead className="bg-h-bg text-left text-[10px] uppercase tracking-wide text-h-muted">
            <tr>
              <th className="px-2 py-1">Description</th>
              <th className="px-2 py-1">SKU</th>
              <th className="px-2 py-1 text-right">Qty</th>
              <th className="px-2 py-1">Unit</th>
              <th className="px-2 py-1 text-right">Unit price</th>
              <th className="px-2 py-1 text-right">Total</th>
              {canEdit && <th className="px-2 py-1" />}
            </tr>
          </thead>
          <tbody>
            {lines.length === 0 ? (
              <tr>
                <td colSpan={canEdit ? 7 : 6} className="px-2 py-3 text-center text-h-muted">
                  No lines yet.
                </td>
              </tr>
            ) : (
              lines.map(l => (
                <LineRow
                  key={l.line_id}
                  line={l}
                  canEdit={canEdit}
                  currency={currency}
                  error={errors[`line-${l.line_id}`]}
                  onPatch={payload => onPatchLine(l.line_id, payload)}
                  onRemove={() => onRemoveLine(l.line_id)}
                />
              ))
            )}
          </tbody>
        </table>
      </div>
      {canEdit && (
        <AddLineForm onAdd={onAddLine} error={errors["new-line"]} />
      )}
    </div>
  );
}
