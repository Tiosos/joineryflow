import type {
  HomeDashboardOut, ItemOut, TrackingGridOut, ProjectListOut,
  ProjectOut, HardwareCatalogOut, AvailabilityOut, CloseOutOut,
  CreateProjectIn, PatchProjectIn,
  CreateItemIn, PatchItemIn, LockTransferIn,
  PatchItemStatusIn, PatchLifecycleIn,
  CreateModuleIn, PatchModuleIn,
  CreatePartIn, PatchPartIn,
  AddCatalogIn, CreateHardwareLineIn, PatchHardwareLineIn,
  HardwareLineOut, ModuleOut, PartOut,
} from "./pm-types";


export class ApiError extends Error {
  constructor(public status: number, message: string, public body?: unknown) {
    super(message);
  }
}


async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, { cache: "no-store", ...init });
  if (!res.ok) {
    let body: unknown;
    try { body = await res.json(); } catch { /* swallow non-JSON error bodies */ }
    throw new ApiError(res.status, res.statusText, body);
  }
  if (res.status === 204) {
    return undefined as T;
  }
  return res.json() as Promise<T>;
}


function jsonInit(method: string, body?: unknown): RequestInit {
  return {
    method,
    headers: { "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  };
}


export const PM = {
  // ===== Reads =====
  homeDashboard: (origin = "") =>
    call<HomeDashboardOut>(`${origin}/api/home/dashboard`),

  projects: (origin = "", fav?: boolean) =>
    call<ProjectListOut>(`${origin}/api/projects${fav === undefined ? "" : `?fav=${fav}`}`),

  project: (origin = "", pid: number) =>
    call<ProjectOut>(`${origin}/api/projects/${pid}`),

  trackingGrid: (origin = "", pid: number, q?: URLSearchParams) =>
    call<TrackingGridOut>(`${origin}/api/projects/${pid}/items${q ? `?${q}` : ""}`),

  item: (origin = "", id: number) =>
    call<ItemOut>(`${origin}/api/items/${id}`),

  availability: (origin = "", id: number) =>
    call<AvailabilityOut>(`${origin}/api/items/${id}/availability`),

  catalog: (origin = "", pid: number) =>
    call<HardwareCatalogOut>(`${origin}/api/projects/${pid}/hardware_catalog`),

  sourceCatalog: (origin = "", table: string) =>
    call<{ table: string; rows: { source_id: number; sku: string | null; description: string; supplier: string | null; unit_cost: number | null }[] }>(
      `${origin}/api/source_catalog/${table}`
    ),

  // ===== Project mutations =====
  createProject: (body: CreateProjectIn) =>
    call<ProjectOut>(`/api/projects`, { ...jsonInit("POST", body), cache: "no-store" }),
  patchProject: (pid: number, body: PatchProjectIn) =>
    call<ProjectOut>(`/api/projects/${pid}`, { ...jsonInit("PATCH", body), cache: "no-store" }),
  closeOutProject: (pid: number) =>
    call<CloseOutOut>(`/api/projects/${pid}/close-out`, { method: "POST", cache: "no-store" }),

  // ===== Favourites =====
  addFavourite: (pid: number) =>
    call<void>(`/api/projects/${pid}/favourites`, { method: "POST", cache: "no-store" }),
  removeFavourite: (pid: number) =>
    call<void>(`/api/projects/${pid}/favourites`, { method: "DELETE", cache: "no-store" }),
  // Convenience: toggle
  toggleFavourite: (pid: number, on: boolean) =>
    on ? PM.addFavourite(pid) : PM.removeFavourite(pid),

  // ===== Item mutations =====
  createItem: (pid: number, body: CreateItemIn) =>
    call<ItemOut>(`/api/projects/${pid}/items`, { ...jsonInit("POST", body), cache: "no-store" }),
  patchItem: (id: number, body: PatchItemIn) =>
    call<ItemOut>(`/api/items/${id}`, { ...jsonInit("PATCH", body), cache: "no-store" }),
  deleteItem: (id: number) =>
    call<void>(`/api/items/${id}`, { method: "DELETE", cache: "no-store" }),
  patchItemStatus: (id: number, body: PatchItemStatusIn) =>
    call<ItemOut>(`/api/items/${id}/status`, { ...jsonInit("PATCH", body), cache: "no-store" }),
  patchItemLifecycle: (id: number, stageKey: string, body: PatchLifecycleIn) =>
    call<ItemOut>(`/api/items/${id}/lifecycle/${stageKey}`, { ...jsonInit("PATCH", body), cache: "no-store" }),

  // ===== Lock =====
  lockItem: (id: number) =>
    call<ItemOut>(`/api/items/${id}/lock`, { method: "POST", cache: "no-store" }),
  unlockItem: (id: number) =>
    call<ItemOut>(`/api/items/${id}/lock`, { method: "DELETE", cache: "no-store" }),
  transferLock: (id: number, body: LockTransferIn) =>
    call<ItemOut>(`/api/items/${id}/lock`, { ...jsonInit("POST", body), cache: "no-store" }),

  // ===== Modules + parts =====
  createModule: (id: number, body: CreateModuleIn) =>
    call<ModuleOut>(`/api/items/${id}/modules`, { ...jsonInit("POST", body), cache: "no-store" }),
  patchModule: (mid: number, body: PatchModuleIn) =>
    call<ModuleOut>(`/api/modules/${mid}`, { ...jsonInit("PATCH", body), cache: "no-store" }),
  deleteModule: (mid: number) =>
    call<void>(`/api/modules/${mid}`, { method: "DELETE", cache: "no-store" }),
  createPart: (mid: number, body: CreatePartIn) =>
    call<PartOut>(`/api/modules/${mid}/parts`, { ...jsonInit("POST", body), cache: "no-store" }),
  patchPart: (pid: number, body: PatchPartIn) =>
    call<PartOut>(`/api/parts/${pid}`, { ...jsonInit("PATCH", body), cache: "no-store" }),
  deletePart: (pid: number) =>
    call<void>(`/api/parts/${pid}`, { method: "DELETE", cache: "no-store" }),

  // ===== Hardware lines + catalog =====
  addCatalog: (pid: number, body: AddCatalogIn) =>
    call<{ catalog_id: number }>(`/api/projects/${pid}/hardware_catalog`, { ...jsonInit("POST", body), cache: "no-store" }),
  removeCatalog: (pid: number, cid: number) =>
    call<void>(`/api/projects/${pid}/hardware_catalog/${cid}`, { method: "DELETE", cache: "no-store" }),
  createHardwareLine: (id: number, body: CreateHardwareLineIn) =>
    call<HardwareLineOut>(`/api/items/${id}/hardware_lines`, { ...jsonInit("POST", body), cache: "no-store" }),
  patchHardwareLine: (lid: number, body: PatchHardwareLineIn) =>
    call<HardwareLineOut>(`/api/hardware_lines/${lid}`, { ...jsonInit("PATCH", body), cache: "no-store" }),
  deleteHardwareLine: (lid: number) =>
    call<void>(`/api/hardware_lines/${lid}`, { method: "DELETE", cache: "no-store" }),
};
