"use client";

import type { ProductTypesResp } from "@/lib/catalog-types";

import type { CatalogTab } from "./CatalogClient";

/** The `ptype` of the "No type" tab. */
export const NO_TYPE = "__none__";

interface Props {
  current: CatalogTab;
  /** The product type shown while `current` is "types": a type name, or NO_TYPE. */
  activeType: string | null;
  types: ProductTypesResp | null;
  onSelectType: (type: string) => void;
  onSelectTab: (tab: CatalogTab) => void;
}

function TabButton({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`relative px-3 py-1.5 text-sm transition ${active ? "text-h-ink" : "text-h-muted hover:text-h-ink"}`}
    >
      {label}
      {active && <span className="absolute inset-x-1 -bottom-2 h-0.5 bg-h-accent" />}
    </button>
  );
}

/** One tab per product type in use, then "No type", Sheet Stock and CV Mappings. */
export default function CatalogTabs({ current, activeType, types, onSelectType, onSelectTab }: Props) {
  const inTypes = current === "types";
  return (
    <div className="flex flex-wrap items-center gap-1 border-b border-h-line pb-2">
      {(types?.types ?? []).map((t) => (
        <TabButton key={t.product_type} label={`${t.product_type} (${t.count})`}
                   active={inTypes && activeType === t.product_type} onClick={() => onSelectType(t.product_type)} />
      ))}
      {types != null && types.untyped > 0 && (
        <TabButton label={`No type (${types.untyped})`} active={inTypes && activeType === NO_TYPE}
                   onClick={() => onSelectType(NO_TYPE)} />
      )}
      <TabButton label="Sheet Stock" active={current === "stock"} onClick={() => onSelectTab("stock")} />
      <TabButton label="CV Mappings" active={current === "cv-mappings"} onClick={() => onSelectTab("cv-mappings")} />
    </div>
  );
}
