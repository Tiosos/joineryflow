export type AttachmentKind =
  | "cv_drawing"
  | "sketchup"
  | "cabvision"
  | "floor_plan"
  | "site_measure";

// Canonical order the bundle returns (matches item_attachments/queries.py::ALL_KINDS).
export const ATTACHMENT_KINDS: readonly AttachmentKind[] = [
  "cv_drawing",
  "sketchup",
  "cabvision",
  "floor_plan",
  "site_measure",
] as const;

// The three slots Combined PDF assembly actually uses (unchanged since #5b —
// sketchup/cabvision are purely additive, per CLAUDE.md's Item & Project
// Detail 2.0 section). Use this, not ATTACHMENT_KINDS, for any "N of 3"
// Combined-PDF copy or filtering.
export const COMBINED_PDF_KINDS: readonly AttachmentKind[] = [
  "cv_drawing",
  "floor_plan",
  "site_measure",
] as const;

export const KIND_LABELS: Record<AttachmentKind, string> = {
  cv_drawing: "CV Production Drawing",
  sketchup: "SketchUp Model",
  cabvision: "Cabinet Vision Job",
  floor_plan: "Floor Plan",
  site_measure: "Site Measure",
};

export interface AttachmentSlot {
  kind: AttachmentKind;
  file_blob_id: number | null;
  original_filename: string | null;
  byte_size: number | null;
  uploaded_by: number | null;
  uploaded_by_name: string | null;
  uploaded_at: string | null;
}

export interface AttachmentsBundle {
  item_id: number;
  slots: AttachmentSlot[];
}
