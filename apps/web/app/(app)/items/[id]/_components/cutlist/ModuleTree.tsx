"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { PM } from "@/lib/pm-fetch";
import type { ModuleOut } from "@/lib/pm-types";

interface ModuleTreeProps {
  itemId: number;
  modules: ModuleOut[];
  activeModuleId: number | null;
  onSelect: (id: number) => void;
}

export function ModuleTree({ itemId, modules, activeModuleId, onSelect }: ModuleTreeProps) {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);

  async function addModule() {
    try {
      const nextNo = String(modules.length + 1).padStart(2, "0");
      const m = await PM.createModule(itemId, { module_no: nextNo, name: "New module" });
      setError(null);
      router.refresh();
      onSelect(m.id);
    } catch {
      setError("Failed to add module");
    }
  }

  return (
    <aside className="w-[220px] shrink-0 flex flex-col gap-1">
      {modules.map((m) => (
        <button
          key={m.id}
          type="button"
          onClick={() => onSelect(m.id)}
          className={[
            "w-full text-left px-3 py-2 text-sm rounded transition-colors",
            m.id === activeModuleId
              ? "bg-h-accent/15 border-l-2 border-h-accent font-medium text-h-ink"
              : "text-h-muted hover:bg-h-surface hover:text-h-ink border-l-2 border-transparent",
          ].join(" ")}
        >
          {m.name ?? "Untitled module"}
        </button>
      ))}
      {error && <p className="text-xs text-h-bad px-3">{error}</p>}
      <button
        type="button"
        onClick={addModule}
        className="mt-2 rounded border border-dashed border-h-line px-3 py-2 text-sm text-h-muted hover:border-h-accent hover:text-h-ink transition-colors"
      >
        + Add module
      </button>
    </aside>
  );
}
