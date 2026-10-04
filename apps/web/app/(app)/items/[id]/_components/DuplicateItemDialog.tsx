"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import type { ItemOut } from "@/lib/pm-types";
import { PM, ApiError } from "@/lib/pm-fetch";

/**
 * Confirm dialog for POST /items/{id}/duplicate (Plan V1 §2). One copy per click; the
 * copy lands in the same project with its own Item ID, its own new cutlist and status
 * CLEAR, and the editor opens on it. Stage dates, locks, QC defects / rework, comments,
 * queries, material takes and orders are deliberately not copied.
 */
export function DuplicateItemDialog({
  item,
  onClose,
}: {
  item: ItemOut;
  onClose: () => void;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !busy) onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [busy, onClose]);

  async function confirm() {
    setBusy(true);
    setError(null);
    try {
      const copy = await PM.duplicateItem(item.id);
      router.push(`/items/${copy.id}`);
    } catch (e) {
      setError(
        e instanceof ApiError
          ? e.status === 403
            ? "Your role cannot duplicate items."
            : e.status === 404
              ? "This item no longer exists."
              : `Duplicate failed (${e.status})`
          : "Duplicate failed",
      );
      setBusy(false);
    }
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Duplicate item"
      data-testid="duplicate-dialog"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4"
    >
      <div className="w-full max-w-md rounded-lg border border-h-line bg-h-bg p-5 shadow-lg">
        <h2 className="text-base font-semibold text-h-ink">
          Duplicate item #{item.item_number}?
        </h2>
        <p className="mt-2 text-sm text-h-ink">
          This makes one copy in the same project, with its own new Item ID and its own new
          cutlist. Its status starts as CLEAR.
        </p>
        <p className="mt-2 text-sm text-h-muted">
          Copied: the item&apos;s details, modules and parts, hardware lines, attachments,
          the document register, and the QC checklist (unticked). Not copied: stage dates,
          locks, QC defects and rework, comments, queries, material takes and orders.
        </p>
        {error && (
          <p
            data-testid="duplicate-error"
            className="mt-3 rounded bg-red-50 px-3 py-2 text-sm text-red-800"
          >
            {error}
          </p>
        )}
        <div className="mt-4 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            disabled={busy}
            className="rounded border border-h-line px-3 py-1.5 text-sm text-h-ink hover:bg-h-line/20 disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={confirm}
            disabled={busy}
            data-testid="duplicate-confirm"
            className="rounded bg-h-accent px-3 py-1.5 text-sm text-white hover:opacity-90 disabled:opacity-50"
          >
            {busy ? "Duplicating…" : "Duplicate"}
          </button>
        </div>
      </div>
    </div>
  );
}
