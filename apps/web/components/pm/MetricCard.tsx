import Link from "next/link";
import type { MetricCard as MetricCardData } from "@/lib/pm-types";

type MetricCardProps = Omit<MetricCardData, "key">;

function formatValue(value: number, unit: MetricCardProps["unit"]): string {
  if (unit !== "money") return String(value);
  return `$${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function MetricCard({ label, value, href, unit }: MetricCardProps) {
  const body = (
    <>
      <div className="text-xs text-h-muted uppercase tracking-wide">{label}</div>
      <div className="mt-2 text-3xl font-mono tabular-nums text-h-ink">{formatValue(value, unit)}</div>
    </>
  );
  if (href == null) {
    return (
      <div data-testid="metric-card" className="block rounded-lg border border-h-line bg-h-surface p-4">
        {body}
      </div>
    );
  }
  return (
    <Link
      href={href}
      data-testid="metric-card"
      className="block rounded-lg border border-h-line bg-h-surface p-4 transition-colors hover:bg-h-bg"
    >
      {body}
    </Link>
  );
}
