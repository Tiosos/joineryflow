"use client";

import { useEffect, useState } from "react";
import type { OrderLine, PatchOrderLineIn } from "@/lib/orders-types";
import { money, qty } from "./shared";
import { ErrorLine } from "./ErrorLine";

export function LineRow({
  line, canEdit, currency, error, onPatch, onRemove,
}: {
  line: OrderLine;
  canEdit: boolean;
  currency: string | null;
  error?: string;
  onPatch: (payload: PatchOrderLineIn) => Promise<boolean>;
  onRemove: () => Promise<void>;
}) {
  const [description, setDescription] = useState(line.item_description);
  const [sku, setSku] = useState(line.sku ?? "");
  const [quantity, setQuantity] = useState(line.quantity);
  const [unit, setUnit] = useState(line.unit ?? "");
  const [unitPrice, setUnitPrice] = useState(line.unit_price);

  // Resync to the server's canonical value after a save — e.g. quantity
  // "5" round-trips as "5.000" (numeric(10,3)) — so the next blur's dirty
  // check compares against what the DB actually holds, not what was typed.
  useEffect(() => setDescription(line.item_description), [line.item_description]);
  useEffect(() => setSku(line.sku ?? ""), [line.sku]);
  useEffect(() => setQuantity(line.quantity), [line.quantity]);
  useEffect(() => setUnit(line.unit ?? ""), [line.unit]);
  useEffect(() => setUnitPrice(line.unit_price), [line.unit_price]);

  if (!canEdit) {
    return (
      <tr className="border-t border-h-line">
        <td className="px-2 py-1 text-h-ink">{line.item_description}</td>
        <td className="px-2 py-1 h-mono text-h-muted">{line.sku ?? "—"}</td>
        <td className="px-2 py-1 text-right h-mono">{qty(line.quantity)}</td>
        <td className="px-2 py-1 text-h-muted">{line.unit ?? "—"}</td>
        <td className="px-2 py-1 text-right h-mono">{money(line.unit_price, currency)}</td>
        <td className="px-2 py-1 text-right h-mono">{money(line.line_total, currency)}</td>
      </tr>
    );
  }

  return (
    <tr className="border-t border-h-line align-top">
      <td className="px-2 py-1">
        <input
          value={description}
          onChange={e => setDescription(e.target.value)}
          onBlur={async () => {
            if (description !== line.item_description
              && !(await onPatch({ item_description: description }))) {
              setDescription(line.item_description);
            }
          }}
          className="w-full rounded border border-h-line bg-h-bg px-1 py-0.5 text-h-ink"
        />
      </td>
      <td className="px-2 py-1">
        <input
          value={sku}
          onChange={e => setSku(e.target.value)}
          onBlur={async () => {
            if (sku !== (line.sku ?? "") && !(await onPatch({ sku: sku || null }))) {
              setSku(line.sku ?? "");
            }
          }}
          className="h-mono w-20 rounded border border-h-line bg-h-bg px-1 py-0.5 text-h-ink"
        />
      </td>
      <td className="px-2 py-1">
        <input
          value={quantity}
          onChange={e => setQuantity(e.target.value)}
          onBlur={async () => {
            if (quantity !== line.quantity && !(await onPatch({ quantity }))) {
              setQuantity(line.quantity);
            }
          }}
          className="h-mono w-16 rounded border border-h-line bg-h-bg px-1 py-0.5 text-right text-h-ink"
        />
      </td>
      <td className="px-2 py-1">
        <input
          value={unit}
          onChange={e => setUnit(e.target.value)}
          onBlur={async () => {
            if (unit !== (line.unit ?? "") && !(await onPatch({ unit: unit || null }))) {
              setUnit(line.unit ?? "");
            }
          }}
          className="w-16 rounded border border-h-line bg-h-bg px-1 py-0.5 text-h-ink"
        />
      </td>
      <td className="px-2 py-1">
        <input
          value={unitPrice}
          onChange={e => setUnitPrice(e.target.value)}
          onBlur={async () => {
            if (unitPrice !== line.unit_price && !(await onPatch({ unit_price: unitPrice }))) {
              setUnitPrice(line.unit_price);
            }
          }}
          className="h-mono w-20 rounded border border-h-line bg-h-bg px-1 py-0.5 text-right text-h-ink"
        />
      </td>
      <td className="px-2 py-1 text-right h-mono">{money(line.line_total, currency)}</td>
      <td className="px-2 py-1">
        <button
          type="button"
          onClick={() => void onRemove()}
          className="text-[#b4443d] hover:underline"
          aria-label="Remove line"
        >
          ×
        </button>
        {error && <ErrorLine msg={error} />}
      </td>
    </tr>
  );
}
