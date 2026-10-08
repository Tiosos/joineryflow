"use client";

import { useState } from "react";
import { CallApiFn } from "./shared";

interface NewLineFormProps {
  revisionId: number;
  callApi: CallApiFn;
  onCreated: () => Promise<void>;
}

export function NewLineForm({ revisionId, callApi, onCreated }: NewLineFormProps) {
  const [description, setDescription] = useState("");
  const [qty, setQty] = useState("1");
  const [unit, setUnit] = useState("EA");
  const [submitting, setSubmitting] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const qtyNum = Number(qty);
    if (!description.trim() || !Number.isFinite(qtyNum) || qtyNum <= 0) return;
    setSubmitting(true);
    const r = await callApi("POST", `/api/revisions/${revisionId}/lines`, {
      description: description.trim(),
      qty: qtyNum,
      unit: unit.trim() || "EA",
    });
    setSubmitting(false);
    if (r.ok) {
      setDescription("");
      setQty("1");
      setUnit("EA");
      await onCreated();
    }
  }

  return (
    <form
      onSubmit={submit}
      className="flex flex-wrap items-end gap-2 rounded border border-dashed border-h-line bg-white p-3"
      data-testid="new-line-form"
    >
      <div className="flex-1 min-w-[200px]">
        <label className="block text-xs uppercase tracking-wide text-h-muted">Description</label>
        <input
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          required
          placeholder="Kitchen island cabinet"
          className="mt-1 w-full rounded border border-h-line px-2 py-1 text-sm"
          data-testid="new-line-description"
        />
      </div>
      <div className="w-24">
        <label className="block text-xs uppercase tracking-wide text-h-muted">Qty</label>
        <input
          type="number"
          min="0.01"
          step="0.01"
          value={qty}
          onChange={(e) => setQty(e.target.value)}
          className="mt-1 w-full rounded border border-h-line px-2 py-1 font-mono text-sm"
          data-testid="new-line-qty"
        />
      </div>
      <div className="w-20">
        <label className="block text-xs uppercase tracking-wide text-h-muted">Unit</label>
        <input
          value={unit}
          onChange={(e) => setUnit(e.target.value)}
          className="mt-1 w-full rounded border border-h-line px-2 py-1 text-sm"
        />
      </div>
      <button
        type="submit"
        disabled={submitting}
        className="rounded bg-h-accent px-3 py-1.5 text-sm font-medium text-white shadow hover:opacity-90 disabled:opacity-50"
        data-testid="new-line-submit"
      >
        + Add line
      </button>
    </form>
  );
}
