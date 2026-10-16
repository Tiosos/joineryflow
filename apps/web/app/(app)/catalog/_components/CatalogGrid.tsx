"use client";

import type { CatalogRow as Row, CatalogSlug, SupplierOption } from "@/lib/catalog-types";

import type { MaterialTab } from "./CatalogClient";
import { BOARD_TEXT_FIELDS } from "./boardFields";
import { EDGING_NUMBER_FIELDS, EDGING_TEXT_FIELDS } from "./edgingFields";
import CatalogRow from "./CatalogRow";

interface Props {
  tab: MaterialTab;
  slug: CatalogSlug;
  rows: Row[];
  canWrite: boolean;
  suppliers: SupplierOption[] | null;
  onChanged: () => void;
}

const LEGACY_COL_LABEL: Record<MaterialTab, string> = {
  board: "Code",
  hardware: "—",
  custom_made: "Internal ref",
  benchtop: "Slab id",
  appliance: "Model #",
  hire: "Contract ref",
  edging: "—",
};

export default function CatalogGrid(p: Props) {
  const legacyLabel = LEGACY_COL_LABEL[p.tab];
  const hasGrain = p.tab === "board" || p.tab === "benchtop";
  const isBoard = p.tab === "board";
  const isEdging = p.tab === "edging";
  const colCount = (hasGrain ? 12 : 11) + (isBoard ? BOARD_TEXT_FIELDS.length + 1 : 0)
    + (isEdging ? EDGING_TEXT_FIELDS.length + EDGING_NUMBER_FIELDS.length + 2 : 0);

  return (
    <div className="overflow-x-auto rounded border border-h-line">
      <table className="min-w-full text-sm">
        <thead className="bg-h-surface text-h-muted">
          <tr className="text-left">
            <th className="px-3 py-2">Description</th>
            <th className="px-3 py-2" title="The old system's product type">Type</th>
            <th className="px-3 py-2">SKU</th>
            <th className="px-3 py-2">{legacyLabel}</th>
            <th className="px-3 py-2">Default supplier</th>
            <th className="px-3 py-2" title="The supplier Generate Orders orders this material from">Supplier link</th>
            <th className="px-3 py-2">Lead (d)</th>
            <th className="px-3 py-2" title="Per unit, ex GST. An order made from this material starts at this price">Unit cost</th>
            {isBoard && BOARD_TEXT_FIELDS.map((f) => <th key={f.key} className="px-3 py-2">{f.label}</th>)}
            {isBoard && <th className="px-3 py-2">Image</th>}
            {isEdging && EDGING_TEXT_FIELDS.map((f) => <th key={f.key} className="px-3 py-2">{f.label}</th>)}
            {isEdging && EDGING_NUMBER_FIELDS.map((f) => <th key={f.key} className="px-3 py-2">{f.label}</th>)}
            {isEdging && <th className="px-3 py-2">Glued</th>}
            {isEdging && <th className="px-3 py-2">Image</th>}
            <th className="px-3 py-2">Synonyms</th>
            {hasGrain && <th className="px-3 py-2" title="Parts on this board are not rotated when nesting">Grain lock</th>}
            <th className="px-3 py-2">Status</th>
            <th className="px-3 py-2"></th>
          </tr>
        </thead>
        <tbody>
          {p.rows.length === 0 && (
            <tr><td colSpan={colCount} className="px-3 py-6 text-center text-h-muted">No rows.</td></tr>
          )}
          {p.rows.map((r) => {
            const key = r.material_id ?? r.hire_id;
            if (key == null) return null;
            return (
              <CatalogRow
                key={key}
                tab={p.tab}
                slug={p.slug}
                row={r}
                canWrite={p.canWrite}
                suppliers={p.suppliers}
                onChanged={p.onChanged}
              />
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
