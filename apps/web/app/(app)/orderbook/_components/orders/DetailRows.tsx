"use client";

import { useEffect, useState, type ReactNode } from "react";
import { ErrorLine } from "./ErrorLine";

/**
 * Label-left rows for the order pop-up, the layout of the old Orderbook's Details window. Each
 * editable row saves on blur and puts the old value back if the save is refused, like
 * `EditableField` (the Order panel's earlier one-column form).
 */
export function Row({ label, children, error, className = "" }: {
  label: string; children: ReactNode; error?: string; className?: string;
}) {
  return (
    <div className={`border-b border-h-line last:border-b-0 ${className}`}>
      <div className="grid grid-cols-[8.5rem_1fr] items-stretch">
        <dt className="flex items-center border-r border-h-line bg-h-bg px-2 py-1.5 text-[10px] font-semibold uppercase tracking-wide text-h-muted">
          {label}
        </dt>
        <dd className="px-2 py-1 text-h-ink">{children}</dd>
      </div>
      {error && <div className="px-2 pb-1"><ErrorLine msg={error} /></div>}
    </div>
  );
}

const INPUT = "w-full rounded border border-h-line bg-h-bg px-1 py-0.5 text-h-ink focus:outline-none focus:ring-1 focus:ring-h-accent";

export function TextRow({ label, value, canEdit, onSave, error, mono = false, type = "text", testId }: {
  label: string; value: string | null; canEdit: boolean;
  onSave: (v: string) => Promise<boolean>; error?: string; mono?: boolean;
  type?: "text" | "date"; testId?: string;
}) {
  const [v, setV] = useState(value ?? "");
  // Resync when the order refetches after another field's save, so a stale local value is never
  // sent again with a now-current `expected_versions`.
  useEffect(() => setV(value ?? ""), [value]);
  return (
    <Row label={label} error={error}>
      {canEdit ? (
        <input
          type={type}
          value={v}
          data-testid={testId}
          onChange={e => setV(e.target.value)}
          onBlur={async () => {
            if (v === (value ?? "")) return;
            if (!(await onSave(v))) setV(value ?? "");
          }}
          className={`${INPUT} ${mono ? "h-mono" : ""}`}
        />
      ) : (
        <span className={mono ? "h-mono" : ""}>{value || "—"}</span>
      )}
    </Row>
  );
}

export function AreaRow({ label, value, canEdit, onSave, error, rows = 2 }: {
  label: string; value: string | null; canEdit: boolean;
  onSave: (v: string) => Promise<boolean>; error?: string; rows?: number;
}) {
  const [v, setV] = useState(value ?? "");
  useEffect(() => setV(value ?? ""), [value]);
  return (
    <Row label={label} error={error}>
      {canEdit ? (
        <textarea
          rows={rows}
          value={v}
          onChange={e => setV(e.target.value)}
          onBlur={async () => {
            if (v === (value ?? "")) return;
            if (!(await onSave(v))) setV(value ?? "");
          }}
          className={`${INPUT} resize-none`}
        />
      ) : (
        <p className="whitespace-pre-wrap">{value || "—"}</p>
      )}
    </Row>
  );
}

export function CheckRow({ label, value, canEdit, onSave, error, testId }: {
  label: string; value: boolean | null; canEdit: boolean;
  onSave: (v: boolean) => Promise<boolean>; error?: string; testId?: string;
}) {
  return (
    <Row label={label} error={error}>
      <input
        type="checkbox"
        checked={!!value}
        disabled={!canEdit}
        data-testid={testId}
        onChange={e => void onSave(e.target.checked)}
        className="h-3.5 w-3.5 accent-[var(--color-h-accent)]"
      />
    </Row>
  );
}

export function SelectRow({ label, value, options, canEdit, onSave, error, testId }: {
  label: string; value: string; options: { value: string; label: string }[]; canEdit: boolean;
  onSave: (v: string) => Promise<boolean>; error?: string; testId?: string;
}) {
  return (
    <Row label={label} error={error}>
      {canEdit ? (
        <select
          value={value}
          data-testid={testId}
          onChange={e => void onSave(e.target.value)}
          className={INPUT}
        >
          {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
      ) : (
        <span>{options.find(o => o.value === value)?.label ?? value}</span>
      )}
    </Row>
  );
}
