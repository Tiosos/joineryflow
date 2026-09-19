"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import type { ProjectOut, TrackingItemRow } from "@/lib/pm-types";
import { ItemsTable } from "@/app/(app)/tracking/_components/ItemsTable";

interface Props {
  projects: ProjectOut[];
  items: TrackingItemRow[];
  selectedProjectId: number;
}

export default function ListClient({ projects, items, selectedProjectId }: Props) {
  const router = useRouter();
  const [cutlistQuery, setCutlistQuery] = useState("");
  const [freeQuery, setFreeQuery] = useState("");

  return (
    <div className="grid gap-3">
      <div className="flex flex-wrap items-center gap-3 rounded-lg border border-h-line bg-h-surface p-3">
        <label className="text-xs font-medium text-h-muted">Project</label>
        <select
          value={selectedProjectId}
          onChange={(e) => router.push(`/list?project_id=${e.target.value}`)}
          className="rounded border border-h-line bg-h-bg px-2 py-1.5 text-sm text-h-ink"
        >
          {projects.map((p) => (
            <option key={p.id} value={p.id}>
              {p.project_code} — {p.name}
            </option>
          ))}
        </select>
        <span className="ml-auto text-xs text-h-muted">
          {items.filter((i) => i.row_type !== "related_part").length} items
        </span>
      </div>

      <div className="flex flex-wrap items-center gap-2 rounded-lg border border-h-line bg-h-surface p-2">
        <input
          type="search"
          placeholder="Cutlist #"
          value={cutlistQuery}
          onChange={(e) => setCutlistQuery(e.target.value)}
          className="w-28 rounded border border-h-line bg-h-bg px-2 py-1 text-xs text-h-ink"
        />
        <input
          type="search"
          placeholder="Search items, rooms, codes…"
          value={freeQuery}
          onChange={(e) => setFreeQuery(e.target.value)}
          className="min-w-[200px] flex-1 rounded border border-h-line bg-h-bg px-2 py-1 text-xs text-h-ink"
        />
      </div>

      <ItemsTable
        items={items}
        cutlistQuery={cutlistQuery}
        freeQuery={freeQuery}
        onOpenItem={() => {}}
        onOpenStatus={() => {}}
      />
    </div>
  );
}
