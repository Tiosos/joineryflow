"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import { listByType, listCatalog, listProductTypes, listSupplierOptions } from "@/lib/catalog-fetch";
import type { ByTypeResp, CatalogListResp, ProductTypesResp, SupplierOption } from "@/lib/catalog-types";

import CatalogBulkImportDialog from "./CatalogBulkImportDialog";
import CatalogFilters from "./CatalogFilters";
import CatalogGrid from "./CatalogGrid";
import CatalogTabs, { NO_TYPE } from "./CatalogTabs";
import MappingPanel from "./MappingPanel";
import NewCatalogRowDialog from "./NewCatalogRowDialog";
import StockPanel from "./StockPanel";
import { TABLE_KEYS, TABLE_LABEL, TAB_TO_SLUG, type TableKey } from "./tables";

interface Project { id: number; project_code: string; name: string; }
interface Me { id: number; auth_role: string; full_name: string; workspace_id: number; }

export type CatalogTab =
  | "types"
  | "board"
  | "hardware"
  | "custom_made"
  | "benchtop"
  | "appliance"
  | "hire"
  | "edging"
  | "glass"
  | "timber"
  | "stock"
  | "cv-mappings";

/** The six tabs backed by a catalog table. "types", "stock" and "cv-mappings"
 *  are their own views and have no catalog slug or legacy column. */
export type MaterialTab = TableKey;

function isMaterialTab(t: CatalogTab): t is MaterialTab {
  return t !== "cv-mappings" && t !== "stock" && t !== "types";
}

interface Props {
  me: Me;
  projects: Project[];
  initialTab: CatalogTab;
  /** `?ptype=`: the product type shown in the type view (NO_TYPE = items with no type). */
  initialPType: string | null;
  initialQ: string | null;
  initialSupplier: string | null;
  initialArchived: boolean;
  initialLink: "all" | "linked" | "unlinked";
  initialProjectId: number | null;
}

export default function CatalogClient(props: Props) {
  const router = useRouter();
  const sp = useSearchParams();

  const tab = props.initialTab;
  const q = props.initialQ;
  const supplier = props.initialSupplier;
  const archived = props.initialArchived;
  const link = props.initialLink;

  const [list, setList] = useState<CatalogListResp | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [newOpen, setNewOpen] = useState(false);
  const [productType, setProductType] = useState("");
  const [types, setTypes] = useState<ProductTypesResp | null>(null);
  const [byType, setByType] = useState<ByTypeResp | null>(null);
  // Which table "+ New" and "Bulk import" write to while a type tab is open.
  const [newTable, setNewTable] = useState<TableKey>("hardware");
  const [bulkOpen, setBulkOpen] = useState(false);
  const [reloadTick, setReloadTick] = useState(0);
  // null = not loaded or unreadable. `GET /suppliers` needs `orderbook:read`, a
  // different grant from the grid's `catalog:write`, so it can fail on its own.
  const [supplierOptions, setSupplierOptions] = useState<SupplierOption[] | null>(null);
  const [supplierError, setSupplierError] = useState(false);

  // Only the six material tabs map to a catalog slug; "stock" and
  // "cv-mappings" render their own panels.
  const inTypes = tab === "types";
  // Open the first type tab (else "No type") when none is named.
  const activeType: string | null = !inTypes ? null
    : props.initialPType ?? types?.types[0]?.product_type ?? (types && types.untyped > 0 ? NO_TYPE : null);
  const materialTab = isMaterialTab(tab) ? tab : null;
  const slug = materialTab ? TAB_TO_SLUG[materialTab] : null;
  const addTab: MaterialTab | null = inTypes ? newTable : materialTab;
  const addSlug = addTab ? TAB_TO_SLUG[addTab] : null;

  const isWriter = ["admin", "manager", "drafter", "editor"].includes(props.me.auth_role);

  useEffect(() => {
    if (slug == null) { setList(null); return; }
    setLoading(true); setError(null);
    listCatalog({ slug, q, supplier, archived })
      .then(setList)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [slug, q, supplier, archived, reloadTick]);

  useEffect(() => {
    if (!inTypes) { setTypes(null); return; }
    listProductTypes(archived).then(setTypes).catch((e) => setError(String(e)));
  }, [inTypes, archived, reloadTick]);

  useEffect(() => {
    if (!inTypes || activeType == null) { setByType(null); return; }
    setLoading(true); setError(null);
    listByType({ productType: activeType === NO_TYPE ? null : activeType, q, supplier, archived })
      .then(setByType)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [inTypes, activeType, q, supplier, archived, reloadTick]);

  useEffect(() => {
    if (!isWriter || (slug == null && !inTypes)) return;
    let live = true;
    listSupplierOptions()
      .then((l) => { if (live) { setSupplierOptions(l); setSupplierError(false); } })
      .catch(() => { if (live) { setSupplierOptions(null); setSupplierError(true); } });
    return () => { live = false; };
  }, [isWriter, slug, inTypes]);

  const updateUrl = useCallback((patch: Record<string, string | null>) => {
    const next = new URLSearchParams(sp.toString());
    for (const [k, v] of Object.entries(patch)) {
      if (v == null || v === "") next.delete(k); else next.set(k, v);
    }
    router.replace(`/catalog?${next.toString()}`);
  }, [router, sp]);

  const suppliers = useMemo(() => {
    const seen = new Set<string>();
    for (const r of list?.rows ?? []) if (r.default_supplier) seen.add(r.default_supplier);
    for (const g of byType?.groups ?? []) for (const r of g.rows) if (r.default_supplier) seen.add(r.default_supplier);
    return Array.from(seen).sort();
  }, [list, byType]);

  const productTypes = useMemo(() => {
    const seen = new Set<string>();
    for (const r of list?.rows ?? []) if (r.product_type) seen.add(r.product_type);
    return Array.from(seen).sort();
  }, [list]);

  const rows = useMemo(() => {
    let all = list?.rows ?? [];
    if (productType) all = all.filter((r) => r.product_type === productType);
    if (link === "linked") return all.filter((r) => r.default_supplier_id != null);
    if (link === "unlinked") return all.filter((r) => r.default_supplier_id == null);
    return all;
  }, [list, link, productType]);
  const unlinkedCount = (list?.rows ?? []).filter((r) => r.default_supplier_id == null).length;

  const typeRowCount = (byType?.groups ?? []).reduce((n, g) => n + g.rows.length, 0);
  const headerText =
    inTypes ? `${typeRowCount} items`
    : tab === "cv-mappings" ? "CV Mappings"
    : tab === "stock" ? "Sheet stock on hand"
    : `${rows.length} ${tab} rows`;

  return (
    <section className="space-y-4">
      <header className="flex items-baseline justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-h-ink">Catalog</h1>
          <p className="mt-1 text-sm text-h-muted">{headerText}</p>
        </div>
        {addTab && isWriter && (
          <div className="flex gap-2">
            {inTypes && (
              <select aria-label="Table for new items" value={newTable}
                      onChange={(e) => setNewTable(e.target.value as TableKey)}
                      className="rounded border border-h-line px-2 py-1 text-sm">
                {TABLE_KEYS.map((k) => <option key={k} value={k}>{TABLE_LABEL[k]}</option>)}
              </select>
            )}
            <button type="button" onClick={() => setBulkOpen(true)}
                    className="rounded border border-h-line px-3 py-1.5 text-sm">
              Bulk import
            </button>
            <button type="button" onClick={() => setNewOpen(true)}
                    className="rounded bg-h-accent px-3 py-1.5 text-sm text-white">
              + New
            </button>
          </div>
        )}
      </header>

      <CatalogTabs
        current={tab}
        activeType={activeType}
        types={types}
        onSelectType={(t) => updateUrl({ tab: null, ptype: t })}
        onSelectTab={(t) => updateUrl({ tab: t, ptype: null })}
      />

      {(materialTab || inTypes) && (
        <CatalogFilters
          searchValue={q ?? ""}
          selectedSupplier={supplier}
          archived={archived}
          link={link}
          showTypeFilter={materialTab != null}
          suppliers={suppliers}
          productTypes={productTypes}
          selectedType={productType}
          onTypeChange={setProductType}
          onSearchChange={(s) => updateUrl({ q: s || null })}
          onSupplierChange={(s) => updateUrl({ supplier: s })}
          onArchivedChange={(a) => updateUrl({ archived: a ? "true" : null })}
          onLinkChange={(l) => updateUrl({ link: l === "all" ? null : l })}
        />
      )}

      {materialTab && materialTab !== "hire" && !inTypes && list && unlinkedCount > 0 && (
        <p className="text-sm text-h-muted" data-testid="unlinked-count">
          {unlinkedCount} of {list.rows.length} rows have no supplier link — Generate Orders
          cannot order them.
        </p>
      )}
      {(materialTab || inTypes) && isWriter && supplierError && (
        <p className="text-sm text-rose-700" data-testid="suppliers-unreadable">
          Couldn&apos;t load suppliers, so links can&apos;t be changed here (it needs read access
          to the Orderbook).
        </p>
      )}

      {loading && <p className="text-sm text-h-muted">Loading…</p>}
      {error && <p className="text-sm text-rose-700">{error}</p>}

      {tab === "cv-mappings" && (
        <MappingPanel canWrite={isWriter} />
      )}

      {tab === "stock" && <StockPanel canWrite={isWriter} />}

      {materialTab && slug && list && (
        <CatalogGrid
          tab={materialTab}
          slug={slug}
          rows={rows}
          canWrite={isWriter}
          suppliers={supplierOptions}
          onChanged={() => setReloadTick((n) => n + 1)}
        />
      )}

      {inTypes && byType && byType.groups.length === 0 && !loading && (
        <p className="text-sm text-h-muted">No items of this type.</p>
      )}
      {inTypes && byType?.groups.map((g) => (
        <div key={g.type} className="space-y-2" data-testid={`type-group-${g.type}`}>
          <h2 className="text-sm font-medium text-h-ink">{TABLE_LABEL[g.type]} ({g.rows.length})</h2>
          <CatalogGrid
            tab={g.type}
            slug={TAB_TO_SLUG[g.type]}
            rows={link === "linked" ? g.rows.filter((r) => r.default_supplier_id != null)
              : link === "unlinked" ? g.rows.filter((r) => r.default_supplier_id == null) : g.rows}
            canWrite={isWriter}
            suppliers={supplierOptions}
            onChanged={() => setReloadTick((n) => n + 1)}
          />
        </div>
      ))}

      {newOpen && addTab && addSlug && (
        <NewCatalogRowDialog
          tab={addTab}
          slug={addSlug}
          productType={inTypes && activeType !== NO_TYPE ? activeType : null}
          projects={props.projects}
          suppliers={supplierOptions}
          onClose={() => setNewOpen(false)}
          onCreated={() => { setNewOpen(false); setReloadTick((n) => n + 1); }}
        />
      )}

      {bulkOpen && addTab && addSlug && (
        <CatalogBulkImportDialog
          slug={addSlug}
          onClose={() => setBulkOpen(false)}
          onCommitted={(resp) => {
            setBulkOpen(false);
            setReloadTick((n) => n + 1);
            if (resp.errors.length > 0) {
              window.alert(`Created ${resp.created}; ${resp.errors.length} errors`);
            }
          }}
        />
      )}
    </section>
  );
}
