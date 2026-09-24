// Global Search (sub-project #11) — mirrors apps/api/app/search/routes.py.

export type SearchType =
  | "project" | "item" | "related_part" | "cutlist" | "order" | "supplier"
  | "drawing" | "sample" | "customer" | "estimate" | "material";

export const TYPE_LABELS: Record<SearchType, string> = {
  project: "Projects",
  item: "Items",
  related_part: "Related parts",
  cutlist: "Cutlists",
  order: "Orders",
  supplier: "Suppliers",
  drawing: "Shop drawings",
  sample: "Samples",
  customer: "Customers",
  estimate: "Estimates",
  material: "Catalog",
};

export interface SearchHit {
  type: SearchType;
  entity_id: number;
  title: string;
  subtitle: string;
  codes: string[];
  status: string | null;
  archived: boolean;
  // null for suppliers: no supplier page exists yet (Q579).
  url: string | null;
  project_code: string | null;
}

export interface SearchResponse {
  hits: SearchHit[];
  total: number;
  type_counts: Partial<Record<SearchType, number>>;
}

export interface SearchHealth {
  meili: "ok" | "down";
  outbox_depth: number;
  oldest_enqueued_at: string | null;
}
