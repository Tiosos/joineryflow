"use client";

import { useEffect, useState } from "react";

import { archiveRow, patchRow } from "@/lib/catalog-fetch";
import type { CatalogRow as Row, CatalogSlug } from "@/lib/catalog-types";

import type { CatalogTab } from "./CatalogClient";

interface Props {
  tab: CatalogTab;
  slug: CatalogSlug;
  row: Row;
  canWrite: boolean;
  onChanged: () => void;
}

const LEGACY_COL_KEY: Record<Exclude<CatalogTab, "cv-mappings">, keyof Row | null> = {
  board: "code",
  hardware: null,
  custom_made: "internal_ref",
  benchtop: "slab_id",
  appliance: "model_number",
  hire: "contract_ref",
};

function Cell({
  value, onSave, canWrite, type = "text",
}: {
  value: string | number | null;
  onSave: (v: string) => void | Promise<void>;
  canWrite: boolean;
  type?: "text" | "number";
}) {
  const [local, setLocal] = useState(value == null ? "" : String(value));
  useEffect(() => { setLocal(value == null ? "" : String(value)); }, [value]);

  if (!canWrite) return <span>{local || "—"}</span>;

  return (
    <input
      type={type}
      value={local}
      onChange={(e) => setLocal(e.target.value)}
      onBlur={() => {
        const orig = value == null ? "" : String(value);
        if (local !== orig) void onSave(local);
      }}
      className="w-full bg-transparent px-1 py-0.5 text-sm focus:bg-h-surface focus:outline focus:outline-1 focus:outline-h-line"
    />
  );
}

export default function CatalogRow({ tab, slug, row, canWrite, onChanged }: Props) {
  const mid = row.material_id ?? row.hire_id;
  if (mid == null) {
    // Defensive: shouldn't happen — every catalog row has either material_id (5 tables)
    // or hire_id (equipment_hire). Render an empty row rather than crashing.
    return null;
  }
  const legacyKey = tab === "cv-mappings" ? null : LEGACY_COL_KEY[tab];
  const legacyVal = legacyKey ? (row[legacyKey] as string | null | undefined) ?? "" : "—";
  const [busy, setBusy] = useState(false);

  const save = async (patch: Record<string, unknown>) => {
    setBusy(true);
    try {
      await patchRow(slug, mid, patch);
      onChanged();
    } catch (e) {
      window.alert(String(e));
    } finally {
      setBusy(false);
    }
  };

  const onArchive = async () => {
    if (!window.confirm("Archive this row?")) return;
    setBusy(true);
    try { await archiveRow(slug, mid); onChanged(); }
    catch (e) { window.alert(String(e)); }
    finally { setBusy(false); }
  };

  return (
    <tr className="border-t border-h-line">
      <td className="px-3 py-1">
        <Cell value={row.description} canWrite={canWrite}
              onSave={(v) => save({ description: v })} />
      </td>
      <td className="px-3 py-1 font-mono">
        <Cell value={row.sku} canWrite={canWrite}
              onSave={(v) => save({ sku: v })} />
      </td>
      <td className="px-3 py-1">
        {legacyKey
          ? <Cell value={legacyVal as string} canWrite={canWrite}
                  onSave={(v) => save({ [legacyKey]: v })} />
          : <span className="text-h-muted">—</span>}
      </td>
      <td className="px-3 py-1">
        <Cell value={row.default_supplier} canWrite={canWrite}
              onSave={(v) => save({ default_supplier: v || null })} />
      </td>
      <td className="px-3 py-1 w-20">
        <Cell value={row.default_lead_time_days} type="number" canWrite={canWrite}
              onSave={(v) => save({ default_lead_time_days: v === "" ? null : Number(v) })} />
      </td>
      <td className="px-3 py-1">
        <Cell value={row.synonyms.join(", ")} canWrite={canWrite}
              onSave={(v) => save({ synonyms: v.split(/\s*,\s*/).filter(Boolean) })} />
      </td>
      <td className="px-3 py-1 text-xs text-h-muted">
        {row.archived_at ? "Archived" : "Active"}
      </td>
      <td className="px-3 py-1">
        {canWrite && !row.archived_at && (
          <button onClick={onArchive} disabled={busy}
                  className="text-xs text-rose-700 hover:underline disabled:opacity-50">
            Archive
          </button>
        )}
      </td>
    </tr>
  );
}
