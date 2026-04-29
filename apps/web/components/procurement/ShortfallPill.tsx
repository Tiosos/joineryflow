"use client";

interface Props { qty: number; }

export function ShortfallPill({ qty }: Props) {
  if (qty <= 0) {
    return <span className="rounded bg-h-good/20 px-1.5 py-0.5 text-xs text-h-good">OK</span>;
  }
  return (
    <span className="rounded bg-h-bad/20 px-1.5 py-0.5 text-xs text-h-bad">Short {qty}</span>
  );
}
