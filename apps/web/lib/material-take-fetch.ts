import type { CurrentSummary, CurrentTake, TakeVersion } from "./material-take-types";

/** API error carrying FastAPI's `detail` (e.g. {code: "TAKE_NOT_DRAFT"}). */
export class ApiError extends Error {
  constructor(public status: number, public detail: unknown) {
    super(`request failed: ${status}`);
  }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`/api${path}`, {
    ...init,
    headers: init?.body ? { "content-type": "application/json" } : undefined,
  });
  if (!r.ok) {
    const body = await r.json().catch(() => ({}));
    throw new ApiError(r.status, body.detail);
  }
  return (r.status === 204 ? undefined : await r.json()) as T;
}

const json = (body: unknown) => ({ body: JSON.stringify(body) });

export const takeApi = {
  current: (itemId: number) => call<CurrentTake>(`/items/${itemId}/material-take`),
  history: (itemId: number) => call<TakeVersion[]>(`/items/${itemId}/material-takes`),
  generate: (itemId: number) =>
    call<{ take_id: number }>(`/items/${itemId}/material-take/generate`, { method: "POST" }),
  regenerate: (takeId: number) =>
    call<void>(`/material-takes/${takeId}/regenerate`, { method: "POST" }),
  addLine: (takeId: number, line: { description: string; unit: string; qty: string; note?: string }) =>
    call<{ line_id: number }>(`/material-takes/${takeId}/lines`, { method: "POST", ...json(line) }),
  patchLine: (takeId: number, lineId: number, changes: Record<string, string | null>) =>
    call<void>(`/material-takes/${takeId}/lines/${lineId}`, { method: "PATCH", ...json(changes) }),
  deleteLine: (takeId: number, lineId: number) =>
    call<void>(`/material-takes/${takeId}/lines/${lineId}`, { method: "DELETE" }),
  approve: (takeId: number) => call<void>(`/material-takes/${takeId}/approve`, { method: "POST" }),
  review: (takeId: number, outcome: "no_impact" | "partial" | "full", note?: string) =>
    call<{ new_take_id: number | null }>(`/material-takes/${takeId}/reviews`,
      { method: "POST", ...json({ outcome, note }) }),
};

export const summaryApi = {
  current: (projectId: number) => call<CurrentSummary>(`/projects/${projectId}/material-summary`),
  build: (projectId: number) =>
    call<{ summary_id: number }>(`/projects/${projectId}/material-summary`, { method: "POST" }),
  patchLine: (summaryId: number, lineId: number, changes: { qty_confirmed?: string | null; note?: string | null }) =>
    call<void>(`/material-summaries/${summaryId}/lines/${lineId}`, { method: "PATCH", ...json(changes) }),
  confirm: (summaryId: number) =>
    call<void>(`/material-summaries/${summaryId}/confirm`, { method: "POST" }),
};

export function errorText(e: unknown): string {
  if (e instanceof ApiError) {
    const code = (e.detail as { code?: string } | undefined)?.code;
    return code ? `${code} (${e.status})` : `Request failed (${e.status})`;
  }
  return "Request failed";
}
