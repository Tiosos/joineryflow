"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import { listCatalog } from "@/lib/catalog-fetch";
import type { CatalogListResp, CatalogSlug } from "@/lib/catalog-types";

import CatalogBulkImportDialog from "./CatalogBulkImportDialog";
import CatalogFilters from "./CatalogFilters";
import CatalogGrid from "./CatalogGrid";
import CatalogTabs from "./CatalogTabs";
import MappingPanel from "./MappingPanel";
import NewCatalogRowDialog from "./NewCatalogRowDialog";

interface Project { id: number; project_code: string; name: string; }
interface Me { id: number; auth_role: string; full_name: string; workspace_id: number; }

export type CatalogTab =
  | "board"
  | "hardware"
  | "custom_made"
  | "benchtop"
  | "appliance"
  | "hire"
  | "cv-mappings";

const TAB_TO_SLUG: Record<Exclude<CatalogTab, "cv-mappings">, CatalogSlug> = {
  board: "board-materials",
  hardware: "hardware-materials",
  custom_made: "custom-made",
  benchtop: "benchtop-materials",
  appliance: "appliances",
  hire: "equipment-hire",
};

interface Props {
  me: Me;
  projects: Project[];
  initialTab: CatalogTab;
  initialQ: string | null;
  initialSupplier: string | null;
  initialArchived: boolean;
  initialProjectId: number | null;
}

export default function CatalogClient(props: Props) {
  const router = useRouter();
  const sp = useSearchParams();

  const tab = props.initialTab;
  const q = props.initialQ;
  const supplier = props.initialSupplier;
  const archived = props.initialArchived;

  const [list, setList] = useState<CatalogListResp | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [newOpen, setNewOpen] = useState(false);
  const [bulkOpen, setBulkOpen] = useState(false);
  const [reloadTick, setReloadTick] = useState(0);

  const slug = tab === "cv-mappings" ? null : TAB_TO_SLUG[tab];

  const isWriter = ["admin", "manager", "drafter", "editor"].includes(props.me.auth_role);

  useEffect(() => {
    if (slug == null) { setList(null); return; }
    setLoading(true); setError(null);
    listCatalog({ slug, q, supplier, archived })
      .then(setList)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [slug, q, supplier, archived, reloadTick]);

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
    return Array.from(seen).sort();
  }, [list]);

  const headerText = tab === "cv-mappings"
    ? "CV Mappings"
    : `${list?.rows.length ?? 0} ${tab} rows`;

  return (
    <section className="space-y-4">
      <header className="flex items-baseline justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-h-ink">Catalog</h1>
          <p className="mt-1 text-sm text-h-muted">{headerText}</p>
        </div>
        {tab !== "cv-mappings" && isWriter && (
          <div className="flex gap-2">
            <button onClick={() => setBulkOpen(true)}
                    className="rounded border border-h-line px-3 py-1.5 text-sm">
              Bulk import
            </button>
            <button onClick={() => setNewOpen(true)}
                    className="rounded bg-h-accent px-3 py-1.5 text-sm text-white">
              + New
            </button>
          </div>
        )}
      </header>

      <CatalogTabs current={tab} onChange={(t) => updateUrl({ tab: t })} />

      {tab !== "cv-mappings" && (
        <CatalogFilters
          searchValue={q ?? ""}
          selectedSupplier={supplier}
          archived={archived}
          suppliers={suppliers}
          onSearchChange={(s) => updateUrl({ q: s || null })}
          onSupplierChange={(s) => updateUrl({ supplier: s })}
          onArchivedChange={(a) => updateUrl({ archived: a ? "true" : null })}
        />
      )}

      {loading && <p className="text-sm text-h-muted">Loading…</p>}
      {error && <p className="text-sm text-rose-700">{error}</p>}

      {tab === "cv-mappings" && (
        <MappingPanel canWrite={isWriter} />
      )}

      {tab !== "cv-mappings" && slug && list && (
        <CatalogGrid
          tab={tab}
          slug={slug}
          rows={list.rows}
          canWrite={isWriter}
          onChanged={() => setReloadTick((n) => n + 1)}
        />
      )}

      {newOpen && tab !== "cv-mappings" && slug && (
        <NewCatalogRowDialog
          tab={tab}
          slug={slug}
          projects={props.projects}
          onClose={() => setNewOpen(false)}
          onCreated={() => { setNewOpen(false); setReloadTick((n) => n + 1); }}
        />
      )}

      {bulkOpen && tab !== "cv-mappings" && slug && (
        <CatalogBulkImportDialog
          slug={slug}
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
