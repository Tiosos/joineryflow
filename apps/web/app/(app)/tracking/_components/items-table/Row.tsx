"use client";

import Link from "next/link";
import type { TrackingItemRow } from "@/lib/pm-types";
import { AvailabilityChip } from "@/components/pm/AvailabilityChip";
import { SubTab, STAGE_KEYS, statusClasses, formatAmount } from "./shared";
import { ReferenceCell } from "./ReferenceCell";
import { OrderCells } from "./OrderCells";
import { JidCell } from "./JidCell";
import { VarBoqPill } from "./VarBoqPill";
import { SubTabCells } from "./SubTabCells";
import { StageCell } from "./StageCell";

export function Row({
  row,
  projectId,
  isDateLike,
  subTab,
  subColCount,
  today,
  relatedCount = 0,
  relatedOpen = false,
  onToggleRelated,
  bulkEnabled,
  checked,
  onToggle,
  onOpen,
  onOpenStatus,
  onOpenAvailability,
  readOnly = false,
}: {
  row: TrackingItemRow;
  projectId: number;
  isDateLike: boolean;
  subTab: SubTab;
  subColCount: number;
  today: string;
  relatedCount?: number;
  relatedOpen?: boolean;
  onToggleRelated?: () => void;
  bulkEnabled: boolean;
  checked: boolean;
  onToggle?: () => void;
  onOpen: () => void;
  onOpenStatus: () => void;
  onOpenAvailability?: (id: number) => void;
  readOnly?: boolean;
}) {
  const isRelated = row.row_type === "related_part";
  return (
    <tr
      data-testid="tracking-row"
      className={`h-pin-row border-t border-h-line hover:bg-h-bg ${isRelated ? "h-pin-related bg-h-bg/60" : ""}`}
    >
      <td className="px-1 py-1 text-center">
        <input
          type="checkbox"
          checked={checked}
          disabled={!bulkEnabled}
          onChange={onToggle}
          className={bulkEnabled ? "cursor-pointer" : "opacity-30"}
          aria-label={`Select item ${row.item_number ?? row.id}`}
          title={bulkEnabled ? "Select for bulk status change" : "Bulk select unavailable"}
        />
      </td>
      <td className="px-1 py-1 text-center">
        {isRelated || readOnly ? (
          // Q559: GET /items/{id} 404s on a related part — it has no Cutlist,
          // Hardware or Board tab to open. Related parts are edited in Tracking.
          // A deleted item 404s the same way.
          <span
            className="inline-block p-0.5 text-h-line"
            title={isRelated ? "A related part has no item editor (Q559)" : "A deleted item cannot be opened"}
          >
            ▪
          </span>
        ) : (
          <button
            type="button"
            onClick={onOpen}
            className="rounded p-0.5 text-h-muted transition hover:bg-h-bg hover:text-h-accent"
            title="Open item details"
            aria-label="Open item details"
          >
            ▶
          </button>
        )}
      </td>
      <td className="whitespace-nowrap px-2 py-1 font-mono text-h-ink">
        <span className="flex items-center gap-1">
          {isRelated ? (
            <span className="w-3.5 shrink-0" />
          ) : relatedCount > 0 ? (
            <button
              type="button"
              onClick={onToggleRelated}
              className="w-3.5 shrink-0 rounded text-[9px] text-h-muted transition hover:text-h-accent"
              title={`${relatedOpen ? "Hide" : "Show"} ${relatedCount} related part${relatedCount === 1 ? "" : "s"}`}
              aria-expanded={relatedOpen}
              aria-label={`${relatedOpen ? "Hide" : "Show"} related parts`}
            >
              {relatedOpen ? "▼" : "▶"}
            </button>
          ) : (
            <span className="w-3.5 shrink-0" />
          )}
          <ReferenceCell row={row} projectId={projectId} readOnly={readOnly} />
        </span>
      </td>
      <td className="whitespace-nowrap px-2 py-1 text-h-ink">
        <JidCell code={row.jid_code} color={row.jid_color} />
      </td>
      <td className="px-2 py-1">
        <VarBoqPill value={row.var_boq ?? "BOQ"} />
      </td>
      <td className="px-2 py-1 text-h-ink">{row.stage ?? "—"}</td>
      <td className="px-2 py-1 text-h-muted">{row.zone ?? "—"}</td>
      <td className="px-2 py-1 text-h-muted">{row.level ?? "—"}</td>
      <td className="px-2 py-1 text-h-muted">{row.room_no ?? "—"}</td>
      <td className="px-2 py-1 text-h-ink">{row.room_desc ?? "—"}</td>
      <td className="px-2 py-1 font-mono text-h-ink">{row.code ?? "—"}</td>
      <td className="px-2 py-1 text-h-ink">
        {isRelated ? (
          <span className="flex items-center gap-1.5 pl-4">
            <span className="rounded bg-h-line/60 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-h-muted">
              {row.related_part_type_key ?? "part"}
            </span>
            {row.description ?? "—"}
          </span>
        ) : (
          row.description ?? "—"
        )}
      </td>
      <td className="px-2 py-1">
        {readOnly ? (
          <span className={`inline-block rounded-full px-2 py-0.5 text-[10px] font-semibold ${statusClasses(row.status)}`}>
            {row.status ?? "—"}
          </span>
        ) : (
          <button
            type="button"
            onClick={onOpenStatus}
            title="Open status detail (Add New Status)"
            aria-label="Open status detail"
            className={`inline-block rounded-full px-2 py-0.5 text-[10px] font-semibold transition hover:opacity-80 hover:ring-2 hover:ring-h-accent/40 ${statusClasses(row.status)}`}
          >
            {row.status ?? "—"}
          </button>
        )}
      </td>
      <td className="px-2 py-1 text-right font-mono tabular-nums text-h-ink">
        {formatAmount(row.total_amount)}
      </td>
      <td className="px-2 py-1 text-right font-mono tabular-nums text-h-ink">{row.qty ?? "—"}</td>
      <td className="px-2 py-1 text-h-muted" title="Contractor">{row.contractor_name ?? "—"}</td>
      <td className="px-2 py-1 text-h-muted">{row.cutlist_owner_name ?? "—"}</td>
      <td className="px-2 py-1 font-mono text-h-muted" title="Factory">{row.factory_code ?? "—"}</td>
      {isRelated && isDateLike ? (
        // Q419: show NO workflow stages for a related part — leave the whole
        // stage area blank rather than borrowing the parent's dates. Blank
        // cells, not em dashes: an em dash reads as "recorded, but empty".
        //
        // Scoped to the stage-date strips alone. Q419 blanks the *workflow-stage*
        // area; the other sub-tabs are not stages, and O/BOOK especially must
        // render for a related part — an order raised against one is the
        // normal case (Q424), which is half of why that sub-tab exists.
        Array.from({ length: STAGE_KEYS.length }).map((_, i) => (
          <td key={i} className="px-2 py-1" />
        ))
      ) : isDateLike ? (
        STAGE_KEYS.map((sk) => (
          <StageCell key={sk} stage={row.stages[sk]} today={today} />
        ))
      ) : subTab === "O/BOOK" ? (
        <OrderCells row={row} />
      ) : (
        <SubTabCells row={row} subTab={subTab} subColCount={subColCount} />
      )}
      <td className="whitespace-nowrap px-2 py-1 font-mono text-[10px] text-h-muted">
        {/* Q541/Q416: the Item ID is the six-digit `num`, not the internal row
            key. It moved here from the CUTLIST column, which now carries the
            cutlist's own number, and keeps the click-through to the editor —
            except on a related part, which has no editor (Q559). */}
        {isRelated || readOnly ? (
          <span>{row.item_number ?? row.id}</span>
        ) : (
          <Link href={`/items/${row.id}`} className="hover:text-h-accent hover:underline">
            {row.item_number ?? row.id}
          </Link>
        )}
      </td>
      {/* #4's availability rollup. The chip is the AvailabilityDrawer's only
          entry point, so it is a button whenever a handler is supplied. A
          related part carries no hardware lines of its own, so it has nothing
          to roll up and shows a plain dash. */}
      <td className="px-2 py-1">
        {isRelated ? (
          <span className="text-h-muted">—</span>
        ) : onOpenAvailability ? (
          <button
            type="button"
            onClick={() => onOpenAvailability(row.id)}
            data-testid="open-availability"
            aria-label="Open item availability"
            className="rounded hover:opacity-80"
          >
            <AvailabilityChip
              ready={row.availability.ready}
              blocked={row.availability.blocked}
            />
          </button>
        ) : (
          <AvailabilityChip
            ready={row.availability.ready}
            blocked={row.availability.blocked}
          />
        )}
      </td>
    </tr>
  );
}
