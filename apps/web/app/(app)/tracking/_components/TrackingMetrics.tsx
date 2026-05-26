"use client";

import type { TrackingItemRow } from "@/lib/pm-types";

interface Props {
  items: TrackingItemRow[];
}

function todayISO(): string {
  return new Date().toISOString().slice(0, 10);
}

function inDaysISO(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}

export function TrackingMetrics({ items }: Props) {
  const today = todayISO();
  const weekOut = inDaysISO(7);
  const total = items.length;

  let overdue = 0;
  let dueWeek = 0;
  let installed = 0;
  for (const it of items) {
    let isOverdue = false;
    let isDueWeek = false;
    for (const sk of Object.keys(it.stages)) {
      const s = it.stages[sk];
      if (!s) continue;
      if (s.due_date && !s.done_date) {
        if (s.due_date < today) isOverdue = true;
        else if (s.due_date <= weekOut) isDueWeek = true;
      }
    }
    if (isOverdue) overdue++;
    if (isDueWeek) dueWeek++;
    const inst = it.stages.INST;
    if (inst?.done_date) installed++;
  }

  const pct = total > 0 ? Math.round((installed / total) * 100) : 0;

  return (
    <section className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      <Metric label="Items in job" value={total} subtitle="total" />
      <Metric label="Overdue" value={overdue} subtitle="across all stages" tone="bad" />
      <Metric label="Due this week" value={dueWeek} subtitle="within 7 days" tone="warn" />
      <Metric label="Installed" value={installed} subtitle={`${pct}% of total`} tone="good" />
    </section>
  );
}

interface MetricProps {
  label: string;
  value: number;
  subtitle?: string;
  tone?: "good" | "warn" | "bad";
}

function Metric({ label, value, subtitle, tone }: MetricProps) {
  const valueColor =
    tone === "bad"
      ? "text-[#b4443d]"
      : tone === "warn"
      ? "text-[#c48a2e]"
      : tone === "good"
      ? "text-[#3f7d48]"
      : "text-h-ink";
  return (
    <div className="rounded-lg border border-h-line bg-h-surface p-4">
      <div className="text-[10px] font-semibold uppercase tracking-wider text-h-muted">
        {label}
      </div>
      <div className={`mt-1 font-mono text-2xl font-semibold tabular-nums ${valueColor}`}>
        {value}
      </div>
      {subtitle ? (
        <div className="mt-1 text-[11px] text-h-muted">{subtitle}</div>
      ) : null}
    </div>
  );
}
