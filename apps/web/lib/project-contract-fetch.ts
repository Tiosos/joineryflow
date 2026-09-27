import type { ProjectContract } from "./project-contract-types";

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, { cache: "no-store", ...init });
  if (!r.ok) {
    const detail = await r.json().catch(() => ({}));
    throw new Error(detail?.detail ?? `${init?.method ?? "GET"} ${path} failed: ${r.status}`);
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
