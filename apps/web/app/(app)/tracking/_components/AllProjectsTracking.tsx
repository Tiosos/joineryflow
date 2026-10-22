import Link from "next/link";
import type { CardFilter, TrackingItemRow } from "@/lib/pm-types";
import { STAGE_KEYS, statusClasses } from "./items-table/shared";

const TITLES: Record<CardFilter, { title: string; note: string }> = {
  overdue: { title: "Overdue items", note: "at least one stage is past its due date and not done" },
  in_optimisation: { title: "In optimisation", note: "marked down (DOWN done), not yet cut (CNC not done)" },
  awaiting_install: { title: "Awaiting install", note: "delivered (DEL done), not yet installed (INST not done)" },
};

interface Props {
  filter: CardFilter | null;
  items: TrackingItemRow[];
  /** Today as YYYY-MM-DD, to tint a stage that is past due. */
  today: string;
}

/** Tracking's All projects scope (Q633): the items a dashboard card counted, across projects. Read-only:
 *  an item is opened in its own project's Tracking or in the item editor. */
export function AllProjectsTracking({ filter, items, today }: Props) {
  const heading = filter ? TITLES[filter] : { title: "All items", note: "every live joinery item you can see" };
  return (
    <div className="grid gap-3" data-testid="tracking-all-projects">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h1 className="text-base font-semibold text-h-ink">{heading.title}</h1>
        <span className="font-mono text-sm tabular-nums text-h-ink2" data-testid="tracking-all-count">{items.length}</span>
        <span className="text-xs text-h-muted">All projects · {heading.note}</span>
        <Link href="/tracking" className="ml-auto text-xs text-h-accent hover:underline">
          Back to project tracking
        </Link>
      </div>
      {items.length === 0 ? (
        <div className="rounded-lg border border-h-line bg-h-surface p-8 text-center text-sm text-h-muted">
          No items match.
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-h-line bg-h-surface">
          <table className="w-full text-xs">
            <thead className="bg-h-bg text-left text-h-muted">
              <tr>
                <th className="px-3 py-2 font-semibold">Project</th>
                <th className="px-3 py-2 font-semibold">Item</th>
                <th className="px-3 py-2 font-semibold">Description</th>
                <th className="px-3 py-2 font-semibold">Status</th>
                <th className="px-3 py-2 font-semibold">Stages</th>
              </tr>
            </thead>
            <tbody>
              {items.map((it) => (
                <tr key={it.id} className="border-t border-h-line" data-testid={`tracking-all-row-${it.id}`}>
                  <td className="px-3 py-2">
                    <Link href={`/tracking?project_id=${it.project_id}`} className="h-mono text-h-accent hover:underline">
                      {it.project_code}
                    </Link>
                  </td>
                  <td className="px-3 py-2">
                    <Link href={`/items/${it.id}`} className="h-mono text-h-accent hover:underline">
                      {it.item_number ?? it.id}
                    </Link>
                  </td>
                  <td className="px-3 py-2 text-h-ink">{it.description}</td>
                  <td className="px-3 py-2">
                    {it.status ? (
                      <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${statusClasses(it.status)}`}>
                        {it.status}
                      </span>
                    ) : null}
                  </td>
                  <td className="px-3 py-2">
                    <div className="flex flex-wrap gap-1">
                      {STAGE_KEYS.map((sk) => {
                        const s = it.stages[sk];
                        if (!s || (!s.due_date && !s.done_date)) return null;
                        const done = Boolean(s.done_date);
                        const late = !done && Boolean(s.due_date) && (s.due_date as string) < today;
                        return (
                          <span
                            key={sk}
                            className={`h-mono rounded border border-h-line px-1.5 py-0.5 text-[10px] ${
                              late ? "text-h-bad" : done ? "text-h-muted" : "text-h-ink2"
                            }`}
                            title={done ? `${sk} done ${s.done_date}` : `${sk} due ${s.due_date}`}
                          >
                            {sk} {done ? s.done_date : s.due_date}
                          </span>
                        );
                      })}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
