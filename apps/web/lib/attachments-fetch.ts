import type {
  AttachmentKind,
  AttachmentsBundle,
} from "./attachments-types";

export async function getAttachments(itemId: number): Promise<AttachmentsBundle> {
  const r = await fetch(`/api/items/${itemId}/attachments`);
  if (!r.ok) throw new Error(`get attachments failed: ${r.status}`);
  return r.json();
}

export async function bindAttachment(
  itemId: number,
  kind: AttachmentKind,
  fileBlobId: number,
): Promise<void> {
  const r = await fetch(`/api/items/${itemId}/attachments/${kind}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ file_blob_id: fileBlobId }),
  });
  if (!r.ok) {
    const detail = await r.json().catch(() => ({}));
    throw new Error(detail?.detail ?? `bind failed: ${r.status}`);
  }
}

export async function clearAttachment(
  itemId: number,
  kind: AttachmentKind,
): Promise<void> {
  const r = await fetch(`/api/items/${itemId}/attachments/${kind}`, {
    method: "DELETE",
  });
  if (!r.ok && r.status !== 404) {
    throw new Error(`clear failed: ${r.status}`);
  }
}
