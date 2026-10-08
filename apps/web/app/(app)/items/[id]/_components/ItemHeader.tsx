"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import type { ItemOut } from "@/lib/pm-types";
import { PM, ApiError } from "@/lib/pm-fetch";

interface Props {
  item: ItemOut;
  /** drafter / manager / admin, like the delete route. */
  canDelete: boolean;
}

export function ItemHeader({ item, canDelete }: Props) {
  const router = useRouter();
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const hardLocked = item.hard_locked_at != null;

  // Soft delete: the item, its related parts and its cutlist are hidden, not removed; a
  // manager/admin can restore them from Tracking's Deleted chip.
  async function remove() {
    if (
      !window.confirm(
        `Delete item #${item.item_number ?? item.id}? Its related parts and cutlist go with it. A manager or admin can restore it from Tracking's Deleted chip.`,
      )
    )
      return;
    setDeleting(true);
    setError(null);
    try {
      await PM.deleteItem(item.id);
      router.push(`/tracking?project_id=${item.project_id}`);
    } catch (e) {
      setError(
        e instanceof ApiError && e.status === 409
          ? "This item is Hard Locked: a manager or admin must clear the lock first."
          : e instanceof ApiError && e.status === 403
            ? "Your role cannot delete items."
            : "Delete failed.",
      );
      setDeleting(false);
    }
  }

  function close() {
    window.close();
    // If window.close() was a no-op (browser blocked it), fall back.
    if (!window.closed) router.push("/dashboard");
  }

  return (
    <header className="flex items-baseline justify-between border-b border-h-line pb-3">
      <div>
        <h1 className="text-lg font-semibold text-h-ink">
          ITEM #{item.item_number ?? item.id}
        </h1>
        <p className="text-sm text-h-muted">
          {item.code ?? "—"} · {item.stage ?? "—"} ·{" "}
          {item.description ?? ""}
        </p>
      </div>
      <div className="flex items-center gap-2">
        {error ? (
          <span data-testid="delete-error" className="text-xs text-[#b4443d]">
            {error}
          </span>
        ) : null}
        {canDelete ? (
          <button
            type="button"
            onClick={remove}
            disabled={deleting || hardLocked}
            data-testid="delete-item"
            title={hardLocked ? "Hard Locked: clear the lock before deleting" : "Delete this item"}
            className="rounded border border-[#b4443d] px-2 py-1 text-xs text-[#b4443d] hover:bg-[#f2dcd9]/40 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {deleting ? "Deleting…" : "Delete"}
          </button>
        ) : null}
        <button
          type="button"
          onClick={close}
          data-testid="close-editor"
          aria-label="Close editor"
          className="rounded px-2 py-1 text-h-muted hover:bg-h-bg hover:text-h-ink"
        >
          ✕
        </button>
      </div>
    </header>
  );
}
