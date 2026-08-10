"use client";

import { useEffect, useState } from "react";
import { fetchItemCutPlan } from "@/lib/cut-floor-fetch";
import type { ItemCutPlanOut } from "@/lib/cut-floor-types";
import { SheetCanvas } from "@/app/(app)/cut-floor/_components/SheetCanvas";

interface BoardTabProps {
  itemId: number;
}

export function BoardTab({ itemId }: BoardTabProps) {
  const [data, setData] = useState<ItemCutPlanOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchItemCutPlan(itemId)
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch((e: Error) => {
        if (!cancelled) setError(e.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [itemId]);

  if (loading) {
    return (
      <div className="rounded-lg border border-h-line bg-h-surface p-8 text-center text-h-muted">
        Loading cut plan…
      </div>
    );
  }
  if (error) {
    return (
      <div className="rounded-lg border border-h-line bg-h-surface p-8 text-center text-h-muted">
        Could not load cut plan: {error}
      </div>
    );
  }
  if (!data || !data.plan) {
    return (
      <div className="rounded-lg border border-h-line bg-h-surface p-8 text-center text-h-muted">
        No CutPlan yet for this project.
      </div>
    );
  }

  const createdAt = new Date(data.plan.created_at);
  const createdLabel = isNaN(createdAt.getTime())
    ? data.plan.created_at
    : createdAt.toLocaleDateString();

  return (
    <div className="flex flex-col gap-4">
      <div className="rounded-lg border border-h-line bg-h-surface p-4">
        <div className="text-sm text-h-muted">Project CutPlan</div>
        <div className="mt-1 text-lg font-medium text-h-ink">
          {data.plan.name}
        </div>
        <div className="mt-1 text-xs text-h-muted">
          Created {createdLabel}
          {data.plan.created_by ? ` · by user #${data.plan.created_by}` : ""}
          {" · "}
          {data.plan.sheet_count} sheet
          {data.plan.sheet_count === 1 ? "" : "s"} · {data.plan.slot_count}{" "}
          slot{data.plan.slot_count === 1 ? "" : "s"}
        </div>
        {data.plan.notes && (
          <div className="mt-2 text-sm text-h-ink">{data.plan.notes}</div>
        )}
      </div>

      {data.sheets.length === 0 ? (
        <div className="rounded-lg border border-h-line bg-h-surface p-8 text-center text-h-muted">
          This item has no parts assigned to any sheet of the latest plan.
        </div>
      ) : (
        data.sheets.map((sheet) => (
          <SheetCanvas
            key={sheet.id}
            sheetNo={sheet.sheet_no}
            materialSku={sheet.material_sku}
            slots={sheet.slots}
          />
        ))
      )}
    </div>
  );
}
