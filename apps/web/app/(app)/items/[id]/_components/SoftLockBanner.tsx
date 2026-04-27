import type { LockWarning } from "@/lib/pm-types";

interface Props {
  warning: LockWarning;
}

export function SoftLockBanner({ warning }: Props) {
  return (
    <div
      role="alert"
      className="rounded-md border border-h-warn bg-h-warn/10 p-3 text-sm text-h-ink"
    >
      Locked by <strong>{warning.owner_name}</strong> — last edit{" "}
      {warning.last_edit_minutes_ago} minutes ago. Your save will overwrite.
    </div>
  );
}
