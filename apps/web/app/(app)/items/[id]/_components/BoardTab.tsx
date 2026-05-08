"use client";

import { useEffect, useState } from "react";
import { fetchItemCutPlan } from "@/lib/cut-floor-fetch";
import type {
  CutSheetOut,
  ItemCutPlanOut,
  PartSlotOut,
} from "@/lib/cut-floor-types";

interface BoardTabProps {
  itemId: number;
}

const VIEWPORT_MAX_WIDTH = 800;
const SHEET_LONG_EDGE_MM = 2440; // canonical reference

function inferSheetExtent(slots: PartSlotOut[]): { width: number; height: number } {
  if (slots.length === 0) return { width: 2440, height: 1220 };
  const maxX = Math.max(...slots.map((s) => s.x + s.w));
  const maxY = Math.max(...slots.map((s) => s.y + s.h));
  return {
    width: Math.max(maxX, SHEET_LONG_EDGE_MM),
    height: Math.max(maxY, 1220),
  };
}

function SheetCanvas({ sheet }: { sheet: CutSheetOut }) {
  const ext = inferSheetExtent(sheet.slots);
  const scale = VIEWPORT_MAX_WIDTH / ext.width;
  const w = ext.width * scale;
  const h = ext.height * scale;

  return (
    <div className="rounded-lg border border-h-line bg-h-surface p-4">
      <div className="mb-2 flex items-baseline justify-between text-sm">
        <div className="font-medium text-h-ink">
          Sheet {sheet.sheet_no}
        </div>
        <div className="font-mono text-xs text-h-muted">
          {sheet.material_sku} · {ext.width}×{ext.height} mm
        </div>
      </div>
      <svg
        viewBox={`0 0 ${w} ${h}`}
        width={w}
        height={h}
        className="block bg-h-bg"
        role="img"
        aria-label={`Cut sheet ${sheet.sheet_no}`}
      >
        <rect
          x={0}
          y={0}
          width={w}
          height={h}
          fill="none"
          stroke="var(--h-line)"
          strokeWidth={1}
        />
        {sheet.slots.map((slot) => {
          const x = slot.x * scale;
          const y = slot.y * scale;
          const sw = slot.w * scale;
          const sh = slot.h * scale;
          const fill = slot.is_foreign
            ? "var(--h-line)"
            : "var(--h-accent)";
          const opacity = slot.is_foreign ? 0.3 : 0.6;
          return (
            <g key={slot.id}>
              <rect
                x={x}
                y={y}
                width={sw}
                height={sh}
                fill={fill}
                fillOpacity={opacity}
                stroke="var(--h-ink)"
                strokeOpacity={0.4}
                strokeWidth={0.5}
              >
                <title>
                  {slot.label ?? `slot ${slot.id}`}
                  {slot.is_foreign ? " (other item)" : ""}
                </title>
              </rect>
              {sw > 60 && sh > 24 && (
                <text
                  x={x + 4}
                  y={y + 14}
                  fontSize={11}
                  fill="var(--h-ink)"
                  fillOpacity={slot.is_foreign ? 0.5 : 0.85}
                  pointerEvents="none"
                >
                  {slot.label ?? `#${slot.id}`}
                </text>
              )}
            </g>
          );
        })}
      </svg>
    </div>
  );
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
          <SheetCanvas key={sheet.id} sheet={sheet} />
        ))
      )}
    </div>
  );
}
