// Mirrors apps/api/app/shop_floor/schemas.py — wire format for #8.

export type ShopFloorStage =
  | "DOWN"
  | "CNC"
  | "EDGED"
  | "PAINTED"
  | "MADE";

export type AssignmentStatus =
  | "assigned"
  | "in_progress"
  | "done"
  | "cancelled";

export interface AssignmentOut {
  assignment_id: number;
  item_id: number;
  stage_key: ShopFloorStage;
  worker_id: number;
  worker_name: string | null;
  status: AssignmentStatus;
  note: string | null;
  assigned_by: number;
  assigned_at: string;
  started_at: string | null;
  ended_at: string | null;
  cancelled_at: string | null;
}

export interface WorkerOut {
  id: number;
  full_name: string;
  email: string;
  is_shop_worker: boolean;
}

export interface BoardCard {
  item_id: number;
  item_number: number;
  code: string | null;
  description: string | null;
  painting_req: boolean;
  paint_after_assembly: boolean;
  next_stage_key: ShopFloorStage;
  assignment: AssignmentOut | null;
}

export interface BoardOut {
  project_id: number;
  project_code: string;
  columns: Record<ShopFloorStage, BoardCard[]>;
}

export interface StationCard {
  assignment_id: number;
  item_id: number;
  item_number: number;
  code: string | null;
  description: string | null;
  room_no: string | null;
  room_desc: string | null;
  project_code: string;
  stage_key: ShopFloorStage;
  status: AssignmentStatus;
  assigned_at: string;
  started_at: string | null;
  note: string | null;
}

export interface StationOut {
  worker_id: number;
  worker_name: string;
  cards: StationCard[];
}

export interface RecentCompletionOut {
  log_id: number;
  item_id: number;
  item_number: number;
  stage_key: ShopFloorStage;
  completed_at: string;
  note: string | null;
}

export interface CompleteOut {
  log_id: number;
  assignment_id: number;
  lifecycle_advanced: boolean;
  next_stage_key: ShopFloorStage | null;
}

export interface UndoOut {
  log_id: number;
  assignment_id: number;
  item_id: number;
  stage_key: ShopFloorStage;
}

export interface AssignIn {
  stage_key: ShopFloorStage;
  worker_id: number;
  note?: string | null;
}

export interface PatchAssignmentIn {
  worker_id?: number | null;
  note?: string | null;
}

export interface CompleteIn {
  note?: string | null;
}

export interface UserAdminOut {
  id: number;
  email: string;
  full_name: string;
  auth_role: string;
  jtbd_role: string | null;
  is_active: boolean;
  is_shop_worker: boolean;
}
