/** Mirrors `purchase_orders/schemas.py`. Decimals arrive as strings (see CLAUDE.md §6). */
export interface PoLine {
  line_no: number;
  order_id: number;
  po_number: string;
  status: string;
  description: string;
  product_code: string | null;
  quantity: string | null;
  unit_of_measure: string | null;
  unit_cost: string | null;
  total_amount: string | null;
  gst_amount: string | null;
  grand_total: string | null;
  requester_name: string | null;
  project_name: string | null;
  location: string | null;
  item_number: number | null;
  arrived_date: string | null;
  has_attachment: boolean;
  is_delivery: boolean;
  invoiced: boolean;
}

export interface PoInvoice {
  invoice_id: number;
  order_id: number;
  line_no: number | null;
  invoice_number: string;
  invoiced_date: string | null;
  qty: string | null;
  payment_method_id: number | null;
  payment_method_name: string | null;
  total_ex: string | null;
  gst: string | null;
  gst_auto: boolean;
  total_inc: string | null;
  notes: string | null;
  delivery_doc_mime: string | null;
  invoice_doc_mime: string | null;
  non_delivery_mime: string | null;
  created_at: string;
  updated_at: string;
  description: string | null;
  product_code: string | null;
}

export type InvoiceSlot = "delivery" | "invoice" | "non_delivery";

export interface PaymentMethod {
  payment_method_id: number;
  name: string;
  is_active: boolean;
}

export interface PoAuthorisation {
  po_document_id: number;
  purchase_order_amount: string;
  payment_method_id: number | null;
  payment_method_name: string | null;
  deposit_pct: string | null;
  amount_required: string | null;
  date_required: string | null;
  on_behalf_of_id: number | null;
  on_behalf_of_name: string | null;
  form_created_at: string | null;
  signed_mime: string | null;
  updated_at: string | null;
}

export interface PoDoc {
  po_document_id: number;
  po_no: number;
  status: "Open" | "Cancelled";
  vendor_id: number;
  vendor_name: string;
  vendor_address: string | null;
  reference_no: string | null;
  ordered_by_id: number | null;
  ordered_by_name: string | null;
  date_ordered: string;
  date_required: string | null;
  date_due: string | null;
  memo: string | null;
  deliver_to: string | null;
  delivery_order_id: number | null;
  delivery_charge: string | null;
  created_at: string;
  updated_at: string;
  lines: PoLine[];
  invoices: PoInvoice[];
  totals: { total_ex: string; gst: string; total_inc: string };
}

export interface SupplierContact {
  contact_id: number;
  vendor_id: number;
  position: string | null;
  name: string;
  mobile: string | null;
  email: string | null;
}
