"use client";

import { useLayoutEffect, useMemo, useRef, useState } from "react";
import type { TrackingItemRow } from "@/lib/pm-types";
import { PIN_COLS, PIN_MIN_SCROLL_PX, SubTab, SUB_TABS, STAGE_KEYS, DATE_LIKE_SUBTABS, SUB_TAB_COLUMNS, SortKey, FilterState, EMPTY_FILTERS, todayISO, uniqStrings, sortRows } from "./items-table/shared";
import { Row } from "./items-table/Row";
import { Th } from "./items-table/Th";
import { FilterSelect } from "./items-table/FilterSelect";

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
  // Bulk selection — optional; pass nothing to disable (List tab reuse).
  selectedIds?: Set<number>;
  onToggleSelect?: (id: number) => void;
  onToggleSelectVisible?: (ids: number[], select: boolean) => void;
  /** The Deleted view: rows are shown but cannot be opened — a deleted item answers 404. */
  readOnly?: boolean;
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
  selectedIds,
  onToggleSelect,
  onToggleSelectVisible,
  readOnly = false,
}: Props) {
  const bulkEnabled = Boolean(selectedIds && onToggleSelect && onToggleSelectVisible);
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

  // Pinned columns: the first PIN_COLS (checkbox .. Lister) stay in place while the stage-date
  // columns scroll. Their left offsets are the measured widths of the columns before them, and
  // pinning only switches on when the card leaves PIN_MIN_SCROLL_PX for the scrolling columns,
  // so a narrow window never ends up with a table it cannot scroll to the right.
  const [pin, setPin] = useState<{ offsets: number[]; on: boolean } | null>(null);
  useLayoutEffect(() => {
    const card = containerRef.current;
    const table = card?.querySelector("table");
    if (!card || !table) return;
    const measure = () => {
      const ths = card.querySelectorAll<HTMLElement>("thead tr:nth-child(2) > th");
      if (ths.length < PIN_COLS) return;
      const offsets: number[] = [];
      let acc = 0;
      for (let i = 0; i < PIN_COLS; i++) {
        offsets.push(Math.round(acc));
        acc += ths[i].getBoundingClientRect().width;
      }
      const on = card.clientWidth - acc >= PIN_MIN_SCROLL_PX;
      setPin((prev) =>
        prev && prev.on === on && prev.offsets.every((o, i) => o === offsets[i]) ? prev : { offsets, on },
      );
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(card);
    ro.observe(table);
    return () => ro.disconnect();
  }, []);

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

  // For TO BE ORDERED, filter to items with at least one blocked hardware line.
  // Declared before `filtered`, whose memo reads it during render.
  const subtabFiltered = useMemo(
    () => (subTab === "TO BE ORDERED" ? parents.filter((it) => it.availability.blocked > 0) : parents),
    [parents, subTab],
  );

  const filtered = useMemo(() => {
    const cq = cutlistQuery.trim();
    const fq = freeQuery.trim().toLowerCase();
    return subtabFiltered.filter((it) => {
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
  }, [subtabFiltered, filters, cutlistQuery, freeQuery]);

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

  const isDateLike = DATE_LIKE_SUBTABS.has(subTab);
  const subCols = isDateLike ? null : SUB_TAB_COLUMNS[subTab as Exclude<SubTab, "DATE" | "TO BE ORDERED">];
  const today = todayISO();

  return (
    <div
      ref={containerRef}
      // Scrolls both ways inside the card (so both scrollbars stay on screen); the header stays put.
      className={`h-scrollbars max-h-[calc(100vh-10rem)] overflow-auto rounded-lg border border-h-line bg-h-surface ${pin?.on ? "h-pinned" : ""}`}
      style={
        pin?.on
          ? (Object.fromEntries(pin.offsets.map((o, i) => [`--pin-${i + 1}`, `${o}px`])) as React.CSSProperties)
          : undefined
      }
      onScroll={() => { savedScrollLeft.current = containerRef.current?.scrollLeft ?? 0; }}
    >
      <table className="w-full text-xs">
        <thead className="sticky top-0 z-10 bg-h-bg text-h-muted shadow-[0_1px_0_0_var(--color-h-line)]">
          <tr>
            <td colSpan={18} />
            <th
              // 18 fixed columns before this (17 pinned + Factory) + the stage/sub-tab columns + Item ID + Avail.
              colSpan={(isDateLike ? 10 : subCols!.length) + 2}
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
          <tr className="h-pin-row h-pin-head">
            <Th className="w-6" />
            <Th className="w-6" />
            <Th sort sortActive={sortKey === "num"} sortAsc={sortAsc} onSort={() => setSort("num")}>CUTLIST</Th>
            <Th>JID</Th>
            <Th>V/B</Th>
            <Th sort sortActive={sortKey === "stage"} sortAsc={sortAsc} onSort={() => setSort("stage")}>Stage</Th>
            <Th sort sortActive={sortKey === "zone"} sortAsc={sortAsc} onSort={() => setSort("zone")}>Zone</Th>
            <Th sort sortActive={sortKey === "level"} sortAsc={sortAsc} onSort={() => setSort("level")}>Lvl</Th>
            <Th sort sortActive={sortKey === "rmNo"} sortAsc={sortAsc} onSort={() => setSort("rmNo")}>Rm#</Th>
            <Th sort sortActive={sortKey === "rmDesc"} sortAsc={sortAsc} onSort={() => setSort("rmDesc")}>Room</Th>
            <Th sort sortActive={sortKey === "code"} sortAsc={sortAsc} onSort={() => setSort("code")}>Code</Th>
            <Th sort sortActive={sortKey === "desc"} sortAsc={sortAsc} onSort={() => setSort("desc")}>Description</Th>
            <Th sort sortActive={sortKey === "status"} sortAsc={sortAsc} onSort={() => setSort("status")}>STATUS</Th>
            <Th align="right" sort sortActive={sortKey === "size"} sortAsc={sortAsc} onSort={() => setSort("size")} title="Total amount $">Total $</Th>
            <Th align="right" sort sortActive={sortKey === "qty"} sortAsc={sortAsc} onSort={() => setSort("qty")}>Qty</Th>
            <Th sort sortActive={sortKey === "assem"} sortAsc={sortAsc} onSort={() => setSort("assem")} title="Contractor">Contractor</Th>
            <Th sort sortActive={sortKey === "lister"} sortAsc={sortAsc} onSort={() => setSort("lister")}>Lister</Th>
            <Th title="Factory the work is made in">Factory</Th>
            {isDateLike ? (
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
          <tr className="h-pin-row border-t border-h-line bg-h-surface">
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
            {/* JID, V/B — no filters in v1 */}
            <td />
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
            <td />
            {isDateLike ? (
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
              <td colSpan={30} className="px-4 py-8 text-center text-h-muted">
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
                  isDateLike={isDateLike}
                  subTab={subTab}
                  subColCount={subCols?.length ?? 0}
                  today={today}
                  relatedCount={kids.length}
                  relatedOpen={isOpen}
                  onToggleRelated={() => toggleRelated(it.id)}
                  bulkEnabled={bulkEnabled}
                  checked={selectedIds?.has(it.id) ?? false}
                  onToggle={onToggleSelect ? () => onToggleSelect(it.id) : undefined}
                  onOpen={() => onOpenItem(it.id)}
                  onOpenStatus={() => onOpenStatus(it.id)}
                  onOpenAvailability={onOpenAvailability}
                  readOnly={readOnly}
                />,
              ];
              if (isOpen) {
                for (const kid of kids) {
                  rows.push(
                    <Row
                      key={kid.id}
                      row={kid}
                      projectId={projectId}
                      isDateLike={isDateLike}
                      subTab={subTab}
                      subColCount={subCols?.length ?? 0}
                      today={today}
                      bulkEnabled={bulkEnabled}
                      checked={selectedIds?.has(kid.id) ?? false}
                      onToggle={onToggleSelect ? () => onToggleSelect(kid.id) : undefined}
                      onOpen={() => onOpenItem(kid.id)}
                      onOpenStatus={() => onOpenStatus(kid.id)}
                      onOpenAvailability={onOpenAvailability}
                      readOnly={readOnly}
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
