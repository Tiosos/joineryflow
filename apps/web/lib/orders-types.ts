/**
 * Order types for the Orderbook page (#10).
 *
 * Mirrors `apps/api/app/orders/schemas.py::OrderOut`. Money and quantity are
 * Pydantic `Decimal`, which serialises to a JSON **string** (`"3551.00"`), not
 * a number — so they are typed `string | null` and parsed at the point of
 * display. Typing them `number` compiles fine and then throws
 * `toFixed is not a function` in the browser.
 */
export interface OrderRow {
  po_id: number;
  po_number: string;
  order_number: string | null;
  supplier_ref_no: string | null;
  status: string;
  priority: string;

  vendor_id: number;
  vendor_name: string | null;

  project_id: number | null;
  project_name: string | null;
  location: string | null;

  /**
   * Q417/Q428: on a related part's order this is the PARENT's cutlist number —
   * the related part never holds one itself.
   */
  item_id: number | null;
  item_number: number | null;
  cutlist_no: string | null;

  category: string;
  description: string;
  product_code: string | null;
  product_description: string | null;

  quantity: string | null;
  unit_of_measure: string | null;
  unit_cost: string | null;
  total_amount: string | null;
  currency: string | null;

  required_date: string | null;
  date_ordered: string | null;
  due_date: string | null;

  notes: string | null;
  internal_comments: string | null;
  attributes: Record<string, unknown>;

  created_at: string;
  updated_at: string | null;

  /** §L Q511/Q512 — field-level optimistic concurrency. */
  field_versions: Record<string, number>;
}

export interface OrderListOut {
  orders: OrderRow[];
}

export interface PatchOrderIn {
  vendor_id?: number | null;
  description?: string | null;
  category?: string | null;
  status?: string | null;
  priority?: string | null;
  order_number?: string | null;
  supplier_ref_no?: string | null;
  location?: string | null;
  product_code?: string | null;
  product_description?: string | null;
  quantity?: string | null;
  unit_of_measure?: string | null;
  unit_cost?: string | null;
  total_amount?: string | null;
  required_date?: string | null;
  date_ordered?: string | null;
  due_date?: string | null;
  notes?: string | null;
  internal_comments?: string | null;
  attributes?: Record<string, unknown> | null;
  expected_versions?: Record<string, number>;
}

/** Mirrors `orders/schemas.py::OrderLineOut`. */
export interface OrderLine {
  line_id: number;
  line_number: number;
  item_description: string;
  sku: string | null;
  quantity: string;
  unit: string | null;
  unit_price: string;
  line_total: string | null;
  material_table: string | null;
  material_id: number | null;
  attributes: Record<string, unknown>;
}

/** `GET /orders/{po_id}` — `OrderRow` plus the line items. */
export interface OrderDetail extends OrderRow {
  lines: OrderLine[];
}

/** Mirrors `orders/schemas.py::CreateOrderLineIn`. */
export interface CreateOrderLineIn {
  item_description: string;
  quantity: string;
  unit_price: string;
  sku?: string | null;
  unit?: string | null;
}

/** Mirrors `orders/schemas.py::PatchOrderLineIn`. No `expected_versions` —
 * field-level optimistic concurrency (§L) is scoped to the order header,
 * not individual lines. */
export interface PatchOrderLineIn {
  item_description?: string | null;
  sku?: string | null;
  quantity?: string | null;
  unit?: string | null;
  unit_price?: string | null;
}
