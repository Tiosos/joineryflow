"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import type { TrackingItemRow } from "@/lib/pm-types";

interface Supplier {
  vendor_id: number;
  name: string;
}

interface Category {
  category_key: string;
  label: string;
}

/**
 * Q426 + Q503: one **generic** order form — fixed fields for everything shared
 * across order types (project, location, cutlist no., quantity, cost, supplier,
 * comments) plus a free `attributes` store for the type-specific fields the
 * reference forms show (benchtop underside, edging, acoustic-panel dimensions,
 * contractor references). Those are not individually validated, which Q503
 * accepts: §21's supplier comparison works on the shared fields only.
 *
 * PROJECT, LOCATION and CUTLIST NO. are **not** inputs (Q427/Q428). The server
 * derives all three from `item_id`, taking the cutlist number from the parent
 * Joinery Item when the row is a related part, which never holds one itself
 * (Q417). This form shows what will be carried rather than letting it be typed.
 */
export function CreateOrderDialog({
  projectId,
  items,
  onClose,
}: {
  projectId: number;
  items: TrackingItemRow[];
  onClose: () => void;
}) {
  const router = useRouter();
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [itemId, setItemId] = useState("");
  const [vendorId, setVendorId] = useState("");
  const [category, setCategory] = useState("Other");
  const [description, setDescription] = useState("");
  const [quantity, setQuantity] = useState("");
  const [unitOfMeasure, setUnitOfMeasure] = useState("");
  const [unitCost, setUnitCost] = useState("");
  const [requiredDate, setRequiredDate] = useState("");
  const [notes, setNotes] = useState("");
  const [attrs, setAttrs] = useState<{ k: string; v: string }[]>([{ k: "", v: "" }]);

  useEffect(() => {
    fetch("/api/suppliers", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => setSuppliers(d?.suppliers ?? []))
      .catch(() => {});
    fetch("/api/order-categories", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => setCategories(d ?? []))
      .catch(() => {});
  }, []);

  // What the server will carry over, shown read-only so the rule is visible.
  const chosen = items.find((i) => String(i.id) === itemId);
  const carriedCutlist =
    chosen == null
      ? null
      : chosen.row_type === "related_part"
      ? (items.find((i) => i.id === chosen.parent_item_id)?.cutlist_no ?? null)
      : chosen.cutlist_no;

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const attributes: Record<string, string> = {};
      for (const { k, v } of attrs) {
        if (k.trim()) attributes[k.trim()] = v;
      }
      const r = await fetch("/api/orders", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          vendor_id: Number(vendorId),
          description,
          category,
          // An order need not belong to an item — Q507 covers all procurement,
          // and purchase_orders.item_id is nullable for exactly that.
          item_id: itemId === "" ? null : Number(itemId),
          project_id: itemId === "" ? projectId : null,
          quantity: quantity === "" ? null : quantity,
          unit_of_measure: unitOfMeasure || null,
          unit_cost: unitCost === "" ? null : unitCost,
          required_date: requiredDate || null,
          notes: notes || null,
          attributes,
        }),
      });
      if (!r.ok) {
        const body = await r.json().catch(() => null);
        setError(body?.detail?.code ?? body?.detail ?? `Failed (${r.status})`);
        return;
      }
      router.refresh();
      onClose();
    } finally {
      setBusy(false);
    }
  }

  const valid = vendorId !== "" && description.trim() !== "";

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/30 p-6"
      role="dialog"
      aria-modal="true"
      aria-label="Create order"
    >
      <div className="w-full max-w-2xl rounded-lg border border-h-line bg-h-surface shadow-lg">
        <div className="flex items-center border-b border-h-line px-4 py-3">
          <h2 className="text-sm font-semibold text-h-ink">Create order</h2>
          <button
            type="button"
            onClick={onClose}
            className="ml-auto rounded border border-h-line px-2 py-1 text-xs text-h-muted"
          >
            Close
          </button>
        </div>

        <div className="grid gap-3 p-4">
          {error && (
            <div role="alert" className="rounded border border-h-line bg-h-bg p-2 text-xs text-[#b4443d]">
              {error}
            </div>
          )}

          <Field label="For item">
            <select
              value={itemId}
              onChange={(e) => setItemId(e.target.value)}
              className={inputCls}
            >
              <option value="">No item — a project-level order</option>
              {items.map((i) => (
                <option key={i.id} value={i.id}>
                  {i.item_number} · {i.code ?? "—"} · {i.description ?? "—"}
                  {i.row_type === "related_part" ? "  (related part)" : ""}
                </option>
              ))}
            </select>
          </Field>

          {/* Q427/Q428 — carried by the server, not typed here. */}
          <div className="rounded border border-h-line bg-h-bg p-2 text-[11px] text-h-muted">
            Carried over automatically:{" "}
            <strong className="text-h-ink">Project</strong>,{" "}
            <strong className="text-h-ink">Location</strong>
            {chosen ? ` (${chosen.stage ?? "—"})` : ""} and{" "}
            <strong className="text-h-ink">Cutlist no.</strong>
            {chosen
              ? carriedCutlist != null
                ? ` (${carriedCutlist}${
                    chosen.row_type === "related_part" ? ", from its parent item" : ""
                  })`
                : " (none yet — it fills in when the parent gets one)"
              : ""}
            .
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Supplier *">
              <select
                value={vendorId}
                onChange={(e) => setVendorId(e.target.value)}
                className={inputCls}
              >
                <option value="">Choose a supplier…</option>
                {suppliers.map((s) => (
                  <option key={s.vendor_id} value={s.vendor_id}>
                    {s.name}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Category">
              <select
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                className={inputCls}
              >
                {categories.map((c) => (
                  <option key={c.category_key} value={c.category_key}>
                    {c.label}
                  </option>
                ))}
              </select>
            </Field>
          </div>

          <Field label="Description *">
            <input
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className={inputCls}
              placeholder="What is being ordered"
            />
          </Field>

          <div className="grid gap-3 sm:grid-cols-4">
            <Field label="Quantity">
              <input
                type="number"
                value={quantity}
                onChange={(e) => setQuantity(e.target.value)}
                className={inputCls}
              />
            </Field>
            <Field label="Unit">
              <input
                value={unitOfMeasure}
                onChange={(e) => setUnitOfMeasure(e.target.value)}
                className={inputCls}
                placeholder="ea / m² / m"
              />
            </Field>
            <Field label="Unit cost">
              <input
                type="number"
                step="0.01"
                value={unitCost}
                onChange={(e) => setUnitCost(e.target.value)}
                className={inputCls}
              />
            </Field>
            <Field label="Required by">
              <input
                type="date"
                value={requiredDate}
                onChange={(e) => setRequiredDate(e.target.value)}
                className={inputCls}
              />
            </Field>
          </div>

          <Field label="Comments">
            <textarea
              rows={2}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              className={`${inputCls} resize-none`}
            />
          </Field>

          <div>
            <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-h-muted">
              Type-specific fields
            </div>
            <p className="mb-2 text-[11px] text-h-muted">
              Whatever this order type needs — benchtop underside and edging,
              panel dimensions, a contractor reference. Stored as given (Q503),
              so these are not searchable or compared across suppliers.
            </p>
            {attrs.map((a, idx) => (
              <div key={idx} className="mb-1 flex gap-2">
                <input
                  value={a.k}
                  onChange={(e) =>
                    setAttrs((prev) =>
                      prev.map((x, i) => (i === idx ? { ...x, k: e.target.value } : x)),
                    )
                  }
                  className={`${inputCls} w-40`}
                  placeholder="Field"
                />
                <input
                  value={a.v}
                  onChange={(e) =>
                    setAttrs((prev) =>
                      prev.map((x, i) => (i === idx ? { ...x, v: e.target.value } : x)),
                    )
                  }
                  className={`${inputCls} flex-1`}
                  placeholder="Value"
                />
              </div>
            ))}
            <button
              type="button"
              onClick={() => setAttrs((p) => [...p, { k: "", v: "" }])}
              className="mt-1 rounded border border-h-line px-2 py-0.5 text-[11px] text-h-muted hover:text-h-ink"
            >
              + Add field
            </button>
          </div>
        </div>

        <div className="flex justify-end gap-2 border-t border-h-line px-4 py-3">
          <button
            type="button"
            onClick={onClose}
            className="rounded border border-h-line px-3 py-1.5 text-xs text-h-ink"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={submit}
            disabled={busy || !valid}
            className="rounded bg-h-accent px-3 py-1.5 text-xs font-medium text-white disabled:opacity-50"
          >
            {busy ? "Creating…" : "Create order"}
          </button>
        </div>
      </div>
    </div>
  );
}

const inputCls =
  "w-full rounded border border-h-line bg-h-bg px-2 py-1 text-xs text-h-ink";

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-h-muted">
        {label}
      </span>
      {children}
    </label>
  );
}
