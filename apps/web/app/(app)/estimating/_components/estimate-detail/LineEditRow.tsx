"use client";

import { useState } from "react";
import type { Line } from "@/lib/estimating-types";
import { CallApiFn } from "./shared";

interface LineEditRowProps {
  line: Line;
  callApi: CallApiFn;
  onSaved: () => Promise<void>;
  onCancel: () => void;
}

export function LineEditRow({ line, callApi, onSaved, onCancel }: LineEditRowProps) {
  const [description, setDescription] = useState(line.description);
  const [qty, setQty] = useState(line.qty);
  const [unit, setUnit] = useState(line.unit);
  const [overrideStr, setOverrideStr] = useState(line.unit_sell_override ?? "");

  async function save() {
    const fields: Record<string, unknown> = {};
    if (description !== line.description) fields.description = description;
    const qtyNum = Number(qty);
    if (Number.isFinite(qtyNum) && qtyNum > 0 && String(qtyNum) !== String(parseFloat(line.qty))) {
      fields.qty = qtyNum;
    }
    if (unit !== line.unit) fields.unit = unit;
    if (overrideStr === "") {
      if (line.unit_sell_override !== null) fields.clear_unit_sell_override = true;
    } else {
      const num = Number(overrideStr);
      if (Number.isFinite(num) && num >= 0) fields.unit_sell_override = num;
    }
    if (Object.keys(fields).length === 0) {
      onCancel();
      return;
    }
    const r = await callApi("PATCH", `/api/lines/${line.line_id}`, fields);
    if (r.ok) await onSaved();
  }

  return (
    <div
      className="mt-2 grid grid-cols-1 gap-2 rounded border border-h-line bg-white p-3 text-xs md:grid-cols-4"
      data-testid={`line-edit-${line.line_id}`}
    >
      <label className="md:col-span-2 flex flex-col">
        <span className="text-h-muted uppercase tracking-wide">Description</span>
        <input
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          className="mt-1 rounded border border-h-line px-2 py-1"
        />
      </label>
      <label className="flex flex-col">
        <span className="text-h-muted uppercase tracking-wide">Qty</span>
        <input
          type="number"
          min="0.01"
          step="0.01"
          value={qty}
          onChange={(e) => setQty(e.target.value)}
          className="mt-1 rounded border border-h-line px-2 py-1 font-mono"
        />
      </label>
      <label className="flex flex-col">
        <span className="text-h-muted uppercase tracking-wide">Unit</span>
        <input
          value={unit}
          onChange={(e) => setUnit(e.target.value)}
          className="mt-1 rounded border border-h-line px-2 py-1"
        />
      </label>
      <label className="md:col-span-2 flex flex-col">
        <span className="text-h-muted uppercase tracking-wide">Unit sell override (blank = use markup)</span>
        <input
          type="number"
          min="0"
          step="0.01"
          value={overrideStr ?? ""}
          onChange={(e) => setOverrideStr(e.target.value)}
          placeholder="auto"
          className="mt-1 rounded border border-h-line px-2 py-1 font-mono"
        />
      </label>
      <div className="md:col-span-2 flex items-end justify-end gap-2">
        <button
          type="button"
          onClick={onCancel}
          className="rounded border border-h-line bg-white px-3 py-1 hover:bg-gray-50"
        >
          Cancel
        </button>
        <button
          type="button"
          onClick={save}
          className="rounded bg-h-accent px-3 py-1 font-medium text-white shadow hover:opacity-90"
          data-testid={`line-edit-save-${line.line_id}`}
        >
          Save
        </button>
      </div>
    </div>
  );
}
