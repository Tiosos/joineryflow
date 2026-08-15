"use client";

import { useEffect, useState } from "react";
import { createRow, listCatalog } from "@/lib/catalog-fetch";
import type { CatalogRow, CatalogSlug } from "@/lib/catalog-types";

const TYPES = ["board","hardware","custom_made","benchtop","appliance","hire"] as const;
type CatType = typeof TYPES[number];

// The canonical catalog surface is `/catalog/{slug}` (sub-project #7a) — it is
// workspace-scoped, Pydantic-validated, audited and soft-archive only. The old
// `/catalogs/{type}` namespace this tab used to call has been retired.
const SLUG: Record<CatType, CatalogSlug> = {
  board:       "board-materials",
  hardware:    "hardware-materials",
  custom_made: "custom-made",
  benchtop:    "benchtop-materials",
  appliance:   "appliances",
  hire:        "equipment-hire",
};

// `sku` + `description` are common to all six; the rest is the per-table legacy
// NOT NULL UNIQUE column, plus `project_id` for the project-scoped hire table.
const CREATE_FIELDS: Record<CatType, string[]> = {
  board:       ["code", "description", "sku"],
  hardware:    ["sku", "description"],
  custom_made: ["internal_ref", "description", "sku"],
  benchtop:    ["slab_id", "description", "sku"],
  appliance:   ["model_number", "description", "sku"],
  hire:        ["contract_ref", "project_id", "description", "sku"],
};

// Bookkeeping columns the rollup view has no use for.
const HIDDEN_COLUMNS = new Set([
  "type", "workspace_id", "archived_at", "archived_by",
]);

interface Props {
  canWrite: boolean;
  catalogType?: string;
}

export function CatalogTabs({ canWrite, catalogType }: Props) {
  const initial = (TYPES as readonly string[]).includes(catalogType ?? "")
    ? (catalogType as CatType) : "hardware";
  const [type, setType] = useState<CatType>(initial);
  const [rows, setRows] = useState<CatalogRow[]>([]);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [err, setErr] = useState<string | null>(null);

  async function refresh() {
    setErr(null);
    try {
      setRows((await listCatalog({ slug: SLUG[type] })).rows);
    } catch (e) { setErr(String(e)); }
  }
  useEffect(() => { refresh(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [type]);

  async function create() {
    // `project_id` is an int FK on equipment_hire; everything else is text.
    const payload: Record<string, unknown> = { ...draft };
    if (type === "hire" && draft.project_id) {
      payload.project_id = Number(draft.project_id);
    }
    try {
      await createRow(SLUG[type], payload);
    } catch (e) { setErr(String(e)); return; }
    setDraft({});
    refresh();
  }

  const columns = Object.keys(rows[0] ?? {}).filter(k => !HIDDEN_COLUMNS.has(k));

  return (
    <div className="grid gap-3">
      <nav className="flex gap-1 border-b border-h-line">
        {TYPES.map(t => (
          <button
            key={t}
            onClick={() => setType(t)}
            className={[
              "px-3 py-2 text-sm capitalize",
              t === type ? "border-b-2 border-h-accent text-h-ink" : "text-h-muted hover:text-h-ink",
            ].join(" ")}
          >{t.replace("_"," ")}</button>
        ))}
      </nav>

      {err && <p className="text-sm text-h-bad">{err}</p>}

      <table className="w-full text-sm">
        <thead className="bg-h-bg text-xs uppercase text-h-muted">
          <tr>
            {columns.map(k => (
              <th key={k} className="px-2 py-1 text-left">{k}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-t border-h-line">
              {columns.map(k => {
                const v = (r as unknown as Record<string, unknown>)[k];
                return (
                  <td key={k} className="px-2 py-1">
                    {Array.isArray(v) ? (v.join(", ") || "—") : String(v ?? "—")}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>

      {canWrite && (
        <div className="flex gap-2">
          {CREATE_FIELDS[type].map(f => (
            <input
              key={f}
              value={draft[f] ?? ""}
              onChange={e => setDraft(d => ({ ...d, [f]: e.target.value }))}
              placeholder={f === "project_id" ? "project_id (numeric)" : f}
              className="rounded border border-h-line bg-h-bg px-2 py-1 text-sm"
            />
          ))}
          <button onClick={create} className="rounded bg-h-accent px-3 py-1 text-sm text-white">+ Add</button>
        </div>
      )}
    </div>
  );
}
