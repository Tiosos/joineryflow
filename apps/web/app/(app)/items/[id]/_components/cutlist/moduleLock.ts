import type { ItemOut } from "@/lib/pm-types";

/** What a lock is being checked against. "content" is the item's cutlist (modules,
 *  parts), hardware, attachment slots and document register, which every lock covers. "status" is its status and stage
 *  dates, which the Approval Lock does not cover: changing status is how an
 *  approved item is unlocked, and production dates follow approval. "records" is
 *  item queries (answering) and the Material Take, which the Approval Lock also
 *  leaves out: takes are approved and queries answered on approved items. */
export type LockScope = "content" | "status" | "records";

/** Why this item's cutlist (modules, parts), hardware and attachments — or, with scope "status",
 *  its status and stage dates — cannot be changed, in words — or null if no
 *  lock applies. Mirrors `assert_item_content_unlocked` in the API (Hard Lock,
 *  Approval Lock, Controlled Lock held by someone else, where the owner and
 *  managers/admins pass). Only decides what to show: the API refuses regardless. */
export function moduleLockReason(
  item: Pick<ItemOut, "hard_locked_at" | "status" | "item_locked" | "cutlist_owner_id">,
  currentUserId: number | null,
  currentUserRole: string | null,
  scope: LockScope = "content",
): string | null {
  if (item.hard_locked_at) return lockMessage("HARD_LOCKED", undefined, scope);
  if (scope === "content" && item.status === "APPROVED") return lockMessage("APPROVAL_LOCKED");
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
export function lockMessage(
  code: string,
  detail?: { owner_name?: string | null },
  scope: LockScope = "content",
): string | null {
  switch (code) {
    case "HARD_LOCKED":
      return `This item is hard-locked. A manager or admin must unlock it before its ${
        scope === "status"
          ? "status or stage dates"
          : scope === "records"
            ? "queries or material take"
            : "cutlist, hardware or attachments"
      } can be changed.`;
    case "APPROVAL_LOCKED":
      return "This item is approved, which locks it. Move its status off Approved before changing its cutlist, hardware or attachments.";
    case "ITEM_LOCKED":
      return `${detail?.owner_name ?? "Another user"} has locked this item. Ask them, or a manager, to make the change or unlock the item.`;
    default:
      return null;
  }
}

/** The wording for a `409` lock refusal carried by a failed request, or null when
 *  the error is anything else. Reads both error shapes in use: `ApiError` (`body`,
 *  pm-fetch) and the CV helper's `detail`. */
export function lockFromError(e: unknown, scope: LockScope = "content"): string | null {
  const err = e as { status?: number; body?: unknown; detail?: unknown };
  const d = (
    (err?.body ?? err?.detail) as
      | { detail?: { code?: string; owner_name?: string | null } }
      | undefined
  )?.detail;
  return err?.status === 409 && d?.code ? lockMessage(d.code, d, scope) : null;
}
