"use client";

import { useEffect, useState } from "react";
import type { ItemOut, ItemStatus } from "@/lib/pm-types";

interface Props {
  itemId: number | null;
  onClose: () => void;
  onUpdated: () => void;
}

const STATUS_CHOICES: ItemStatus[] = [
  "CLEAR", "VOID", "NOTE!", "LIVE", "APPROVED", "HOLD",
];

export function StatusPopup({ itemId, onClose, onUpdated }: Props) {
  const [item, setItem] = useState<ItemOut | null>(null);
  const [loading, setLoading] = useState(false);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [pickedStatus, setPickedStatus] = useState<ItemStatus | null>(null);
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  useEffect(() => {
    if (itemId == null) {
      setItem(null);
      setPickedStatus(null);
      setNote("");
      setSubmitError(null);
      setFetchError(null);
      return;
    }
    setLoading(true);
    setFetchError(null);
    fetch(`/api/items/${itemId}`, { cache: "no-store" })
      .then((r) => (r.ok ? (r.json() as Promise<ItemOut>) : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((data) => {
        setItem(data);
        const current = (data.status as ItemStatus) ?? "CLEAR";
        setPickedStatus(STATUS_CHOICES.includes(current) ? current : "CLEAR");
      })
      .catch((e: unknown) => setFetchError(e instanceof Error ? e.message : "Failed to load"))
      .finally(() => setLoading(false));
  }, [itemId]);

  if (itemId == null) return null;

  const statusLog = item ? item.edit_log.filter((r) => r.field === "item.status") : [];
  const canSubmit = !!pickedStatus && note.trim().length > 0 && !submitting && !!item;

  async function submit() {
    if (!canSubmit || !item || !pickedStatus) return;
    setSubmitting(true);
    setSubmitError(null);
    try {
      const r = await fetch(`/api/items/${item.id}/status`, {
        method: "PATCH",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ status: pickedStatus, note: note.trim() }),
        cache: "no-store",
      });
      if (!r.ok) {
        throw new Error(`HTTP ${r.status}`);
      }
      onUpdated();
      onClose();
    } catch (e: unknown) {
      setSubmitError(e instanceof Error ? e.message : "Update failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="w-full max-w-2xl overflow-hidden rounded-lg border border-h-line bg-h-surface shadow-xl">
        <header className="flex items-center justify-between border-b border-h-line bg-[#1f2937] px-5 py-3">
          <div className="text-sm font-semibold text-white">Add New Status</div>
          <div className="text-[11px] font-mono text-white/70">
            {item ? `#${item.item_number ?? item.id} · ${item.code ?? "—"}` : "—"}
          </div>
        </header>

        {loading ? (
          <div className="p-8 text-center text-h-muted">Loading…</div>
        ) : fetchError ? (
          <div className="p-8 text-center text-[#b4443d]">{fetchError}</div>
        ) : !item ? (
          <div className="p-8 text-center text-h-muted">Not found.</div>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-0 border-b border-h-line">
              <div className="border-r border-h-line p-4">
                <div className="mb-2 rounded bg-[#e6efe5] px-3 py-1 text-center text-xs font-semibold uppercase tracking-wider text-[#3f7d48]">
                  Status
                </div>
                <ul className="grid gap-1.5">
                  {STATUS_CHOICES.map((s) => (
                    <li key={s}>
                      <label className="flex cursor-pointer items-center gap-2 rounded px-2 py-1 text-sm text-h-ink hover:bg-h-bg">
                        <input
                          type="radio"
                          name="status-choice"
                          value={s}
                          checked={pickedStatus === s}
                          onChange={() => setPickedStatus(s)}
                          className="h-3 w-3 accent-h-accent"
                        />
                        <span className="font-mono">{s}</span>
                      </label>
                    </li>
                  ))}
                </ul>
              </div>

              <div className="p-4">
                <div className="mb-2 rounded bg-[#e6efe5] px-3 py-1 text-center text-xs font-semibold uppercase tracking-wider text-[#3f7d48]">
                  Status Notes <span className="text-[#b4443d]">(*Required)</span>
                </div>
                <textarea
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  placeholder="Description of Status Change..."
                  rows={4}
                  className="w-full resize-y rounded border border-h-line bg-h-surface p-2 text-sm text-h-ink placeholder:text-h-muted"
                />
                {submitError ? (
                  <div className="mt-2 text-xs text-[#b4443d]">{submitError}</div>
                ) : null}
                <div className="mt-3 flex items-center gap-2">
                  <button
                    type="button"
                    disabled
                    title="Bulk update not yet wired"
                    className="flex items-center gap-2 rounded border border-[#b4443d] bg-[#b4443d] px-3 py-2 text-xs font-semibold text-white opacity-50 disabled:cursor-not-allowed"
                  >
                    <span>⚠</span>
                    <span className="leading-tight">Update Status<br />To All</span>
                  </button>
                  <button
                    type="button"
                    disabled={!canSubmit}
                    onClick={submit}
                    className="flex items-center gap-2 rounded border border-[#3f7d48] bg-white px-3 py-2 text-xs font-semibold text-[#3f7d48] hover:bg-[#e6efe5] disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    <span>↻</span>
                    <span className="leading-tight">Update<br />Current Item</span>
                  </button>
                </div>
              </div>
            </div>

            <div className="p-4">
              <div className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-h-muted">
                Status Log
              </div>
              {statusLog.length === 0 ? (
                <div className="rounded border border-h-line bg-h-bg p-4 text-center text-xs text-h-muted">
                  No prior status changes for this item.
                </div>
              ) : (
                <ul className="grid max-h-48 gap-1 overflow-y-auto rounded border border-h-line bg-h-bg p-2">
                  {statusLog.map((row) => (
                    <li
                      key={row.log_id}
                      className="grid grid-cols-[auto_1fr_auto] gap-x-3 rounded bg-h-surface px-2 py-1.5 text-xs"
                    >
                      <span className="font-mono tabular-nums text-h-muted">
                        {formatTs(row.ts)}
                      </span>
                      <span className="text-h-ink">
                        <span className="text-h-muted">{row.actor_name ?? "—"}: </span>
                        <span className="font-mono">{row.old_value ?? "—"}</span>
                        <span className="mx-1 text-h-muted">→</span>
                        <span className="font-mono">{row.new_value ?? "—"}</span>
                      </span>
                      <span className="text-h-muted">{row.actor_name ?? ""}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <footer className="flex justify-end gap-2 border-t border-h-line bg-h-bg px-4 py-2">
              <button
                type="button"
                onClick={onClose}
                className="rounded border border-h-line bg-h-surface px-3 py-1 text-sm text-h-ink hover:bg-h-bg"
              >
                Close
              </button>
            </footer>
          </>
        )}
      </div>
    </div>
  );
}

function formatTs(ts: string): string {
  return ts.replace("T", " ").slice(0, 16);
}
