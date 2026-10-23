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
  created_by_name: string | null;
  /** Q611: `amount_delta` is the selling-price impact (Q612); cost impact is shown beside it, never summed. */
  number: number;
  reason: string | null; // empty only on variations that predate Q611
  requester: string | null;
  requested_on: string | null; // YYYY-MM-DD
  cost_impact: string | null; // Decimal string
  time_impact_days: number | null; // signed working days, informational
  /** Q608: only Approved counts toward `current_value`. */
  status: "Draft" | "Approved" | "Rejected" | "Voided";
  decided_by: number | null;
  decided_by_name: string | null;
  decided_at: string | null;
  decision_note: string | null;
  /** Q610: a voided variation keeps its approval but no longer counts. */
  voided_by: number | null;
  voided_by_name: string | null;
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
