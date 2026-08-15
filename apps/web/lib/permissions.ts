/**
 * The user shape and the RBAC gate, client-safe.
 *
 * These live here rather than in `lib/session.ts` because that module imports
 * `next/headers`, which makes it server-only — a client component importing
 * `can` from it drags `next/headers` into the browser bundle and fails the
 * build. `lib/session.ts` re-exports everything below, so server code can keep
 * importing from either.
 */

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
