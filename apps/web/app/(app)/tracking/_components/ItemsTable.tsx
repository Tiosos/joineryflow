"use client";

import { useLayoutEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import type { TrackingItemRow } from "@/lib/pm-types";
import { AvailabilityChip } from "@/components/pm/AvailabilityChip";

// Q425 adds O/BOOK to the strip the legacy mock established. It swaps the
// right-hand columns like every other entry — one row per item stays Tracking's
// spine — and carries the Create Order button.
export type SubTab =
  | "DATE" | "iTIME" | "HARDWARE" | "SITE MEASURE" | "INVOICE" | "QC" | "O/BOOK";

export const SUB_TABS: SubTab[] = [
  "DATE", "iTIME", "HARDWARE", "SITE MEASURE", "INVOICE", "QC", "O/BOOK",
];

const STAGE_KEYS = [
  "REQ", "SM", "LISTED", "DOWN", "CNC", "EDGED", "PAINTED", "MADE", "DEL", "INST",
] as const;

const SUB_TAB_COLUMNS: Record<Exclude<SubTab, "DATE">, { key: string; label: string }[]> = {
  iTIME: [
    { key: "hours", label: "Hours" },
    { key: "operator", label: "Operator" },
    { key: "start", label: "Start" },
    { key: "end", label: "End" },
  ],
  HARDWARE: [
    { key: "hinges", label: "Hinges" },
    { key: "handles", label: "Handles" },
    { key: "runners", label: "Runners" },
    { key: "ordered", label: "Ordered" },
    { key: "received", label: "Received" },
  ],
  "SITE MEASURE": [
    { key: "smdate", label: "SM Date" },
    { key: "by", label: "By" },
    { key: "variance", label: "Variance" },
    { key: "signoff", label: "Signed Off" },
  ],
  INVOICE: [
    { key: "invno", label: "Invoice #" },
    { key: "invdate", label: "Date" },
    { key: "amount", label: "Amount" },
    { key: "paid", label: "Paid" },
  ],
  QC: [
    { key: "checked", label: "Checked" },
    { key: "by", label: "By" },
    { key: "result", label: "Result" },
    { key: "rework", label: "Rework" },
  ],
  "O/BOOK": [
    { key: "orderno", label: "Order #" },
    { key: "supplier", label: "Supplier" },
    { key: "ostatus", label: "Status" },
    { key: "eta", label: "ETA" },
  ],
};

type SortKey =
  | "num" | "stage" | "zone" | "level" | "rmNo" | "rmDesc" | "code"
  | "desc" | "status" | "size" | "qty" | "assem" | "lister" | "itemId"
  | `stage:${(typeof STAGE_KEYS)[number]}`;

interface FilterState {
  stage: string;
  zone: string;
  level: string;
  rmNo: string;
  rmDesc: string;
  code: string;
  status: string;
  lister: string;
}

const EMPTY_FILTERS: FilterState = {
  stage: "", zone: "", level: "", rmNo: "", rmDesc: "",
  code: "", status: "", lister: "",
};

interface Props {
  items: TrackingItemRow[];
  /** Needed for the cutlist deep link — a row carries no project of its own. */
  projectId: number;
  cutlistQuery: string;
  freeQuery: string;
  onOpenItem: (id: number) => void;
  onOpenStatus: (id: number) => void;
  /** Q432: the orderbook write holders — admin, manager, drafter, purchase_officer. */
  canCreateOrder?: boolean;
  onCreateOrder?: () => void;
  /**
   * Opens the item-scoped AvailabilityDrawer (#4). The chip was the drawer's
   * only entry point and lived on the old `TrackingGrid`, which #9a replaced
   * with this table without carrying it over — leaving the drawer reachable
   * only by hand-typing `?drawer=item-availability&itemId=N`. Restored here.
   */
  onOpenAvailability?: (id: number) => void;
}

function statusClasses(status: string | null): string {
  switch (status) {
    case "CLEAR":    return "bg-[#e4efe5] text-[#3f7d48]";
    case "VOID":     return "bg-[#f2dcd9] text-[#b4443d]";
    case "NOTE!":    return "bg-[#f4ebd9] text-[#c48a2e]";
    case "LIVE":     return "bg-[#f3e0d6] text-[#a84f31]";
    case "APPROVED": return "bg-[#e4efe5] text-[#3f7d48]";
    case "HOLD":     return "bg-[#f4ebd9] text-[#c48a2e]";
    default:         return "bg-[#f4f2ed] text-[#8f8b80]";
  }
}

function addDaysISO(iso: string, days: number): string {
  const d = new Date(iso + "T00:00:00Z");
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

function todayISO(): string {
  return new Date().toISOString().slice(0, 10);
}

function dateCellColor(dueIso: string | null, doneIso: string | null, todayIso: string): string {
  if (doneIso) return "text-[#3f7d48]";
  if (dueIso && dueIso < todayIso) return "text-[#b4443d] font-semibold";
  if (dueIso && dueIso <= addDaysISO(todayIso, 7)) return "text-[#c48a2e]";
  return "text-h-muted";
}

export function ItemsTable({
  items,
  projectId,
  cutlistQuery,
  freeQuery,
  onOpenItem,
  onOpenStatus,
  canCreateOrder = false,
  onCreateOrder,
  onOpenAvailability,
}: Props) {
  const [filters, setFilters] = useState<FilterState>(EMPTY_FILTERS);
  const [sortKey, setSortKey] = useState<SortKey>("num");
  const [sortAsc, setSortAsc] = useState(true);
  const [subTab, setSubTab] = useState<SubTab>("DATE");
  // Q422: related parts are collapsed when Tracking first opens. The set holds
  // the parent ids the user has opened.
  const [expanded, setExpanded] = useState<Set<number>>(() => new Set());
  const containerRef = useRef<HTMLDivElement>(null);
  const savedScrollLeft = useRef(0);

  useLayoutEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollLeft = savedScrollLeft.current;
    }
  }, [subTab]);

  // Q420: related parts are not free-standing rows — they hang off a parent.
  // Everything the grid does (filter, sort, the filter dropdowns' options) runs
  // over the Joinery Items alone; each parent's related parts follow it, so no
  // sort order can separate a child from its parent.
  const parents = useMemo(
    () => items.filter((i) => i.row_type !== "related_part"),
    [items],
  );
  const childrenByParent = useMemo(() => {
    const m = new Map<number, TrackingItemRow[]>();
    for (const it of items) {
      if (it.row_type !== "related_part" || it.parent_item_id == null) continue;
      const kids = m.get(it.parent_item_id);
      if (kids) kids.push(it);
      else m.set(it.parent_item_id, [it]);
    }
    return m;
  }, [items]);

  const levels  = useMemo(() => uniqStrings(parents.map((i) => i.level)), [parents]);
  const rooms   = useMemo(() => uniqStrings(parents.map((i) => i.room_no)), [parents]);
  const descs   = useMemo(() => uniqStrings(parents.map((i) => i.room_desc)), [parents]);
  const codes   = useMemo(() => uniqStrings(parents.map((i) => i.code)), [parents]);
  const listers = useMemo(() => uniqStrings(parents.map((i) => i.cutlist_owner_name)), [parents]);

  const filtered = useMemo(() => {
    const cq = cutlistQuery.trim();
    const fq = freeQuery.trim().toLowerCase();
    return parents.filter((it) => {
      if (filters.stage && it.stage !== filters.stage) return false;
      if (filters.zone && it.zone !== filters.zone) return false;
      if (filters.level && it.level !== filters.level) return false;
      if (filters.rmNo && it.room_no !== filters.rmNo) return false;
      if (filters.rmDesc && it.room_desc !== filters.rmDesc) return false;
      if (filters.code && it.code !== filters.code) return false;
      if (filters.status && it.status !== filters.status) return false;
      if (filters.lister && it.cutlist_owner_name !== filters.lister) return false;
      // The box is labelled "Cutlist #", so it matches the cutlist number — but
      // Q541 draws Item IDs and cutlist numbers from ONE sequence, so the two
      // can never collide and matching either keeps a six-digit number typed
      // from a printed sheet finding its row whichever kind it is.
      if (cq) {
        const nums = [it.cutlist_no, it.item_number].filter((n) => n != null);
        if (!nums.some((n) => String(n).includes(cq))) return false;
      }
      if (fq) {
        const hay = [it.code, it.description, it.room_desc, it.room_no, it.stage]
          .filter(Boolean)
          .join(" ")
          .toLowerCase();
        if (!hay.includes(fq)) return false;
      }
      return true;
    });
  }, [parents, filters, cutlistQuery, freeQuery]);

  const sorted = useMemo(() => sortRows(filtered, sortKey, sortAsc), [filtered, sortKey, sortAsc]);

  function setSort(key: SortKey) {
    if (key === sortKey) {
      setSortAsc(!sortAsc);
    } else {
      setSortKey(key);
      setSortAsc(true);
    }
  }

  function patch<K extends keyof FilterState>(k: K, v: FilterState[K]) {
    setFilters((s) => ({ ...s, [k]: v }));
  }

  function toggleRelated(parentId: number) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(parentId)) next.delete(parentId);
      else next.add(parentId);
      return next;
    });
  }

  function clearFilters() {
    setFilters(EMPTY_FILTERS);
    setSortKey("num");
    setSortAsc(true);
  }

  const isDate = subTab === "DATE";
  const subCols = isDate ? null : SUB_TAB_COLUMNS[subTab];
  const today = todayISO();

  return (
    <div
      ref={containerRef}
      className="overflow-x-auto rounded-lg border border-h-line bg-h-surface"
      onScroll={() => { savedScrollLeft.current = containerRef.current?.scrollLeft ?? 0; }}
    >
      <table className="w-full text-xs">
        <thead className="bg-h-bg text-h-muted">
          <tr>
            <td colSpan={15} />
            <th
              colSpan={(isDate ? 10 : subCols!.length) + 1}
              className="px-2 py-1 text-right"
            >
              {SUB_TABS.map((st) => (
                <button
                  key={st}
                  type="button"
                  onClick={() => setSubTab(st)}
                  className={`mx-0.5 rounded px-2.5 py-1 text-[11px] font-medium transition ${
                    st === subTab
                      ? "bg-h-accent text-white"
                      : "text-h-muted hover:text-h-ink"
                  }`}
                >
                  {st}
                </button>
              ))}
              {subTab === "O/BOOK" && canCreateOrder && (
                <button
                  type="button"
                  onClick={onCreateOrder}
                  className="ml-2 rounded bg-h-accent px-2.5 py-1 text-[11px] font-medium text-white"
                >
                  + Create Order
                </button>
              )}
            </th>
          </tr>
          <tr>
            <Th className="w-6" />
            <Th className="w-6" />
            <Th sort sortActive={sortKey === "num"} sortAsc={sortAsc} onSort={() => setSort("num")}>CUTLIST</Th>
            <Th sort sortActive={sortKey === "stage"} sortAsc={sortAsc} onSort={() => setSort("stage")}>Stage</Th>
            <Th sort sortActive={sortKey === "zone"} sortAsc={sortAsc} onSort={() => setSort("zone")}>Zone</Th>
            <Th sort sortActive={sortKey === "level"} sortAsc={sortAsc} onSort={() => setSort("level")}>Lvl</Th>
            <Th sort sortActive={sortKey === "rmNo"} sortAsc={sortAsc} onSort={() => setSort("rmNo")}>Rm#</Th>
            <Th sort sortActive={sortKey === "rmDesc"} sortAsc={sortAsc} onSort={() => setSort("rmDesc")}>Room</Th>
            <Th sort sortActive={sortKey === "code"} sortAsc={sortAsc} onSort={() => setSort("code")}>Code</Th>
            <Th sort sortActive={sortKey === "desc"} sortAsc={sortAsc} onSort={() => setSort("desc")}>Description</Th>
            <Th sort sortActive={sortKey === "status"} sortAsc={sortAsc} onSort={() => setSort("status")}>STATUS</Th>
            <Th align="right" sort sortActive={sortKey === "size"} sortAsc={sortAsc} onSort={() => setSort("size")}>Size</Th>
            <Th align="right" sort sortActive={sortKey === "qty"} sortAsc={sortAsc} onSort={() => setSort("qty")}>Qty</Th>
            <Th sort sortActive={sortKey === "assem"} sortAsc={sortAsc} onSort={() => setSort("assem")}>Assembler</Th>
            <Th sort sortActive={sortKey === "lister"} sortAsc={sortAsc} onSort={() => setSort("lister")}>Lister</Th>
            {isDate ? (
              STAGE_KEYS.map((sk) => (
                <Th
                  key={sk}
                  sort
                  sortActive={sortKey === (`stage:${sk}` as SortKey)}
                  sortAsc={sortAsc}
                  onSort={() => setSort(`stage:${sk}` as SortKey)}
                >
                  {sk}
                </Th>
              ))
            ) : (
              subCols!.map((c) => <Th key={c.key}>{c.label}</Th>)
            )}
            <Th sort sortActive={sortKey === "itemId"} sortAsc={sortAsc} onSort={() => setSort("itemId")}>Item ID</Th>
            <Th>Avail.</Th>
          </tr>
          <tr className="border-t border-h-line bg-h-surface">
            <td />
            <td className="px-1 py-1">
              <button
                type="button"
                onClick={clearFilters}
                className="rounded border border-h-line bg-h-bg px-1.5 py-0.5 text-[10px] text-h-muted hover:text-h-ink"
                title="Clear filters + sort"
              >
                Clear
              </button>
            </td>
            <td />
            <td className="px-1 py-1">
              <FilterSelect value={filters.stage} onChange={(v) => patch("stage", v)} options={["Joinery Lab", "Joinery General", "PC2", "Stone"]} placeholder="All stages" />
            </td>
            <td className="px-1 py-1">
              <FilterSelect value={filters.zone} onChange={(v) => patch("zone", v)} options={["03", "04", "05"]} placeholder="All zones" />
            </td>
            <td className="px-1 py-1">
              <FilterSelect value={filters.level} onChange={(v) => patch("level", v)} options={levels} placeholder="All levels" />
            </td>
            <td className="px-1 py-1">
              <FilterSelect value={filters.rmNo} onChange={(v) => patch("rmNo", v)} options={rooms} placeholder="All rooms" />
            </td>
            <td className="px-1 py-1">
              <FilterSelect value={filters.rmDesc} onChange={(v) => patch("rmDesc", v)} options={descs} placeholder="All rooms" />
            </td>
            <td className="px-1 py-1">
              <FilterSelect value={filters.code} onChange={(v) => patch("code", v)} options={codes} placeholder="All codes" />
            </td>
            <td />
            <td className="px-1 py-1">
              <FilterSelect value={filters.status} onChange={(v) => patch("status", v)} options={["CLEAR", "VOID", "NOTE!", "LIVE", "APPROVED", "HOLD"]} placeholder="All statuses" />
            </td>
            <td /><td />
            <td className="px-1 py-1">
              <FilterSelect value={""} onChange={() => {}} options={[]} placeholder="All assemblers" disabled />
            </td>
            <td className="px-1 py-1">
              <FilterSelect value={filters.lister} onChange={(v) => patch("lister", v)} options={listers} placeholder="All listers" />
            </td>
            {isDate ? (
              <>
                <td /><td /><td /><td /><td /><td /><td /><td /><td /><td />
              </>
            ) : (
              subCols!.map((c) => <td key={c.key} />)
            )}
            <td /><td />
          </tr>
        </thead>
        <tbody>
          {sorted.length === 0 ? (
            <tr>
              <td colSpan={27} className="px-4 py-8 text-center text-h-muted">
                No items match your filters.
              </td>
            </tr>
          ) : (
            sorted.flatMap((it) => {
              const kids = childrenByParent.get(it.id) ?? [];
              const isOpen = expanded.has(it.id);
              const rows = [
                <Row
                  key={it.id}
                  row={it}
                  projectId={projectId}
                  isDate={isDate}
                  subTab={subTab}
                  subColCount={subCols?.length ?? 0}
                  today={today}
                  relatedCount={kids.length}
                  relatedOpen={isOpen}
                  onToggleRelated={() => toggleRelated(it.id)}
                  onOpen={() => onOpenItem(it.id)}
                  onOpenStatus={() => onOpenStatus(it.id)}
                  onOpenAvailability={onOpenAvailability}
                />,
              ];
              if (isOpen) {
                for (const kid of kids) {
                  rows.push(
                    <Row
                      key={kid.id}
                      row={kid}
                      projectId={projectId}
                      isDate={isDate}
                      subTab={subTab}
                      subColCount={subCols?.length ?? 0}
                      today={today}
                      onOpen={() => onOpenItem(kid.id)}
                      onOpenStatus={() => onOpenStatus(kid.id)}
                      onOpenAvailability={onOpenAvailability}
                    />,
                  );
                }
              }
              return rows;
            })
          )}
        </tbody>
      </table>
    </div>
  );
}

function Row({
  row,
  projectId,
  isDate,
  subTab,
  subColCount,
  today,
  relatedCount = 0,
  relatedOpen = false,
  onToggleRelated,
  onOpen,
  onOpenStatus,
  onOpenAvailability,
}: {
  row: TrackingItemRow;
  projectId: number;
  isDate: boolean;
  subTab: SubTab;
  subColCount: number;
  today: string;
  relatedCount?: number;
  relatedOpen?: boolean;
  onToggleRelated?: () => void;
  onOpen: () => void;
  onOpenStatus: () => void;
  onOpenAvailability?: (id: number) => void;
}) {
  const isRelated = row.row_type === "related_part";
  return (
    <tr
      data-testid="tracking-row"
      className={`border-t border-h-line hover:bg-h-bg ${isRelated ? "bg-h-bg/60" : ""}`}
    >
      <td className="px-1 py-1 text-center text-h-muted" title="Omit (mock-only)">
        <input type="checkbox" disabled className="opacity-30" />
      </td>
      <td className="px-1 py-1 text-center">
        {isRelated ? (
          // Q559: GET /items/{id} 404s on a related part — it has no Cutlist,
          // Hardware or Board tab to open. Related parts are edited in Tracking.
          <span
            className="inline-block p-0.5 text-h-line"
            title="A related part has no item editor (Q559)"
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
          <ReferenceCell row={row} projectId={projectId} />
        </span>
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
        <button
          type="button"
          onClick={onOpenStatus}
          title="Open status detail (Add New Status)"
          aria-label="Open status detail"
          className={`inline-block rounded-full px-2 py-0.5 text-[10px] font-semibold transition hover:opacity-80 hover:ring-2 hover:ring-h-accent/40 ${statusClasses(row.status)}`}
        >
          {row.status ?? "—"}
        </button>
      </td>
      <td className="px-2 py-1 text-right text-h-muted">—</td>
      <td className="px-2 py-1 text-right font-mono tabular-nums text-h-ink">{row.qty ?? "—"}</td>
      <td className="px-2 py-1 text-h-muted" title="Assembler (mock-only)">—</td>
      <td className="px-2 py-1 text-h-muted">{row.cutlist_owner_name ?? "—"}</td>
      {isRelated && isDate ? (
        // Q419: show NO workflow stages for a related part — leave the whole
        // stage area blank rather than borrowing the parent's dates. Blank
        // cells, not em dashes: an em dash reads as "recorded, but empty".
        //
        // Scoped to the DATE strip alone. Q419 blanks the *workflow-stage*
        // area; the other sub-tabs are not stages, and O/BOOK especially must
        // render for a related part — an order raised against one is the
        // normal case (Q424), which is half of why that sub-tab exists.
        Array.from({ length: STAGE_KEYS.length }).map((_, i) => (
          <td key={i} className="px-2 py-1" />
        ))
      ) : isDate ? (
        STAGE_KEYS.map((sk) => (
          <StageCell key={sk} stage={row.stages[sk]} today={today} />
        ))
      ) : subTab === "O/BOOK" ? (
        <OrderCells row={row} />
      ) : (
        Array.from({ length: subColCount }).map((_, i) => (
          <td key={i} className="px-2 py-1 text-h-muted">—</td>
        ))
      )}
      <td className="whitespace-nowrap px-2 py-1 font-mono text-[10px] text-h-muted">
        {/* Q541/Q416: the Item ID is the six-digit `num`, not the internal row
            key. It moved here from the CUTLIST column, which now carries the
            cutlist's own number, and keeps the click-through to the editor —
            except on a related part, which has no editor (Q559). */}
        {isRelated ? (
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

/**
 * Q417: the leftmost reference depends on the row type — a Joinery Item shows
 * its cutlist number, a related part shows the supplier-order number, because
 * a related part never receives a cutlist number at all.
 *
 * Q567 fixes what "issued" means: the API returns `issued_order_no` only once
 * that order carries a `date_ordered`, so a draft order leaves the cell blank.
 *
 * Q418: clicking the order number opens Orderbook **on that order**.
 * `/orderbook` reads `purchase_orders` since the E2 rework and honours the
 * `order` param by selecting the row and opening its detail panel; #4's
 * procurement-batch queue moved to the Delivery queue tab beside it (Q504).
 */
function ReferenceCell({ row, projectId }: { row: TrackingItemRow; projectId: number }) {
  if (row.row_type !== "related_part") {
    // Q438/Q568: the cutlist's number, which several items share — not this
    // item's own. Blank while the item has no cutlist, which Q440 allows
    // indefinitely; its Item ID still identifies the row.
    //
    // `plan_v1.md` §1218: "Clicking that number opens a separate window
    // containing the cutlist details" — Q545 defines "separate window" as a
    // target="_blank" tab, and Q474 puts those details on /list.
    if (row.cutlist_no == null) {
      return <span className="text-h-muted" title="No cutlist assigned yet">—</span>;
    }
    return (
      <Link
        href={`/list?project_id=${projectId}&cutlist=${row.cutlist_id}`}
        target="_blank"
        className="hover:text-h-accent hover:underline"
        title="Open this cutlist in a new tab"
      >
        {row.cutlist_no}
      </Link>
    );
  }
  if (!row.issued_order_no) {
    return (
      <span className="text-h-muted" title="No supplier order issued yet">
        —
      </span>
    );
  }
  return (
    <Link
      href={`/orderbook?order=${encodeURIComponent(row.issued_order_no)}`}
      className="text-h-accent hover:underline"
      title="Open this order in Orderbook"
    >
      {row.issued_order_no}
    </Link>
  );
}

/**
 * Q425's O/BOOK columns: this row's latest order, whatever its state — a Draft
 * raised moments ago is precisely what the sub-tab is for. Related parts get
 * these columns too: an order against a related part is the normal case (Q424).
 */
function OrderCells({ row }: { row: TrackingItemRow }) {
  if (row.order_no == null) {
    return (
      <>
        <td className="px-2 py-1 text-h-muted">—</td>
        <td className="px-2 py-1 text-h-muted">—</td>
        <td className="px-2 py-1 text-h-muted">—</td>
        <td className="px-2 py-1 text-h-muted">—</td>
      </>
    );
  }
  return (
    <>
      <td className="whitespace-nowrap px-2 py-1 font-mono text-h-ink">
        <Link
          href={`/orderbook?order=${encodeURIComponent(row.order_no)}`}
          target="_blank"
          className="hover:text-h-accent hover:underline"
          title="Open this order in Orderbook"
        >
          {row.order_no}
        </Link>
      </td>
      <td className="px-2 py-1 text-h-ink">{row.order_supplier ?? "—"}</td>
      <td className="px-2 py-1">
        <span className="rounded-full bg-h-line/50 px-2 py-0.5 text-[10px] font-semibold text-h-ink">
          {row.order_status ?? "—"}
        </span>
      </td>
      <td className="px-2 py-1 font-mono text-[10px] tabular-nums text-h-muted">
        {row.order_due_date ? row.order_due_date.slice(5) : "—"}
      </td>
    </>
  );
}

function StageCell({
  stage,
  today,
}: {
  stage?: { due_date: string | null; done_date: string | null };
  today: string;
}) {
  if (!stage || (!stage.due_date && !stage.done_date)) {
    return <td className="px-2 py-1 text-h-muted">—</td>;
  }
  const display = stage.done_date ?? stage.due_date;
  return (
    <td className={`px-2 py-1 font-mono text-[10px] tabular-nums ${dateCellColor(stage.due_date, stage.done_date, today)}`}>
      {display ? display.slice(5) : "—"}
    </td>
  );
}

function Th({
  children,
  className = "",
  align = "left",
  sort,
  sortActive,
  sortAsc,
  onSort,
  title,
}: {
  children?: React.ReactNode;
  className?: string;
  align?: "left" | "right";
  sort?: boolean;
  sortActive?: boolean;
  sortAsc?: boolean;
  onSort?: () => void;
  title?: string;
}) {
  const alignClass = align === "right" ? "text-right" : "text-left";
  const sortIndicator = sort ? (
    <span className={`ml-1 inline-block text-[8px] ${sortActive ? "text-h-ink" : "text-h-line"}`}>
      {sortActive ? (sortAsc ? "▲" : "▼") : "↕"}
    </span>
  ) : null;
  return (
    <th
      className={`px-2 py-2 font-mono text-[10px] font-semibold uppercase tracking-wider ${alignClass} ${className} ${sort ? "cursor-pointer select-none hover:text-h-ink" : ""}`}
      onClick={onSort}
      title={title}
    >
      {children}
      {sortIndicator}
    </th>
  );
}

function FilterSelect({
  value,
  onChange,
  options,
  placeholder,
  disabled,
}: {
  value: string;
  onChange: (v: string) => void;
  options: string[];
  placeholder: string;
  disabled?: boolean;
}) {
  return (
    <select
      value={value}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value)}
      className="w-full rounded border border-h-line bg-h-surface px-1 py-0.5 text-[10px] text-h-ink disabled:opacity-50"
    >
      <option value="">{placeholder}</option>
      {options.map((o) => (
        <option key={o} value={o}>
          {o}
        </option>
      ))}
    </select>
  );
}

function uniqStrings(values: (string | null | undefined)[]): string[] {
  const seen = new Set<string>();
  for (const v of values) {
    if (v != null && v !== "") seen.add(v);
  }
  return Array.from(seen).sort();
}

function sortRows(rows: TrackingItemRow[], key: SortKey, asc: boolean): TrackingItemRow[] {
  const out = [...rows];
  out.sort((a, b) => compareRows(a, b, key));
  return asc ? out : out.reverse();
}

function compareRows(a: TrackingItemRow, b: TrackingItemRow, key: SortKey): number {
  if (key.startsWith("stage:")) {
    const sk = key.slice(6);
    const av = a.stages[sk]?.done_date ?? a.stages[sk]?.due_date ?? "";
    const bv = b.stages[sk]?.done_date ?? b.stages[sk]?.due_date ?? "";
    return cmp(av, bv);
  }
  switch (key as Exclude<SortKey, `stage:${string}`>) {
    // "num" is the CUTLIST column, which now carries the cutlist's number.
    case "num":    return cmp(a.cutlist_no ?? 0, b.cutlist_no ?? 0);
    case "stage":  return cmp(a.stage ?? "", b.stage ?? "");
    case "zone":   return cmp(a.zone ?? "", b.zone ?? "");
    case "level":  return cmp(a.level ?? "", b.level ?? "");
    case "rmNo":   return cmp(a.room_no ?? "", b.room_no ?? "");
    case "rmDesc": return cmp(a.room_desc ?? "", b.room_desc ?? "");
    case "code":   return cmp(a.code ?? "", b.code ?? "");
    case "desc":   return cmp(a.description ?? "", b.description ?? "");
    case "status": return cmp(a.status ?? "", b.status ?? "");
    case "size":   return 0;
    case "qty":    return cmp(a.qty ?? 0, b.qty ?? 0);
    case "assem":  return 0;
    case "lister": return cmp(a.cutlist_owner_name ?? "", b.cutlist_owner_name ?? "");
    case "itemId": return cmp(a.item_number ?? a.id, b.item_number ?? b.id);
  }
}

function cmp(a: string | number, b: string | number): number {
  if (a < b) return -1;
  if (a > b) return 1;
  return 0;
}
