import type { ItemQueryOut } from "./pm-types";

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

export const itemQueriesApi = {
  list: (itemId: number) => call<ItemQueryOut[]>(`/api/items/${itemId}/queries`),
  ask: (itemId: number, question: string) =>
    call<ItemQueryOut>(`/api/items/${itemId}/queries`, jsonInit("POST", { question })),
  answer: (queryId: number, answer: string) =>
    call<ItemQueryOut>(`/api/queries/${queryId}/answer`, jsonInit("POST", { answer })),
  editAnswer: (queryId: number, answer: string) =>
    call<ItemQueryOut>(`/api/queries/${queryId}/answer`, jsonInit("PATCH", { answer })),
};
