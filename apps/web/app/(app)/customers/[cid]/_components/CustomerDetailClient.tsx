"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import type { Me } from "@/lib/session";
import type {
  Customer,
  EstimateStatus,
  EstimateSummary,
} from "@/lib/estimating-types";

interface Props {
  me: Me;
  customer: Customer;
  activeEstimates: EstimateSummary[];
  archivedEstimates: EstimateSummary[];
}

const STATUS_COLOURS: Record<EstimateStatus, string> = {
  draft: "bg-gray-200 text-gray-700",
  sent: "bg-blue-100 text-blue-800",
  accepted: "bg-green-100 text-green-800",
  rejected: "bg-red-100 text-red-800",
  expired: "bg-amber-100 text-amber-800",
  withdrawn: "bg-gray-100 text-gray-600",
};

function fmtMoney(s: string | null | undefined): string {
  if (!s) return "—";
  const n = parseFloat(s);
  if (!Number.isFinite(n)) return "—";
  return `$${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export default function CustomerDetailClient({
  me, customer, activeEstimates, archivedEstimates,
}: Props) {
  const router = useRouter();
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canWrite =
    me.auth_role === "admin" || me.auth_role === "manager" || me.auth_role === "estimator";
  const isArchived = !!customer.archived_at;

  async function archive() {
    if (!window.confirm(`Archive "${customer.name}"?`)) return;
    setBusy(true);
    setError(null);
    try {
      const r = await fetch(`/api/customers/${customer.customer_id}/archive`, {
        method: "POST",
      });
      if (!r.ok) {
        let msg = `Archive failed (${r.status})`;
        try {
          const j = await r.json();
          if (j?.detail?.code) msg = j.detail.code;
        } catch { /* ignore */ }
        setError(msg);
        return;
      }
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="space-y-4">
      <div>
        <Link
          href="/customers"
          className="text-xs uppercase tracking-wide text-h-muted hover:text-h-ink"
        >
          ← Customers
        </Link>
        <div className="mt-1 flex items-baseline justify-between gap-3">
          <h1 className="text-2xl font-semibold text-h-ink">{customer.name}</h1>
          <div className="flex items-center gap-2">
            {isArchived ? (
              <span className="rounded-full bg-gray-200 px-2 py-0.5 text-xs uppercase tracking-wide text-gray-700">
                Archived
              </span>
            ) : null}
            {canWrite && !isArchived ? (
              <button
                type="button"
                onClick={() => setEditing((s) => !s)}
                className="rounded border border-h-line bg-white px-3 py-1.5 text-sm hover:bg-gray-50"
                data-testid="edit-customer-btn"
              >
                {editing ? "Cancel" : "✎ Edit"}
              </button>
            ) : null}
            {canWrite && !isArchived ? (
              <button
                type="button"
                onClick={archive}
                disabled={busy}
                className="rounded border border-red-200 bg-red-50 px-3 py-1.5 text-sm text-red-800 hover:bg-red-100 disabled:opacity-50"
                data-testid="archive-customer-btn"
              >
                Archive
              </button>
            ) : null}
          </div>
        </div>
      </div>

      {error ? (
        <div className="rounded bg-red-50 px-3 py-2 text-sm text-red-800" data-testid="api-error">
          {error}
        </div>
      ) : null}

      {editing ? (
        <CustomerEditForm
          customer={customer}
          onSaved={() => { setEditing(false); router.refresh(); }}
          onCancel={() => setEditing(false)}
        />
      ) : (
        <CustomerSummary customer={customer} />
      )}

      <EstimateListBlock
        title="Active estimates"
        estimates={activeEstimates}
        emptyMessage="No active estimates yet."
      />
      <EstimateListBlock
        title="Archived estimates"
        estimates={archivedEstimates}
        emptyMessage="No archived estimates."
      />
    </section>
  );
}

function CustomerSummary({ customer }: { customer: Customer }) {
  return (
    <dl className="grid grid-cols-1 gap-2 rounded border border-h-line bg-h-surface p-3 text-sm sm:grid-cols-2">
      <SummaryRow label="Email" value={customer.email} />
      <SummaryRow label="Phone" value={customer.phone} />
      <SummaryRow label="ABN" value={customer.abn} />
      <SummaryRow label="Billing" value={customer.billing_address} wide />
      <SummaryRow label="Notes" value={customer.notes} wide />
    </dl>
  );
}

function SummaryRow({
  label, value, wide,
}: { label: string; value?: string | null; wide?: boolean }) {
  return (
    <div className={wide ? "sm:col-span-2" : ""}>
      <dt className="text-xs uppercase tracking-wide text-h-muted">{label}</dt>
      <dd className="text-h-ink">{value ?? "—"}</dd>
    </div>
  );
}

interface EditFormProps {
  customer: Customer;
  onSaved: () => void;
  onCancel: () => void;
}

function CustomerEditForm({ customer, onSaved, onCancel }: EditFormProps) {
  const [name, setName] = useState(customer.name);
  const [email, setEmail] = useState(customer.email ?? "");
  const [phone, setPhone] = useState(customer.phone ?? "");
  const [billing, setBilling] = useState(customer.billing_address ?? "");
  const [abn, setAbn] = useState(customer.abn ?? "");
  const [notes, setNotes] = useState(customer.notes ?? "");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const r = await fetch(`/api/customers/${customer.customer_id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: name.trim(),
          email: email.trim() || null,
          phone: phone.trim() || null,
          billing_address: billing.trim() || null,
          abn: abn.trim() || null,
          notes: notes.trim() || null,
        }),
      });
      if (!r.ok) {
        let msg = `Save failed (${r.status})`;
        try {
          const j = await r.json();
          if (j?.detail?.code) msg = j.detail.code;
        } catch { /* ignore */ }
        setError(msg);
        return;
      }
      onSaved();
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form
      onSubmit={submit}
      className="grid grid-cols-1 gap-2 rounded border border-h-line bg-white p-3 text-sm sm:grid-cols-2"
      data-testid="customer-edit-form"
    >
      <Field label="Name" value={name} onChange={setName} required testid="edit-name" />
      <Field label="Email" value={email} onChange={setEmail} type="email" />
      <Field label="Phone" value={phone} onChange={setPhone} />
      <Field label="ABN" value={abn} onChange={setAbn} />
      <Field label="Billing address" value={billing} onChange={setBilling} wide />
      <TextArea label="Notes" value={notes} onChange={setNotes} />
      {error ? (
        <div className="sm:col-span-2 rounded bg-red-50 px-3 py-2 text-red-800">{error}</div>
      ) : null}
      <div className="sm:col-span-2 flex justify-end gap-2">
        <button
          type="button"
          onClick={onCancel}
          className="rounded border border-h-line bg-white px-3 py-1.5 hover:bg-gray-50"
        >
          Cancel
        </button>
        <button
          type="submit"
          disabled={submitting || name.trim() === ""}
          className="rounded bg-h-accent px-3 py-1.5 font-medium text-white shadow hover:opacity-90 disabled:opacity-50"
          data-testid="save-customer-btn"
        >
          {submitting ? "Saving…" : "Save"}
        </button>
      </div>
    </form>
  );
}

function Field({
  label, value, onChange, required, type = "text", wide, testid,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  required?: boolean;
  type?: string;
  wide?: boolean;
  testid?: string;
}) {
  return (
    <label className={`flex flex-col ${wide ? "sm:col-span-2" : ""}`}>
      <span className="text-xs uppercase tracking-wide text-h-muted">{label}</span>
      <input
        type={type}
        value={value}
        required={required}
        onChange={(e) => onChange(e.target.value)}
        className="mt-1 rounded border border-h-line px-2 py-1"
        data-testid={testid}
      />
    </label>
  );
}

function TextArea({
  label, value, onChange,
}: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <label className="sm:col-span-2 flex flex-col">
      <span className="text-xs uppercase tracking-wide text-h-muted">{label}</span>
      <textarea
        value={value}
        rows={3}
        onChange={(e) => onChange(e.target.value)}
        className="mt-1 rounded border border-h-line px-2 py-1"
      />
    </label>
  );
}

function EstimateListBlock({
  title, estimates, emptyMessage,
}: {
  title: string;
  estimates: EstimateSummary[];
  emptyMessage: string;
}) {
  return (
    <div className="space-y-2">
      <h2 className="text-sm font-semibold text-h-ink">{title}</h2>
      {estimates.length === 0 ? (
        <p className="rounded border border-dashed border-h-line p-3 text-sm text-h-muted">
          {emptyMessage}
        </p>
      ) : (
        <ul className="divide-y divide-h-line rounded border border-h-line bg-h-surface">
          {estimates.map((est) => (
            <li key={est.estimate_id}>
              <Link
                href={`/estimating/${est.estimate_id}`}
                className="flex items-center justify-between gap-3 px-3 py-2 hover:bg-white"
                data-testid={`customer-estimate-${est.estimate_id}`}
              >
                <span className="flex items-baseline gap-2">
                  <span className="font-mono text-sm font-semibold text-h-ink">
                    {est.estimate_no}
                  </span>
                  <span className="text-sm text-h-ink">{est.title}</span>
                </span>
                <span className="flex items-center gap-3 text-sm">
                  {est.current_status ? (
                    <span
                      className={`rounded-full px-2 py-0.5 text-xs font-medium uppercase tracking-wide ${STATUS_COLOURS[est.current_status]}`}
                    >
                      {est.current_status}
                    </span>
                  ) : null}
                  <span className="font-mono text-h-muted">
                    v{est.current_rev_no ?? "?"}
                  </span>
                  <span className="font-mono text-h-ink">
                    {fmtMoney(est.current_total_inc_gst)}
                  </span>
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
