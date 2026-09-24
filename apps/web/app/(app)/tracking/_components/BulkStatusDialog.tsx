"use client";

import { useState } from "react";

const STATUS_OPTIONS = ["CLEAR", "VOID", "NOTE!", "LIVE", "APPROVED", "HOLD"] as const;
export type StatusKey = (typeof STATUS_OPTIONS)[number];

interface BulkStatusResponse {
  updated: number;
  not_found: number[];
  cross_workspace: number[];
}

interface Props {
  open: boolean;
  itemIds: number[];
  onClose: () => void;
  onApplied: (result: BulkStatusResponse) => void;
}

export function BulkStatusDialog({ open, itemIds, onClose, onApplied }: Props) {
  const [status, setStatus] = useState<StatusKey>("HOLD");
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  if (!open) return null;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setErrorMsg(null);
    if (note.trim().length === 0) {
      setErrorMsg("Note is required for status changes.");
      return;
    }
    setSubmitting(true);
    try {
      const res = await fetch("/api/items/bulk-status", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ item_ids: itemIds, status, note: note.trim() }),
      });
      if (!res.ok) {
        const body = await res.text();
        setErrorMsg(`Bulk status failed (HTTP ${res.status}): ${body.slice(0, 200)}`);
        return;
      }
      const json: BulkStatusResponse = await res.json();
      onApplied(json);
      setNote("");
      onClose();
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
      aria-labelledby="bulk-status-title"
      onClick={onClose}
    >
      <form
        onSubmit={handleSubmit}
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-md rounded-lg border border-h-line bg-h-surface p-4 shadow-xl"
      >
        <h2 id="bulk-status-title" className="text-sm font-semibold text-h-ink">
          Apply status to {itemIds.length} selected item{itemIds.length === 1 ? "" : "s"}
        </h2>

        <label className="mt-4 block text-xs text-h-muted">
          Status
          <select
            value={status}
            onChange={(e) => setStatus(e.target.value as StatusKey)}
            className="mt-1 block w-full rounded border border-h-line bg-h-bg px-2 py-1 text-xs text-h-ink"
            disabled={submitting}
          >
            {STATUS_OPTIONS.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>

        <label className="mt-3 block text-xs text-h-muted">
          Note (required)
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Why is this status changing? (required)"
            rows={3}
            className="mt-1 block w-full rounded border border-h-line bg-h-bg px-2 py-1 text-xs text-h-ink"
            disabled={submitting}
            required
            minLength={1}
          />
        </label>

        {errorMsg ? (
          <p className="mt-3 rounded border border-[#b4443d] bg-[#f2dcd9] px-2 py-1 text-[11px] text-[#b4443d]">
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
            disabled={submitting || note.trim().length === 0}
            className="rounded bg-h-accent px-3 py-1 text-xs font-semibold text-white disabled:opacity-50"
          >
            {submitting ? "Applying…" : `Apply ${status}`}
          </button>
        </div>
      </form>
    </div>
  );
}
