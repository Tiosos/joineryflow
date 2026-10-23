"use client";

import type { StageDates } from "@/lib/pm-types";

// A stage's tint comes from the server's state (Q591), never from comparing dates here.
const TONE: Record<string, { cls: string; title: string }> = {
  overdue: { cls: "text-[#b4443d] font-semibold", title: "Overdue" },
  at_risk: { cls: "text-[#c48a2e] font-semibold", title: "At risk: due soon and an earlier stage is not done" },
  delayed: { cls: "text-[#c48a2e]", title: "Done late" },
  done: { cls: "text-[#3f7d48]", title: "Done" },
};

export function StageCell({ stage }: { stage?: StageDates }) {
  if (!stage || (!stage.due_date && !stage.done_date)) {
    return <td className="px-2 py-1 text-h-muted">—</td>;
  }
  const display = stage.done_date ?? stage.due_date;
  const tone = stage.state ? TONE[stage.state] : undefined;
  return (
    <td
      className={`px-2 py-1 font-mono text-[10px] tabular-nums ${tone?.cls ?? "text-h-muted"}`}
      title={tone?.title}
    >
      {display ? display.slice(5) : "—"}
    </td>
  );
}
