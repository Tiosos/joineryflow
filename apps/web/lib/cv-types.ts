// Mirrors apps/api/app/cv/schemas.py — wire format for the CV import wizard (#7b).

export type CatalogTable =
  | "board_materials"
  | "hardware_materials"
  | "custom_made"
  | "benchtop_materials"
  | "appliances"
  | "equipment_hire";

export type SimpleCatalogTable =
  | "board_materials"
  | "hardware_materials"
  | "custom_made"
  | "benchtop_materials"
  | "appliances";

export type ResolutionKind = "mapped" | "synonym_match" | "unknown";

export interface CvRowResolution {
  kind: ResolutionKind;
  target_table?: CatalogTable | null;
  target_material_id?: number | null;
  target_description?: string | null;
  hint?: string | null;
}

export interface CvRowError {
  row_index: number;
  code: string;
  field: string | null;
  value: string | null;
  message: string;
}

export interface CvParsedPart {
  row_index: number;
  part_name: string;
  qty: number;
  len_mm: number;
  wid_mm: number;
  thickness_mm: number | null;
  cv_code: string;
  edge: string | null;
  colour: string | null;
  notes: string | null;
  resolution: CvRowResolution;
}

export interface CvParsedModule {
  module_no: number;
  parts: CvParsedPart[];
}

export interface CvUnknownCode {
  cv_code: string;
  occurrences: number;
  suggested_table: CatalogTable | null;
}

export interface CvPreviewSummary {
  row_count: number;
  mapped: number;
  synonym: number;
  unknown: number;
  invalid: number;
}

export interface CvPreviewOut {
  run_id: number;
  summary: CvPreviewSummary;
  modules: CvParsedModule[];
  unknown_codes: CvUnknownCode[];
  errors: CvRowError[];
}

export type CvUseExistingResolution = {
  action: "use_existing";
  cv_code: string;
  target_table: CatalogTable;
  target_material_id: number;
};

export type CvCreateNewResolution = {
  action: "create_new";
  cv_code: string;
  target_table: SimpleCatalogTable;
  sku: string;
  description: string;
  default_supplier?: string | null;
  default_lead_time_days?: number | null;
};

export type CvSkipResolution = {
  action: "skip";
  cv_code: string;
};

export type CvCommitResolution =
  | CvUseExistingResolution
  | CvCreateNewResolution
  | CvSkipResolution;

export interface CvCommitIn {
  resolutions: CvCommitResolution[];
  replace: boolean;
}

export interface CvCommitOut {
  run_id: number;
  modules_created: number;
  parts_created: number;
  mappings_created: number;
  catalog_rows_created: number;
  replaced_module_ids: number[];
}

export interface CvImportRunOut {
  cv_import_run_id: number;
  project_id: number;
  item_id: number;
  source_filename: string;
  sha256: string;
  row_count: number;
  status: "preview" | "committed" | "failed";
  started_at: string;
  completed_at: string | null;
  created_by: number;
}
