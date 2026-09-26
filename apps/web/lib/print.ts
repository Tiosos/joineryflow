import type { AttachmentsBundle, AttachmentKind } from "./attachments-types";
import { COMBINED_PDF_KINDS, KIND_LABELS } from "./attachments-types";

export type PrintKind = "cutlist" | "hardware" | "combined";

export function printUrl(itemId: number, kind: PrintKind): string {
  return `/api/items/${itemId}/${kind}.pdf`;
}

export function combinedTooltip(bundle: AttachmentsBundle | null): string {
  if (!bundle) return "Generate Combined PDF";
  const present: string[] = [];
  const missing: string[] = [];
  for (const kind of COMBINED_PDF_KINDS) {
    const slot = bundle.slots.find((s) => s.kind === kind);
    if (slot?.file_blob_id) present.push(KIND_LABELS[kind]);
    else missing.push(KIND_LABELS[kind]);
  }
  const lines: string[] = ["Combined PDF — opens in new tab."];
  if (present.length) lines.push(`Includes: ${present.join(", ")}.`);
  if (missing.length) lines.push(`Missing (placeholder pages): ${missing.join(", ")}.`);
  return lines.join("\n");
}

export function attachmentsCountLabel(bundle: AttachmentsBundle | null): string {
  if (!bundle) return "0 of 3 slots populated";
  // The bundle also carries sketchup / cabvision, which Combined does not use.
  const populated = bundle.slots.filter(
    (s) => COMBINED_PDF_KINDS.includes(s.kind) && s.file_blob_id != null,
  ).length;
  return `${populated} of 3 slots populated · used by Print Combined PDF`;
}

export function getKindFromSlot(slot: { kind: AttachmentKind }): AttachmentKind {
  return slot.kind;
}
