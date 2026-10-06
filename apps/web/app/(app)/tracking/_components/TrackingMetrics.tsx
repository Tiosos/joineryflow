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
  // The tracking list carries related parts inline (Q558). They are not items
  // in the job and have no stages at all (Q419), so counting them would both
  // inflate "Items in job" and drag the installed percentage down against a
  // denominator of rows that can never be installed.
  const joineryItems = items.filter((i) => i.row_type !== "related_part");
  const total = joineryItems.length;

  let overdue = 0;
  let dueWeek = 0;
  let installed = 0;
  for (const it of joineryItems) {
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
    <section className="flex flex-wrap items-center gap-x-8 gap-y-1 rounded-lg border border-h-line bg-h-surface px-4 py-2">
      <Metric label="Items in job" value={total} subtitle="joinery items, related parts not counted" />
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
    <div className="flex items-baseline gap-2">
      <span className="text-[10px] font-semibold uppercase tracking-wider text-h-muted">{label}</span>
      <span className={`font-mono text-lg font-semibold tabular-nums ${valueColor}`}>{value}</span>
      {subtitle ? <span className="text-[11px] text-h-muted">{subtitle}</span> : null}
    </div>
  );
}
