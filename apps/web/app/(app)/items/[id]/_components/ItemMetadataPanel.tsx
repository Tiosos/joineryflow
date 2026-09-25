"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import type { ItemOut, PatchItemIn } from "@/lib/pm-types";
import { AreaRoomPicker } from "./AreaRoomPicker";

interface Props {
  item: ItemOut;
  /** Drafter-narrow gate, as everywhere else that mutates an item. */
  canEdit?: boolean;
}

// Room # / Room Description / Stage left this list in C6: they are now the
// Area and Room selectors below, which write the same three columns server-side
// (Q454/Q455, migration 0026). Typing free text into them would let an item's
// area and room drift out of the entities that now own them.
const FIELDS: {
  key: keyof PatchItemIn;
  label: string;
  type?: "text" | "checkbox" | "number";
}[] = [
  { key: "level", label: "Level" },
  { key: "description", label: "Description" },
  { key: "qty", label: "Qty", type: "number" },
  { key: "painting_required", label: "Painting required?", type: "checkbox" },
  {
    key: "solid_surface_required",
    label: "Solid surface required?",
    type: "checkbox",
  },
  // Item & Project Detail 2.0 (#11): Cutlist Printed and the three reference
  // fields below join the existing two flags here rather than a separate
  // header-chip / "Refs panel" component — same varchar(64)/boolean PATCH
  // pattern already handled by BoolField/MetaField, one place a user already
  // looks for per-item flags.
  { key: "cutlist_printed", label: "Cutlist printed?", type: "checkbox" },
  { key: "floor_plan", label: "Floor Plan" },
  { key: "rls", label: "RLS" },
  { key: "joiery_details", label: "Joinery Details" },
];

interface BoolFieldProps {
  label: string;
  initialValue: boolean;
  onToggle: (v: boolean) => Promise<boolean>;
}

function BoolField({ label, initialValue, onToggle }: BoolFieldProps) {
  const [checked, setChecked] = useState(initialValue);

  async function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    const next = e.target.checked;
    setChecked(next); // optimistic
    const success = await onToggle(next);
    if (!success) setChecked(!next); // rollback
  }

  return (
    <label className="flex items-center gap-2 text-sm text-h-ink cursor-pointer">
      <input
        type="checkbox"
        checked={checked}
        onChange={handleChange}
        className="rounded border-h-line"
      />
      {label}
    </label>
  );
}

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

export function ItemMetadataPanel({ item, canEdit = true }: Props) {
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
        // Controlled Lock: a non-owner's save is held for approval, not lost.
        // The field still reverts, because the item itself has not changed.
        const held =
          res.status === 409 &&
          (await res.json().catch(() => null))?.detail?.code ===
            "LOCK_REQUEST_CREATED";
        setErrors((e) => ({
          ...e,
          [field as string]: held
            ? "Held for the lock owner to approve"
            : `Save failed (${res.status})`,
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
        {/* Q454/Q455: Area and Room are entities now, so these are selectors
            rather than free text. Q458 allows the move and item_edit_log
            records it. */}
        <AreaRoomPicker
          projectId={item.project_id}
          areaId={item.area_id ?? null}
          roomId={item.room_id ?? null}
          canEdit={canEdit}
          onChange={async (next) => {
            setErrors((e) => ({ ...e, area_room: "" }));
            const res = await fetch(`/api/items/${item.id}`, {
              method: "PATCH",
              headers: { "content-type": "application/json" },
              body: JSON.stringify(next),
            });
            if (!res.ok) {
              const body = await res.json().catch(() => null);
              const code = body?.detail?.code;
              setErrors((e) => ({
                ...e,
                area_room:
                  code === "LOCK_REQUEST_CREATED"
                    ? "Held for the lock owner to approve"
                    : code === "ROOM_WITHOUT_AREA"
                      ? "Choose an area first — rooms belong to one"
                      : code === "BAD_ROOM"
                        ? "That room is not in this area"
                        : `Save failed (${res.status})`,
              }));
              return false;
            }
            router.refresh();
            return true;
          }}
        />
        {errors.area_room && (
          <span className="text-xs text-[#b4443d]">{errors.area_room}</span>
        )}
        {FIELDS.map((f) => {
          const v = item[f.key as keyof ItemOut] as unknown;
          if (f.type === "checkbox") {
            return (
              <div key={f.key as string}>
                <BoolField
                  label={f.label}
                  initialValue={Boolean(v)}
                  onToggle={(next) => patchField(f.key, next)}
                />
                {errors[f.key as string] && (
                  <span className="text-xs text-h-bad">
                    {errors[f.key as string]}
                  </span>
                )}
              </div>
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
        {/* group_id is read-only in v1 — not exposed in PatchItemIn */}
        {item.group_id && (
          <div className="space-y-1">
            <p className="text-xs text-h-muted">Group ID</p>
            <p className="text-sm text-h-ink font-mono">{item.group_id}</p>
          </div>
        )}
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
