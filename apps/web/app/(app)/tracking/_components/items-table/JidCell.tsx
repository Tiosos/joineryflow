"use client";



export function JidCell({ code, color }: { code: string | null | undefined; color: string | null | undefined }) {
  if (!code && !color) return <span className="text-h-muted">—</span>;
  return (
    <span className="inline-flex items-center gap-1 whitespace-nowrap">
      {color ? (
        <span
          className="inline-block h-3 w-3 rounded-sm border border-h-line"
          style={{ backgroundColor: color }}
          aria-hidden="true"
          title={`JID color ${color}`}
        />
      ) : null}
      <span className="font-mono text-[9px]">{code ?? "—"}</span>
    </span>
  );
}
