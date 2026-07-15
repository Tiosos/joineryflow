// Mirrors apps/api/app/cut_floor/schemas.py — wire format for #7c.

export type CutScheduleStatus =
  | "planned"
  | "running"
  | "done"
  | "cancelled";

export interface PartSlotOut {
  id: number;
  x: number;
  y: number;
  w: number;
  h: number;
  label: string | null;
  part_id: number | null;
  is_foreign: boolean;
}

export interface CutSheetOut {
  id: number;
  sheet_no: number;
  material_sku: string;
  slots: PartSlotOut[];
}

export interface CutPlanSummary {
  id: number;
  name: string;
  project_id: number;
  notes: string | null;
  created_by: number | null;
  created_at: string;
  sheet_count: number;
  slot_count: number;
}

export interface CutPlanOut {
  id: number;
  name: string;
  project_id: number;
  notes: string | null;
  created_by: number | null;
  created_at: string;
  sheets: CutSheetOut[];
}

export interface ItemCutPlanOut {
  plan: CutPlanSummary | null;
  sheets: CutSheetOut[];
}

export interface PartSlotIn {
  x: number;
  y: number;
  w: number;
  h: number;
  label?: string | null;
  part_id?: number | null;
}

export interface CutSheetIn {
  sheet_no: number;
  material_sku: string;
  slots: PartSlotIn[];
}

export interface CutPlanIn {
  name: string;
  notes?: string | null;
  sheets: CutSheetIn[];
}

export interface CutScheduleOut {
  id: number;
  cut_plan_id: number;
  cut_plan_name: string | null;
  project_id: number | null;
  scheduled_for: string | null;
  status: CutScheduleStatus;
  priority: number;
  assigned_to: number | null;
  assigned_to_full_name: string | null;
  created_at: string;
  updated_at: string;
  created_by: number | null;
}

export interface CutScheduleIn {
  cut_plan_id: number;
  scheduled_for: string;
  assigned_to?: number | null;
}

export interface CutSchedulePatchIn {
  scheduled_for?: string | null;
  assigned_to?: number | null;
  status?: CutScheduleStatus | null;
  priority?: number | null;
}

export interface ReorderIn {
  scheduled_for: string;
  ordered_ids: number[];
}

// --- Optimiser (sub-project #9 stub) ---------------------------------------

export interface OptimiseIn {
  name: string;
  material_sku: string;
  sheet_len_mm: number;
  sheet_wid_mm: number;
  kerf_mm?: number;
  include_only_item_ids?: number[] | null;
}

export interface OptimiseSkip {
  label: string;
  reason: string;
  part_id: number | null;
}

export interface OptimiseSummary {
  total_parts: number;
  placed: number;
  skipped: number;
  skipped_reasons: OptimiseSkip[];
  sheets_used: number;
  utilization_pct: number;
}

export interface OptimiseOut {
  proposal: CutPlanIn;
  summary: OptimiseSummary;
}
