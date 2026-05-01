import type {
  DrawingDetail,
  DrawingList,
  RevisionStatus,
  Subtab,
} from "./shop-drawings-types";

interface ListParams {
  projectId: number;
  subtab: Subtab;
  room?: string | null;
  reviewerId?: number | null;
  q?: string | null;
}

export async function listDrawings(p: ListParams): Promise<DrawingList> {
  const q = new URLSearchParams({ subtab: p.subtab });
  if (p.room) q.set("room", p.room);
  if (p.reviewerId != null) q.set("reviewer_id", String(p.reviewerId));
  if (p.q) q.set("q", p.q);
  const r = await fetch(`/api/projects/${p.projectId}/shop-drawings?${q}`);
  if (!r.ok) throw new Error(`list drawings failed: ${r.status}`);
  return r.json();
}

export async function getDrawing(drawingId: number): Promise<DrawingDetail> {
  const r = await fetch(`/api/shop-drawings/${drawingId}`);
  if (!r.ok) throw new Error(`get drawing failed: ${r.status}`);
  return r.json();
}

export async function createDrawing(input: {
  projectId: number;
  title: string;
  room: string | null;
  fileBlobId: number;
  submitImmediately: boolean;
}): Promise<DrawingDetail> {
  const r = await fetch(`/api/projects/${input.projectId}/shop-drawings`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      title: input.title,
      room: input.room,
      file_blob_id: input.fileBlobId,
      submit_immediately: input.submitImmediately,
    }),
  });
  if (!r.ok) throw new Error((await r.json())?.detail ?? `create failed: ${r.status}`);
  return r.json();
}

export async function patchDrawing(
  drawingId: number,
  patch: { title?: string; room?: string | null }
): Promise<DrawingDetail> {
  const r = await fetch(`/api/shop-drawings/${drawingId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  if (!r.ok) throw new Error((await r.json())?.detail ?? `patch failed: ${r.status}`);
  return r.json();
}

export async function archiveDrawing(drawingId: number): Promise<void> {
  const r = await fetch(`/api/shop-drawings/${drawingId}/archive`, { method: "POST" });
  if (!r.ok) throw new Error(`archive failed: ${r.status}`);
}

export async function addRevision(drawingId: number, fileBlobId: number): Promise<DrawingDetail> {
  const r = await fetch(`/api/shop-drawings/${drawingId}/revisions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ file_blob_id: fileBlobId }),
  });
  if (!r.ok) throw new Error((await r.json())?.detail ?? `add revision failed: ${r.status}`);
  return r.json();
}

export async function transitionRevision(
  drawingId: number,
  revisionId: number,
  action: "submit" | "withdraw" | "approve" | "reject",
  reviewNote?: string
): Promise<{ revision_id: number; status: RevisionStatus }> {
  const init: RequestInit = { method: "POST" };
  if (action === "reject") {
    init.headers = { "Content-Type": "application/json" };
    init.body = JSON.stringify({ review_note: reviewNote ?? "" });
  }
  const r = await fetch(`/api/shop-drawings/${drawingId}/revisions/${revisionId}/${action}`, init);
  if (!r.ok) throw new Error((await r.json())?.detail ?? `${action} failed: ${r.status}`);
  return r.json();
}
