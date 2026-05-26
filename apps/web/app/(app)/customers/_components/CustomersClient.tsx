"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import type { Me } from "@/lib/session";
import type { Customer } from "@/lib/estimating-types";

interface Props {
  me: Me;
  initialCustomers: Customer[];
  initialQ: string;
  initialIncludeArchived: boolean;
}

export default function CustomersClient({
  me,
  initialCustomers,
  initialQ,
  initialIncludeArchived,
}: Props) {
  const router = useRouter();
  const [showNew, setShowNew] = useState(false);
  const [q, setQ] = useState(initialQ);

  const canWrite =
    me.auth_role === "admin" ||
    me.auth_role === "manager" ||
    me.auth_role === "estimator";

  const updateUrl = useCallback(
    (patch: Record<string, string | null>) => {
      const params = new URLSearchParams();
      if (q && !("q" in patch)) params.set("q", q);
      if (initialIncludeArchived && !("include_archived" in patch))
        params.set("include_archived", "true");
      for (const [k, v] of Object.entries(patch)) {
        if (v == null || v === "") params.delete(k);
        else params.set(k, v);
      }
      router.replace(`/customers?${params.toString()}`);
    },
    [router, q, initialIncludeArchived],
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
          <h1 className="text-2xl font-semibold text-h-ink">Customers</h1>
          <p className="mt-1 text-sm text-h-muted">
            {initialCustomers.length} customer
            {initialCustomers.length === 1 ? "" : "s"}
          </p>
        </div>
        {canWrite ? (
          <button
            type="button"
            onClick={() => setShowNew(true)}
            className="rounded bg-h-accent px-3 py-1.5 text-sm font-medium text-white shadow hover:opacity-90"
            data-testid="new-customer-btn"
          >
            + New customer
          </button>
        ) : null}
      </header>

      <div className="flex items-center gap-3 border-b border-h-line pb-3">
        <input
          type="search"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search name, email, phone…"
          className="w-72 rounded border border-h-line bg-white px-2 py-1 text-sm"
          data-testid="customers-search"
        />
        <label className="flex items-center gap-1 text-sm text-h-muted">
          <input
            type="checkbox"
            checked={initialIncludeArchived}
            onChange={(e) =>
              updateUrl({ include_archived: e.target.checked ? "true" : null })
            }
          />
          Include archived
        </label>
      </div>

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
        {initialCustomers.length === 0 ? (
          <p className="col-span-full rounded border border-dashed border-h-line p-8 text-center text-sm text-h-muted">
            No customers yet.{" "}
            {canWrite ? (
              <button
                type="button"
                onClick={() => setShowNew(true)}
                className="text-h-accent underline"
              >
                + Create your first customer
              </button>
            ) : null}
          </p>
        ) : (
          initialCustomers.map((c) => (
            <Link
              key={c.customer_id}
              href={`/customers/${c.customer_id}`}
              className={`block rounded border border-h-line bg-h-surface p-4 transition hover:border-h-ink ${
                c.archived_at ? "opacity-50" : ""
              }`}
              data-testid={`customer-row-${c.customer_id}`}
            >
              <div className="flex items-baseline justify-between">
                <div>
                  <div className="text-sm font-semibold text-h-ink">{c.name}</div>
                  {c.email ? <div className="text-xs text-h-muted">{c.email}</div> : null}
                  {c.phone ? <div className="text-xs text-h-muted">{c.phone}</div> : null}
                </div>
                {c.archived_at ? (
                  <span className="rounded-full bg-gray-200 px-2 py-0.5 text-xs uppercase tracking-wide text-gray-700">
                    Archived
                  </span>
                ) : null}
              </div>
              {c.billing_address ? (
                <div className="mt-2 text-xs text-h-muted">{c.billing_address}</div>
              ) : null}
              {c.abn ? (
                <div className="mt-1 text-xs text-h-muted">ABN {c.abn}</div>
              ) : null}
            </Link>
          ))
        )}
      </div>

      {showNew ? (
        <NewCustomerDialog
          onClose={() => setShowNew(false)}
          onCreated={() => {
            setShowNew(false);
            router.refresh();
          }}
        />
      ) : null}
    </section>
  );
}

function NewCustomerDialog({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: () => void;
}) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [billing, setBilling] = useState("");
  const [abn, setAbn] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const r = await fetch("/api/customers", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: name.trim(),
          email: email.trim() || null,
          phone: phone.trim() || null,
          billing_address: billing.trim() || null,
          abn: abn.trim() || null,
        }),
      });
      if (!r.ok) {
        let msg = `Create failed (${r.status})`;
        try {
          const j = await r.json();
          if (j?.detail?.code) msg = j.detail.code;
        } catch {
          // ignore
        }
        setError(msg);
        return;
      }
      onCreated();
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
        <h2 className="text-lg font-semibold text-h-ink">New customer</h2>
        <Input label="Name" value={name} onChange={setName} required testid="customer-name" />
        <Input label="Email" value={email} onChange={setEmail} type="email" />
        <Input label="Phone" value={phone} onChange={setPhone} />
        <Input label="Billing address" value={billing} onChange={setBilling} />
        <Input label="ABN" value={abn} onChange={setAbn} />
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
            disabled={submitting || name.trim().length === 0}
            className="rounded bg-h-accent px-3 py-1.5 text-sm font-medium text-white shadow hover:opacity-90 disabled:opacity-50"
          >
            {submitting ? "Creating…" : "Create"}
          </button>
        </div>
      </form>
    </div>
  );
}

function Input({
  label,
  value,
  onChange,
  required,
  type = "text",
  testid,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  required?: boolean;
  type?: string;
  testid?: string;
}) {
  return (
    <div>
      <label className="block text-xs font-medium uppercase text-h-muted">
        {label}
      </label>
      <input
        type={type}
        required={required}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="mt-1 w-full rounded border border-h-line bg-white px-2 py-1 text-sm"
        data-testid={testid}
      />
    </div>
  );
}
