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
    const body = await r.json().catch(() => ({}));
    // status + body ride on the error so a 409 lock refusal can be worded (lockFromError)
    throw Object.assign(
      new Error(typeof body?.detail === "string" ? body.detail : `bind failed: ${r.status}`),
      { status: r.status, body },
    );
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
    const body = await r.json().catch(() => ({}));
    throw Object.assign(new Error(`clear failed: ${r.status}`), { status: r.status, body });
  }
}
