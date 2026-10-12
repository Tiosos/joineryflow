"use client";

import { useEffect, useState } from "react";
import { listSupplierOptions } from "@/lib/catalog-fetch";
import type { SupplierOption } from "@/lib/catalog-types";
import type { OrderCategory } from "@/lib/orders-types";
import { PRIORITIES } from "./orders/shared";
import { AreaRow, CheckRow, Row, SelectRow, TextRow } from "./orders/DetailRows";
import { OrderTypeFields, typeFieldKeys } from "./orders/OrderTypeFields";

type Draft = {
  vendor_id: string; category: string; description: string; project_id: string; location: string;
  priority: string; required_date: string; order_number: string; supplier_ref_no: string;
  product_code: string; stock_tracked: boolean; quantity: string; unit_of_measure: string;
  unit_cost: string; total_amount: string; gst_applicable: boolean; gst_included_in_price: boolean;
  product_website: string; product_description: string; line_item_comments: string;
  internal_comments: string; attributes: Record<string, unknown>;
};

const EMPTY: Draft = {
  vendor_id: "", category: "Other", description: "", project_id: "", location: "", priority: "Medium",
  required_date: "", order_number: "", supplier_ref_no: "", product_code: "", stock_tracked: false,
  quantity: "", unit_of_measure: "", unit_cost: "", total_amount: "", gst_applicable: true,
  gst_included_in_price: false, product_website: "", product_description: "",
  line_item_comments: "", internal_comments: "", attributes: {},
};

const ok = () => Promise.resolve(true);

/**
 * The Orderbook's New button: the order pop-up's layout as a form. Nothing exists until
 * "Create order", which saves a Pending order (`POST /orders`). The project is optional (an order
 * with no project is a stock or office buy, Q554); there is no item link, so there is no cutlist
 * number. The type's own fields are the same ones the order pop-up edits.
 */
export function NewOrderDialog({
  categories, onClose, onCreated,
}: {
  categories: OrderCategory[]; onClose: () => void; onCreated: (poNumber: string) => void;
}) {
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [suppliers, setSuppliers] = useState<SupplierOption[]>([]);
  const [projects, setProjects] = useState<{ id: number; project_code: string; name: string }[]>([]);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formErr, setFormErr] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    listSupplierOptions().then(s => setSuppliers(s.filter(x => x.status === "Active"))).catch(() => {});
    fetch("/api/projects", { cache: "no-store" })
      .then(r => (r.ok ? r.json() : null))
      .then(b => setProjects(b?.projects ?? []))
      .catch(() => {});
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const set = <K extends keyof Draft>(k: K, v: Draft[K]) => setDraft(d => ({ ...d, [k]: v }));
  const setText = (k: keyof Draft) => (v: string) => { set(k, v as never); return ok(); };

  /** A number field: refuse a non-number; the sub total follows qty × cost, like the order pop-up. */
  function setNumber(field: "quantity" | "unit_cost" | "total_amount", v: string) {
    const val = v.trim();
    if (val !== "" && Number.isNaN(Number(val))) {
      setErrors(e => ({ ...e, [field]: "Enter a number" }));
      return Promise.resolve(false);
    }
    setErrors(e => ({ ...e, [field]: "" }));
    setDraft(d => {
      const next = { ...d, [field]: val };
      if (field !== "total_amount" && next.quantity !== "" && next.unit_cost !== "") {
        next.total_amount = (Number(next.quantity) * Number(next.unit_cost)).toFixed(2);
      }
      return next;
    });
    return ok();
  }

  async function create() {
    setFormErr(null);
    if (!draft.vendor_id) { setFormErr("Choose a supplier"); return; }
    if (!draft.description.trim()) { setFormErr("Describe what is being ordered"); return; }
    setSaving(true);
    const project = projects.find(p => String(p.id) === draft.project_id);
    // The type's own fields only: switching type hides the old ones, which must not be saved.
    const keep = typeFieldKeys(draft.category);
    const attributes = Object.fromEntries(Object.entries(draft.attributes).filter(([k]) => keep.includes(k)));
    const text = (v: string) => (v.trim() === "" ? null : v.trim());
    const res = await fetch("/api/orders", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        vendor_id: Number(draft.vendor_id), category: draft.category,
        description: draft.description.trim(), priority: draft.priority,
        project_id: project ? project.id : null, project_name: project ? project.name : null,
        location: text(draft.location), required_date: text(draft.required_date),
        order_number: text(draft.order_number), supplier_ref_no: text(draft.supplier_ref_no),
        product_code: text(draft.product_code), product_description: text(draft.product_description),
        product_website: text(draft.product_website), line_item_comments: text(draft.line_item_comments),
        internal_comments: text(draft.internal_comments),
        quantity: text(draft.quantity), unit_of_measure: text(draft.unit_of_measure),
        unit_cost: text(draft.unit_cost), total_amount: text(draft.total_amount),
        stock_tracked: draft.stock_tracked, gst_applicable: draft.gst_applicable,
        gst_included_in_price: draft.gst_included_in_price, attributes,
      }),
    }).catch(() => null);
    setSaving(false);
    if (!res || !res.ok) {
      setFormErr(res?.status === 422 ? "Some of the fields are not valid" : "Could not create the order");
      return;
    }
    const created = (await res.json()) as { po_number: string };
    onCreated(created.po_number);
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/40 p-4"
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div role="dialog" aria-label="New order" data-testid="new-order-dialog"
        className="w-full max-w-5xl rounded-lg border border-h-line bg-h-surface text-xs shadow-xl">
        <header className="flex flex-wrap items-center gap-3 border-b border-h-line bg-h-bg px-4 py-3">
          <h2 className="text-sm text-h-ink">New order</h2>
          <span className="text-h-muted">Starts as Pending, for the purchase officer to decide.</span>
          <button type="button" onClick={onClose}
            className="ml-auto rounded border border-h-line bg-h-surface px-3 py-1 text-sm text-h-ink hover:bg-h-bg">Cancel</button>
          <button type="button" disabled={saving} onClick={() => void create()} data-testid="new-order-create"
            className="rounded bg-h-accent px-4 py-1 text-sm font-medium text-white disabled:opacity-50">Create order</button>
        </header>
        {formErr && <p data-testid="new-order-error" className="px-4 pt-3 text-[#b4443d]">{formErr}</p>}

        <div className="grid gap-6 p-4 lg:grid-cols-2">
          <dl className="self-start rounded border border-h-line">
            <Row label="Supplier">
              <select value={draft.vendor_id} onChange={e => set("vendor_id", e.target.value)} data-testid="new-order-supplier"
                className="w-full rounded border border-h-line bg-h-bg px-1 py-0.5 text-h-ink">
                <option value="">Choose a supplier</option>
                {suppliers.map(s => <option key={s.vendor_id} value={s.vendor_id}>{s.name}</option>)}
              </select>
            </Row>
            <SelectRow label="Order type" value={draft.category} canEdit testId="new-order-category"
              options={categories.map(c => ({ value: c.category_key, label: c.label }))}
              onSave={v => { set("category", v); return ok(); }} />
            <AreaRow label="Description" rows={2} value={draft.description} canEdit onSave={setText("description")} />
            <TextRow label="Order number" value={draft.order_number} canEdit mono onSave={setText("order_number")} />
            <SelectRow label="Priority" value={draft.priority} canEdit
              options={PRIORITIES.map(p => ({ value: p, label: p }))}
              onSave={v => { set("priority", v); return ok(); }} />
            <TextRow label="Date required" type="date" value={draft.required_date} canEdit mono onSave={setText("required_date")} />
            <Row label="Project">
              <select value={draft.project_id} onChange={e => set("project_id", e.target.value)} data-testid="new-order-project"
                className="w-full rounded border border-h-line bg-h-bg px-1 py-0.5 text-h-ink">
                <option value="">No project</option>
                {projects.map(p => <option key={p.id} value={p.id}>{p.project_code} {p.name}</option>)}
              </select>
            </Row>
            <TextRow label="Location" value={draft.location} canEdit onSave={setText("location")} />
            <TextRow label="Supplier ref no." value={draft.supplier_ref_no} canEdit mono onSave={setText("supplier_ref_no")} />
            <TextRow label="Product code" value={draft.product_code} canEdit mono onSave={setText("product_code")} />
            <CheckRow label="Stock tracked" value={draft.stock_tracked} canEdit
              onSave={v => { set("stock_tracked", v); return ok(); }} />
            <TextRow label="Qty" value={draft.quantity} canEdit mono testId="new-order-qty"
              onSave={v => setNumber("quantity", v)} error={errors.quantity} />
            <OrderTypeFields category={draft.category} attributes={draft.attributes} canEdit
              onSave={(k, v) => { setDraft(d => ({ ...d, attributes: { ...d.attributes, [k]: v } })); return ok(); }} />
            <CheckRow label="GST applicable" value={draft.gst_applicable} canEdit
              onSave={v => { set("gst_applicable", v); return ok(); }} />
            <CheckRow label="GST included in price?" value={draft.gst_included_in_price} canEdit
              onSave={v => { set("gst_included_in_price", v); return ok(); }} />
            <TextRow label="Cost" value={draft.unit_cost} canEdit mono testId="new-order-cost"
              onSave={v => setNumber("unit_cost", v)} error={errors.unit_cost} />
            <TextRow label="UM" value={draft.unit_of_measure} canEdit onSave={setText("unit_of_measure")} />
            <TextRow label="Sub total" value={draft.total_amount} canEdit mono testId="new-order-total"
              onSave={v => setNumber("total_amount", v)} error={errors.total_amount} />
          </dl>

          <div className="grid content-start gap-3">
            <dl className="rounded border border-h-line">
              <TextRow label="Website" value={draft.product_website} canEdit onSave={setText("product_website")} />
              <AreaRow label="Product description" rows={3} value={draft.product_description} canEdit
                onSave={setText("product_description")} />
              <AreaRow label="Line item comments" rows={2} value={draft.line_item_comments} canEdit
                onSave={setText("line_item_comments")} />
              <AreaRow label="Internal comments" rows={4} value={draft.internal_comments} canEdit
                onSave={setText("internal_comments")} />
            </dl>
            <p className="text-[10px] text-h-muted">
              Line item comments are seen on the purchase order; internal comments are not. Files, the
              product image and the other tabs come after the order exists.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
