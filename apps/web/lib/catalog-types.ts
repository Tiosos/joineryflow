export type CatalogTable =
  | "board_materials"
  | "hardware_materials"
  | "custom_made"
  | "benchtop_materials"
  | "appliances"
  | "equipment_hire";

export type CatalogSlug =
  | "board-materials"
  | "hardware-materials"
  | "custom-made"
  | "benchtop-materials"
  | "appliances"
  | "equipment-hire";

export interface CatalogRow {
  type: string;
  material_id?: number;
  hire_id?: number;
  workspace_id: number;
  sku: string;
  description: string;
  code?: string | null;
  internal_ref?: string | null;
  slab_id?: string | null;
  model_number?: string | null;
  contract_ref?: string | null;
  project_id?: number | null;
  synonyms: string[];
  default_supplier: string | null;
  /** The real supplier link (`vendors`); Generate Orders reads this, not the text. */
  default_supplier_id: number | null;
  default_supplier_name: string | null;
  default_lead_time_days: number | null;
  archived_at: string | null;
  archived_by: number | null;
  grain_locked?: boolean; // board + benchtop only (migration 0024)
}

/** A supplier as the picker needs it (`GET /suppliers`). */
export interface SupplierOption {
  vendor_id: number;
  name: string;
  status: string;
}

export interface CatalogListResp {
  type: string;
  rows: CatalogRow[];
}

export interface BulkImportResp {
  created: number;
  errors: { row_index: number; error: string }[];
  /** Created rows whose `default_supplier` matched exactly one supplier. */
  linked: number;
  /** Created rows that named a supplier but were left unlinked. */
  unlinked: { row_index: number; default_supplier: string; reason: string }[];
}

export interface CvMapping {
  cv_material_mapping_id: number;
  workspace_id: number;
  cv_code: string;
  target_material_table: CatalogTable;
  target_material_id: number;
  target_description: string | null;
  notes: string | null;
  created_by: number;
  created_at: string;
  updated_at: string;
}

export interface CvMappingListResp {
  rows: CvMapping[];
  total: number;
}
