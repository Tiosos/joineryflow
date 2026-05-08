import type {
  AssignIn,
  AssignmentOut,
  BoardOut,
  CompleteIn,
  CompleteOut,
  PatchAssignmentIn,
  RecentCompletionOut,
  StationOut,
  UndoOut,
  UserAdminOut,
  WorkerOut,
} from "./shop-floor-types";

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

// --- Board + workers ------------------------------------------------------

export async function fetchBoard(projectId: number): Promise<BoardOut> {
  const res = await fetch(`/api/projects/${projectId}/shop-floor/board`, {
    credentials: "include",
    cache: "no-store",
  });
  return check<BoardOut>(res, "fetchBoard");
}

export async function fetchProjectWorkers(
  projectId: number,
): Promise<WorkerOut[]> {
  const res = await fetch(`/api/projects/${projectId}/shop-floor/workers`, {
    credentials: "include",
    cache: "no-store",
  });
  return check<WorkerOut[]>(res, "fetchProjectWorkers");
}

// --- Station + recent completions ----------------------------------------

export async function fetchWorkerQueue(workerId: number): Promise<StationOut> {
  const res = await fetch(`/api/workers/${workerId}/queue`, {
    credentials: "include",
    cache: "no-store",
  });
  return check<StationOut>(res, "fetchWorkerQueue");
}

export async function fetchRecentCompletions(
  workerId: number,
): Promise<RecentCompletionOut[]> {
  const res = await fetch(
    `/api/workers/${workerId}/recent-completions`,
    { credentials: "include", cache: "no-store" },
  );
  return check<RecentCompletionOut[]>(res, "fetchRecentCompletions");
}

// --- Assignment lifecycle ------------------------------------------------

export async function createAssignment(
  projectId: number,
  itemId: number,
  body: AssignIn,
): Promise<AssignmentOut> {
  const res = await fetch(
    `/api/projects/${projectId}/items/${itemId}/assignments`,
    {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
  return check<AssignmentOut>(res, "createAssignment");
}

export async function patchAssignment(
  aid: number,
  body: PatchAssignmentIn,
): Promise<AssignmentOut> {
  const res = await fetch(`/api/assignments/${aid}`, {
    method: "PATCH",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return check<AssignmentOut>(res, "patchAssignment");
}

export async function cancelAssignment(aid: number): Promise<AssignmentOut> {
  const res = await fetch(`/api/assignments/${aid}`, {
    method: "DELETE",
    credentials: "include",
  });
  return check<AssignmentOut>(res, "cancelAssignment");
}

export async function startAssignment(aid: number): Promise<AssignmentOut> {
  const res = await fetch(`/api/assignments/${aid}/start`, {
    method: "POST",
    credentials: "include",
  });
  return check<AssignmentOut>(res, "startAssignment");
}

export async function completeAssignment(
  aid: number,
  body: CompleteIn,
): Promise<CompleteOut> {
  const res = await fetch(`/api/assignments/${aid}/complete`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body ?? {}),
  });
  return check<CompleteOut>(res, "completeAssignment");
}

export async function undoCompletion(logId: number): Promise<UndoOut> {
  const res = await fetch(`/api/completions/${logId}/undo`, {
    method: "POST",
    credentials: "include",
  });
  return check<UndoOut>(res, "undoCompletion");
}

// --- /it admin worker roster ---------------------------------------------

export async function fetchUserList(): Promise<UserAdminOut[]> {
  const res = await fetch("/api/users", {
    credentials: "include",
    cache: "no-store",
  });
  return check<UserAdminOut[]>(res, "fetchUserList");
}

export async function patchUserShopWorker(
  uid: number,
  isShopWorker: boolean,
): Promise<UserAdminOut> {
  const res = await fetch(`/api/users/${uid}/shop-worker`, {
    method: "PATCH",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ is_shop_worker: isShopWorker }),
  });
  return check<UserAdminOut>(res, "patchUserShopWorker");
}
