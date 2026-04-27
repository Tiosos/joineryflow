"use client";

import Link from "next/link";
import type { TrackingItemRow } from "@/lib/pm-types";
import { StatusChip } from "./StatusChip";
import { AvailabilityChip } from "./AvailabilityChip";
import { StageDates } from "./StageDates";

interface Props {
  items: TrackingItemRow[];
  canEdit: boolean;
}

export function TrackingGrid({ items, canEdit }: Props) {
  return (
    <div className="overflow-x-auto rounded-lg border border-h-line bg-h-surface">
      <table className="w-full text-sm">
        <thead className="bg-h-bg">
          <tr className="text-h-muted">
            <th className="px-2 py-2 text-left font-mono text-xs uppercase">#</th>
            <th className="px-2 py-2 text-left font-mono text-xs uppercase">Status</th>
            <th className="px-2 py-2 text-left font-mono text-xs uppercase">Stage</th>
            <th className="px-2 py-2 text-left font-mono text-xs uppercase">Lvl</th>
            <th className="px-2 py-2 text-left font-mono text-xs uppercase">Rm#</th>
            <th className="px-2 py-2 text-left font-mono text-xs uppercase">RmDesc</th>
            <th className="px-2 py-2 text-left font-mono text-xs uppercase">Code</th>
            <th className="px-2 py-2 text-left font-mono text-xs uppercase">Description</th>
            <th className="px-2 py-2 text-right font-mono text-xs uppercase">Qty</th>
            <th className="px-2 py-2 text-left font-mono text-xs uppercase">Owner</th>
            {/* 10 lifecycle stage columns */}
            <th
              className="px-2 py-2 text-center font-mono text-xs uppercase"
              colSpan={10}
            >
              Lifecycle
            </th>
            <th className="px-2 py-2 text-left font-mono text-xs uppercase">Avail</th>
            <th className="px-2 py-2"></th>
          </tr>
        </thead>
        <tbody>
          {items.map((it) => (
            <tr
              key={it.id}
              data-testid="tracking-row"
              className="border-t border-h-line hover:bg-h-bg"
            >
              <td className="px-2 py-1.5 font-mono text-xs text-h-muted">
                {it.item_number ?? it.id}
              </td>
              <td className="px-2 py-1.5">
                <StatusChip status={it.status} />
              </td>
              <td className="px-2 py-1.5 text-h-muted">{it.stage ?? "—"}</td>
              <td className="px-2 py-1.5 text-h-muted">{it.level ?? "—"}</td>
              <td className="px-2 py-1.5 text-h-muted">{it.room_no ?? "—"}</td>
              <td className="px-2 py-1.5 text-h-muted">{it.room_desc ?? "—"}</td>
              <td className="px-2 py-1.5 font-mono text-xs text-h-ink">
                {it.code ?? "—"}
              </td>
              <td className="px-2 py-1.5 text-h-ink">{it.description ?? "—"}</td>
              <td className="px-2 py-1.5 text-right font-mono tabular-nums text-h-ink">
                {it.qty ?? "—"}
              </td>
              <td className="px-2 py-1.5 text-xs text-h-muted">
                {it.cutlist_owner_name ?? "—"}
              </td>
              <StageDates stages={it.stages} />
              <td className="px-2 py-1.5">
                <AvailabilityChip
                  ready={it.availability.ready}
                  blocked={it.availability.blocked}
                />
              </td>
              <td className="px-2 py-1.5 text-right">
                {canEdit ? (
                  <Link
                    href={`/items/${it.id}?tab=cutlist`}
                    data-testid="open-item"
                    aria-label="Open item"
                    className="inline-block rounded px-2 py-1 text-h-accent hover:bg-h-accent/10"
                  >
                    ▶
                  </Link>
                ) : (
                  <span className="text-h-muted">—</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
