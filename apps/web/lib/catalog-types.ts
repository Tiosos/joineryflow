export type CatalogTable =
  | "board_materials"
  | "hardware_materials"
  | "custom_made"
  | "benchtop_materials"
  | "appliances"
  | "equipment_hire"
  | "edging_materials"
  | "glass_materials";

export type CatalogSlug =
  | "board-materials"
  | "hardware-materials"
  | "custom-made"
  | "benchtop-materials"
  | "appliances"
  | "equipment-hire"
  | "edging-materials"
  | "glass-materials";

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
  /** Starts an order line's price (Generate Orders, add from catalog). The API sends it as a JSON number. */
  unit_cost: number | null;
  /** The old system's product type (Glass, Supplies...), free text; the tab is separate. */
  product_type: string | null;
  archived_at: string | null;
  archived_by: number | null;
  grain_locked?: boolean; // board + benchtop only (migration 0024)
  // Board only (migration 0068): the old Orders screen's board fields, plain text.
  colour?: string | null;
  substrate?: string | null;
  finish?: string | null;
  sided?: string | null;
  grain?: string | null;
  rating?: string | null;
  hmr?: string | null;
  product_website?: string | null;
  has_image?: boolean; // board + edging
  // Edging only (migration 0069). Roll length in metres, width and thickness in mm: JSON numbers.
  edge_type?: string | null;
  um?: string | null;
  roll_length_m?: number | null;
  edge_width_mm?: number | null;
  edge_thickness_mm?: number | null;
  glued?: boolean;
  // Glass only (migration 0070). Sizes in mm: JSON numbers. Glass type and power point are free text.
  edge_finish?: string | null;
  glass_type?: string | null;
  power_point?: string | null;
  length_mm?: number | null;
  width_mm?: number | null;
  thickness_mm?: number | null;
  shaped?: boolean; // glass + benchtop
  // brand + hardware_type: Hardware only (0072); um and product_website are shared with other types above.
  brand?: string | null;
  hardware_type?: string | null;
  // Benchtop only (migration 0071). Sizes in mm (thickness_mm is the bench thickness): JSON numbers.
  underside?: string | null;
  edge_details?: string | null;
  laminate_supplier?: string | null;
  laminate_code?: string | null;
  bench_length_mm?: number | null;
  bench_width_mm?: number | null;
  pieces?: number | null;
  joins?: number | null;
  cable_entry?: number | null;
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

/** `GET /catalog/product-types`: the tabs of the Catalog screen. */
export interface ProductTypesResp {
  types: { product_type: string; count: number }[];
  /** Items with no product type. */
  untyped: number;
}

/** `GET /catalog/by-type`: one type's items, grouped by the table each lives in. */
export interface ByTypeResp {
  product_type: string | null;
  groups: { type: "board" | "hardware" | "custom_made" | "benchtop" | "appliance" | "hire"; rows: CatalogRow[] }[];
}
