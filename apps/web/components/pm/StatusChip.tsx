import type { ItemStatus } from "@/lib/pm-types";

const STATUS_TONE: Record<ItemStatus, { bg: string; text: string }> = {
  CLEAR:    { bg: "bg-h-good/15",   text: "text-h-good" },
  LIVE:     { bg: "bg-h-accent/15", text: "text-h-accent" },
  APPROVED: { bg: "bg-h-good/15",   text: "text-h-good" },
  HOLD:     { bg: "bg-h-warn/15",   text: "text-h-warn" },
  "NOTE!":  { bg: "bg-h-warn/15",   text: "text-h-warn" },
  VOID:     { bg: "bg-h-bad/15",    text: "text-h-bad" },
};

interface Props {
  status: string | null;
}

export function StatusChip({ status }: Props) {
  if (!status) return <span className="text-h-muted">—</span>;
  const tone =
    STATUS_TONE[status as ItemStatus] ?? { bg: "bg-h-line", text: "text-h-muted" };
  return (
    <span
      className={`inline-block rounded px-1.5 py-0.5 text-xs font-mono ${tone.bg} ${tone.text}`}
    >
      {status}
    </span>
  );
}
