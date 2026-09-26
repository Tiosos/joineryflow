"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import type { PatchProjectIn, ProjectOut } from "@/lib/pm-types";
import { PM } from "@/lib/pm-fetch";

interface Props {
  project: ProjectOut;
  /** PATCH /projects/{id} is manager/admin only (a manual route check, not
      the tracking:write RBAC row) — narrower than contacts/lift access. */
  canEdit: boolean;
}

const TEXT_FIELDS: { key: keyof PatchProjectIn; label: string }[] = [
  { key: "site_street", label: "Street" },
  { key: "site_suburb", label: "Suburb" },
  { key: "site_postcode", label: "Postcode" },
  { key: "site_state", label: "State" },
  { key: "tg_project_manager", label: "TG Project Manager" },
  { key: "tg_coordinator", label: "TG Coordinator" },
];

export function ProjectDetailsPanel({ project, canEdit }: Props) {
  const router = useRouter();
  const [errors, setErrors] = useState<Record<string, string>>({});

  async function patchField(field: keyof PatchProjectIn, value: unknown): Promise<boolean> {
    setErrors((e) => ({ ...e, [field as string]: "" }));
    try {
      await PM.patchProject(project.id, { [field]: value } as PatchProjectIn);
      router.refresh();
      return true;
    } catch {
      setErrors((e) => ({ ...e, [field as string]: "Save failed" }));
      return false;
    }
  }

  return (
    <section className="rounded-lg border border-h-line bg-h-surface p-4">
      <h2 className="mb-3 text-sm font-semibold text-h-ink">Details</h2>
      <div className="grid gap-3">
        {TEXT_FIELDS.map((f) => (
          <TextField
            key={f.key as string}
            label={f.label}
            defaultValue={(project[f.key as keyof ProjectOut] as string | null) ?? ""}
            disabled={!canEdit}
            error={errors[f.key as string]}
            onBlurSave={(v) => patchField(f.key, v === "" ? null : v)}
          />
        ))}
        <label className="flex items-center gap-2 text-sm text-h-ink">
          <input
            type="checkbox"
            checked={project.tg_solid ?? false}
            disabled={!canEdit}
            onChange={(e) => void patchField("tg_solid", e.target.checked)}
            className="rounded border-h-line"
          />
          TG Solid
        </label>
      </div>
    </section>
  );
}

function TextField({
  label,
  defaultValue,
  disabled,
  error,
  onBlurSave,
}: {
  label: string;
  defaultValue: string;
  disabled: boolean;
  error?: string;
  onBlurSave: (v: string) => Promise<boolean>;
}) {
  const [value, setValue] = useState(defaultValue);

  async function handleBlur() {
    if (value === defaultValue) return;
    const ok = await onBlurSave(value);
    if (!ok) setValue(defaultValue);
  }

  return (
    <div className="space-y-1">
      <label className="block text-xs text-h-muted">{label}</label>
      <input
        type="text"
        value={value}
        disabled={disabled}
        onChange={(e) => setValue(e.target.value)}
        onBlur={handleBlur}
        className="w-full rounded border border-h-line bg-h-bg px-2 py-1 text-sm text-h-ink focus:outline-none focus:ring-1 focus:ring-h-accent disabled:opacity-60"
      />
      {error && <span className="text-xs text-h-bad">{error}</span>}
    </div>
  );
}
