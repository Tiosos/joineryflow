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
