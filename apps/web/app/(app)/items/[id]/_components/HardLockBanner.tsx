"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import type { ItemOut } from "@/lib/pm-types";
import { PM, ApiError } from "@/lib/pm-fetch";

interface Props {
  item: ItemOut;
  /** Only a manager/admin may set or clear a Hard Lock (Q508). */
  canManage: boolean;
}

/**
 * §L Hard Lock (Q508) — unlike the Controlled Lock, this blocks PATCH
 * /items/{id} for everyone, including the current owner, until a
 * manager/admin explicitly clears it. Approval Lock (also Q508) needs no
 * banner of its own here: it is `status === "APPROVED"`, already shown by
 * the status pill elsewhere in the editor, and is unlocked by changing
 * status rather than by a button.
 */
export function HardLockBanner({ item, canManage }: Props) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const locked = item.hard_locked_at != null;

  async function toggle() {
    setBusy(true);
    setError(null);
    try {
      if (locked) {
        await PM.hardUnlockItem(item.id);
      } else {
        await PM.hardLockItem(item.id);
      }
      router.refresh();
    } catch (e) {
      setError(e instanceof ApiError ? `Failed (${e.status})` : "Failed");
    } finally {
      setBusy(false);
    }
  }

  if (!locked && !canManage) return null;

  return (
    <div
      role={locked ? "alert" : undefined}
      className={
        locked
          ? "flex items-center justify-between gap-3 rounded-md border border-h-bad bg-h-bad/10 p-3 text-sm text-h-ink"
          : "flex items-center justify-between gap-3 rounded-md border border-h-line bg-h-surface p-2 text-xs text-h-muted"
      }
    >
      <span>
        {locked ? (
          <>
            🔒 Hard-locked by <strong>{item.hard_locked_by_name ?? "—"}</strong> —
            no one can change this item until it is unlocked.
          </>
        ) : (
          "Not hard-locked."
        )}
      </span>
      {canManage && (
        <button
          type="button"
          onClick={toggle}
          disabled={busy}
          className="shrink-0 rounded border border-h-line bg-h-surface px-2 py-1 text-xs text-h-ink hover:bg-h-line/40 disabled:opacity-50"
        >
          {busy ? "…" : locked ? "Unlock" : "Hard-lock"}
        </button>
      )}
      {error && <span className="text-xs text-h-bad">{error}</span>}
    </div>
  );
}
