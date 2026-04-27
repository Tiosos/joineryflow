import type { EditLogRow } from "@/lib/pm-types";

interface LogTabProps {
  rows: EditLogRow[];
}

export function LogTab({ rows }: LogTabProps) {
  if (rows.length === 0) {
    return <p className="text-sm text-h-muted">No edit history yet.</p>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-h-line text-left text-xs text-h-muted">
            <th className="pb-2 pr-4 font-medium">When</th>
            <th className="pb-2 pr-4 font-medium">Actor</th>
            <th className="pb-2 pr-4 font-medium">Field</th>
            <th className="pb-2 pr-4 font-medium">Old</th>
            <th className="pb-2 font-medium">New</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const ts = new Date(row.ts);
            const ago = formatAgo(ts);
            return (
              <tr key={row.log_id} className="border-b border-h-line/50">
                <td
                  className="py-1.5 pr-4 font-mono text-xs text-h-muted"
                  title={ts.toISOString()}
                >
                  {ago}
                </td>
                <td className="py-1.5 pr-4 text-h-ink">
                  {row.actor_name ?? "—"}
                </td>
                <td className="py-1.5 pr-4 font-mono text-xs text-h-ink">
                  {row.field}
                </td>
                <td className="py-1.5 pr-4 text-h-muted">
                  {row.old_value ?? "—"}
                </td>
                <td className="py-1.5 text-h-ink">{row.new_value ?? "—"}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function formatAgo(date: Date): string {
  const diff = Math.floor((Date.now() - date.getTime()) / 1000);
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}
