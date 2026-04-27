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
  { key: "estimator_notes", label: "Estimator notes" },
];

export function ItemMetadataPanel({ item }: Props) {
  const router = useRouter();
  const [errors, setErrors] = useState<Record<string, string>>({});

  async function patchField(key: string, value: unknown) {
    setErrors((e) => ({ ...e, [key]: "" }));
    const res = await fetch(`/api/items/${item.id}`, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ [key]: value }),
    });
    if (!res.ok) {
      setErrors((e) => ({ ...e, [key]: `Save failed (${res.status})` }));
      return;
    }
    router.refresh();
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
                  onChange={(e) =>
                    patchField(f.key as string, e.target.checked)
                  }
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
          return (
            <label key={f.key as string} className="grid gap-1">
              <span className="text-xs font-medium uppercase text-h-muted">
                {f.label}
              </span>
              <input
                type={f.type ?? "text"}
                defaultValue={v == null ? "" : String(v)}
                onBlur={(e) => {
                  const newVal =
                    f.type === "number"
                      ? e.target.value === ""
                        ? null
                        : Number(e.target.value)
                      : e.target.value === ""
                        ? null
                        : e.target.value;
                  const oldStr = v == null ? "" : String(v);
                  if (e.target.value === oldStr) return;
                  patchField(f.key as string, newVal);
                }}
                className="rounded border border-h-line bg-h-bg px-2 py-1 text-sm text-h-ink"
              />
              {errors[f.key as string] && (
                <span className="text-xs text-h-bad">
                  {errors[f.key as string]}
                </span>
              )}
            </label>
          );
        })}
      </div>
    </aside>
  );
}
