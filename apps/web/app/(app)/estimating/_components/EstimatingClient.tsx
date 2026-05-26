"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import type { Me } from "@/lib/session";
import type {
  Customer,
  EstimateStatus,
  EstimateSummary,
} from "@/lib/estimating-types";

interface Props {
  me: Me;
  initialEstimates: EstimateSummary[];
  customers: Customer[];
  initialSubtab: "active" | "archive";
  initialQ: string;
}

const STATUS_COLOURS: Record<EstimateStatus, string> = {
  draft: "bg-gray-200 text-gray-700",
  sent: "bg-blue-100 text-blue-800",
  accepted: "bg-green-100 text-green-800",
  rejected: "bg-red-100 text-red-800",
  expired: "bg-amber-100 text-amber-800",
  withdrawn: "bg-gray-100 text-gray-600",
};

export default function EstimatingClient({
  me,
  initialEstimates,
  customers,
  initialSubtab,
  initialQ,
}: Props) {
  const router = useRouter();
  const sp = useSearchParams();
  const [q, setQ] = useState(initialQ);
  const [showNew, setShowNew] = useState(false);

  const canWrite =
    me.auth_role === "admin" ||
    me.auth_role === "manager" ||
    me.auth_role === "estimator";

  const updateUrl = useCallback(
    (patch: Record<string, string | null>) => {
      const next = new URLSearchParams(sp.toString());
      for (const [k, v] of Object.entries(patch)) {
        if (v == null || v === "") next.delete(k);
        else next.set(k, v);
      }
      router.replace(`/estimating?${next.toString()}`);
    },
    [router, sp],
  );

  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    if (q === initialQ) return;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      updateUrl({ q: q || null });
    }, 300);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [q, initialQ, updateUrl]);

  return (
    <section className="space-y-4">
      <header className="flex items-baseline justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-h-ink">Estimating</h1>
          <p className="mt-1 text-sm text-h-muted">
            {initialEstimates.length} {initialSubtab} estimate
            {initialEstimates.length === 1 ? "" : "s"}
          </p>
        </div>
        {canWrite ? (
          <button
            type="button"
            onClick={() => setShowNew(true)}
            className="rounded bg-h-accent px-3 py-1.5 text-sm font-medium text-white shadow hover:opacity-90"
            data-testid="new-estimate-btn"
          >
            + New estimate
          </button>
        ) : null}
      </header>

      <div className="flex items-center gap-3 border-b border-h-line pb-3">
        <button
          type="button"
          onClick={() => updateUrl({ subtab: null })}
          className={`text-sm font-medium ${
            initialSubtab === "active"
              ? "text-h-ink underline underline-offset-4"
              : "text-h-muted hover:text-h-ink"
          }`}
        >
          Active
        </button>
        <button
          type="button"
          onClick={() => updateUrl({ subtab: "archive" })}
          className={`text-sm font-medium ${
            initialSubtab === "archive"
              ? "text-h-ink underline underline-offset-4"
              : "text-h-muted hover:text-h-ink"
          }`}
        >
          Archive
        </button>
        <input
          type="search"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search estimate number, title, customer…"
          className="ml-auto w-72 rounded border border-h-line bg-white px-2 py-1 text-sm"
          data-testid="estimating-search"
        />
      </div>

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
        {initialEstimates.length === 0 ? (
          <div className="col-span-full rounded border border-dashed border-h-line p-8 text-center text-sm text-h-muted">
            No estimates yet.{" "}
            {canWrite ? (
              <button
                type="button"
                onClick={() => setShowNew(true)}
                className="text-h-accent underline"
              >
                + Create your first quote
              </button>
            ) : (
              "Ask your estimator to create one."
            )}
          </div>
        ) : (
          initialEstimates.map((est) => (
            <Link
              key={est.estimate_id}
              href={`/estimating/${est.estimate_id}`}
              className="block rounded border border-h-line bg-h-surface p-4 transition hover:border-h-ink"
            >
              <div className="flex items-baseline justify-between">
                <span className="font-mono text-sm font-semibold text-h-ink">
                  {est.estimate_no}
                </span>
                {est.current_status ? (
                  <span
                    className={`rounded-full px-2 py-0.5 text-xs font-medium uppercase tracking-wide ${STATUS_COLOURS[est.current_status]}`}
                  >
                    {est.current_status}
                  </span>
                ) : null}
              </div>
              <div className="mt-2 text-sm text-h-ink">{est.title}</div>
              <div className="mt-1 text-xs text-h-muted">{est.customer_name}</div>
              <div className="mt-3 flex items-end justify-between">
                <span className="text-xs text-h-muted">
                  v{est.current_rev_no ?? "?"}
                </span>
                <span className="font-mono text-sm text-h-ink">
                  {est.current_total_inc_gst
                    ? `$${parseFloat(est.current_total_inc_gst).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                    : "—"}
                </span>
              </div>
              {est.converted_project_id ? (
                <div className="mt-2 text-xs text-green-700">
                  Converted → project #{est.converted_project_id}
                </div>
              ) : null}
            </Link>
          ))
        )}
      </div>

      {showNew ? (
        <NewEstimateDialog
          customers={customers}
          onClose={() => setShowNew(false)}
          onCreated={(eid) => router.push(`/estimating/${eid}`)}
        />
      ) : null}
    </section>
  );
}

interface NewEstimateDialogProps {
  customers: Customer[];
  onClose: () => void;
  onCreated: (eid: number) => void;
}

function NewEstimateDialog({ customers, onClose, onCreated }: NewEstimateDialogProps) {
  const [customerId, setCustomerId] = useState<number | null>(
    customers[0]?.customer_id ?? null,
  );
  const [title, setTitle] = useState("");
  const [siteAddress, setSiteAddress] = useState("");
  const [newCustomerName, setNewCustomerName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      let cid = customerId;
      if (newCustomerName.trim()) {
        const r = await fetch("/api/customers", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name: newCustomerName.trim() }),
        });
        if (!r.ok) {
          setError(`Customer create failed (${r.status})`);
          return;
        }
        const cust = (await r.json()) as Customer;
        cid = cust.customer_id;
      }
      if (cid == null) {
        setError("Pick a customer or enter a new name.");
        return;
      }
      const r2 = await fetch("/api/estimates", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          customer_id: cid,
          title: title.trim(),
          site_address: siteAddress.trim() || null,
        }),
      });
      if (!r2.ok) {
        setError(`Create failed (${r2.status})`);
        return;
      }
      const body = (await r2.json()) as { estimate_id: number };
      onCreated(body.estimate_id);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/40">
      <form
        onSubmit={submit}
        className="w-full max-w-md space-y-3 rounded border border-h-line bg-white p-5 shadow-xl"
      >
        <h2 className="text-lg font-semibold text-h-ink">New estimate</h2>

        <div>
          <label className="block text-xs font-medium uppercase text-h-muted">
            Customer
          </label>
          <select
            value={customerId ?? ""}
            onChange={(e) => setCustomerId(Number(e.target.value) || null)}
            className="mt-1 w-full rounded border border-h-line bg-white px-2 py-1 text-sm"
          >
            {customers.length === 0 ? <option value="">No customers</option> : null}
            {customers.map((c) => (
              <option key={c.customer_id} value={c.customer_id}>
                {c.name}
              </option>
            ))}
          </select>
          <input
            type="text"
            placeholder="…or add a new customer"
            value={newCustomerName}
            onChange={(e) => setNewCustomerName(e.target.value)}
            className="mt-2 w-full rounded border border-h-line bg-white px-2 py-1 text-sm"
          />
        </div>

        <div>
          <label className="block text-xs font-medium uppercase text-h-muted">
            Title
          </label>
          <input
            required
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className="mt-1 w-full rounded border border-h-line bg-white px-2 py-1 text-sm"
            data-testid="estimate-title"
          />
        </div>

        <div>
          <label className="block text-xs font-medium uppercase text-h-muted">
            Site address
          </label>
          <input
            value={siteAddress}
            onChange={(e) => setSiteAddress(e.target.value)}
            className="mt-1 w-full rounded border border-h-line bg-white px-2 py-1 text-sm"
          />
        </div>

        {error ? (
          <div className="rounded bg-red-50 px-3 py-2 text-sm text-red-800">{error}</div>
        ) : null}

        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded border border-h-line bg-white px-3 py-1.5 text-sm hover:bg-gray-50"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={submitting}
            className="rounded bg-h-accent px-3 py-1.5 text-sm font-medium text-white shadow hover:opacity-90 disabled:opacity-50"
          >
            {submitting ? "Creating…" : "Create"}
          </button>
        </div>
      </form>
    </div>
  );
}
