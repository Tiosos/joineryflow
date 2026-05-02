"use client";

import type { Subtab } from "@/lib/shop-drawings-types";

interface Props {
  current: Subtab;
  onChange: (next: Subtab) => void;
  counts: { total: number; awaiting_review: number };
}

const TABS: { key: Subtab; label: string }[] = [
  { key: "current", label: "Current" },
  { key: "in_review", label: "In review" },
  { key: "archive", label: "Archive" },
];

export default function SubtabStrip({ current, onChange, counts }: Props) {
  return (
    <div className="flex items-center gap-2 border-b border-h-line pb-2">
      {TABS.map((t) => {
        const active = t.key === current;
        const badge =
          t.key === "in_review" && counts.awaiting_review > 0 ? (
            <span className="ml-1.5 inline-flex items-center justify-center rounded-full bg-h-accent/15 px-1.5 text-xs text-h-accent">
              {counts.awaiting_review}
            </span>
          ) : null;
        return (
          <button
            key={t.key}
            type="button"
            onClick={() => onChange(t.key)}
            className={`relative rounded px-3 py-1.5 text-sm transition focus:outline-none focus:ring-2 focus:ring-h-accent ${
              active ? "text-h-ink" : "text-h-muted hover:text-h-ink"
            }`}
          >
            {t.label}
            {badge}
            {active && (
              <span className="absolute inset-x-1 -bottom-2 h-0.5 bg-h-accent" />
            )}
          </button>
        );
      })}
    </div>
  );
}
