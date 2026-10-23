// Contract Value + variations (Plan V1 §16-17, Q491) and the derived
// actual-costs rollup (Q493/Q549). Money and quantities travel as JSON
// strings (Pydantic Decimal) — the orders-types.ts / material-take-types.ts
// lesson: type them `number` and `.toFixed` throws.

/** A Joinery Item a variation touches (Q609); `num` is the Item ID. */
export interface VariationItem {
  item_id: number;
  num: number;
  description: string | null;
}

export interface ContractVariation {
  variation_id: number;
  project_id: number;
  description: string;
  amount_delta: string;
  created_at: string;
  created_by: number | null;
  /** Q608: only Approved counts toward `current_value`. */
  status: "Draft" | "Approved" | "Rejected" | "Voided";
  decided_by: number | null;
  decided_at: string | null;
  decision_note: string | null;
  /** Q610: a voided variation keeps its approval but no longer counts. */
  voided_by: number | null;
  voided_at: string | null;
  void_reason: string | null;
  /** Empty = a project-level variation. */
  items: VariationItem[];
}

export interface ProjectContract {
  project_id: number;
  original_value: string;
  current_value: string;
  created_at: string;
  created_by: number | null;
  variations: ContractVariation[];
}

export interface ActualCosts {
  project_id: number;
  materials_actual: string;
  labour_actual: string | null;
  total_actual: string | null;
  unresolved_labour_completions: number;
  labour_by_item: Record<string, string | null>;
}
