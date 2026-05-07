"use client";
import { useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import type { ItemOut } from "@/lib/pm-types";
import { ModuleTree } from "./ModuleTree";
import { PartsGrid } from "./PartsGrid";
import { CvImportDialog } from "./CvImportDialog";

interface CutlistTabProps {
  item: ItemOut;
}

export function CutlistTab({ item }: CutlistTabProps) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const importOpen = searchParams.get("import") === "cv";

  const [activeModuleId, setActiveModuleId] = useState<number | null>(
    item.modules[0]?.id ?? null
  );

  const activeModule = item.modules.find((m) => m.id === activeModuleId) ?? null;

  function openImport() {
    const sp = new URLSearchParams(searchParams.toString());
    sp.set("tab", "cutlist");
    sp.set("import", "cv");
    router.push(`?${sp.toString()}`);
  }

  function closeImport() {
    const sp = new URLSearchParams(searchParams.toString());
    sp.delete("import");
    router.push(`?${sp.toString()}`);
    router.refresh();
  }

  return (
    <>
      <div className="mb-3 flex items-center justify-end">
        <button
          type="button"
          onClick={openImport}
          className="rounded-md border border-h-line bg-h-bg px-3 py-1 text-sm font-medium text-h-ink hover:bg-h-surface"
        >
          Import from CV
        </button>
      </div>

      {item.modules.length === 0 ? (
        <div className="flex gap-4">
          <ModuleTree
            itemId={item.id}
            modules={item.modules}
            activeModuleId={null}
            onSelect={setActiveModuleId}
          />
          <div className="flex-1 rounded-lg border border-h-line bg-h-surface p-8 text-center text-h-muted">
            Add a module to start the cutlist, or click <strong>Import from CV</strong>.
          </div>
        </div>
      ) : (
        <div className="flex gap-4">
          <ModuleTree
            itemId={item.id}
            modules={item.modules}
            activeModuleId={activeModuleId}
            onSelect={setActiveModuleId}
          />
          {activeModule ? (
            <PartsGrid key={activeModule.id} module={activeModule} />
          ) : (
            <div className="flex-1 text-sm text-h-muted">Select a module.</div>
          )}
        </div>
      )}

      {importOpen && (
        <CvImportDialog
          itemId={item.id}
          itemHasModules={item.modules.length > 0}
          existingModuleCount={item.modules.length}
          onClose={closeImport}
        />
      )}
    </>
  );
}
