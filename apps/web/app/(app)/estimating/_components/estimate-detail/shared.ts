import type { EstimateStatus, GenerateOrdersResult, HardwareMaterialType, PartMaterialType, StageKey } from "@/lib/estimating-types";
import { TENDER_STAGE_LABELS, TENDER_STAGE_ORDER } from "@/lib/estimating-types";

export function nextStageLabel(status: EstimateStatus | undefined): string | null {
  if (!status) return null;
  const idx = (TENDER_STAGE_ORDER as readonly string[]).indexOf(status);
  if (idx === -1 || idx === TENDER_STAGE_ORDER.length - 1) return null;
  return TENDER_STAGE_LABELS[TENDER_STAGE_ORDER[idx + 1]];
}

export interface CatalogRow {
  material_id: number;
  sku: string;
  description: string;
  default_supplier?: string | null;
}

export type MaterialKind = PartMaterialType | HardwareMaterialType;

export type CatalogMap = Record<MaterialKind, CatalogRow[]>;

export const PART_KINDS: PartMaterialType[] = ["BOARD", "CUSTOM", "BENCHTOP"];
export const HW_KINDS: HardwareMaterialType[] = ["HARDWARE", "APPLIANCE"];
export const ALL_KINDS: MaterialKind[] = [...PART_KINDS, ...HW_KINDS];

export const KIND_LABEL: Record<MaterialKind, string> = {
  BOARD: "Board",
  CUSTOM: "Custom",
  BENCHTOP: "Benchtop",
  HARDWARE: "Hardware",
  APPLIANCE: "Appliance",
};

export const KIND_SLUG: Record<MaterialKind, string> = {
  BOARD: "board-materials",
  CUSTOM: "custom-made",
  BENCHTOP: "benchtop-materials",
  HARDWARE: "hardware-materials",
  APPLIANCE: "appliances",
};


export const STAGE_KEYS: StageKey[] = [
  "REQ", "SM", "LISTED", "DOWN", "CNC", "EDGED",
  "PAINTED", "MADE", "DEL", "INST",
];

// The 10 pre-SUBMITTED pipeline stages (Q487/488) share one "in progress"
// look; SUBMITTED and the three terminal outcomes each get their own.
export const STATUS_COLOURS: Record<EstimateStatus, string> = {
  OPPORTUNITY: "bg-gray-200 text-gray-700",
  INITIAL_REVIEW: "bg-gray-200 text-gray-700",
  GO_NO_GO: "bg-gray-200 text-gray-700",
  INFO_REQUESTED: "bg-gray-200 text-gray-700",
  DOCS_RECEIVED: "bg-gray-200 text-gray-700",
  ESTIMATING: "bg-gray-200 text-gray-700",
  SUPPLIER_PRICING: "bg-gray-200 text-gray-700",
  INTERNAL_REVIEW: "bg-gray-200 text-gray-700",
  QUOTE_PREPARED: "bg-gray-200 text-gray-700",
  MGMT_APPROVAL: "bg-gray-200 text-gray-700",
  SUBMITTED: "bg-blue-100 text-blue-800",
  WON: "bg-green-100 text-green-800",
  LOST: "bg-red-100 text-red-800",
  WITHDRAWN: "bg-gray-100 text-gray-600",
};

export function fmtMoney(s: string | null | undefined): string {
  if (!s) return "$0.00";
  const n = parseFloat(s);
  if (!Number.isFinite(n)) return "$0.00";
  return `$${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function isPartKind(k: MaterialKind): k is PartMaterialType {
  return k === "BOARD" || k === "CUSTOM" || k === "BENCHTOP";
}

export function summariseGenerateResult(result: GenerateOrdersResult): string {
  const orderWord = result.orders_created === 1 ? "order" : "orders";
  const lineWord = result.lines_created === 1 ? "line" : "lines";
  let msg = `${result.orders_created} ${orderWord} generated (${result.lines_created} ${lineWord}).`;
  const left = result.uncovered_line_ids?.length ?? 0;
  if (left > 0) {
    const n = result.unassigned.length;
    msg += ` ${n} ${n === 1 ? "material was" : "materials were"} not ordered because`
      + ` ${n === 1 ? "it has" : "they have"} no default supplier, so ${left}`
      + ` ${left === 1 ? "line is" : "lines are"} still not fully ordered`
      + " — link a supplier (or mark the material ordered by hand) and generate again.";
  }
  return msg;
}

export type CallApiFn = (
  method: string,
  url: string,
  body?: unknown,
) => Promise<{ ok: boolean; data?: unknown; error?: string }>;

export interface PickerPayload {
  kind: MaterialKind;
  material_id: number;
  qty: number;
  len_mm?: number | null;
  wid_mm?: number | null;
  paint_instruction: "NONE" | "DOUBLE_SIDE" | "SINGLE_SIDE" | "EDGE_ONLY";
  comment?: string;
}
