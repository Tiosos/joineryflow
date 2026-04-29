"use client";
import type { MaterialType } from "@/lib/procurement-types";

const LABEL: Record<MaterialType, string> = {
  BOARD:"Board", HARDWARE:"Hardware", CUSTOM:"Custom",
  BENCHTOP:"Benchtop", APPLIANCE:"Appliance", HIRE:"Hire",
};

export function MaterialTypeTag({ type }: { type: MaterialType }) {
  return <span className="rounded border border-h-line px-1.5 py-0.5 text-xs text-h-muted">{LABEL[type]}</span>;
}
