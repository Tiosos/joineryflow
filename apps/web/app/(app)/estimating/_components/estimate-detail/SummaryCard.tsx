"use client";



export function SummaryCard({ label, value, bold }: { label: string; value: string; bold?: boolean }) {
  return (
    <div className="rounded border border-h-line bg-h-surface p-3">
      <div className="text-xs uppercase tracking-wide text-h-muted">{label}</div>
      <div
        className={`mt-1 font-mono ${bold ? "text-xl font-semibold text-h-ink" : "text-lg text-h-ink"}`}
        data-testid={`summary-${label.toLowerCase().replace(/[^a-z]+/g, "-")}`}
      >
        {value}
      </div>
    </div>
  );
}
