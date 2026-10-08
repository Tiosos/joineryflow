"use client";

import type { EstimateDetail } from "@/lib/estimating-types";
import { STATUS_COLOURS, fmtMoney } from "./shared";

interface RevisionRailProps {
  revisions: EstimateDetail["revisions"];
  currentId: number | null;
  selectedId: number | null;
  onSelect: (rid: number | null) => void;
}

export function RevisionRail({ revisions, currentId, selectedId, onSelect }: RevisionRailProps) {
  const sorted = [...revisions].sort((a, b) => b.rev_no - a.rev_no);
  return (
    <div
      className="flex flex-wrap gap-2 rounded border border-h-line bg-h-surface p-2 text-xs"
      data-testid="revision-rail"
    >
      <span className="text-h-muted uppercase tracking-wide self-center">Revisions</span>
      {sorted.map((r) => {
        const isCurrent = r.revision_id === currentId;
        const isSelected = r.revision_id === selectedId;
        return (
          <button
            key={r.revision_id}
            type="button"
            onClick={() => onSelect(isCurrent ? null : r.revision_id)}
            className={`rounded border px-2 py-1 ${
              isSelected
                ? "border-h-accent bg-white shadow"
                : "border-h-line bg-white hover:bg-gray-50"
            }`}
            data-testid={`revision-rail-${r.rev_no}`}
          >
            <span className="font-mono">v{r.rev_no}</span>{" "}
            <span
              className={`ml-1 rounded-full px-1.5 py-0.5 text-[10px] font-semibold uppercase ${STATUS_COLOURS[r.status]}`}
            >
              {r.status}
            </span>
            {isCurrent ? (
              <span className="ml-1 text-[10px] text-h-muted">current</span>
            ) : null}
            <span className="ml-2 font-mono text-h-muted">{fmtMoney(r.total_inc_gst)}</span>
          </button>
        );
      })}
    </div>
  );
}
