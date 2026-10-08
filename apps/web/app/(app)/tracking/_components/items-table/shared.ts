import type { TrackingItemRow } from "@/lib/pm-types";

// Columns pinned at the left (checkbox through Lister) and the room that must stay for the rest.
export const PIN_COLS = 17;

export const PIN_MIN_SCROLL_PX = 400;

// Q425 adds O/BOOK to the strip the legacy mock established. It swaps the
// right-hand columns like every other entry — one row per item stays Tracking's
// spine — and carries the Create Order button.
export type SubTab =
  | "DATE" | "TO BE ORDERED" | "iTIME" | "HARDWARE" | "SITE MEASURE" | "INVOICE" | "QC" | "O/BOOK";

export const SUB_TABS: SubTab[] = [
  "DATE", "TO BE ORDERED", "iTIME", "HARDWARE", "SITE MEASURE", "INVOICE", "QC", "O/BOOK",
];

export const STAGE_KEYS = [
  "REQ", "SM", "LISTED", "DOWN", "CNC", "EDGED", "PAINTED", "MADE", "DEL", "INST",
] as const;

// SubTabs that render the same 10 stage-date columns as DATE.
export const DATE_LIKE_SUBTABS: ReadonlySet<SubTab> = new Set<SubTab>(["DATE", "TO BE ORDERED"]);

export const SUB_TAB_COLUMNS: Record<Exclude<SubTab, "DATE" | "TO BE ORDERED">, { key: string; label: string }[]> = {
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
  "O/BOOK": [
    { key: "orderno", label: "Order #" },
    { key: "supplier", label: "Supplier" },
    { key: "ostatus", label: "Status" },
    { key: "eta", label: "ETA" },
  ],
};

export type SortKey =
  | "num" | "stage" | "zone" | "level" | "rmNo" | "rmDesc" | "code"
  | "desc" | "status" | "size" | "qty" | "assem" | "lister" | "itemId"
  | `stage:${(typeof STAGE_KEYS)[number]}`;

export interface FilterState {
  stage: string;
  zone: string;
  level: string;
  rmNo: string;
  rmDesc: string;
  code: string;
  status: string;
  lister: string;
}

export const EMPTY_FILTERS: FilterState = {
  stage: "", zone: "", level: "", rmNo: "", rmDesc: "",
  code: "", status: "", lister: "",
};

export function statusClasses(status: string | null): string {
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

export function addDaysISO(iso: string, days: number): string {
  const d = new Date(iso + "T00:00:00Z");
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

export function todayISO(): string {
  return new Date().toISOString().slice(0, 10);
}

export function dateCellColor(dueIso: string | null, doneIso: string | null, todayIso: string): string {
  if (doneIso) return "text-[#3f7d48]";
  if (dueIso && dueIso < todayIso) return "text-[#b4443d] font-semibold";
  if (dueIso && dueIso <= addDaysISO(todayIso, 7)) return "text-[#c48a2e]";
  return "text-h-muted";
}

export function formatAmount(amount: string | null | undefined): string {
  if (amount == null || amount === "") return "—";
  const n = Number(amount);
  if (!Number.isFinite(n)) return "—";
  return n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function uniqStrings(values: (string | null | undefined)[]): string[] {
  const seen = new Set<string>();
  for (const v of values) {
    if (v != null && v !== "") seen.add(v);
  }
  return Array.from(seen).sort();
}

export function sortRows(rows: TrackingItemRow[], key: SortKey, asc: boolean): TrackingItemRow[] {
  const out = [...rows];
  out.sort((a, b) => compareRows(a, b, key));
  return asc ? out : out.reverse();
}

export function compareRows(a: TrackingItemRow, b: TrackingItemRow, key: SortKey): number {
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

export function cmp(a: string | number, b: string | number): number {
  if (a < b) return -1;
  if (a > b) return 1;
  return 0;
}
