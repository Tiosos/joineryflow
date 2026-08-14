"use client";

import Link from "next/link";
import { ProjectMaterialsTable } from "./ProjectMaterialsTable";
import { BatchesTable } from "./BatchesTable";
import { CatalogTabs } from "./CatalogTabs";

const TABS = ["materials", "batches", "catalog"] as const;
type Tab = (typeof TABS)[number];

interface Props {
  projectId: number;
  tab: Tab;
  canWrite: boolean;
  canWriteCatalog: boolean;
  sp: Record<string, string | undefined>;
}

export function ProcurementTabs({ projectId, tab, canWrite, canWriteCatalog, sp }: Props) {
  return (
    <>
      <nav role="tablist" className="flex gap-1 border-b border-h-line">
        {TABS.map((t) => (
          <Link
            key={t}
            role="tab"
            aria-selected={tab === t}
            href={`/projects/${projectId}/procurement?tab=${t}`}
            className={[
              "px-3 py-2 text-sm capitalize",
              tab === t
                ? "border-b-2 border-h-accent text-h-ink"
                : "text-h-muted hover:text-h-ink",
            ].join(" ")}
          >
            {t}
          </Link>
        ))}
      </nav>
      <div className="pt-4">
        {tab === "materials" && (
          <ProjectMaterialsTable projectId={projectId} canWrite={canWrite} sp={sp} />
        )}
        {tab === "batches" && (
          <BatchesTable projectId={projectId} canWrite={canWrite} sp={sp} />
        )}
        {tab === "catalog" && (
          <CatalogTabs canWrite={canWriteCatalog} catalogType={sp.catalog_type} />
        )}
      </div>
    </>
  );
}
