/**
 * RBAC-engine admin API types (Plan V1 §3.4, Q466–473).
 * Source: apps/api/app/permission_groups/schemas.py
 *
 * The backend has shipped since migration `0037` with no web UI —
 * `_ALL_MODULES` / `_ACTIONS` here must stay in sync with
 * apps/api/app/auth/permissions.py's own lists.
 */

export const ALL_MODULES = [
  "dashboard",
  "tracking",
  "list",
  "shop_dwgs",
  "isample",
  "orderbook",
  "catalog",
  "cut_floor",
  "shop_floor",
  "estimating",
  "qc",
  "it_management",
] as const;

export const ALL_ACTIONS = ["read", "write", "approve", "comment"] as const;

export type ModuleName = (typeof ALL_MODULES)[number];
export type ActionName = (typeof ALL_ACTIONS)[number];

export interface GrantOut {
  module: string;
  action: string;
}

export interface GroupOut {
  group_id: number;
  name: string;
  is_system: boolean;
  grants: GrantOut[];
}

export interface CreateGroupIn {
  name: string;
}

export interface SetGrantsIn {
  grants: GrantOut[];
}

export interface MembershipOut {
  membership_id: number;
  user_id: number;
  user_full_name: string;
  group_id: number;
  group_name: string;
  project_id: number | null;
  project_code: string | null;
}

export interface CreateMembershipIn {
  user_id: number;
  project_id?: number | null;
}
