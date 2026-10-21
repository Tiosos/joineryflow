import { apiCall, jsonInit } from "./api";
import type { CreateTaskBody, PatchTaskBody, TaskList, TaskOut, TaskStatus } from "./tasks-types";

export interface TaskQuery {
  assignee?: "me" | number;
  status?: TaskStatus | "active";
  /** Tasks on this project, or on any of its items and cutlists. */
  projectId?: number;
  cutlistId?: number;
  limit?: number;
}

export const tasksApi = {
  list: (q: TaskQuery = {}) => {
    const qs = new URLSearchParams();
    if (q.assignee !== undefined) qs.set("assignee", String(q.assignee));
    if (q.status) qs.set("status", q.status);
    if (q.projectId !== undefined) qs.set("project_id", String(q.projectId));
    if (q.cutlistId !== undefined) qs.set("cutlist_id", String(q.cutlistId));
    qs.set("limit", String(q.limit ?? 100));
    return apiCall<TaskList>(`/api/tasks?${qs}`);
  },
  get: (id: number) => apiCall<TaskOut>(`/api/tasks/${id}`),
  forItem: (itemId: number) => apiCall<TaskList>(`/api/items/${itemId}/tasks?limit=200`),
  create: (body: CreateTaskBody) => apiCall<TaskOut>("/api/tasks", jsonInit("POST", body)),
  patch: (id: number, body: PatchTaskBody) =>
    apiCall<TaskOut>(`/api/tasks/${id}`, jsonInit("PATCH", body)),
  setStatus: (id: number, status: TaskStatus) =>
    apiCall<TaskOut>(`/api/tasks/${id}/status`, jsonInit("POST", { status })),
};

/** The words for a refusal code (`apiCall` throws the `code` of a 409 as the message). */
export function taskErrorText(e: unknown): string {
  const m = e instanceof Error ? e.message : String(e);
  switch (m) {
    case "TASK_CLOSED": return "This task is closed. Reopen it before editing.";
    case "ASSIGNEE_CANNOT_READ_TARGET": return "That person cannot open the record this task is about.";
    case "ASSIGNEE_NOT_FOUND": return "That person is not in this workspace.";
    case "FIELD_CONFLICT": return "Someone else changed this task. Reload and try again.";
    case "forbidden": return "You do not have permission to do that.";
    case "not found": return "That task or record no longer exists.";
    default: return m;
  }
}
