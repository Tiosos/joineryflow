"use client";

import type { DrawingCard as Card } from "@/lib/shop-drawings-types";

import BlueprintPlaceholder from "./BlueprintPlaceholder";
import StatusPill from "./StatusPill";
import VersionChip from "./VersionChip";

function pad4(n: number): string { return String(n).padStart(4, "0"); }
function ddmmyyyy(iso: string): string {
  const d = new Date(iso);
  const dd = String(d.getDate()).padStart(2, "0");
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  return `${dd}/${mm}/${d.getFullYear()}`;
}

interface Props { card: Card; onClick: () => void; }

export default function DrawingCard({ card, onClick }: Props) {
  const isArchived = card.archived_at != null;
  const personName = card.latest_reviewed_by_name ?? card.latest_uploaded_by_name ?? "—";
  const dateIso = card.latest_reviewed_at ?? card.latest_uploaded_at;

  return (
    <button
      onClick={onClick}
      className="group block w-full overflow-hidden rounded-lg border border-h-line bg-h-surface text-left transition hover:border-h-accent/60 hover:shadow-sm focus:outline-none focus:ring-2 focus:ring-h-accent"
    >
      <div className="relative aspect-[16/10] border-b border-h-line">
        <BlueprintPlaceholder seed={card.drawing_id} />
        <div className="absolute left-2 top-2">
          {isArchived ? (
            <span className="inline-flex rounded-full bg-h-line/40 px-2 py-0.5 text-[11px] uppercase tracking-wide text-h-muted">Archived</span>
          ) : (
            <StatusPill status={card.latest_status} />
          )}
        </div>
        <div className="absolute right-2 top-2">
          <VersionChip revNo={card.latest_rev_no} />
        </div>
      </div>
      <div className="space-y-1 p-3">
        <div className="flex items-baseline gap-2">
          <span className="h-mono text-xs text-h-muted">#SD-{pad4(card.drawing_id)}</span>
          <span className="truncate text-sm font-medium text-h-ink">{card.title}</span>
        </div>
        <p className="text-xs text-h-muted">
          {(card.room ?? "—")} · {card.project_code}
        </p>
        <p className="h-mono text-xs text-h-muted">
          {personName} · {ddmmyyyy(dateIso)}
        </p>
      </div>
    </button>
  );
}
