"use client";

// Shared SVG sheet renderer — used by the Board tab (item editor) and the
// Optimise dialog (cut-floor). Extracted from BoardTab in sub-project #9.

export interface CanvasSlot {
  x: number;
  y: number;
  w: number;
  h: number;
  label: string | null;
  is_foreign?: boolean;
}

const VIEWPORT_MAX_WIDTH = 800;
const SHEET_LONG_EDGE_MM = 2440; // canonical reference

export function inferSheetExtent(
  slots: CanvasSlot[],
): { width: number; height: number } {
  if (slots.length === 0) return { width: 2440, height: 1220 };
  const maxX = Math.max(...slots.map((s) => s.x + s.w));
  const maxY = Math.max(...slots.map((s) => s.y + s.h));
  return {
    width: Math.max(maxX, SHEET_LONG_EDGE_MM),
    height: Math.max(maxY, 1220),
  };
}

interface SheetCanvasProps {
  sheetNo: number;
  materialSku: string;
  slots: CanvasSlot[];
  // When the sheet dimensions are known (e.g. the optimiser sheet stock),
  // pass them explicitly; otherwise the extent is inferred from the slots.
  extent?: { width: number; height: number };
}

export function SheetCanvas({
  sheetNo,
  materialSku,
  slots,
  extent,
}: SheetCanvasProps) {
  const ext = extent ?? inferSheetExtent(slots);
  const scale = VIEWPORT_MAX_WIDTH / ext.width;
  const w = ext.width * scale;
  const h = ext.height * scale;

  return (
    <div className="rounded-lg border border-h-line bg-h-surface p-4">
      <div className="mb-2 flex items-baseline justify-between text-sm">
        <div className="font-medium text-h-ink">Sheet {sheetNo}</div>
        <div className="font-mono text-xs text-h-muted">
          {materialSku} · {Math.round(ext.width)}×{Math.round(ext.height)} mm
        </div>
      </div>
      <div className="overflow-x-auto">
        <svg
          viewBox={`0 0 ${w} ${h}`}
          width={w}
          height={h}
          className="block bg-h-bg"
          role="img"
          aria-label={`Cut sheet ${sheetNo}`}
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
          {slots.map((slot, i) => {
            const x = slot.x * scale;
            const y = slot.y * scale;
            const sw = slot.w * scale;
            const sh = slot.h * scale;
            const fill = slot.is_foreign ? "var(--h-line)" : "var(--h-accent)";
            const opacity = slot.is_foreign ? 0.3 : 0.6;
            const label = slot.label ?? `slot ${i + 1}`;
            return (
              <g key={i}>
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
                    {label}
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
                    {label}
                  </text>
                )}
              </g>
            );
          })}
        </svg>
      </div>
    </div>
  );
}
