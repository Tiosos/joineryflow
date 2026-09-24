"use client";

import { useLayoutEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import type { TrackingItemRow } from "@/lib/pm-types";

export type SubTab =
  | "DATE"
  | "TO BE ORDERED"
  | "iTIME"
  | "HARDWARE"
  | "SITE MEASURE"
  | "INVOICE"
  | "QC";

export const SUB_TABS: SubTab[] = [
  "DATE", "TO BE ORDERED", "iTIME", "HARDWARE", "SITE MEASURE", "INVOICE", "QC",
];

const STAGE_KEYS = [
  "REQ", "SM", "LISTED", "DOWN", "CNC", "EDGED", "PAINTED", "MADE", "DEL", "INST",
] as const;

// SubTabs that render the same 10 stage-date columns as DATE.
const DATE_LIKE_SUBTABS: ReadonlySet<SubTab> = new Set<SubTab>(["DATE", "TO BE ORDERED"]);

const SUB_TAB_COLUMNS: Record<Exclude<SubTab, "DATE" | "TO BE ORDERED">, { key: string; label: string }[]> = {
  iTIME: [
    { key: "hours", label: "Hours" },
    { key: "operator", label: "Operator" },
    { key: "start", label: "Start" },
    { key: "end", label: "End" },
  ],
  HARDWARE: [
    { key: "lines", label: "Lines" },
    { key: "ready", label: "Ready" },
    { key: "blocked", label: "Blocked" },
  ],
  "SITE MEASURE": [
    { key: "reqdate", label: "REQ Date" },
    { key: "smdate", label: "SM Date" },
    { key: "by", label: "By" },
    { key: "notes", label: "Notes" },
    { key: "snapshot", label: "Snapshot" },
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
  cutlistQuery: string;
  freeQuery: string;
  onOpenItem: (id: number) => void;
  onOpenStatus: (id: number) => void;
  // Bulk selection — optional; pass nothing to disable (List tab reuse).
  selectedIds?: Set<number>;
  onToggleSelect?: (id: number) => void;
  onToggleSelectVisible?: (ids: number[], select: boolean) => void;
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
  cutlistQuery,
  freeQuery,
  onOpenItem,
  onOpenStatus,
  selectedIds,
  onToggleSelect,
  onToggleSelectVisible,
}: Props) {
  const bulkEnabled = Boolean(selectedIds && onToggleSelect && onToggleSelectVisible);
  const [filters, setFilters] = useState<FilterState>(EMPTY_FILTERS);
  const [sortKey, setSortKey] = useState<SortKey>("num");
  const [sortAsc, setSortAsc] = useState(true);
  const [subTab, setSubTab] = useState<SubTab>("DATE");
  const containerRef = useRef<HTMLDivElement>(null);
  const savedScrollLeft = useRef(0);

  useLayoutEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollLeft = savedScrollLeft.current;
    }
  }, [subTab]);

  const levels  = useMemo(() => uniqStrings(items.map((i) => i.level)), [items]);
  const rooms   = useMemo(() => uniqStrings(items.map((i) => i.room_no)), [items]);
  const descs   = useMemo(() => uniqStrings(items.map((i) => i.room_desc)), [items]);
  const codes   = useMemo(() => uniqStrings(items.map((i) => i.code)), [items]);
  const listers = useMemo(() => uniqStrings(items.map((i) => i.cutlist_owner_name)), [items]);

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
      if (cq && !(it.item_number != null && String(it.item_number).includes(cq))) return false;
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

  function clearFilters() {
    setFilters(EMPTY_FILTERS);
    setSortKey("num");
    setSortAsc(true);
  }

  const isDateLike = DATE_LIKE_SUBTABS.has(subTab);
  const subCols = isDateLike ? null : SUB_TAB_COLUMNS[subTab as Exclude<SubTab, "DATE" | "TO BE ORDERED">];
  const today = todayISO();

  // For TO BE ORDERED, filter to items with at least one blocked hardware line.
  const subtabFiltered = useMemo(
    () => (subTab === "TO BE ORDERED" ? items.filter((it) => it.availability.blocked > 0) : items),
    [items, subTab],
  );

  return (
    <div
      ref={containerRef}
      className="overflow-x-auto rounded-lg border border-h-line bg-h-surface"
      onScroll={() => { savedScrollLeft.current = containerRef.current?.scrollLeft ?? 0; }}
    >
      <table className="w-full text-xs">
        <thead className="bg-h-bg text-h-muted">
          <tr>
            <td colSpan={17} />
            <th
              colSpan={(isDateLike ? 10 : subCols!.length) + 1}
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
            </th>
          </tr>
          <tr>
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
            {isDateLike ? (
              <>
                <td /><td /><td /><td /><td /><td /><td /><td /><td /><td />
              </>
            ) : (
              subCols!.map((c) => <td key={c.key} />)
            )}
            <td />
          </tr>
        </thead>
        <tbody>
          {sorted.length === 0 ? (
            <tr>
              <td colSpan={28} className="px-4 py-8 text-center text-h-muted">
                No items match your filters.
              </td>
            </tr>
          ) : (
            sorted.map((it) => (
              <Row
                key={it.id}
                row={it}
                subTab={subTab}
                isDateLike={isDateLike}
                subColCount={subCols?.length ?? 0}
                today={today}
                bulkEnabled={bulkEnabled}
                checked={selectedIds?.has(it.id) ?? false}
                onToggle={onToggleSelect ? () => onToggleSelect(it.id) : undefined}
                onOpen={() => onOpenItem(it.id)}
                onOpenStatus={() => onOpenStatus(it.id)}
              />
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

function Row({
  row,
  subTab,
  isDateLike,
  subColCount,
  today,
  bulkEnabled,
  checked,
  onToggle,
  onOpen,
  onOpenStatus,
}: {
  row: TrackingItemRow;
  subTab: SubTab;
  isDateLike: boolean;
  subColCount: number;
  today: string;
  bulkEnabled: boolean;
  checked: boolean;
  onToggle?: () => void;
  onOpen: () => void;
  onOpenStatus: () => void;
}) {
  return (
    <tr className="border-t border-h-line hover:bg-h-bg">
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
        <button
          type="button"
          onClick={onOpen}
          className="rounded p-0.5 text-h-muted transition hover:bg-h-bg hover:text-h-accent"
          title="Open item details"
          aria-label="Open item details"
        >
          ▶
        </button>
      </td>
      <td className="px-2 py-1 font-mono text-h-ink">
        <Link href={`/items/${row.id}`} className="hover:text-h-accent hover:underline">
          {row.item_number ?? row.id}
        </Link>
      </td>
      <td className="px-2 py-1 text-h-ink">
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
      <td className="px-2 py-1 text-h-ink">{row.description ?? "—"}</td>
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
      <td className="px-2 py-1 text-right font-mono tabular-nums text-h-ink">
        {formatAmount(row.total_amount)}
      </td>
      <td className="px-2 py-1 text-right font-mono tabular-nums text-h-ink">{row.qty ?? "—"}</td>
      <td className="px-2 py-1 text-h-muted" title="Contractor">{row.contractor_name ?? "—"}</td>
      <td className="px-2 py-1 text-h-muted">{row.cutlist_owner_name ?? "—"}</td>
      {isDateLike ? (
        STAGE_KEYS.map((sk) => (
          <StageCell key={sk} stage={row.stages[sk]} today={today} />
        ))
      ) : (
        <SubTabCells row={row} subTab={subTab} subColCount={subColCount} />
      )}
      <td className="px-2 py-1 font-mono text-[10px] text-h-muted">{row.id}</td>
    </tr>
  );
}


function JidCell({ code, color }: { code: string | null | undefined; color: string | null | undefined }) {
  if (!code && !color) return <span className="text-h-muted">—</span>;
  return (
    <span className="inline-flex items-center gap-1.5">
      {color ? (
        <span
          className="inline-block h-3 w-3 rounded-sm border border-h-line"
          style={{ backgroundColor: color }}
          aria-hidden="true"
          title={`JID color ${color}`}
        />
      ) : null}
      <span className="font-mono text-[10px]">{code ?? "—"}</span>
    </span>
  );
}

function VarBoqPill({ value }: { value: "BOQ" | "VAR" }) {
  const isVar = value === "VAR";
  const cls = isVar
    ? "bg-[#f3e0d6] text-[#a84f31]"
    : "bg-h-bg text-h-muted border border-h-line";
  return (
    <span className={`inline-block rounded-full px-1.5 py-0.5 text-[9px] font-semibold ${cls}`}>
      {value}
    </span>
  );
}

function formatAmount(amount: string | null | undefined): string {
  if (amount == null || amount === "") return "—";
  const n = Number(amount);
  if (!Number.isFinite(n)) return "—";
  return n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}


// SubTab data cells for non-date subtabs.  INVOICE + iTIME + QC stay as `—`
// stubs (Invoice ships in #13; iTIME / QC are out of scope for #10).
function SubTabCells({
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
    case "num":    return cmp(a.item_number ?? 0, b.item_number ?? 0);
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
    case "itemId": return cmp(a.id, b.id);
  }
}

function cmp(a: string | number, b: string | number): number {
  if (a < b) return -1;
  if (a > b) return 1;
  return 0;
}
