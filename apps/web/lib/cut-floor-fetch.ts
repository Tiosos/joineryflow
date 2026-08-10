import type {
  CutPlanIn,
  CutPlanOut,
  CutPlanSummary,
  CutScheduleIn,
  CutSchedulePatchIn,
  CutScheduleOut,
  ItemCutPlanOut,
  OptimiseIn,
  OptimiseOut,
  ReorderIn,
} from "./cut-floor-types";

interface ApiError extends Error {
  status: number;
  detail: unknown;
}

async function check<T>(res: Response, op: string): Promise<T> {
  if (!res.ok) {
    let detail: unknown = await res.text();
    try {
      detail = JSON.parse(detail as string);
    } catch {
      // keep as text
    }
    const err = new Error(`${op}: ${res.status}`) as ApiError;
    err.status = res.status;
    err.detail = detail;
    throw err;
  }
  if (res.status === 204) {
    return undefined as T;
  }
  return res.json() as Promise<T>;
}

// --- CutPlan ---------------------------------------------------------------

export async function fetchItemCutPlan(
  itemId: number,
): Promise<ItemCutPlanOut> {
  const res = await fetch(`/api/items/${itemId}/cut-plan`, {
    credentials: "include",
    cache: "no-store",
  });
  return check<ItemCutPlanOut>(res, "fetchItemCutPlan");
}

export async function listCutPlansForProject(
  projectId: number,
): Promise<CutPlanSummary[]> {
  const res = await fetch(`/api/projects/${projectId}/cut-plans`, {
    credentials: "include",
    cache: "no-store",
  });
  return check<CutPlanSummary[]>(res, "listCutPlansForProject");
}

export async function createCutPlan(
  projectId: number,
  body: CutPlanIn,
): Promise<CutPlanOut> {
  const res = await fetch(`/api/projects/${projectId}/cut-plans`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return check<CutPlanOut>(res, "createCutPlan");
}

export async function deleteCutPlan(planId: number): Promise<void> {
  const res = await fetch(`/api/cut-plans/${planId}`, {
    method: "DELETE",
    credentials: "include",
  });
  await check<void>(res, "deleteCutPlan");
}

export async function optimiseProject(
  projectId: number,
  body: OptimiseIn,
): Promise<OptimiseOut> {
  const res = await fetch(`/api/projects/${projectId}/optimise`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return check<OptimiseOut>(res, "optimiseProject");
}

// --- CutSchedule -----------------------------------------------------------

export async function listCutSchedules(opts: {
  date?: string;
  projectId?: number;
  status?: string;
}): Promise<CutScheduleOut[]> {
  const qs = new URLSearchParams();
  if (opts.date) qs.set("date", opts.date);
  if (opts.projectId) qs.set("project_id", String(opts.projectId));
  if (opts.status) qs.set("status", opts.status);
  const url = qs.toString()
    ? `/api/cut-schedules?${qs.toString()}`
    : "/api/cut-schedules";
  const res = await fetch(url, {
    credentials: "include",
    cache: "no-store",
  });
  return check<CutScheduleOut[]>(res, "listCutSchedules");
}

export async function createCutSchedule(
  body: CutScheduleIn,
): Promise<CutScheduleOut> {
  const res = await fetch("/api/cut-schedules", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return check<CutScheduleOut>(res, "createCutSchedule");
}

export async function patchCutSchedule(
  sid: number,
  body: CutSchedulePatchIn,
): Promise<CutScheduleOut> {
  const res = await fetch(`/api/cut-schedules/${sid}`, {
    method: "PATCH",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return check<CutScheduleOut>(res, "patchCutSchedule");
}

export async function reorderCutSchedules(
  body: ReorderIn,
): Promise<CutScheduleOut[]> {
  const res = await fetch("/api/cut-schedules/reorder", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return check<CutScheduleOut[]>(res, "reorderCutSchedules");
}

export async function cancelCutSchedule(
  sid: number,
): Promise<CutScheduleOut> {
  const res = await fetch(`/api/cut-schedules/${sid}`, {
    method: "DELETE",
    credentials: "include",
  });
  return check<CutScheduleOut>(res, "cancelCutSchedule");
}
