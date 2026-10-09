"use client";

import type { LinePart } from "@/lib/estimating-types";

interface PartRowProps {
  part: LinePart;
  isDraft: boolean;
  onPatch: (qty: number) => Promise<void>;
  onRemove: () => Promise<void>;
}

export function PartRow({ part, isDraft, onPatch, onRemove }: PartRowProps) {
  return (
    <div className="flex justify-between gap-2">
      <span>
        <span className="font-mono text-h-muted">{part.material_type}</span>{" "}
        {part.sku_snapshot} · {part.description_snapshot}
        {part.len_mm || part.wid_mm ? (
          <span className="ml-1 font-mono text-h-muted">
            {part.len_mm ?? "?"}×{part.wid_mm ?? "?"}
          </span>
        ) : null}
      </span>
      <span className="flex items-center gap-2">
        {isDraft ? (
          <input
            type="number"
            min="0.01"
            step="0.01"
            defaultValue={part.qty}
            onBlur={(e) => {
              const n = Number(e.target.value);
              if (n !== parseFloat(part.qty)) onPatch(n);
            }}
            className="w-16 rounded border border-h-line px-1 font-mono text-right"
            data-testid={`part-qty-${part.part_id}`}
          />
        ) : (
          <span className="font-mono">{parseFloat(part.qty)}</span>
        )}
        <span className="font-mono">{`$${parseFloat(part.cost_extended).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}</span>
        {isDraft ? (
          <button
            type="button"
            onClick={onRemove}
            className="text-red-700 hover:text-red-900"
            title="Remove part"
            data-testid={`remove-part-${part.part_id}`}
          >
            ×
          </button>
        ) : null}
      </span>
    </div>
  );
}
