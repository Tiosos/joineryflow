export type AttachmentKind = "cv_drawing" | "floor_plan" | "site_measure";

export const ATTACHMENT_KINDS: readonly AttachmentKind[] = [
  "cv_drawing",
  "floor_plan",
  "site_measure",
] as const;

export const KIND_LABELS: Record<AttachmentKind, string> = {
  cv_drawing: "CV Production Drawing",
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
