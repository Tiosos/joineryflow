"use client";

import type { CatalogRow as Row, CatalogSlug } from "@/lib/catalog-types";

import type { CatalogTab } from "./CatalogClient";
import CatalogRow from "./CatalogRow";

interface Props {
  tab: CatalogTab;
  slug: CatalogSlug;
  rows: Row[];
  canWrite: boolean;
  onChanged: () => void;
}

const LEGACY_COL_LABEL: Record<Exclude<CatalogTab, "cv-mappings">, string> = {
  board: "Code",
  hardware: "—",
  custom_made: "Internal ref",
  benchtop: "Slab id",
  appliance: "Model #",
  hire: "Contract ref",
};

export default function CatalogGrid(p: Props) {
  if (p.tab === "cv-mappings") return null;
  const legacyLabel = LEGACY_COL_LABEL[p.tab];

  return (
    <div className="overflow-x-auto rounded border border-h-line">
      <table className="min-w-full text-sm">
        <thead className="bg-h-surface text-h-muted">
          <tr className="text-left">
            <th className="px-3 py-2">Description</th>
            <th className="px-3 py-2">SKU</th>
            <th className="px-3 py-2">{legacyLabel}</th>
            <th className="px-3 py-2">Default supplier</th>
            <th className="px-3 py-2">Lead (d)</th>
            <th className="px-3 py-2">Synonyms</th>
            <th className="px-3 py-2">Status</th>
            <th className="px-3 py-2"></th>
          </tr>
        </thead>
        <tbody>
          {p.rows.length === 0 && (
            <tr><td colSpan={8} className="px-3 py-6 text-center text-h-muted">No rows.</td></tr>
          )}
          {p.rows.map((r) => (
            <CatalogRow
              key={(r.material_id ?? r.hire_id) as number}
              tab={p.tab}
              slug={p.slug}
              row={r}
              canWrite={p.canWrite}
              onChanged={p.onChanged}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}
