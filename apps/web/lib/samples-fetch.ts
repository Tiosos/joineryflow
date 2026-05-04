import type {
  LedgerResp,
  Sample,
  SampleListResp,
  SampleStatus,
  SampleSubtab,
} from "./samples-types";

interface ListParams {
  projectId: number;
  subtab: SampleSubtab;
  q?: string | null;
  status?: SampleStatus | null;
  supplier?: string | null;
}

export async function listSamples(p: ListParams): Promise<SampleListResp> {
  const qs = new URLSearchParams({ subtab: p.subtab });
  if (p.q) qs.set("q", p.q);
  if (p.status) qs.set("status", p.status);
  if (p.supplier) qs.set("supplier", p.supplier);
  const r = await fetch(`/api/projects/${p.projectId}/samples?${qs}`);
  if (!r.ok) throw new Error(`list samples failed: ${r.status}`);
  return r.json();
}

export async function getSample(sampleId: number): Promise<Sample> {
  const r = await fetch(`/api/samples/${sampleId}`);
  if (!r.ok) throw new Error(`get sample failed: ${r.status}`);
  return r.json();
}

export async function createSample(input: {
  projectId: number;
  title: string;
  room: string | null;
  hex_swatch: string;
  supplier: string | null;
  photo_file_blob_id: number | null;
}): Promise<Sample> {
  const r = await fetch(`/api/projects/${input.projectId}/samples`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      title: input.title,
      room: input.room,
      hex_swatch: input.hex_swatch,
      supplier: input.supplier,
      photo_file_blob_id: input.photo_file_blob_id,
    }),
  });
  if (!r.ok) {
    const detail = await r.json().catch(() => ({}));
    throw new Error(detail?.detail ?? `create failed: ${r.status}`);
  }
  return r.json();
}

export async function patchSample(
  sampleId: number,
  patch: Partial<Pick<Sample, "title" | "room" | "hex_swatch" | "supplier">>,
): Promise<Sample> {
  const r = await fetch(`/api/samples/${sampleId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  if (!r.ok) {
    const detail = await r.json().catch(() => ({}));
    throw new Error(detail?.detail ?? `patch failed: ${r.status}`);
  }
  return r.json();
}

export async function approveSample(sampleId: number, reviewNote?: string): Promise<Sample> {
  const r = await fetch(`/api/samples/${sampleId}/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ review_note: reviewNote ?? null }),
  });
  if (!r.ok) {
    const detail = await r.json().catch(() => ({}));
    throw new Error(detail?.detail ?? `approve failed: ${r.status}`);
  }
  return r.json();
}

export async function rejectSample(sampleId: number, reviewNote: string): Promise<Sample> {
  const r = await fetch(`/api/samples/${sampleId}/reject`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ review_note: reviewNote }),
  });
  if (!r.ok) {
    const detail = await r.json().catch(() => ({}));
    throw new Error(detail?.detail ?? `reject failed: ${r.status}`);
  }
  return r.json();
}

export async function archiveSample(sampleId: number): Promise<void> {
  const r = await fetch(`/api/samples/${sampleId}/archive`, { method: "POST" });
  if (!r.ok && r.status !== 409) {
    throw new Error(`archive failed: ${r.status}`);
  }
}

export async function bindSamplePhoto(sampleId: number, fileBlobId: number): Promise<void> {
  const r = await fetch(`/api/samples/${sampleId}/photo`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ file_blob_id: fileBlobId }),
  });
  if (!r.ok) {
    const detail = await r.json().catch(() => ({}));
    throw new Error(detail?.detail ?? `bind photo failed: ${r.status}`);
  }
}

export async function clearSamplePhoto(sampleId: number): Promise<void> {
  const r = await fetch(`/api/samples/${sampleId}/photo`, { method: "DELETE" });
  if (!r.ok && r.status !== 404) {
    throw new Error(`clear photo failed: ${r.status}`);
  }
}

export async function listLedger(
  projectId: number,
  limit = 50,
  offset = 0,
): Promise<LedgerResp> {
  const r = await fetch(`/api/projects/${projectId}/samples/ledger?limit=${limit}&offset=${offset}`);
  if (!r.ok) throw new Error(`ledger failed: ${r.status}`);
  return r.json();
}
