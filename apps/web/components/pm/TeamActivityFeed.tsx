import type { TeamActivityRow } from "@/lib/pm-types";

interface Props {
  rows: TeamActivityRow[];
}

export function TeamActivityFeed({ rows }: Props) {
  return (
    <section className="rounded-lg border border-h-line bg-h-surface p-4">
      <h2 className="mb-3 text-sm font-semibold text-h-ink">Team Activity</h2>
      {rows.length === 0 ? (
        <p className="text-sm text-h-muted">No recent activity.</p>
      ) : (
        <ul className="space-y-2" role="list">
          {rows.map((r, i) => (
            <li key={i} className="text-sm text-h-muted">
              <span className="text-h-ink">{r.actor_name}</span>{" "}
              <span className="font-mono text-xs">{r.event}</span>
              {r.target && (
                <>
                  {" · "}
                  <span>{r.target}</span>
                </>
              )}
              <span className="ml-2 text-xs">{new Date(r.ts).toLocaleString()}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
