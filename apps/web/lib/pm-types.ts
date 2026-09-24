// PM Workbench API types — mirrors Python Pydantic schemas in
// apps/api/app/{projects,items,parts,hardware_lines,home}/schemas.py
//
// Date fields are ISO 8601 strings (YYYY-MM-DD).
// Datetime fields are ISO 8601 timestamps with UTC offset.
// No runtime validation — the FastAPI layer is the source of truth.

// =============================================================================
// Projects
// Source: apps/api/app/projects/schemas.py
// =============================================================================

export interface ProjectOut {
  id: number;
  project_code: string;
  name: string;
  pm_id: number | null;
  pm_name: string | null;
  status: string | null;
  item_count: number;
  total_value: number | null;
  install_start: string | null; // date → ISO 8601 YYYY-MM-DD
  is_favourite: boolean;
  created_at: string; // datetime → ISO 8601 timestamp
  // Q408's Project Details tiles (C5) — existing columns, newly served.
  created_by: string | null;
  tg_solid: boolean | null;
  total_line_items: number | null;
}

export interface ProjectListOut {
  projects: ProjectOut[];
}

export interface CreateProjectIn {
  project_code: string;
  name: string;
  pm_id?: number | null;
  install_start?: string | null; // date → ISO 8601 YYYY-MM-DD
}

export interface PatchProjectIn {
  name?: string | null;
  pm_id?: number | null; // note: API rejects explicit null (model_validator)
  install_start?: string | null; // date → ISO 8601 YYYY-MM-DD
  status?: string | null;
}

// =============================================================================
// Tracking grid (items list)
// Source: apps/api/app/items/schemas.py
// =============================================================================

export interface StageDates {
  due_date: string | null; // date → ISO 8601 YYYY-MM-DD
  done_date: string | null; // date → ISO 8601 YYYY-MM-DD
}

export interface AvailabilityRollup {
  ready: number;
  blocked: number;
}

export interface TrackingItemRow {
  id: number;
  item_number: number | null;
  status: string | null;
  stage: string | null; // site location (items.stage), not lifecycle_stage
  zone: string | null; // varchar(16) in DB
  level: string | null;
  room_no: string | null;
  room_desc: string | null;
  code: string | null;
  description: string | null;
  qty: number | null;
  cutlist_owner_id: number | null;
  cutlist_owner_name: string | null;
  item_locked: boolean;
  stages: Record<string, StageDates>; // keyed by stage_key: REQ..INST
  availability: AvailabilityRollup;
  // Q420/Q422: related parts arrive in the SAME list, directly beneath their
  // parent, and the grid nests on these. A related part has no stages at all
  // (Q419), so `stages` is empty for it — that is not "nothing recorded yet".
  row_type: "joinery_item" | "related_part";
  parent_item_id: number | null;
  related_part_type_key: string | null;
  // Q438: the cutlist this item belongs to. SHARED — several rows carry the
  // same number — and null until one is assigned, which Q440 allows
  // indefinitely. Not the same as item_number, which is the Item ID (Q541).
  cutlist_id: number | null;
  cutlist_no: number | null;
  // Q417: the leftmost reference is the cutlist number for a Joinery Item and
  // the most recent ISSUED supplier-order number for a related part.
  issued_order_no: string | null;
  issued_order_po_id: number | null;
  // Q425: the O/BOOK sub-tab's columns — the latest order on this row in ANY
  // state, so a Draft raised a moment ago shows. Distinct from
  // issued_order_no, which Q567 restricts to orders actually sent.
  order_po_id: number | null;
  order_no: string | null;
  order_status: string | null;
  order_supplier: string | null;
  order_due_date: string | null;
}

export interface TrackingGridOut {
  project_id: number;
  items: TrackingItemRow[];
}

// =============================================================================
// Item detail
// Source: apps/api/app/items/schemas.py
// =============================================================================

export interface PartOut {
  id: number;
  module_id: number;
  qty: number;
  part_name: string | null;
  len_mm: number | null;
  wid_mm: number | null;
  board_material: string | null; // resolved from board_materials.description via FK JOIN
  edge: string | null;
  colour: string | null;
  paint_instruction: string | null;
  comment: string | null;
  is_rev_c: boolean; // hardcoded false — no DB column per T11
}

export interface ModuleOut {
  id: number;
  name: string | null;
  parts: PartOut[];
}

export interface HardwareLineOut {
  id: number;
  catalog_id: number;
  catalog_description: string | null;
  catalog_supplier: string | null;
  catalog_source_table: string | null; // material_type from project_hardware_catalog
  qty: number;
  note: string | null;
}

export interface EditLogRow {
  log_id: number;
  actor_id: number | null;
  actor_name: string | null;
  field: string;
  old_value: string | null;
  new_value: string | null;
  ts: string; // datetime → ISO 8601 timestamp
}

export interface LockWarning {
  owner_id: number;
  owner_name: string;
  last_edit_minutes_ago: number;
}

export interface ItemOut {
  id: number;
  project_id: number;
  item_number: number | null;
  status: string | null;
  stage: string | null;
  zone: string | null; // legacy varchar(16)
  level: string | null;
  room_no: string | null;
  room_desc: string | null;
  code: string | null;
  description: string | null;
  qty: number | null;
  cutlist_owner_id: number | null;
  item_locked: boolean;
  estimator_notes: string | null;
  painting_required: boolean | null; // DB col: painting_req
  solid_surface_required: boolean | null; // DB col: solid_surface_req
  group_id: string | null;
  // Q454/Q455 — Area and Room as entities (0026). The legacy stage / room_no /
  // room_desc above stay populated alongside these until a later migration
  // drops them (Q435).
  area_id: number | null;
  room_id: number | null;
  stages: Record<string, StageDates>;
  modules: ModuleOut[];
  hardware_lines: HardwareLineOut[];
  edit_log: EditLogRow[];
  lock_warning: LockWarning | null;
}

// =============================================================================
// Item availability
// Source: apps/api/app/items/schemas.py
// =============================================================================

export type AvailabilityStatus = "ready" | "ordered" | "none";

export interface AvailabilityLine {
  line_id: number;
  status: AvailabilityStatus;
  eta: string | null; // date → ISO 8601 YYYY-MM-DD
  batch_id: number | null;
}

export interface AvailabilityOut {
  item_id: number;
  lines: AvailabilityLine[];
}

// =============================================================================
// Item write inputs
// Source: apps/api/app/items/schemas.py
// =============================================================================

export interface CreateItemIn {
  description?: string | null;
  qty?: number | null;
  stage?: string | null;
  code?: string | null;
  level?: string | null;
  room_no?: string | null; // DB col: rm_no
  room_desc?: string | null; // DB col: rm_desc
  zone?: string | null; // varchar(16) in DB
}

export interface PatchItemIn {
  area_id?: number | null;
  room_id?: number | null;
  description?: string | null;
  qty?: number | null;
  stage?: string | null;
  code?: string | null;
  level?: string | null;
  room_no?: string | null;
  room_desc?: string | null;
  zone?: string | null;
  estimator_notes?: string | null;
  painting_required?: boolean | null; // DB col: painting_req
  solid_surface_required?: boolean | null; // DB col: solid_surface_req
}

export interface LockTransferIn {
  owner_id: number;
}

export type ItemStatus = "CLEAR" | "VOID" | "NOTE!" | "LIVE" | "APPROVED" | "HOLD";

export interface PatchItemStatusIn {
  status: ItemStatus;
  note?: string | null;
}

export interface PatchLifecycleIn {
  due_date?: string | null; // date → ISO 8601 YYYY-MM-DD
  done_date?: string | null; // date → ISO 8601 YYYY-MM-DD
}

// =============================================================================
// Parts / modules write inputs
// Source: apps/api/app/parts/schemas.py
// =============================================================================

export interface CreateModuleIn {
  module_no: string;
  name?: string | null;
  notes?: string | null;
}

export interface PatchModuleIn {
  name?: string | null;
  notes?: string | null;
}

export type PaintInstruction = "NONE" | "DOUBLE_SIDE" | "SINGLE_SIDE" | "EDGE_ONLY";

export interface CreatePartIn {
  qty?: number; // default 1
  part_name?: string | null;
  len_mm?: number | null;
  wid_mm?: number | null;
  board_material_id?: number | null; // FK to board_materials.material_id
  edge?: string | null;
  colour?: string | null;
  paint_instruction?: PaintInstruction | null;
  comment?: string | null;
  // is_rev_c excluded — no DB column per T11
}

export interface PatchPartIn {
  qty?: number | null;
  part_name?: string | null;
  len_mm?: number | null;
  wid_mm?: number | null;
  board_material_id?: number | null; // FK to board_materials.material_id
  edge?: string | null;
  colour?: string | null;
  paint_instruction?: PaintInstruction | null;
  comment?: string | null;
}

// =============================================================================
// Hardware lines + catalog
// Source: apps/api/app/hardware_lines/schemas.py
// =============================================================================

export type SourceTable =
  | "board_materials"
  | "hardware_materials"
  | "custom_made"
  | "benchtop_materials"
  | "appliances"
  | "equipment_hire";

export interface HardwareCatalogRow {
  catalog_id: number;
  source_table: string; // SourceTable values at runtime
  source_id: number;
  sku: string | null;
  name: string;
  supplier: string | null;
  unit_cost: number | null;
  qty: number;
}

export interface HardwareCatalogOut {
  project_id: number;
  rows: HardwareCatalogRow[];
}

export interface AddCatalogIn {
  source_table: SourceTable;
  source_id: number;
  qty?: number; // default 1 on backend
}

export interface CreateHardwareLineIn {
  catalog_id: number;
  qty?: number; // default 1
  note?: string | null;
}

export interface PatchHardwareLineIn {
  qty?: number | null;
  note?: string | null;
}

// =============================================================================
// Home dashboard
// Source: apps/api/app/home/schemas.py
// =============================================================================

export interface MetricCard {
  key: string;
  label: string;
  value: number; // int | float both map to number
  href: string;
}

export interface MyDayItem {
  item_id: number;
  project_code: string;
  description: string | null;
  next_due_stage_key: string | null;
  next_due_date: string | null; // date → ISO 8601 YYYY-MM-DD
}

export interface DeliveryToday {
  batch_id: number;
  project_code: string;
  supplier: string;
  eta: string; // date → ISO 8601 YYYY-MM-DD (required, no null)
}

export interface TeamActivityRow {
  actor_name: string;
  event: string;
  target: string | null;
  ts: string; // datetime → ISO 8601 timestamp
}

export interface FavouriteProject {
  id: number;
  project_code: string;
  name: string;
}

export type RoleView =
  | "ceo"
  | "pm"
  | "drafter"
  | "estimator"
  | "editor"
  | "purchase_officer"
  | "viewer";

export interface HomeDashboardOut {
  role_view: RoleView;
  metrics: MetricCard[];
  my_day: MyDayItem[];
  deliveries_today: DeliveryToday[];
  team_activity: TeamActivityRow[];
  favourite_projects: FavouriteProject[];
  all_projects_count: number;
}

// =============================================================================
// Team status (legacy/home.html parity)
// Source: apps/api/app/users/schemas.py
// =============================================================================

export type WorkStatus = "IN" | "ON_SITE" | "SHOP" | "WFH" | "OFF";

export interface TeamMemberOut {
  id: number;
  full_name: string;
  auth_role: string;
  jtbd_role: string | null;
  work_status: WorkStatus | null;
  location_label: string | null;
  is_self: boolean;
}

export interface TeamOut {
  members: TeamMemberOut[];
}

export interface MyStatusPatch {
  work_status?: WorkStatus | null;
  location_label?: string | null;
}
