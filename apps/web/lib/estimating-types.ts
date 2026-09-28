// The 12-stage tender lifecycle (Plan V1 §5, Q487/488/548) — 11 sequential
// stages then a 12th, terminal position resolving to WON / LOST / WITHDRAWN.
// Replaces the old 6-value draft/sent/accepted/rejected/expired/withdrawn
// enum; `expired` no longer exists on its own (Q548 maps a lapsed quote
// onto LOST).
export const TENDER_STAGE_ORDER = [
  "OPPORTUNITY", "INITIAL_REVIEW", "GO_NO_GO", "INFO_REQUESTED",
  "DOCS_RECEIVED", "ESTIMATING", "SUPPLIER_PRICING", "INTERNAL_REVIEW",
  "QUOTE_PREPARED", "MGMT_APPROVAL", "SUBMITTED",
] as const;

export type EstimateStatus =
  | (typeof TENDER_STAGE_ORDER)[number]
  | "WON"
  | "LOST"
  | "WITHDRAWN";

export const TENDER_STAGE_LABELS: Record<EstimateStatus, string> = {
  OPPORTUNITY: "Opportunity",
  INITIAL_REVIEW: "Initial Review",
  GO_NO_GO: "Go / No-Go",
  INFO_REQUESTED: "Information Requested",
  DOCS_RECEIVED: "Documents Received",
  ESTIMATING: "Estimating",
  SUPPLIER_PRICING: "Supplier Pricing",
  INTERNAL_REVIEW: "Internal Review",
  QUOTE_PREPARED: "Quote Prepared",
  MGMT_APPROVAL: "Management Approval",
  SUBMITTED: "Submitted",
  WON: "Won",
  LOST: "Lost",
  WITHDRAWN: "Withdrawn",
};

export type PartMaterialType = "BOARD" | "CUSTOM" | "BENCHTOP";
export type HardwareMaterialType = "HARDWARE" | "APPLIANCE";
export type StageKey =
  | "REQ" | "SM" | "LISTED" | "DOWN" | "CNC" | "EDGED"
  | "PAINTED" | "MADE" | "DEL" | "INST";

export interface Customer {
  customer_id: number;
  name: string;
  email?: string | null;
  phone?: string | null;
  billing_address?: string | null;
  abn?: string | null;
  notes?: string | null;
  archived_at?: string | null;
  created_at: string;
}

export interface EstimateSummary {
  estimate_id: number;
  estimate_no: string;
  title: string;
  site_address?: string | null;
  customer_id: number;
  customer_name: string;
  current_revision_id: number | null;
  current_rev_no: number | null;
  current_status: EstimateStatus | null;
  current_total_inc_gst: string | null;
  converted_project_id: number | null;
  created_at: string;
  updated_at: string;
}

export interface LinePart {
  part_id: number;
  material_type: PartMaterialType;
  material_id?: number | null;
  sku_snapshot?: string | null;
  description_snapshot?: string | null;
  supplier_snapshot?: string | null;
  qty: string;
  len_mm?: number | null;
  wid_mm?: number | null;
  cost_per_unit_snapshot: string;
  cost_extended: string;
  paint_instruction: "NONE" | "DOUBLE_SIDE" | "SINGLE_SIDE" | "EDGE_ONLY";
  comment?: string | null;
}

export interface LineHardware {
  hw_id: number;
  material_type: HardwareMaterialType;
  material_id?: number | null;
  sku_snapshot?: string | null;
  description_snapshot?: string | null;
  supplier_snapshot?: string | null;
  qty: string;
  cost_per_unit_snapshot: string;
  cost_extended: string;
  comment?: string | null;
}

export interface LineLabour {
  labour_id: number;
  stage_key: StageKey;
  hours: string;
  rate_snapshot: string;
  cost_extended: string;
}

export interface Line {
  line_id: number;
  seq: number;
  description: string;
  qty: string;
  unit: string;
  has_breakdown: boolean;
  material_cost: string;
  labour_cost: string;
  total_cost: string;
  unit_sell_override: string | null;
  unit_sell: string;
  total_sell: string;
  notes?: string | null;
  parts: LinePart[];
  hardware: LineHardware[];
  labour: LineLabour[];
}

export interface Revision {
  revision_id: number;
  estimate_id: number;
  rev_no: number;
  status: EstimateStatus;
  markup_pct: string;
  gst_pct: string;
  terms_text?: string | null;
  workspace_stage_rates_snapshot?: Record<string, number> | null;
  subtotal_cost: string;
  subtotal_sell: string;
  total_inc_gst: string;
  gst_amount: string;
  sent_at?: string | null;
  locked_at?: string | null;
  accepted_at?: string | null;
  rejected_at?: string | null;
  expires_at?: string | null;
  lost_reason?: string | null;
  converted_project_id?: number | null;
  orders_generated_at?: string | null;
  created_at: string;
  lines: Line[];
}

export interface EstimateDetail {
  estimate_id: number;
  estimate_no: string;
  title: string;
  site_address?: string | null;
  customer: Customer;
  current_revision_id: number | null;
  revisions: Revision[];
  created_at: string;
  updated_at: string;
}

export interface LabourRate {
  stage_key: StageKey;
  hourly_rate: string;
  effective_from: string;
  updated_at: string;
}

export interface HandoverPreviewLine {
  line_id: number;
  seq: number;
  description: string;
  qty: string;
  has_breakdown: boolean;
  total_sell: string;
}

export interface HandoverPreview {
  revision_id: number;
  status: EstimateStatus;
  already_converted_project_id: number | null;
  proposed_contract_value: string;
  lines: HandoverPreviewLine[];
}

export interface ConvertResult {
  project_id: number;
  project_code: string;
  items_created: number;
  parts_created: number;
  hardware_lines_created: number;
  project_hardware_catalog_added: number;
  contract_value: string;
}

export interface OrderPreviewLine {
  material_type: PartMaterialType | HardwareMaterialType;
  material_id: number;
  sku?: string | null;
  description?: string | null;
  qty: string;
  unit: string;
  unit_cost: string;
}

export interface OrderPreviewGroup {
  supplier_id: number;
  supplier_name?: string | null;
  category: string;
  lines: OrderPreviewLine[];
}

export interface OrderPreview {
  revision_id: number;
  status: EstimateStatus;
  converted_project_id: number | null;
  orders_generated_at?: string | null;
  groups: OrderPreviewGroup[];
  unassigned: OrderPreviewLine[];
}

export interface GenerateOrdersResult {
  orders_created: number;
  lines_created: number;
  po_ids: number[];
  unassigned: OrderPreviewLine[];
}
