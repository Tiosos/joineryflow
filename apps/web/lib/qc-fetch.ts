import type {
  ChecklistItemOut,
  DefectOut,
  QcDashboard,
  QcDashboardFilters,
  ReworkOut,
} from "./qc-types";
import { apiCall, jsonInit } from "./api";

export const qcApi = {
  dashboard: (f: QcDashboardFilters) => {
    const q = new URLSearchParams();
    if (f.projectId != null) q.set("project_id", String(f.projectId));
    if (f.dateFrom) q.set("date_from", f.dateFrom);
    if (f.dateTo) q.set("date_to", f.dateTo);
    const qs = q.toString();
    return apiCall<QcDashboard>(`/api/qc/dashboard${qs ? `?${qs}` : ""}`);
  },

  listDefects: (itemId: number) => apiCall<DefectOut[]>(`/api/items/${itemId}/qc/defects`),
  createDefect: (itemId: number, description: string, stageKey?: string | null) =>
    apiCall<DefectOut>(`/api/items/${itemId}/qc/defects`,
      jsonInit("POST", { description, stage_key: stageKey ?? null })),
  resolveDefect: (defectId: number, resolvedNote?: string | null) =>
    apiCall<DefectOut>(`/api/qc/defects/${defectId}/resolve`,
      jsonInit("POST", { resolved_note: resolvedNote ?? null })),

  listChecklist: (itemId: number) => apiCall<ChecklistItemOut[]>(`/api/items/${itemId}/qc/checklist`),
  addChecklistItem: (itemId: number, label: string) =>
    apiCall<ChecklistItemOut>(`/api/items/${itemId}/qc/checklist`, jsonInit("POST", { label })),
  toggleChecklistItem: (checklistItemId: number, isChecked: boolean) =>
    apiCall<ChecklistItemOut>(`/api/qc/checklist/${checklistItemId}`,
      jsonInit("PATCH", { is_checked: isChecked })),
  removeChecklistItem: (checklistItemId: number) =>
    apiCall<void>(`/api/qc/checklist/${checklistItemId}`, { method: "DELETE" }),

  listRework: (itemId: number) => apiCall<ReworkOut[]>(`/api/items/${itemId}/qc/rework`),
  createRework: (
    itemId: number,
    body: { kind: string; cause: string; scope: string; responsibility?: string | null; cost?: string | null },
  ) => apiCall<ReworkOut>(`/api/items/${itemId}/qc/rework`, jsonInit("POST", body)),
  closeRework: (reworkId: number, closedNote?: string | null) =>
    apiCall<ReworkOut>(`/api/qc/rework/${reworkId}/close`,
      jsonInit("POST", { closed_note: closedNote ?? null })),
};
