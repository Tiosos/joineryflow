"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import type { ItemOut, PatchItemIn } from "@/lib/pm-types";

interface Props {
  item: ItemOut;
}

const FIELDS: {
  key: keyof PatchItemIn;
  label: string;
  type?: "text" | "checkbox" | "number";
}[] = [
  { key: "level", label: "Level" },
  { key: "room_no", label: "Room #" },
  { key: "room_desc", label: "Room Description" },
  { key: "description", label: "Description" },
  { key: "stage", label: "Stage (site location)" },
  { key: "qty", label: "Qty", type: "number" },
  { key: "painting_required", label: "Painting required?", type: "checkbox" },
  {
    key: "solid_surface_required",
    label: "Solid surface required?",
    type: "checkbox",
  },
];

interface MetaFieldProps {
  label: string;
  defaultValue: string;
  type?: "text" | "number";
  onBlurSave: (v: string) => Promise<boolean>;
}

function MetaField({ label, defaultValue, type = "text", onBlurSave }: MetaFieldProps) {
  const [value, setValue] = useState(defaultValue);

  async function handleBlur() {
    const restored = defaultValue;
    const success = await onBlurSave(value);
    if (!success) {
      setValue(restored);
    }
  }

  return (
    <div className="space-y-1">
      <label className="block text-xs text-h-muted">{label}</label>
      <input
        type={type}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onBlur={handleBlur}
        className="w-full rounded border border-h-line bg-h-bg px-2 py-1 text-sm text-h-ink focus:outline-none focus:ring-1 focus:ring-h-accent"
      />
    </div>
  );
}

function NotesField({
  defaultValue,
  onBlurSave,
}: {
  defaultValue: string;
  onBlurSave: (v: string) => Promise<boolean>;
}) {
  const [value, setValue] = useState(defaultValue);

  async function handleBlur() {
    const success = await onBlurSave(value);
    if (!success) setValue(defaultValue);
  }

  return (
    <textarea
      rows={3}
      value={value}
      onChange={(e) => setValue(e.target.value)}
      onBlur={handleBlur}
      className="w-full rounded border border-h-line bg-h-bg px-2 py-1 text-sm text-h-ink focus:outline-none focus:ring-1 focus:ring-h-accent resize-none"
    />
  );
}

export function ItemMetadataPanel({ item }: Props) {
  const router = useRouter();
  const [errors, setErrors] = useState<Record<string, string>>({});

  async function patchField(field: keyof PatchItemIn, value: unknown): Promise<boolean> {
    setErrors((e) => ({ ...e, [field as string]: "" }));
    try {
      const res = await fetch(`/api/items/${item.id}`, {
        method: "PATCH",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ [field]: value }),
      });
      if (!res.ok) {
        setErrors((e) => ({
          ...e,
          [field as string]: `Save failed (${res.status})`,
        }));
        return false;
      }
      router.refresh();
      return true;
    } catch {
      setErrors((e) => ({
        ...e,
        [field as string]: `Failed to save ${field as string}`,
      }));
      return false;
    }
  }

  return (
    <aside className="rounded-lg border border-h-line bg-h-surface p-4">
      <h2 className="mb-3 text-sm font-semibold text-h-ink">Metadata</h2>
      <div className="grid gap-3">
        {FIELDS.map((f) => {
          const v = item[f.key as keyof ItemOut] as unknown;
          if (f.type === "checkbox") {
            return (
              <label
                key={f.key as string}
                className="flex items-center gap-2 text-sm"
              >
                <input
                  type="checkbox"
                  defaultChecked={Boolean(v)}
                  onChange={(e) => patchField(f.key, e.target.checked)}
                />
                <span className="text-h-ink">{f.label}</span>
                {errors[f.key as string] && (
                  <span className="text-xs text-h-bad">
                    {errors[f.key as string]}
                  </span>
                )}
              </label>
            );
          }
          const strVal = v == null ? "" : String(v);
          return (
            <div key={f.key as string}>
              <MetaField
                label={f.label}
                defaultValue={strVal}
                type={f.type === "number" ? "number" : "text"}
                onBlurSave={async (newStr) => {
                  const newVal =
                    f.type === "number"
                      ? newStr === ""
                        ? null
                        : Number(newStr)
                      : newStr === ""
                        ? null
                        : newStr;
                  if (newStr === strVal) return true;
                  return patchField(f.key, newVal);
                }}
              />
              {errors[f.key as string] && (
                <span className="text-xs text-h-bad">
                  {errors[f.key as string]}
                </span>
              )}
            </div>
          );
        })}
        <div>
          <label className="block text-xs font-medium uppercase text-h-muted mb-1">
            Estimator notes
          </label>
          <NotesField
            defaultValue={item.estimator_notes ?? ""}
            onBlurSave={(v) =>
              patchField("estimator_notes", v === "" ? null : v)
            }
          />
          {errors["estimator_notes"] && (
            <span className="text-xs text-h-bad">
              {errors["estimator_notes"]}
            </span>
          )}
        </div>
      </div>
    </aside>
  );
}
