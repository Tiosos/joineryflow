export type SampleStatus = "pending" | "approved" | "rejected";
export type SampleSubtab = "board" | "archive";

export interface Sample {
  sample_id: number;
  project_id: number;
  project_code: string;
  title: string;
  room: string | null;
  hex_swatch: string;
  supplier: string | null;
  status: SampleStatus;
  review_note: string | null;
  reviewed_by: number | null;
  reviewed_by_name: string | null;
  reviewed_at: string | null;
  photo_file_blob_id: number | null;
  photo_filename: string | null;
  archived_at: string | null;
  archived_by: number | null;
  created_by: number;
  created_by_name: string | null;
  created_at: string;
  updated_at: string;
}

export interface SampleListResp {
  samples: Sample[];
  total: number;
  counts: { pending: number; approved: number; rejected: number };
}

export interface LedgerEntry {
  id: number;
  actor_id: number | null;
  actor_name: string | null;
  event: string;
  sample_id: number;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface LedgerResp {
  entries: LedgerEntry[];
  total: number;
  limit: number;
  offset: number;
}
