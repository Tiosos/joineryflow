"use client";

import { useState } from "react";

interface Props {
  projectId: number;
  onClose: () => void;
  /** Called with the new item's id once it exists; the caller opens the editor. */
  onCreated: (itemId: number) => void;
}

export function NewItemDialog({ projectId, onClose, onCreated }: Props) {
  const [description, setDescription] = useState("");
  const [code, setCode] = useState("");
  const [qty, setQty] = useState("1");
  const [submitting, setSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setErrorMsg(null);
    const qtyNum = Number(qty);
    if (!Number.isInteger(qtyNum) || qtyNum < 1) {
      setErrorMsg("Qty must be a whole number of 1 or more.");
      return;
    }
    setSubmitting(true);
    try {
      const res = await fetch(`/api/projects/${projectId}/items`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          description: description.trim(),
          code: code.trim() || null,
          qty: qtyNum,
        }),
      });
      if (!res.ok) {
        const body = await res.text();
        setErrorMsg(`Could not create the item (HTTP ${res.status}): ${body.slice(0, 200)}`);
        return;
      }
      const created: { id: number } = await res.json();
      onCreated(created.id);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Network error");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="new-item-title"
      data-testid="new-item-dialog"
      onClick={onClose}
    >
      <form
        onSubmit={handleSubmit}
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-md rounded-lg border border-h-line bg-h-surface p-4 shadow-xl"
      >
        <h2 id="new-item-title" className="text-sm font-semibold text-h-ink">
          New item
        </h2>
        <p className="mt-1 text-xs text-h-muted">
          Creates the item in this project and opens it in the item editor.
        </p>

        <label className="mt-4 block text-xs text-h-muted">
          Description (required)
          <input
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            className="mt-1 block w-full rounded border border-h-line bg-h-bg px-2 py-1 text-xs text-h-ink"
            disabled={submitting}
            required
            autoFocus
            data-testid="new-item-description"
          />
        </label>

        <div className="mt-3 grid grid-cols-[1fr_5rem] gap-3">
          <label className="block text-xs text-h-muted">
            Code
            <input
              value={code}
              onChange={(e) => setCode(e.target.value)}
              className="mt-1 block w-full rounded border border-h-line bg-h-bg px-2 py-1 font-mono text-xs text-h-ink"
              disabled={submitting}
              data-testid="new-item-code"
            />
          </label>
          <label className="block text-xs text-h-muted">
            Qty
            <input
              type="number"
              min={1}
              step={1}
              value={qty}
              onChange={(e) => setQty(e.target.value)}
              className="mt-1 block w-full rounded border border-h-line bg-h-bg px-2 py-1 font-mono text-xs text-h-ink"
              disabled={submitting}
              data-testid="new-item-qty"
            />
          </label>
        </div>

        {errorMsg ? (
          <p
            className="mt-3 rounded border border-[#b4443d] bg-[#f2dcd9] px-2 py-1 text-[11px] text-[#b4443d]"
            data-testid="new-item-error"
          >
            {errorMsg}
          </p>
        ) : null}

        <div className="mt-4 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            disabled={submitting}
            className="rounded border border-h-line bg-h-surface px-3 py-1 text-xs text-h-muted hover:text-h-ink"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={submitting || description.trim().length === 0}
            className="rounded bg-h-accent px-3 py-1 text-xs font-semibold text-white disabled:opacity-50"
            data-testid="new-item-create"
          >
            {submitting ? "Creating…" : "Create and open"}
          </button>
        </div>
      </form>
    </div>
  );
}
