"use client";
import { useState } from "react";
import type { ItemOut } from "@/lib/pm-types";
import { ModuleTree } from "./ModuleTree";
import { PartsGrid } from "./PartsGrid";

interface CutlistTabProps {
  item: ItemOut;
}

export function CutlistTab({ item }: CutlistTabProps) {
  const [activeModuleId, setActiveModuleId] = useState<number | null>(
    item.modules[0]?.id ?? null
  );

  const activeModule = item.modules.find((m) => m.id === activeModuleId) ?? null;

  if (item.modules.length === 0 && activeModuleId === null) {
    return (
      <div className="flex gap-4">
        <ModuleTree
          itemId={item.id}
          modules={item.modules}
          activeModuleId={null}
          onSelect={setActiveModuleId}
        />
        <div className="flex-1 rounded-lg border border-h-line bg-h-surface p-8 text-center text-h-muted">
          Add a module to start the cutlist.
        </div>
      </div>
    );
  }

  return (
    <div className="flex gap-4">
      <ModuleTree
        itemId={item.id}
        modules={item.modules}
        activeModuleId={activeModuleId}
        onSelect={setActiveModuleId}
      />
      {activeModule ? (
        <PartsGrid key={activeModule.id} itemId={item.id} module={activeModule} />
      ) : (
        <div className="flex-1 text-sm text-h-muted">Select a module.</div>
      )}
    </div>
  );
}
