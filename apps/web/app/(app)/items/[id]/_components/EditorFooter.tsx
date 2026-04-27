"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { PM } from "@/lib/pm-fetch";
import type { ItemOut } from "@/lib/pm-types";

interface EditorFooterProps {
  item: ItemOut;
  currentUserId: number | null;
  currentUserRole: string | null;
}

export function EditorFooter({
  item,
  currentUserId,
  currentUserRole,
}: EditorFooterProps) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isOwner =
    currentUserId !== null && item.cutlist_owner_id === currentUserId;
  const hasDrafterRole =
    currentUserRole === "drafter" ||
    currentUserRole === "manager" ||
    currentUserRole === "admin";
  // Any drafter+ can lock (claim) an unlocked item.
  // Only the owner, manager, or admin can unlock.
  const canToggleLock = item.item_locked
    ? isOwner || currentUserRole === "manager" || currentUserRole === "admin"
    : hasDrafterRole;

  async function handleLockToggle() {
    setBusy(true);
    setError(null);
    try {
      if (item.item_locked) {
        await PM.unlockItem(item.id);
      } else {
        await PM.lockItem(item.id);
      }
      router.refresh();
    } catch {
      setError("Failed to toggle lock");
    } finally {
      setBusy(false);
    }
  }

  const printTitle = "PDF generation ships in sub-project #5";

  return (
    <footer className="flex items-center justify-between rounded-lg border border-h-line bg-h-surface px-4 py-3">
      <div className="flex items-center gap-2">
        <button
          type="button"
          disabled
          title={printTitle}
          className="rounded border border-h-line px-3 py-1.5 text-sm text-h-muted opacity-50 cursor-not-allowed"
        >
          Print Cutlist
        </button>
        <button
          type="button"
          disabled
          title={printTitle}
          className="rounded border border-h-line px-3 py-1.5 text-sm text-h-muted opacity-50 cursor-not-allowed"
        >
          Print Hardware
        </button>
        <button
          type="button"
          disabled
          title={printTitle}
          className="rounded border border-h-line px-3 py-1.5 text-sm text-h-muted opacity-50 cursor-not-allowed"
        >
          Print Combined PDF
        </button>
      </div>

      <div className="flex items-center gap-3">
        {error && <span className="text-xs text-h-bad">{error}</span>}
        <button
          type="button"
          onClick={handleLockToggle}
          disabled={busy || !canToggleLock}
          className={[
            "rounded px-4 py-1.5 text-sm font-medium transition-colors",
            item.item_locked
              ? "border border-h-warn text-h-warn hover:bg-h-warn/10"
              : "bg-h-accent text-white hover:opacity-90",
            !canToggleLock || busy ? "opacity-50 cursor-not-allowed" : "",
          ]
            .join(" ")
            .trim()}
        >
          {item.item_locked ? "Unlock" : "Lock"}
        </button>
      </div>
    </footer>
  );
}
