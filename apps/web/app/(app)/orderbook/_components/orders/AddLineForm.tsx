"use client";

import { useState } from "react";
import type { CreateOrderLineIn } from "@/lib/orders-types";
import { ErrorLine } from "./ErrorLine";

export function AddLineForm({
  onAdd, error,
}: { onAdd: (payload: CreateOrderLineIn) => Promise<boolean>; error?: string }) {
  const [description, setDescription] = useState("");
  const [sku, setSku] = useState("");
  const [quantity, setQuantity] = useState("1");
  const [unit, setUnit] = useState("");
  const [unitPrice, setUnitPrice] = useState("0");
  const [busy, setBusy] = useState(false);

  async function submit() {
    if (!description.trim() || busy) return;
    setBusy(true);
    try {
      const ok = await onAdd({
        item_description: description.trim(),
        quantity,
        unit_price: unitPrice,
        sku: sku || null,
        unit: unit || null,
      });
      if (ok) {
        setDescription(""); setSku(""); setQuantity("1"); setUnit(""); setUnitPrice("0");
      }
    } finally {
      // A thrown network error or invalid-JSON response (onAdd doesn't
      // catch either) must still release the button — otherwise it's
      // stuck on "Adding…" for the rest of the panel's life.
      setBusy(false);
    }
  }

  return (
    <div className="mt-2 flex flex-wrap items-center gap-2">
      <input
        placeholder="Description"
        value={description}
        onChange={e => setDescription(e.target.value)}
        className="min-w-[160px] flex-1 rounded border border-h-line bg-h-bg px-2 py-1 text-h-ink"
      />
      <input
        placeholder="SKU"
        value={sku}
        onChange={e => setSku(e.target.value)}
        className="h-mono w-24 rounded border border-h-line bg-h-bg px-2 py-1 text-h-ink"
      />
      <input
        placeholder="Qty"
        value={quantity}
        onChange={e => setQuantity(e.target.value)}
        className="h-mono w-16 rounded border border-h-line bg-h-bg px-2 py-1 text-h-ink"
      />
      <input
        placeholder="Unit"
        value={unit}
        onChange={e => setUnit(e.target.value)}
        className="w-16 rounded border border-h-line bg-h-bg px-2 py-1 text-h-ink"
      />
      <input
        placeholder="Unit price"
        value={unitPrice}
        onChange={e => setUnitPrice(e.target.value)}
        className="h-mono w-20 rounded border border-h-line bg-h-bg px-2 py-1 text-h-ink"
      />
      <button
        type="button"
        onClick={() => void submit()}
        disabled={busy || !description.trim()}
        className="rounded bg-h-accent px-3 py-1 text-white disabled:opacity-40"
      >
        {busy ? "Adding…" : "+ Add line"}
      </button>
      {error && <ErrorLine msg={error} />}
    </div>
  );
}
