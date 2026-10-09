"use client";

import { useState } from "react";
import type { Line } from "@/lib/estimating-types";
import { CatalogMap, CallApiFn } from "./shared";
import { LineCard } from "./LineCard";

interface DraggableLineListProps {
  lines: Line[];
  isDraft: boolean;
  catalogs: CatalogMap;
  onReorder: (orderedLineIds: number[]) => Promise<void>;
  onChanged: () => Promise<void>;
  onClone: (line: Line) => Promise<void>;
  callApi: CallApiFn;
}

export function DraggableLineList({
  lines, isDraft, catalogs, onReorder, onChanged, onClone, callApi,
}: DraggableLineListProps) {
  const [draggedId, setDraggedId] = useState<number | null>(null);

  function handleDragStart(lid: number) {
    setDraggedId(lid);
  }

  function handleDragOver(e: React.DragEvent) {
    e.preventDefault();
  }

  async function handleDrop(targetLid: number) {
    if (draggedId == null || draggedId === targetLid) {
      setDraggedId(null);
      return;
    }
    const ids = lines.map((l) => l.line_id);
    const fromIdx = ids.indexOf(draggedId);
    const toIdx = ids.indexOf(targetLid);
    if (fromIdx < 0 || toIdx < 0) {
      setDraggedId(null);
      return;
    }
    const next = [...ids];
    next.splice(fromIdx, 1);
    next.splice(toIdx, 0, draggedId);
    setDraggedId(null);
    await onReorder(next);
  }

  return (
    <div className="space-y-3" data-testid="lines-list">
      {lines.map((line) => (
        <div
          key={line.line_id}
          draggable={isDraft}
          onDragStart={() => handleDragStart(line.line_id)}
          onDragOver={handleDragOver}
          onDrop={() => handleDrop(line.line_id)}
          className={draggedId === line.line_id ? "opacity-50" : ""}
        >
          <LineCard
            line={line}
            isDraft={isDraft}
            catalogs={catalogs}
            onChanged={onChanged}
            onClone={onClone}
            callApi={callApi}
          />
        </div>
      ))}
    </div>
  );
}
