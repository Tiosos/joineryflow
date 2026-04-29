"use client";
import type { BatchStatus } from "@/lib/procurement-types";

const COPY: Record<BatchStatus, { label: string; cls: string }> = {
  OPEN:       { label: "Open",       cls: "bg-h-muted/20 text-h-muted" },
  IN_TRANSIT: { label: "In transit", cls: "bg-h-warn/20 text-h-warn" },
  DELIVERED:  { label: "Delivered",  cls: "bg-h-good/20 text-h-good" },
  CANCELLED:  { label: "Cancelled",  cls: "bg-h-bad/20 text-h-bad" },
};

export function BatchStatusPill({ status }: { status: BatchStatus }) {
  const c = COPY[status];
  return <span className={`rounded px-1.5 py-0.5 text-xs ${c.cls}`}>{c.label}</span>;
}
