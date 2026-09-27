import type { ItemOut } from "@/lib/pm-types";

/**
 * §L Approval Lock (Q508) — "information automatically locks when
 * approved." There is no column for it: it is `status === "APPROVED"`, and
 * unlocking is changing status away from APPROVED on the Actions tab, not a
 * button here. This banner exists so a 409 APPROVAL_LOCKED on a save has a
 * visible reason before the user even tries.
 */
export function ApprovalLockBanner({ item }: { item: ItemOut }) {
  if (item.status !== "APPROVED") return null;
  return (
    <div
      role="alert"
      className="rounded-md border border-h-bad bg-h-bad/10 p-3 text-sm text-h-ink"
    >
      🔒 Locked — status is <strong>Approved</strong>. Change the status on the
      Actions tab to make further changes.
    </div>
  );
}
