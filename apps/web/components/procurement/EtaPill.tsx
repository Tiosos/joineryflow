"use client";

interface Props { eta: string | null; }

export function EtaPill({ eta }: Props) {
  if (!eta) return <span className="text-h-muted">—</span>;
  const d = new Date(eta);
  const today = new Date(); today.setHours(0,0,0,0);
  const overdue = d < today;
  return (
    <span className={["h-mono text-xs", overdue ? "text-h-bad" : "text-h-ink"].join(" ")}>
      {eta}
    </span>
  );
}
