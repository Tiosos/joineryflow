"use client";

import type { CatalogTab } from "./CatalogClient";

interface Props {
  current: CatalogTab;
  onChange: (next: CatalogTab) => void;
}

const TABS: { key: CatalogTab; label: string }[] = [
  { key: "board",       label: "Board" },
  { key: "hardware",    label: "Hardware" },
  { key: "custom_made", label: "Custom" },
  { key: "benchtop",    label: "Benchtop" },
  { key: "appliance",   label: "Appliances" },
  { key: "hire",        label: "Equipment Hire" },
  { key: "stock",       label: "Sheet Stock" },
  { key: "cv-mappings", label: "CV Mappings" },
];

export default function CatalogTabs({ current, onChange }: Props) {
  return (
    <div className="flex items-center gap-1 border-b border-h-line pb-2">
      {TABS.map((t) => {
        const active = t.key === current;
        return (
          <button
            key={t.key}
            type="button"
            onClick={() => onChange(t.key)}
            className={`relative px-3 py-1.5 text-sm transition ${
              active ? "text-h-ink" : "text-h-muted hover:text-h-ink"
            }`}
          >
            {t.label}
            {active && <span className="absolute inset-x-1 -bottom-2 h-0.5 bg-h-accent" />}
          </button>
        );
      })}
    </div>
  );
}
