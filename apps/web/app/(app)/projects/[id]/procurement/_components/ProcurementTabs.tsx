"use client";

import { useState } from "react";
import { ProjectMaterialsTable } from "./ProjectMaterialsTable";
import BatchesTable from "./BatchesTable";
import CatalogTabs from "./CatalogTabs";

interface ProcurementTabsProps {
  projectId: string;
  userRole: string;
}

type TabName = "materials" | "batches" | "catalog";

export default function ProcurementTabs({
  projectId,
  userRole,
}: ProcurementTabsProps) {
  const [activeTab, setActiveTab] = useState<TabName>("materials");

  const tabs: { name: TabName; label: string }[] = [
    { name: "materials", label: "Project Materials" },
    { name: "batches", label: "Batches" },
    { name: "catalog", label: "Catalog" },
  ];

  return (
    <div className="flex-1 flex flex-col border-t border-h-line">
      <div className="flex border-b border-h-line">
        {tabs.map((tab) => (
          <button
            key={tab.name}
            onClick={() => setActiveTab(tab.name)}
            className={`px-4 py-3 font-medium text-sm transition-colors ${
              activeTab === tab.name
                ? "text-h-accent border-b-2 border-h-accent"
                : "text-h-muted hover:text-h-ink"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div className="flex-1 overflow-auto">
        {activeTab === "materials" && (
          <ProjectMaterialsTable projectId={Number(projectId)} canWrite={userRole !== "viewer"} sp={{}} />
        )}
        {activeTab === "batches" && (
          <BatchesTable projectId={projectId} userRole={userRole} />
        )}
        {activeTab === "catalog" && (
          <CatalogTabs projectId={projectId} userRole={userRole} />
        )}
      </div>
    </div>
  );
}
