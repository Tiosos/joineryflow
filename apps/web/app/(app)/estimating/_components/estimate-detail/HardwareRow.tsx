"use client";

import type { LineHardware } from "@/lib/estimating-types";

interface HardwareRowProps {
  hardware: LineHardware;
  isDraft: boolean;
  onPatch: (qty: number) => Promise<void>;
  onRemove: () => Promise<void>;
}

export function HardwareRow({ hardware, isDraft, onPatch, onRemove }: HardwareRowProps) {
  return (
    <div className="flex justify-between gap-2">
      <span>
        <span className="font-mono text-h-muted">{hardware.material_type}</span>{" "}
        {hardware.sku_snapshot} · {hardware.description_snapshot}
      </span>
      <span className="flex items-center gap-2">
        {isDraft ? (
          <input
            type="number"
            min="0.01"
            step="0.01"
            defaultValue={hardware.qty}
            onBlur={(e) => {
              const n = Number(e.target.value);
              if (n !== parseFloat(hardware.qty)) onPatch(n);
            }}
            className="w-16 rounded border border-h-line px-1 font-mono text-right"
            data-testid={`hw-qty-${hardware.hw_id}`}
          />
        ) : (
          <span className="font-mono">{parseFloat(hardware.qty)}</span>
        )}
        <span className="font-mono">{`$${parseFloat(hardware.cost_extended).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}</span>
        {isDraft ? (
          <button
            type="button"
            onClick={onRemove}
            className="text-red-700 hover:text-red-900"
            title="Remove hardware"
            data-testid={`remove-hw-${hardware.hw_id}`}
          >
            ×
          </button>
        ) : null}
      </span>
    </div>
  );
}
