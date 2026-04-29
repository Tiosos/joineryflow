import type {
  AllocationListOut, AllocationOut,
  AvailabilityOut, BatchListOut, BatchOut,
  ProjectMaterialsOut, QueueOut,
} from "./procurement-types";

async function http<T>(input: RequestInfo, init?: RequestInit): Promise<T> {
  const r = await fetch(input, { credentials: "include", ...init });
  if (!r.ok) {
    const text = await r.text().catch(() => "");
    throw new Error(`${r.status} ${r.statusText}: ${text}`);
  }
  return r.json() as Promise<T>;
}

export const ProcFetch = {
  projectMaterials: (pid: number) =>
    http<ProjectMaterialsOut>(`/api/projects/${pid}/materials`),
  itemAvailability: (iid: number) =>
    http<AvailabilityOut>(`/api/items/${iid}/availability`),
  listBatches: (qs: URLSearchParams) =>
    http<BatchListOut>(`/api/batches${qs.toString() ? `?${qs}` : ""}`),
  createBatch: (body: object) =>
    http<BatchOut>(`/api/batches`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  patchBatch: (bid: number, body: object) =>
    http<BatchOut>(`/api/batches/${bid}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  cancelBatch: (bid: number) =>
    fetch(`/api/batches/${bid}`, { method: "DELETE", credentials: "include" }),
  listAllocations: (bid: number) =>
    http<AllocationListOut>(`/api/batches/${bid}/allocations`),
  createAllocation: (bid: number, body: object) =>
    http<AllocationOut>(`/api/batches/${bid}/allocations`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  deleteAllocation: (aid: number) =>
    fetch(`/api/allocations/${aid}`, { method: "DELETE", credentials: "include" }),
  queue: (qs: URLSearchParams) =>
    http<QueueOut>(`/api/procurement-queue${qs.toString() ? `?${qs}` : ""}`),
};
