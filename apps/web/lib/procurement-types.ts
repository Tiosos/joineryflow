export type MaterialType   = "BOARD"|"HARDWARE"|"CUSTOM"|"BENCHTOP"|"APPLIANCE"|"HIRE";
export type BatchStatus    = "OPEN"|"IN_TRANSIT"|"DELIVERED"|"CANCELLED";
export type MaterialStatus = "OK"|"SHORT"|"OVERDUE";

// numeric() comes back from Pydantic as a string
export interface MaterialRow {
  material_type: MaterialType;
  material_id: number;
  name: string;
  sku: string | null;
  qty_demand: string;
  qty_on_order: string;
  qty_received: string;
  qty_allocated: string;
  shortfall: string;
  earliest_eta: string | null;
  status: MaterialStatus;
}

export interface ProjectMaterialsOut {
  project_id: number;
  rows: MaterialRow[];
}

export interface BatchOut {
  batch_id: number;
  project_id: number;
  material_type: MaterialType;
  material_id: number;
  supplier: string | null;
  po_ref: string | null;
  qty_ordered: string;
  qty_received: string;
  cost_per_unit: string | null;
  ordered_date: string | null;
  eta_date: string | null;
  received_date: string | null;
  cancelled_at: string | null;
  notes: string | null;
  status: BatchStatus;
  qty_allocated: string;
}

export interface BatchListOut { batches: BatchOut[]; }

export interface AllocationOut {
  allocation_id: number;
  batch_id: number;
  item_hardware_line_id: number;
  qty_allocated: string;
  created_at: string;
  item_code: string | null;
  item_description: string | null;
}

export interface AllocationListOut {
  allocations: AllocationOut[];
  qty_received: string;
  qty_allocated_total: string;
  qty_remaining: string;
}

export interface AvailabilityLine {
  line_id: number;
  seq: number | null;
  catalog_id: number;
  material_type: MaterialType;
  material_id: number;
  qty_needed: string;
  qty_received: string;
  qty_on_order: string;
  qty_allocated_to_line: string;
  earliest_eta: string | null;
  // PM Workbench-era fields preserved by Task 6:
  status: "ready" | "ordered" | "none";
  eta: string | null;
  batch_id: number | null;
}

export interface AvailabilityOut {
  item_id: number;
  ready: number;
  blocked: number;
  lines: AvailabilityLine[];
}

export interface QueueRow {
  batch_id: number;
  project_id: number;
  project_code: string;
  project_name: string;
  supplier: string | null;
  po_ref: string | null;
  material_type: string;
  material_id: number;
  material_name: string | null;
  qty_ordered: string;
  qty_received: string;
  eta_date: string | null;
  status: BatchStatus;
}

export interface QueueOut { rows: QueueRow[]; }
