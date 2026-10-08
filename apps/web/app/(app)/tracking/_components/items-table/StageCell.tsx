"use client";

import { dateCellColor } from "./shared";

export function StageCell({
  stage,
  today,
}: {
  stage?: { due_date: string | null; done_date: string | null };
  today: string;
}) {
  if (!stage || (!stage.due_date && !stage.done_date)) {
    return <td className="px-2 py-1 text-h-muted">—</td>;
  }
  const display = stage.done_date ?? stage.due_date;
  return (
    <td className={`px-2 py-1 font-mono text-[10px] tabular-nums ${dateCellColor(stage.due_date, stage.done_date, today)}`}>
      {display ? display.slice(5) : "—"}
    </td>
  );
}
