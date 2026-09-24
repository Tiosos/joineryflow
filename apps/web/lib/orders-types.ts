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
}

export interface OrderListOut {
  orders: OrderRow[];
}
