"use client";

import { useState } from "react";
import { apiCall, jsonInit } from "@/lib/api";
import type { PaymentMethod } from "@/lib/po-types";

const INPUT = "w-full rounded border border-h-line bg-h-bg px-1.5 py-1 text-h-ink focus:outline-none focus:ring-1 focus:ring-h-accent disabled:opacity-60";
const MINI = "rounded border border-h-line bg-h-bg px-1.5 py-0.5 text-h-muted hover:text-h-ink";

/**
 * The Payment Method / Payment Type choice. The list is the workspace's (`/payment-methods`); a
 * purchase officer or admin (`canKeep`) can add to it, rename or switch off an entry from "Edit list".
 * A switched-off entry stays visible while it is the chosen one and cannot be picked again.
 */
export function PaymentMethodSelect({
  label, value, methods, canKeep, disabled, onChange, onListChanged, testId,
}: {
  label: string; value: number | null; methods: PaymentMethod[]; canKeep: boolean; disabled?: boolean;
  onChange: (id: number | null) => void; onListChanged: () => void; testId: string;
}) {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const shown = methods.filter(m => m.is_active || m.payment_method_id === value);

  async function run(fn: () => Promise<unknown>) {
    setErr(null);
    try { await fn(); onListChanged(); }
    catch (e) { setErr((e as Error).message === "PAYMENT_METHOD_EXISTS" ? "That name is already on the list" : "Could not save the list"); }
  }

  return (
    <div className="grid gap-1">
      <div className="flex items-center gap-2">
        <span className="text-h-muted">{label}</span>
        {canKeep && (
          <button type="button" data-testid={`${testId}-edit`} onClick={() => setEditing(e => !e)}
            className="ml-auto text-[10px] text-h-muted underline hover:text-h-ink">{editing ? "Done" : "Edit list"}</button>
        )}
      </div>
      <select aria-label={label} disabled={disabled} value={value ?? ""} data-testid={testId}
        onChange={e => onChange(e.target.value ? Number(e.target.value) : null)} className={INPUT}>
        <option value="" />
        {shown.map(m => <option key={m.payment_method_id} value={m.payment_method_id}>{m.name}{m.is_active ? "" : " (off)"}</option>)}
      </select>
      {editing && (
        <div data-testid={`${testId}-list`} className="grid gap-1 rounded border border-h-line bg-h-bg p-2">
          {methods.map(m => (
            <div key={m.payment_method_id} className="flex items-center gap-2">
              <input aria-label={`Rename ${m.name}`} defaultValue={m.name}
                onBlur={e => { const v = e.target.value.trim(); if (v && v !== m.name) void run(() => apiCall(`/api/payment-methods/${m.payment_method_id}`, jsonInit("PATCH", { name: v }))); }}
                className={`${INPUT} flex-1`} />
              <button type="button" className={MINI}
                onClick={() => void run(() => apiCall(`/api/payment-methods/${m.payment_method_id}`, jsonInit("PATCH", { is_active: !m.is_active })))}>
                {m.is_active ? "Switch off" : "Switch on"}</button>
            </div>
          ))}
          <div className="flex items-center gap-2">
            <input aria-label="New payment method" placeholder="New entry, e.g. Sam's credit card" value={name} data-testid={`${testId}-new`}
              onChange={e => setName(e.target.value)} className={`${INPUT} flex-1`} />
            <button type="button" data-testid={`${testId}-add`} disabled={!name.trim()} className={MINI}
              onClick={() => void run(async () => { await apiCall("/api/payment-methods", jsonInit("POST", { name: name.trim() })); setName(""); })}>Add</button>
          </div>
          {err && <p role="alert" className="text-[#b4443d]">{err}</p>}
        </div>
      )}
    </div>
  );
}
