import type { DeliveryToday } from "@/lib/pm-types";

interface Props {
  items: DeliveryToday[];
}

export function DeliveriesList({ items }: Props) {
  return (
    <section className="rounded-lg border border-h-line bg-h-surface p-4">
      <h2 className="mb-3 text-sm font-semibold text-h-ink">Deliveries Today</h2>
      {items.length === 0 ? (
        <p className="text-sm text-h-muted">No deliveries scheduled today.</p>
      ) : (
        <ul className="space-y-2" role="list">
          {items.map((d) => (
            <li key={d.batch_id} className="flex items-baseline gap-2">
              <span className="font-mono text-xs text-h-muted">{d.project_code}</span>
              <span className="flex-1 truncate text-sm text-h-ink">{d.supplier}</span>
              <span className="font-mono text-xs text-h-accent">{d.eta}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
