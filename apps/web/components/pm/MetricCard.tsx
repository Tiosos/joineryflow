import Link from "next/link";
import type { MetricCard as MetricCardData } from "@/lib/pm-types";

type MetricCardProps = Omit<MetricCardData, "key">;

export function MetricCard({ label, value, href }: MetricCardProps) {
  return (
    <Link
      href={href}
      data-testid="metric-card"
      className="block rounded-lg border border-h-line bg-h-surface p-4 transition-colors hover:bg-h-bg"
    >
      <div className="text-xs text-h-muted uppercase tracking-wide">{label}</div>
      <div className="mt-2 text-3xl font-mono tabular-nums text-h-ink">{value}</div>
    </Link>
  );
}
