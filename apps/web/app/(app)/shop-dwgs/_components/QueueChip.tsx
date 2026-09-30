import { QUEUE_LABELS, type Queue } from "@/lib/shop-drawings-types";

/** Colour per queue — existing design tokens only. */
export const QUEUE_TONE: Record<Queue, string> = {
  all: "bg-h-line/40 text-h-muted",
  being_drawn: "bg-h-info/15 text-h-info",
  internal_review: "bg-h-warn/15 text-h-warn",
  update_required: "bg-h-bad/15 text-h-bad",
  completed: "bg-h-good/15 text-h-good",
  awaiting_submission: "bg-h-accent-soft text-h-accent",
  submitted: "bg-h-good/15 text-h-good",
  archive: "bg-h-line/40 text-h-muted",
};

export default function QueueChip({ queue }: { queue: string }) {
  const q = (queue in QUEUE_LABELS ? queue : "all") as Queue;
  return (
    <span
      data-testid="queue-chip"
      className={`inline-flex items-center whitespace-nowrap rounded px-2 py-0.5 text-[11px] font-medium ${QUEUE_TONE[q]}`}
    >
      {QUEUE_LABELS[q]}
    </span>
  );
}
