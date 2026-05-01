export type RevisionStatus = "draft" | "pending" | "approved" | "rejected";

export interface FileBlob {
  file_blob_id: number;
  sha256: string;
  mime: string;
  byte_size: number;
  original_filename: string;
  deduped: boolean;
}

export interface DrawingCard {
  drawing_id: number;
  project_id: number;
  project_code: string;
  title: string;
  room: string | null;
  archived_at: string | null;
  current_revision_id: number | null;
  latest_rev_no: number;
  latest_status: RevisionStatus;
  latest_uploaded_at: string;
  latest_uploaded_by_name: string | null;
  latest_reviewed_at: string | null;
  latest_reviewed_by_name: string | null;
  latest_file_blob_id: number;
}

export interface DrawingList {
  drawings: DrawingCard[];
  total: number;
  awaiting_review: number;
  distinct_rooms: number;
}

export interface Revision {
  revision_id: number;
  rev_no: number;
  status: RevisionStatus;
  file_blob_id: number;
  file_mime: string;
  uploaded_by: number;
  uploaded_by_name: string | null;
  uploaded_at: string;
  reviewed_by: number | null;
  reviewed_by_name: string | null;
  reviewed_at: string | null;
  review_note: string | null;
}

export interface DrawingDetail {
  drawing_id: number;
  project_id: number;
  project_code: string;
  title: string;
  room: string | null;
  current_revision_id: number | null;
  archived_at: string | null;
  archived_by: number | null;
  created_by: number;
  created_at: string;
  revisions: Revision[];
}

export type Subtab = "current" | "in_review" | "archive";
