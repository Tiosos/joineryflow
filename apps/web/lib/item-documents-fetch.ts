import type { ItemDocumentOut, PatchDocumentIn } from "./pm-types";

/** status + body ride on the error so a 409 lock refusal can be worded (`lockFromError`). */
async function fail(r: Response, what: string): Promise<never> {
  const body = await r.json().catch(() => ({}));
  throw Object.assign(
    new Error(typeof body?.detail === "string" ? body.detail : `${what} failed: ${r.status}`),
    { status: r.status, body },
  );
}

export async function listDocuments(itemId: number): Promise<ItemDocumentOut[]> {
  const r = await fetch(`/api/items/${itemId}/documents`);
  if (!r.ok) return fail(r, "list documents");
  return r.json();
}

export async function bindDocument(
  itemId: number,
  fileBlobId: number,
  label: string | null,
  sortOrder: number,
): Promise<ItemDocumentOut> {
  const r = await fetch(`/api/items/${itemId}/documents`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ file_blob_id: fileBlobId, label, sort_order: sortOrder }),
  });
  if (!r.ok) return fail(r, "bind document");
  return r.json();
}

export async function patchDocument(
  documentId: number,
  patch: PatchDocumentIn,
): Promise<ItemDocumentOut> {
  const r = await fetch(`/api/documents/${documentId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  if (!r.ok) return fail(r, "update document");
  return r.json();
}

export async function unbindDocument(documentId: number): Promise<void> {
  const r = await fetch(`/api/documents/${documentId}`, { method: "DELETE" });
  if (!r.ok && r.status !== 404) return fail(r, "remove document");
}
