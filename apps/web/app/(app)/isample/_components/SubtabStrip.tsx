"use client";

type Subtab = "board" | "ledger" | "archive";

interface Props {
  current: Subtab;
  onChange: (next: Subtab) => void;
  pendingCount: number;
}

const TABS: { key: Subtab; label: string }[] = [
  { key: "board",   label: "Board" },
  { key: "ledger",  label: "Approval ledger" },
  { key: "archive", label: "Archive" },
];

export default function SubtabStrip({ current, onChange, pendingCount }: Props) {
  return (
    <div className="flex items-center gap-2 border-b border-h-line pb-2">
      {TABS.map((t) => {
        const active = t.key === current;
        const badge = t.key === "board" && pendingCount > 0
          ? <span className="ml-1.5 inline-flex items-center justify-center rounded-full bg-h-accent/15 px-1.5 text-xs text-h-accent">{pendingCount}</span>
          : null;
        return (
          <button
            key={t.key}
            type="button"
            onClick={() => onChange(t.key)}
            className={`relative px-3 py-1.5 text-sm transition ${
              active ? "text-h-ink" : "text-h-muted hover:text-h-ink"
            }`}
          >
            {t.label}{badge}
            {active && <span className="absolute inset-x-1 -bottom-2 h-0.5 bg-h-accent" />}
          </button>
        );
      })}
    </div>
  );
}
