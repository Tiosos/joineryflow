export type RevisionStatus = "draft" | "pending" | "approved" | "rejected";

export interface FileBlob {
  file_blob_id: number;
  sha256: string;
  mime: string;
  byte_size: number;
  original_filename: string;
  deduped: boolean;
}

export type DrawingType = "IFA" | "IFC";

/** Register queues, derived server-side from the latest revision's status plus
 *  submitted_at / archived_at (see shop_drawings/schemas.py). */
export type StatusQueue =
  | "being_drawn"
  | "internal_review"
  | "update_required"
  | "completed"
  | "awaiting_submission"
  | "submitted"
  | "archive";
export type Queue = "all" | StatusQueue;

export const QUEUE_ORDER: StatusQueue[] = [
  "update_required",
  "being_drawn",
  "internal_review",
  "completed",
  "awaiting_submission",
  "submitted",
  "archive",
];

export const QUEUE_LABELS: Record<Queue, string> = {
  all: "Register",
  being_drawn: "Being Drawn",
  internal_review: "Internal Review",
  update_required: "Update Required",
  completed: "Completed",
  awaiting_submission: "Awaiting Submission",
  submitted: "Submitted",
  archive: "Archive",
};

/** The register's "Overdue" flag: a due date before today on a drawing that is
 *  still being worked on (not completed, and not archived). */
export function isOverdue(d: {
  due_date: string | null;
  queue: string;
  archived_at: string | null;
}): boolean {
  if (!d.due_date || d.archived_at || d.queue === "completed") return false;
  const t = new Date();
  const iso = `${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, "0")}-${String(t.getDate()).padStart(2, "0")}`;
  return d.due_date < iso; // ISO dates compare lexically
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
  drawing_no: string | null;
  type: DrawingType;
  level: string | null;
  joinery_id: string | null;
  zone: string | null;
  room_no: string | null;
  assigned_to: number | null;
  assigned_to_name: string | null;
  due_date: string | null;
  submitted_at: string | null;
  queue: StatusQueue | string;
  comment_count: number;
}

export interface DrawingList {
  drawings: DrawingCard[];
  total: number;
  awaiting_review: number;
  distinct_rooms: number;
  queues: Record<StatusQueue, number>;
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
  drawing_no: string | null;
  type: DrawingType;
  level: string | null;
  joinery_id: string | null;
  zone: string | null;
  room_no: string | null;
  assigned_to: number | null;
  assigned_to_name: string | null;
  due_date: string | null;
  submitted_at: string | null;
  revisions: Revision[];
}

export interface HistoryEvent {
  event: string;
  actor_name: string | null;
  created_at: string;
  payload: Record<string, unknown>;
}

/** Register fields the details panel and upload dialog can set (all optional). */
export interface RegisterFields {
  type?: DrawingType;
  level?: string | null;
  joinery_id?: string | null;
  zone?: string | null;
  room_no?: string | null;
  assigned_to?: number | null;
  due_date?: string | null;
}
