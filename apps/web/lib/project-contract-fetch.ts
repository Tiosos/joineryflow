import type { ProjectContract } from "./project-contract-types";

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, { cache: "no-store", ...init });
  if (!r.ok) {
    const body = await r.json().catch(() => ({}));
    const detail = body?.detail;
    // `detail` can be a plain string, or an object like {code: "..."} — coercing
    // an object straight into Error's message would stringify to "[object Object]".
    const message =
      typeof detail === "string" ? detail :
      typeof detail?.code === "string" ? detail.code :
      `${init?.method ?? "GET"} ${path} failed: ${r.status}`;
    throw new Error(message);
  }
  return r.json() as Promise<T>;
}

function jsonInit(method: string, body: unknown): RequestInit {
  return { method, headers: { "content-type": "application/json" }, body: JSON.stringify(body) };
}

export const projectContractApi = {
  addVariation: (projectId: number, description: string, amountDelta: string) =>
    call<ProjectContract>(
      `/api/projects/${projectId}/contract/variations`,
      jsonInit("POST", { description, amount_delta: amountDelta }),
    ),
};
