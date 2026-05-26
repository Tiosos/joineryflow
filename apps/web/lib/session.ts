import { cookies } from "next/headers";

export const SESSION_COOKIE_NAME = "jf_session";
const COOKIE_NAME = SESSION_COOKIE_NAME;
const API = process.env.API_URL ?? "http://api:8000";

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
};

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
