/** Mirrors `order_tabs/schemas.py` and the supplier card of `suppliers/schemas.py`. Decimals arrive as strings. */
export interface DeliveryRow {
  delivery_id: number;
  qty: string;
  date_received: string;
  signed_by: string | null;
  notes: string | null;
  has_docket: boolean;
  docket_mime: string | null;
  created_at: string;
}

export interface DeliveryLog {
  quantity: string | null;
  deliveries: DeliveryRow[];
  sum_received: string;
  remaining: string | null;
}

export interface StockRow {
  po_id: number;
  quantity: string | null;
  product_code: string | null;
  project_name: string | null;
  description: string;
  total_amount: string | null;
  category: string;
}

export interface TrackingTabData {
  order_number: string;
  description: string;
  quantity: string | null;
  item: { item_id: number; item_number: number; description: string | null; qty: number | null; date_made: string | null } | null;
}

export interface CutlistRow {
  cutlist_no: number;
  created_at: string;
  project_name: string;
  item_description: string | null;
}

export interface CutlistsTabData {
  product_found: boolean;
  cutlists: CutlistRow[];
}

export interface SupplierCard {
  vendor_id: number;
  name: string;
  website: string | null;
  notes: string | null;
  metadata: string | null;
  has_logo: boolean;
}

export interface GlassRate {
  glass_rate_id: number;
  kind: "glass" | "process";
  name: string;
  rate: string;
  um: string;
  supplier_no: string | null;
  sort_order: number;
  is_active: boolean;
}

export interface GlassCalcLine {
  glass_rate_id: number;
  kind: "glass" | "process";
  name: string;
  rate: string;
  um: string;
  supplier_no: string | null;
  qty: string;
  ticked: boolean;
  cost: string;
}

export interface GlassCalc {
  length_mm: number | null;
  width_mm: number | null;
  thick_mm: number | null;
  area_m2: string | null;
  perimeter_m: string | null;
  lines: GlassCalcLine[];
  total: string;
  suggested_size: { length_mm: number; width_mm: number; thick_mm: number | null } | null;
}

export interface TimberForm {
  face: string | null;
  back: string | null;
  substrate: string | null;
  face_by_tg: boolean;
  back_by_tg: boolean;
  substrate_by_tg: boolean;
  finished_description: string | null;
  deliver_to: string | null;
  special_instructions: string | null;
  has_form: boolean;
  form_created_at: string | null;
}

export interface TgRun {
  run_id: number;
  production_start: string | null;
  date_made: string | null;
  made_by: string | null;
  date_ex_factory: string | null;
  location: string | null;
  notes: string | null;
}
