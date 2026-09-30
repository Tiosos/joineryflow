import type { ItemOut } from "@/lib/pm-types";

/** Why this item's modules and parts cannot be changed, in words — or null if no
 *  lock applies. Mirrors `assert_item_content_unlocked` in the API (Hard Lock,
 *  Approval Lock, Controlled Lock held by someone else, where the owner and
 *  managers/admins pass). Only decides what to show: the API refuses regardless. */
export function moduleLockReason(
  item: Pick<ItemOut, "hard_locked_at" | "status" | "item_locked" | "cutlist_owner_id">,
  currentUserId: number | null,
  currentUserRole: string | null,
): string | null {
  if (item.hard_locked_at) return lockMessage("HARD_LOCKED");
  if (item.status === "APPROVED") return lockMessage("APPROVAL_LOCKED");
  const isAuthority = currentUserRole === "manager" || currentUserRole === "admin";
  if (
    item.item_locked &&
    item.cutlist_owner_id !== null &&
    item.cutlist_owner_id !== currentUserId &&
    !isAuthority
  ) {
    return lockMessage("ITEM_LOCKED");
  }
  return null;
}

/** The wording for a lock code, whether decided client-side or from a 409
 *  (`detail.code`, plus `owner_name` for ITEM_LOCKED). Null for any other code. */
export function lockMessage(code: string, detail?: { owner_name?: string | null }): string | null {
  switch (code) {
    case "HARD_LOCKED":
      return "This item is hard-locked. A manager or admin must unlock it before its modules or parts can be changed.";
    case "APPROVAL_LOCKED":
      return "This item is approved, which locks it. Move its status off Approved before changing its modules or parts.";
    case "ITEM_LOCKED":
      return `${detail?.owner_name ?? "Another user"} has locked this item. Ask them, or a manager, to make the change or unlock the item.`;
    default:
      return null;
  }
}

/** The wording for a `409` lock refusal carried by a failed request, or null when
 *  the error is anything else. Reads both error shapes in use: `ApiError` (`body`,
 *  pm-fetch) and the CV helper's `detail`. */
export function lockFromError(e: unknown): string | null {
  const err = e as { status?: number; body?: unknown; detail?: unknown };
  const d = (
    (err?.body ?? err?.detail) as
      | { detail?: { code?: string; owner_name?: string | null } }
      | undefined
  )?.detail;
  return err?.status === 409 && d?.code ? lockMessage(d.code, d) : null;
}
