"use client";

import type { Revision } from "@/lib/shop-drawings-types";

import StatusPill from "./StatusPill";

interface Props {
  revisions: Revision[];
  selectedId: number;
  onSelect: (revisionId: number) => void;
}

function ddmmyyyy(iso: string): string {
  const d = new Date(iso);
  return `${String(d.getDate()).padStart(2, "0")}/${String(d.getMonth() + 1).padStart(2, "0")}/${d.getFullYear()}`;
}

export default function RevisionHistoryStrip({ revisions, selectedId, onSelect }: Props) {
  return (
    <ol className="divide-y divide-h-line border-y border-h-line">
      {revisions.map((r) => {
        const active = r.revision_id === selectedId;
        return (
          <li key={r.revision_id}>
            <button
              type="button"
              onClick={() => onSelect(r.revision_id)}
              className={`flex w-full items-center justify-between gap-3 px-3 py-2 text-left text-sm transition ${
                active ? "bg-h-accent/10 text-h-ink" : "text-h-muted hover:text-h-ink"
              }`}
            >
              <span className="h-mono">v{r.rev_no}</span>
              <StatusPill status={r.status} />
              <span className="flex-1 truncate">{r.uploaded_by_name ?? "—"}</span>
              <span className="h-mono">{ddmmyyyy(r.uploaded_at)}</span>
            </button>
          </li>
        );
      })}
    </ol>
  );
}
