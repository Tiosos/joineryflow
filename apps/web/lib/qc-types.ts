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
