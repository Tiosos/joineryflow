"use client";

import { useEffect, useState } from "react";
import { ErrorLine } from "./ErrorLine";
import { Field } from "./Field";

export function EditableDateField({
  label, value, canEdit, onSave, error,
}: {
  label: string;
  value: string | null;
  canEdit: boolean;
  onSave: (v: string) => Promise<boolean>;
  error?: string;
}) {
  const [v, setV] = useState(value ?? "");
  useEffect(() => setV(value ?? ""), [value]);
  if (!canEdit) return <Field label={label} value={value} mono />;
  return (
    <div>
      <dt className="text-[10px] uppercase tracking-wide text-h-muted">{label}</dt>
      <input
        type="date"
        value={v}
        onChange={e => setV(e.target.value)}
        onBlur={async () => {
          if (v === (value ?? "")) return;
          if (!(await onSave(v))) setV(value ?? "");
        }}
        className="h-mono w-full rounded border border-h-line bg-h-bg px-1 py-0.5 text-h-ink focus:outline-none focus:ring-1 focus:ring-h-accent"
      />
      {error && <ErrorLine msg={error} />}
    </div>
  );
}
