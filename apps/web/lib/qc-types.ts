// Mirrors apps/api/app/qc/schemas.py — wire format for QC (Q515-517).

export type DefectStatus = "open" | "resolved";
export type ReworkKind = "internal" | "full";
export type ReworkStatus = "open" | "closed";

export interface DefectOut {
  defect_id: number;
  item_id: number;
  stage_key: string | null;
  description: string;
  status: DefectStatus;
  resolved_note: string | null;
  resolved_by: number | null;
  resolved_by_name: string | null;
  resolved_at: string | null;
  created_by: number;
  created_by_name: string | null;
  created_at: string;
  updated_at: string;
}

export interface ChecklistItemOut {
  checklist_item_id: number;
  item_id: number;
  label: string;
  is_checked: boolean;
  checked_by: number | null;
  checked_by_name: string | null;
  checked_at: string | null;
  sort_order: number;
  created_by: number;
  created_at: string;
}

export interface ReworkOut {
  rework_id: number;
  item_id: number;
  kind: ReworkKind;
  cause: string;
  scope: string;
  responsibility: string | null;
  /** Decimal, arrives as a JSON string (the orders-types.ts / material-take-types.ts lesson). */
  cost: string | null;
  status: ReworkStatus;
  closed_note: string | null;
  closed_by: number | null;
  closed_by_name: string | null;
  closed_at: string | null;
  created_by: number;
  created_by_name: string | null;
  created_at: string;
  updated_at: string;
}

// ---- QC Dashboard (Plan V1 §4.2) — GET /qc/dashboard ------------------------
// Money arrives as a JSON string (Pydantic Decimal), never a number.

export interface DashboardStageCount {
  stage_key: string | null; // null = raised without a stage
  label: string;
  open: number;
}

export interface DashboardDefectProject {
  project_id: number;
  project_code: string;
  project_name: string;
  open: number;
  oldest_open_at: string;
  by_stage: DashboardStageCount[];
}

export interface DashboardReworkProject {
  project_id: number;
  project_code: string;
  project_name: string;
  internal: number;
  full: number;
  cost_total: string;
  cost_missing: number;
  oldest_open_at: string;
}

export interface DashboardItem {
  item_id: number;
  num: number;
  item_code: string | null;
  description: string | null;
  project_id: number;
  project_code: string;
  open_defects: number;
  open_rework: number;
  oldest_open_at: string;
}

export interface QcDashboard {
  scope: {
    items_in_scope: number;
    open_defects_out_of_scope: number;
    open_rework_out_of_scope: number;
  };
  defects_open: number;
  defects_by_stage: DashboardStageCount[];
  defects_by_project: DashboardDefectProject[];
  rework_open: number;
  rework_cost_total: string;
  rework_cost_missing: number;
  rework_by_project: DashboardReworkProject[];
  items: DashboardItem[];
}

export interface QcDashboardFilters {
  projectId: number | null;
  dateFrom: string; // "" = unbounded
  dateTo: string;
}
