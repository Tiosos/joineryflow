import type {
  CreateGroupIn,
  CreateMembershipIn,
  GroupOut,
  MembershipOut,
  SetGrantsIn,
} from "./permission-groups-types";

export class ApiError extends Error {
  constructor(public status: number, message: string, public body?: unknown) {
    super(message);
  }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, { cache: "no-store", ...init });
  if (!res.ok) {
    let body: unknown;
    try {
      body = await res.json();
    } catch {
      /* swallow non-JSON error bodies */
    }
    throw new ApiError(res.status, res.statusText, body);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

function jsonInit(method: string, body: unknown): RequestInit {
  return { method, headers: { "content-type": "application/json" }, body: JSON.stringify(body) };
}

export const PermissionGroups = {
  list: () => call<GroupOut[]>("/api/permission-groups"),
  create: (body: CreateGroupIn) =>
    call<GroupOut>("/api/permission-groups", jsonInit("POST", body)),
  setGrants: (groupId: number, body: SetGrantsIn) =>
    call<GroupOut>(`/api/permission-groups/${groupId}/grants`, jsonInit("PUT", body)),
  remove: (groupId: number) =>
    call<void>(`/api/permission-groups/${groupId}`, { method: "DELETE" }),
  listMemberships: (groupId: number) =>
    call<MembershipOut[]>(`/api/permission-groups/${groupId}/memberships`),
  addMembership: (groupId: number, body: CreateMembershipIn) =>
    call<MembershipOut>(
      `/api/permission-groups/${groupId}/memberships`,
      jsonInit("POST", body),
    ),
  removeMembership: (membershipId: number) =>
    call<void>(`/api/permission-groups/memberships/${membershipId}`, { method: "DELETE" }),
};
