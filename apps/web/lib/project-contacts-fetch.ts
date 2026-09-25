import type { CreateContactIn, PatchContactIn, ProjectContactOut } from "./pm-types";

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, { cache: "no-store", ...init });
  if (!r.ok) {
    const detail = await r.json().catch(() => ({}));
    throw new Error(detail?.detail ?? `${init?.method ?? "GET"} ${path} failed: ${r.status}`);
  }
  if (r.status === 204) return undefined as T;
  return r.json() as Promise<T>;
}

function jsonInit(method: string, body: unknown): RequestInit {
  return { method, headers: { "content-type": "application/json" }, body: JSON.stringify(body) };
}

export const projectContactsApi = {
  create: (projectId: number, body: CreateContactIn) =>
    call<ProjectContactOut>(`/api/projects/${projectId}/contacts`, jsonInit("POST", body)),
  patch: (contactId: number, body: PatchContactIn) =>
    call<ProjectContactOut>(`/api/contacts/${contactId}`, jsonInit("PATCH", body)),
  remove: (contactId: number) =>
    call<void>(`/api/contacts/${contactId}`, { method: "DELETE" }),
};
