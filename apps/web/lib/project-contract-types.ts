// Contract Value + variations (Plan V1 §16-17, Q491) and the derived
// actual-costs rollup (Q493/Q549). Money and quantities travel as JSON
// strings (Pydantic Decimal) — the orders-types.ts / material-take-types.ts
// lesson: type them `number` and `.toFixed` throws.

export interface ContractVariation {
  variation_id: number;
  project_id: number;
  description: string;
  amount_delta: string;
  created_at: string;
  created_by: number | null;
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
  labour_actual: string;
  total_actual: string;
  labour_by_item: Record<string, string>;
}
