"use client";

import type { TrackingItemRow } from "@/lib/pm-types";
import { SubTab } from "./shared";

// SubTab data cells for non-date subtabs.  INVOICE + iTIME + QC stay as `—`
// stubs (Invoice ships in #13; iTIME / QC are out of scope for #10).
export function SubTabCells({
  row,
  subTab,
  subColCount,
}: {
  row: TrackingItemRow;
  subTab: SubTab;
  subColCount: number;
}) {
  if (subTab === "HARDWARE") {
    return (
      <>
        <td className="px-2 py-1 text-right font-mono tabular-nums text-h-ink">
          {row.hardware_line_count ?? 0}
        </td>
        <td className="px-2 py-1 text-right font-mono tabular-nums text-[#3f7d48]">
          {row.availability.ready}
        </td>
        <td className="px-2 py-1 text-right font-mono tabular-nums text-[#b4443d]">
          {row.availability.blocked}
        </td>
      </>
    );
  }

  if (subTab === "SITE MEASURE") {
    const req = row.stages.REQ?.due_date ?? null;
    const smDone = row.stages.SM?.done_date ?? null;
    const smDue = row.stages.SM?.due_date ?? null;
    const smDisplay = smDone ?? smDue;
    return (
      <>
        <td className="px-2 py-1 font-mono text-[10px] tabular-nums text-h-muted">
          {req ?? "—"}
        </td>
        <td className="px-2 py-1 font-mono text-[10px] tabular-nums text-h-muted">
          {smDisplay ?? "—"}
        </td>
        <td className="px-2 py-1 text-h-muted">{row.lister ?? "—"}</td>
        <td className="px-2 py-1 text-h-muted">{row.site_measure_notes ?? "—"}</td>
        <td className="px-2 py-1">
          {row.site_measure_attachment_id ? (
            <a
              href={`/api/files/${row.site_measure_attachment_id}`}
              target="_blank"
              rel="noopener noreferrer"
              className="text-h-accent hover:underline"
            >
              View
            </a>
          ) : (
            <span className="text-h-muted">—</span>
          )}
        </td>
      </>
    );
  }

  return (
    <>
      {Array.from({ length: subColCount }).map((_, i) => (
        <td key={i} className="px-2 py-1 text-h-muted">—</td>
      ))}
    </>
  );
}
