// The one fetch wrapper for JSON calls through the Next proxy (`/api/...`).
// An error carries FastAPI's `detail` as its message: a plain string, or the
// `code` of a `{code, …}` 409 (coercing the object into Error's message would
// give "[object Object]"). A 204 resolves to undefined.
export async function apiCall<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, { cache: "no-store", ...init });
  if (!r.ok) {
    const body = await r.json().catch(() => ({}));
    const detail = body?.detail;
    const message =
      typeof detail === "string" ? detail :
      typeof detail?.code === "string" ? detail.code :
      `${init?.method ?? "GET"} ${path} failed: ${r.status}`;
    throw new Error(message);
  }
  if (r.status === 204) return undefined as T;
  return r.json() as Promise<T>;
}

export function jsonInit(method: string, body: unknown): RequestInit {
  return { method, headers: { "content-type": "application/json" }, body: JSON.stringify(body) };
}
