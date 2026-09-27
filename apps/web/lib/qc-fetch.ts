import type { ChecklistItemOut, DefectOut, ReworkOut } from "./qc-types";

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

export const qcApi = {
  listDefects: (itemId: number) => call<DefectOut[]>(`/api/items/${itemId}/qc/defects`),
  createDefect: (itemId: number, description: string, stageKey?: string | null) =>
    call<DefectOut>(`/api/items/${itemId}/qc/defects`,
      jsonInit("POST", { description, stage_key: stageKey ?? null })),
  resolveDefect: (defectId: number, resolvedNote?: string | null) =>
    call<DefectOut>(`/api/qc/defects/${defectId}/resolve`,
      jsonInit("POST", { resolved_note: resolvedNote ?? null })),

  listChecklist: (itemId: number) => call<ChecklistItemOut[]>(`/api/items/${itemId}/qc/checklist`),
  addChecklistItem: (itemId: number, label: string) =>
    call<ChecklistItemOut>(`/api/items/${itemId}/qc/checklist`, jsonInit("POST", { label })),
  toggleChecklistItem: (checklistItemId: number, isChecked: boolean) =>
    call<ChecklistItemOut>(`/api/qc/checklist/${checklistItemId}`,
      jsonInit("PATCH", { is_checked: isChecked })),
  removeChecklistItem: (checklistItemId: number) =>
    call<void>(`/api/qc/checklist/${checklistItemId}`, { method: "DELETE" }),

  listRework: (itemId: number) => call<ReworkOut[]>(`/api/items/${itemId}/qc/rework`),
  createRework: (
    itemId: number,
    body: { kind: string; cause: string; scope: string; responsibility?: string | null; cost?: string | null },
  ) => call<ReworkOut>(`/api/items/${itemId}/qc/rework`, jsonInit("POST", body)),
  closeRework: (reworkId: number, closedNote?: string | null) =>
    call<ReworkOut>(`/api/qc/rework/${reworkId}/close`,
      jsonInit("POST", { closed_note: closedNote ?? null })),
};
