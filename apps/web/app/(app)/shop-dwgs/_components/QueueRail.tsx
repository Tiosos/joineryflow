"use client";

import {
  QUEUE_LABELS,
  QUEUE_ORDER,
  type Queue,
  type StatusQueue,
} from "@/lib/shop-drawings-types";

interface Props {
  queue: Queue;
  counts: Record<StatusQueue, number>;
  total: number;
  mine: boolean;
  onQueue: (q: Queue) => void;
  onMine: (on: boolean) => void;
}

const SUBMISSION: StatusQueue[] = ["awaiting_submission", "submitted"];

/** Left workflow rail: a progress donut, "My drawings", and one entry per
 *  register queue with its count. Counts cover the whole project, whatever the
 *  current filters, so the numbers don't shift as you search. */
export default function QueueRail({ queue, counts, total, mine, onQueue, onMine }: Props) {
  const done = counts.completed ?? 0;
  const review = counts.internal_review ?? 0;
  const remaining = Math.max(total - done - review, 0);

  const item = (q: StatusQueue, indent = false) => {
    const active = queue === q;
    return (
      <li key={q}>
        <button
          type="button"
          data-testid={`queue-${q}`}
          aria-current={active ? "true" : undefined}
          onClick={() => onQueue(q)}
          className={`flex w-full items-center justify-between rounded px-2.5 py-1.5 text-left text-sm transition ${
            indent ? "pl-6 " : ""
          }${active ? "bg-h-accent-soft font-medium text-h-ink" : "text-h-ink2 hover:bg-h-surface-alt hover:text-h-ink"}`}
        >
          <span>{QUEUE_LABELS[q]}</span>
          <span className="h-mono rounded-full bg-h-surface-alt px-1.5 text-[11px] text-h-ink2">
            {counts[q] ?? 0}
          </span>
        </button>
      </li>
    );
  };

  return (
    <nav aria-label="Register queues" className="w-full shrink-0 space-y-4 lg:w-56">
      <Donut done={done} review={review} remaining={remaining} total={total} />

      <button
        type="button"
        data-testid="queue-mine"
        aria-pressed={mine}
        onClick={() => onMine(!mine)}
        className={`flex w-full items-center justify-between rounded border px-2.5 py-1.5 text-sm ${
          mine ? "border-h-accent bg-h-accent-soft text-h-ink" : "border-h-line bg-h-surface text-h-ink2 hover:text-h-ink"
        }`}
      >
        My drawings
        <span className="text-[11px] text-h-muted">{mine ? "on" : "off"}</span>
      </button>

      <div>
        <p className="px-2.5 pb-1 text-[11px] font-semibold uppercase tracking-wider text-h-muted">Workspace</p>
        <ul className="space-y-0.5">
          <li>
            <button
              type="button"
              data-testid="queue-all"
              aria-current={queue === "all" ? "true" : undefined}
              onClick={() => onQueue("all")}
              className={`flex w-full items-center justify-between rounded px-2.5 py-1.5 text-left text-sm transition ${
                queue === "all" ? "bg-h-accent-soft font-medium text-h-ink" : "text-h-ink2 hover:bg-h-surface-alt hover:text-h-ink"
              }`}
            >
              <span>{QUEUE_LABELS.all}</span>
              <span className="h-mono rounded-full bg-h-surface-alt px-1.5 text-[11px] text-h-ink2">{total}</span>
            </button>
          </li>
          {QUEUE_ORDER.filter((q) => q !== "archive" && !SUBMISSION.includes(q)).map((q) => item(q))}
        </ul>
      </div>

      <div>
        <p className="px-2.5 pb-1 text-[11px] font-semibold uppercase tracking-wider text-h-muted">Submissions</p>
        <ul className="space-y-0.5">{SUBMISSION.map((q) => item(q))}</ul>
      </div>

      <ul className="space-y-0.5 border-t border-h-line pt-3">{item("archive")}</ul>
    </nav>
  );
}

function Donut({ done, review, remaining, total }: { done: number; review: number; remaining: number; total: number }) {
  const r = 26;
  const c = 2 * Math.PI * r;
  const seg = (n: number) => (total > 0 ? (n / total) * c : 0);
  const parts = [
    { n: done, cls: "stroke-h-good", label: "Completed" },
    { n: review, cls: "stroke-h-warn", label: "In review" },
    { n: remaining, cls: "stroke-h-line", label: "Remaining" },
  ];
  let offset = 0;
  return (
    <div className="flex items-center gap-3 rounded border border-h-line bg-h-surface p-3">
      <svg width="64" height="64" viewBox="0 0 64 64" role="img" aria-label={`${done} of ${total} drawings completed`}>
        <g transform="rotate(-90 32 32)">
          {parts.map((p) => {
            const len = seg(p.n);
            const el = (
              <circle
                key={p.label}
                cx="32" cy="32" r={r} fill="none" strokeWidth="9"
                className={p.cls}
                strokeDasharray={`${len} ${c - len}`}
                strokeDashoffset={-offset}
              />
            );
            offset += len;
            return el;
          })}
        </g>
      </svg>
      <dl className="flex-1 space-y-0.5 text-[11px] text-h-ink2">
        {parts.map((p) => (
          <div key={p.label} className="flex justify-between">
            <dt>{p.label}</dt>
            <dd className="h-mono text-h-ink">{p.n}</dd>
          </div>
        ))}
        <div className="flex justify-between border-t border-h-line pt-0.5">
          <dt>Total active</dt>
          <dd className="h-mono font-medium text-h-ink">{total}</dd>
        </div>
      </dl>
    </div>
  );
}
