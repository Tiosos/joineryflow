import Link from "next/link";
import type { MyDayItem } from "@/lib/pm-types";

interface Props {
  items: MyDayItem[];
}

export function MyDayList({ items }: Props) {
  return (
    <section className="rounded-lg border border-h-line bg-h-surface p-4">
      <h2 className="mb-3 text-sm font-semibold text-h-ink">My Day</h2>
      {items.length === 0 ? (
        <p className="text-sm text-h-muted">Nothing due in the next 3 days.</p>
      ) : (
        <ul className="space-y-2" role="list">
          {items.map((it) => (
            <li key={it.item_id} data-testid="myday-row">
              <Link
                href={`/items/${it.item_id}?tab=cutlist`}
                className="flex items-baseline gap-2 hover:bg-h-bg -mx-2 px-2 py-1 rounded"
              >
                <span className="font-mono text-xs text-h-muted">{it.project_code}</span>
                <span className="flex-1 truncate text-sm text-h-ink">
                  {it.description ?? "—"}
                </span>
                {it.next_due_date && (
                  <span className="font-mono text-xs text-h-accent">
                    {it.next_due_stage_key}·{it.next_due_date}
                  </span>
                )}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
