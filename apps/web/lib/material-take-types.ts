// Material Take + Material Summary (sub-project #12) — mirrors
// apps/api/app/material_takes/schemas.py and material_summaries/schemas.py.
// Every quantity is a STRING: Pydantic Decimal serialises to a JSON string
// (see orders-types.ts); typing it `number` compiles and then breaks at runtime.

export type MaterialType =
  | "BOARD" | "HARDWARE" | "CUSTOM" | "BENCHTOP" | "APPLIANCE" | "HIRE" | "OTHER";
export type Unit = "sheet" | "each" | "m" | "m2";

export interface TakeLine {
  line_id: number;
  material_type: MaterialType;
  material_id: number | null;
  description: string;
  unit: Unit;
  qty_generated: string | null;
  wastage_pct: string;
  qty: string;
  source: "generated" | "manual";
  note: string | null;
}

export interface Take {
  take_id: number;
  item_id: number;
  version: number;
  status: "draft" | "approved" | "superseded";
  generated_at: string;
  approved_at: string | null;
  lines: TakeLine[];
}

export interface CurrentTake {
  item_id: number;
  draft: Take | null;
  approved: Take | null;
  outdated: boolean;
}

export interface TakeVersion {
  take_id: number;
  version: number;
  status: Take["status"];
  generated_at: string;
  approved_at: string | null;
}

export interface SummarySource {
  item_id: number;
  num: number | null;
  description: string | null;
  take_version: number;
  qty: string;
}

export interface SummaryLine {
  line_id: number;
  material_type: MaterialType;
  material_id: number | null;
  description: string;
  unit: Unit;
  qty_consolidated: string;
  qty_confirmed: string | null;
  note: string | null;
  stale: boolean;
  nest_sheets: number | null;
  qty_on_order: string | null;
  qty_received: string | null;
  sources: SummarySource[];
}

export interface Summary {
  summary_id: number;
  project_id: number;
  status: "draft" | "confirmed";
  confirmed_at: string | null;
  created_at: string;
  lines: SummaryLine[];
}

export interface MissingTake {
  item_id: number;
  num: number | null;
  description: string | null;
}

export interface CurrentSummary {
  summary: Summary | null;
  missing_takes: MissingTake[];
}

export const UNIT_LABEL: Record<Unit, string> = {
  sheet: "sheets", each: "ea", m: "m", m2: "m²",
};
