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
  /** Server-computed: true for a Cancelled / Delivered order (read-only except
   *  `status`). The API enforces it; the UI only reads it to decide what to render. */
  locked: boolean;

  /** PO approval. `needs_approval` is the server's answer (total over the workspace limit,
   *  or the project manager's `requires_approval` flag); the UI only reads it. */
  requires_approval: boolean;
  needs_approval: boolean;
  approval_requested_by: number | null;
  approval_requested_by_name: string | null;
  approval_requested_at: string | null;
  approval_decided_by: number | null;
  approval_decided_by_name: string | null;
  approval_decided_at: string | null;
  approval_note: string | null;
  /** What the last approval approved (Decimal, so a string); a rise above it sends the order back. */
  approved_total: string | null;

  cost_center_id: number | null;
  cost_center_code: string | null;
  cost_center_name: string | null;
}

/** Pydantic `Decimal`, so the budget arrives as a string. */
export interface CostCentre {
  cost_center_id: number;
  code: string;
  name: string;
  budget_amount: string;
  is_active: boolean;
  /** From the budget ledger: what approved orders still hold, what delivered ones cost, the rest. */
  committed: string;
  spent: string;
  remaining: string;
}

export interface OrderListOut {
  orders: OrderRow[];
}

export interface PatchOrderIn {
  // Omit a field to leave it alone. These five are refused if sent as an explicit
  // null (a 422) — the API has no "clear" for them — so they are not `| null`.
  vendor_id?: number;
  description?: string;
  category?: string;
  status?: string;
  priority?: string;
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
