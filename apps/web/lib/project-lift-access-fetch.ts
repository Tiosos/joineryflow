import type { ProjectLiftAccessOut, UpsertLiftAccessIn } from "./pm-types";

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, { cache: "no-store", ...init });
  if (!r.ok) {
    const detail = await r.json().catch(() => ({}));
    throw new Error(detail?.detail ?? `${init?.method ?? "GET"} ${path} failed: ${r.status}`);
  }
  if (r.status === 204) return undefined as T;
  return r.json() as Promise<T>;
}

// PUT is a full overwrite, not a partial merge (project_lift_access/queries.py
// upsert_lift_access sets both columns from the body every time) — callers
// must always send both `notes` and `sketch_file_blob_id` together, not just
// the one field being changed.
export const liftAccessApi = {
  upsert: (projectId: number, body: UpsertLiftAccessIn) =>
    call<ProjectLiftAccessOut>(`/api/projects/${projectId}/lift-access`, {
      method: "PUT",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    }),
};
