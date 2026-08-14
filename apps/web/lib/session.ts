import { cookies } from "next/headers";

export const SESSION_COOKIE_NAME = "jf_session";
const COOKIE_NAME = SESSION_COOKIE_NAME;
const API = process.env.API_URL ?? "http://api:8000";

/** IA modules in the RBAC matrix (`_ALL_MODULES` in permissions.py). */
export type Module =
  | "dashboard"
  | "tracking"
  | "list"
  | "shop_dwgs"
  | "isample"
  | "orderbook"
  | "catalog"
  | "cut_floor"
  | "shop_floor"
  | "estimating"
  | "it_management";

export type Action = "read" | "write" | "approve" | "comment";

export type Me = {
  id: number;
  workspace_id: number;
  email: string;
  full_name: string;
  auth_role:
    | "admin"
    | "manager"
    | "editor"
    | "drafter"
    | "estimator"
    | "purchase_officer"
    | "viewer";
  /** `{module: [actions]}` for this user's role, served by `/auth/me`. */
  permissions: Partial<Record<Module, Action[]>>;
};

/**
 * Gate a surface on the RBAC matrix rather than a hardcoded role list, so the
 * web tier can never drift from `apps/api/app/auth/permissions.py`.
 *
 * Fails closed: a null user, or a `me` from a cached response predating the
 * `permissions` field, denies.
 */
export function can(
  me: Me | null | undefined,
  module: Module,
  action: Action,
): boolean {
  return me?.permissions?.[module]?.includes(action) ?? false;
}

export async function getSessionCookie(): Promise<string | null> {
  const c = await cookies();
  return c.get(COOKIE_NAME)?.value ?? null;
}

export async function fetchMe(): Promise<Me | null> {
  const tok = await getSessionCookie();
  if (!tok) return null;
  const r = await fetch(`${API}/auth/me`, {
    headers: { cookie: `${COOKIE_NAME}=${tok}` },
    cache: "no-store",
  });
  return r.ok ? ((await r.json()) as Me) : null;
}
